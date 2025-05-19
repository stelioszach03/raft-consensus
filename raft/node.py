"""Raft consensus node implementation."""
import asyncio
import logging
import random
import os
import time
from typing import Dict, List, Any, Optional, Set, Tuple

from raft.config import RaftConfig
from raft.log import RaftLog, LogEntry
from raft.rpc import RaftRPC
from raft.state import NodeState, PersistentState, VolatileState, LeaderState, ClusterState

logger = logging.getLogger(__name__)


class RaftNode:
    """
    Implementation of a node in the Raft consensus algorithm.
    
    Each node can be in one of three states:
    - Follower: responds to RPCs from leaders and candidates
    - Candidate: used to elect a new leader
    - Leader: handles all client requests
    """
    
    def __init__(self, config: RaftConfig):
        self.config = config
        self.node_id = config.node_id
        
        # Ξεκάθαρη διεύθυνση κόμβου για RPC επικοινωνία
        self.node_address = f"{config.host}:{config.port}"
        
        # Αναγνώριση peers - διορθωμένο φιλτράρισμα
        self.peers = []
        for peer in config.cluster_nodes:
            # Αποκλείουμε κάθε node αν το node_id μας είναι μέρος του peer string
            if self.node_id not in peer and peer not in self.peers:
                self.peers.append(peer)
                
        logger.info(f"Node {self.node_id} initialized with address {self.node_address}")
        logger.info(f"Node {self.node_id} initialized with peers: {self.peers}")
        
        # Initialize state
        self.persistent_state = PersistentState(config.state_path)
        self.volatile_state = VolatileState()
        self.leader_state: Optional[LeaderState] = None
        
        # Initialize log
        self.log = RaftLog(config.log_path)
        
        # Initialize RPC server
        self.rpc = RaftRPC(self.node_id, config.host, config.port)
        self.rpc.register_vote_handler(self.handle_vote_request)
        self.rpc.register_append_entries_handler(self.handle_append_entries)
        
        # Scheduled tasks
        self.election_timer: Optional[asyncio.Task] = None
        self.heartbeat_timer: Optional[asyncio.Task] = None
        
        # Shutdown flag
        self.shutdown_event = asyncio.Event()
        
        # For tracking applied commands
        self.state_machine: Dict[str, Any] = {}
        
        # Cluster state information for UI
        self.cluster_state = ClusterState(self.node_id, config)
        
        # Βελτιωμένος μηχανισμός εκλογών
        self.election_in_progress = False
        self.last_election_time = 0.0
        self.consecutive_elections = 0
        self.max_consecutive_elections = 3
        
        # Σταθερότητα και αποφυγή flapping
        self.min_election_timeout = config.election_timeout_min / 1000.0
        self.leader_stability_timeout = self.min_election_timeout * 3
        
        # ΚΡΙΣΙΜΗ ΑΛΛΑΓΗ: Ξεκινάμε όλοι ως followers χωρίς αναγνωρισμένο leader
        self.volatile_state.state = NodeState.FOLLOWER
        self.volatile_state.leader_id = None  # Ξεκάθαρα κανένας leader
        
        # Ενημέρωση cluster state
        self.update_cluster_state()
        
        # ΑΠΛΟΠΟΙΗΜΕΝΗ ΛΟΓΙΚΗ: Ο node0 καθυστερεί ΠΟΛΥ λιγότερο από τους άλλους στην εκκίνηση εκλογής
        if self.node_id == "node0":
            election_delay = 0.5  # Μικρή καθυστέρηση για τον node0
        else:
            # Οι άλλοι κόμβοι περιμένουν πολύ περισσότερο
            node_num = int(self.node_id[-1])
            election_delay = 5.0 + (node_num * 2.0)  # Πολύ μεγαλύτερη διαφορά
    
        logger.info(f"Node {self.node_id} will start election after {election_delay}s")
        self.reset_election_timer_with_delay(election_delay)
    
    def reset_election_timer_with_delay(self, delay: float) -> None:
        """Reset the election timeout timer with a specific delay."""
        if self.election_timer:
            self.election_timer.cancel()
        
        logger.info(f"Node {self.node_id} setting delayed election timeout: {delay:.2f}s")
        
        self.election_timer = asyncio.create_task(self.election_timeout(delay))
    
    async def start(self) -> None:
        """Start the Raft node."""
        logger.info(f"Starting Raft node {self.node_id}")
        
        # Start RPC server
        await self.rpc.start()
        
        # Start as follower
        self.become_follower(self.persistent_state.current_term)
        
        # Main loop
        try:
            while not self.shutdown_event.is_set():
                # Apply committed entries to state machine
                await self.apply_committed_entries()
                
                # Sleep a bit to prevent CPU hogging
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            logger.info(f"Node {self.node_id} task cancelled")
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Stop the Raft node."""
        logger.info(f"Stopping Raft node {self.node_id}")
        
        # Cancel timers
        if self.election_timer:
            self.election_timer.cancel()
        
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
        
        # Stop RPC server
        await self.rpc.stop()
    
    def reset_election_timer(self) -> None:
        """Reset the election timeout timer."""
        if self.election_timer:
            self.election_timer.cancel()
        
        # Εξασφάλιση μοναδικού timeout βασισμένου στο node_id
        node_num = int(self.node_id[-1])
        base_timeout = self.config.election_timeout_min / 1000.0
        # Αύξηση διαφοράς μεταξύ των timeouts
        timeout = base_timeout + (node_num * 0.5) + random.uniform(0.1, 0.3)
        
        logger.info(f"Node {self.node_id} setting election timeout: {timeout:.2f}s")
        
        self.election_timer = asyncio.create_task(self.election_timeout(timeout))
    
    async def election_timeout(self, timeout: float) -> None:
        """
        Election timeout handler.
        When this timeout triggers, the node becomes a candidate and starts an election.
        """
        try:
            await asyncio.sleep(timeout)
            
            # Αν υπάρχει ήδη leader, δεν ξεκινάμε εκλογή
            if self.volatile_state.leader_id is not None:
                logger.debug(f"Node {self.node_id} skipping election, already have leader {self.volatile_state.leader_id}")
                self.reset_election_timer()
                return
                
            # Προστασία από πολύ συχνές εκλογές
            current_time = asyncio.get_event_loop().time()
            min_time_between_elections = 1.0
            
            if current_time - self.last_election_time < min_time_between_elections:
                logger.debug(f"Node {self.node_id} skipping election, too soon after last one")
                self.reset_election_timer()
                return
            
            if self.election_in_progress:
                logger.debug(f"Node {self.node_id} skipping election, another one in progress")
                self.reset_election_timer()
                return
                
            if self.consecutive_elections >= self.max_consecutive_elections:
                logger.debug(f"Node {self.node_id} has initiated too many consecutive elections, backing off")
                await asyncio.sleep(random.uniform(1.0, 2.0) * (1 + (self.consecutive_elections - self.max_consecutive_elections) * 0.5))
                self.consecutive_elections = 0
                self.reset_election_timer()
                return
                
            if self.volatile_state.state != NodeState.LEADER:
                logger.info(f"Node {self.node_id} election timeout - starting election")
                await self.start_election()
        except asyncio.CancelledError:
            # Timer was cancelled
            pass
    
    async def start_election(self) -> None:
        """Start a leader election."""
        # Σημειώνουμε ότι μια εκλογή είναι σε εξέλιξη
        if self.election_in_progress:
            logger.debug(f"Node {self.node_id} already has an election in progress")
            return
                
        self.election_in_progress = True
        self.last_election_time = asyncio.get_event_loop().time()
        self.consecutive_elections += 1
        
        try:
            # Increment current term
            self.persistent_state.current_term += 1
            new_term = self.persistent_state.current_term
            
            # Change to candidate state - ΜΗΝ κάνεις reset timer εδώ!
            # Χρησιμοποιούμε απευθείας τις εντολές αντί να καλέσουμε become_candidate()
            logger.info(f"Node {self.node_id} becoming candidate for term {self.persistent_state.current_term}")
            self.volatile_state.state = NodeState.CANDIDATE
            self.update_cluster_state()  # Ενημέρωση UI
            
            # Vote for self
            self.persistent_state.record_vote(self.node_id)
            
            # Get last log info
            last_log_term, last_log_index = self.log.get_last_log_term_and_index()
            
            # Track votes
            votes_received = 1  # Vote for self
            votes_needed = (len(self.peers) + 1) // 2 + 1
            
            # Περισσότερες πληροφορίες για το debugging
            logger.info(f"Node {self.node_id} starting election for term {new_term}, need {votes_needed} votes")
            logger.info(f"Peers to contact: {self.peers}")
            
            # Request votes from all peers
            vote_tasks = []
            for peer in self.peers:
                # Βεβαιωθείτε ότι δεν ζητάμε ψήφο από τον εαυτό μας
                task = asyncio.create_task(
                    self.rpc.request_vote(
                        peer,
                        new_term,
                        self.node_id,
                        last_log_index,
                        last_log_term
                    )
                )
                vote_tasks.append(task)
            
            if not vote_tasks:
                logger.warning(f"No peers available for vote requests")
                self.election_in_progress = False
                self.reset_election_timer()
                return
            
            # Περιμένουμε απαντήσεις με αυξημένο timeout
            try:
                results = await asyncio.gather(*vote_tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"Error in vote request: {result}")
                        continue
                        
                    logger.info(f"Vote result: {result}")
                    
                    if result.get("vote_granted", False):
                        votes_received += 1
                        logger.info(f"Node {self.node_id} received vote - now has {votes_received}/{votes_needed}")
                    
                    # If we got a higher term, revert to follower
                    if result.get("term", 0) > self.persistent_state.current_term:
                        logger.info(f"Node {self.node_id} discovered higher term during election")
                        self.become_follower(result["term"])
                        return
                
                # If we have enough votes, become leader
                if votes_received >= votes_needed:
                    logger.info(f"Node {self.node_id} won election with {votes_received} votes")
                    self.consecutive_elections = 0
                    self.become_leader()
                else:
                    # If we don't have enough votes, return to follower state
                    logger.info(f"Node {self.node_id} lost election with {votes_received}/{votes_needed} votes")
                    # Προσθήκα καθυστέρησης για αποφυγή συνεχών εκλογών
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    self.become_follower(self.persistent_state.current_term)
            except Exception as e:
                logger.error(f"Error in election process: {e}")
                self.become_follower(self.persistent_state.current_term)
                
        finally:
            # Mark the election as finished
            self.election_in_progress = False
    
    async def send_heartbeats(self) -> None:
        """Send heartbeats (empty AppendEntries) to all peers."""
        try:
            while (
                not self.shutdown_event.is_set() and 
                self.volatile_state.state == NodeState.LEADER
            ):
                # Log
                logger.debug(f"Leader {self.node_id} sending heartbeats to {len(self.peers)} peers")
                
                # We'll create a single task for each peer
                heartbeat_tasks = []
                
                for peer in self.peers:
                    # Get prev log info for this peer
                    prev_log_index = self.leader_state.next_index[peer] - 1 if self.leader_state else 0
                    prev_log_term = 0
                    
                    if prev_log_index > 0:
                        entry = self.log.get_entry(prev_log_index)
                        if entry:
                            prev_log_term = entry.term
                    
                    # Check if we need to send entries to this peer
                    entries_to_send = []
                    if self.leader_state and self.log.last_index >= self.leader_state.next_index[peer]:
                        # Get entries to send
                        log_entries = self.log.get_entries_from(self.leader_state.next_index[peer])
                        if log_entries:
                            entries_to_send = [entry.to_dict() for entry in log_entries]
                    
                    # Create task for this peer
                    task = asyncio.create_task(
                        self.rpc.append_entries(
                            peer,
                            self.persistent_state.current_term,
                            self.node_id,
                            prev_log_index,
                            prev_log_term,
                            entries_to_send,
                            self.volatile_state.commit_index
                        )
                    )
                    heartbeat_tasks.append((peer, task))
                
                # Wait for all heartbeats with protection
                if heartbeat_tasks:
                    try:
                        for peer, task in heartbeat_tasks:
                            try:
                                response = await asyncio.wait_for(task, timeout=3.0)
                                
                                # If we get a higher term, become follower
                                if response.get("term", 0) > self.persistent_state.current_term:
                                    logger.info(f"Node {self.node_id} discovered higher term during heartbeat")
                                    self.become_follower(response["term"])
                                    return
                                
                                # Process successful response
                                if response.get("success", False):
                                    # If we sent entries, update match index
                                    if self.leader_state and len(entries_to_send) > 0:
                                        last_sent_idx = prev_log_index + len(entries_to_send)
                                        self.leader_state.update_follower_progress(peer, last_sent_idx)
                                        
                                        # Try to update commit index
                                        self.update_commit_index()
                                elif self.leader_state and self.leader_state.next_index[peer] > 1:
                                    # Decrement next index for failed consistency check
                                    self.leader_state.next_index[peer] -= 1
                                
                            except asyncio.TimeoutError:
                                logger.warning(f"Timeout sending heartbeat to {peer}")
                            except Exception as e:
                                logger.error(f"Error sending heartbeat to {peer}: {e}")
                    except Exception as e:
                        logger.error(f"Error in heartbeat processing: {e}")
                
                # Update cluster state for UI
                self.update_cluster_state()
                
                # Wait before sending next heartbeat
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {e}")
    
    def update_commit_index(self) -> None:
        """
        Update commit index if there exists a majority-replicated index in current term.
        Called when a follower successfully replicates entries.
        """
        if self.volatile_state.state != NodeState.LEADER or not self.leader_state:
            return
        
        # Get our current match indices plus our own last log index
        match_indices = list(self.leader_state.match_index.values())
        match_indices.append(self.log.last_index)  # Include leader's own log
        
        # Sort to find the median (majority-replicated) index
        match_indices.sort()
        majority_index = len(match_indices) // 2
        potential_commit_index = match_indices[majority_index]
        
        # Only advance commit index for entries from current term
        if potential_commit_index > self.volatile_state.commit_index:
            # Verify the term of the entry at the potential commit index
            entry = self.log.get_entry(potential_commit_index)
            if entry and entry.term == self.persistent_state.current_term:
                logger.info(f"Advancing commit index to {potential_commit_index}")
                self.volatile_state.commit_index = potential_commit_index
    
    async def apply_committed_entries(self) -> None:
        """Apply committed log entries to the state machine."""
        while self.volatile_state.last_applied < self.volatile_state.commit_index:
            self.volatile_state.last_applied += 1
            entry = self.log.get_entry(self.volatile_state.last_applied)
            
            if entry:
                # Apply command to state machine
                await self.apply_command(entry.command)
                logger.info(f"Applied entry {self.volatile_state.last_applied} to state machine: {entry.command}")
        
        # Update UI state after applying entries
        self.update_cluster_state()
    
    async def apply_command(self, command: Dict[str, Any]) -> Any:
        """Apply a command to the state machine."""
        # Simple key-value store implementation
        operation = command.get("operation")
        
        if operation == "set":
            key = command.get("key")
            value = command.get("value")
            if key is not None:
                self.state_machine[key] = value
                return value
        
        elif operation == "get":
            key = command.get("key")
            if key is not None:
                return self.state_machine.get(key)
        
        elif operation == "delete":
            key = command.get("key")
            if key is not None and key in self.state_machine:
                del self.state_machine[key]
                return True
            return False
        
        # No-op command for leader election
        elif operation == "no-op":
            return None
            
        return None
    
    async def handle_vote_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a RequestVote RPC.
        Returns a dict with 'term' and 'vote_granted' fields.
        """
        term = request.get("term", 0)
        candidate_id = request.get("candidate_id", "")
        last_log_index = request.get("last_log_index", 0)
        last_log_term = request.get("last_log_term", 0)
        
        logger.debug(f"Node {self.node_id} received vote request from {candidate_id} for term {term}")
        
        # If the term is outdated, reject vote
        if term < self.persistent_state.current_term:
            logger.debug(f"Rejecting vote: term {term} < our term {self.persistent_state.current_term}")
            return {
                "term": self.persistent_state.current_term,
                "vote_granted": False
            }
        
        # If the term is newer, update our term and become follower
        if term > self.persistent_state.current_term:
            logger.debug(f"Updating term: {self.persistent_state.current_term} -> {term}")
            self.become_follower(term)
        
        # Check if we can vote for this candidate
        vote_granted = False
        
        # We can vote if:
        # 1. We haven't voted in this term, or we've already voted for this candidate
        # 2. Candidate's log is at least as up-to-date as ours
        if (self.persistent_state.voted_for is None or 
            self.persistent_state.voted_for == candidate_id):
            
            # Check if candidate's log is at least as up-to-date as ours
            our_last_term, our_last_index = self.log.get_last_log_term_and_index()
            
            log_is_current = False
            if last_log_term > our_last_term:
                log_is_current = True
            elif last_log_term == our_last_term and last_log_index >= our_last_index:
                log_is_current = True
                
            if log_is_current:
                # Grant vote
                vote_granted = True
                self.persistent_state.record_vote(candidate_id)
                logger.debug(f"Granting vote to {candidate_id} for term {term}")
                
                # Reset election timer since we're granting a vote
                self.reset_election_timer()
            else:
                logger.debug(f"Rejecting vote: candidate log not current: ({last_log_term},{last_log_index}) vs ours ({our_last_term},{our_last_index})")
        else:
            logger.debug(f"Rejecting vote: already voted for {self.persistent_state.voted_for} in term {self.persistent_state.current_term}")
        
        return {
            "term": self.persistent_state.current_term,
            "vote_granted": vote_granted
        }
    
    async def handle_append_entries(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an AppendEntries RPC.
        Returns a dict with 'term' and 'success' fields.
        """
        term = request.get("term", 0)
        leader_id = request.get("leader_id", "")
        prev_log_index = request.get("prev_log_index", 0)
        prev_log_term = request.get("prev_log_term", 0)
        entries = request.get("entries", [])
        leader_commit = request.get("leader_commit", 0)
        
        # Log for debugging (limit for heartbeats)
        is_heartbeat = not entries
        if is_heartbeat:
            logger.debug(f"Node {self.node_id} received heartbeat from {leader_id} (term {term})")
        else:
            logger.debug(f"Node {self.node_id} received {len(entries)} entries from {leader_id} (term {term})")
        
        # If the term is outdated, reject
        if term < self.persistent_state.current_term:
            logger.debug(f"Rejecting AppendEntries: term {term} < our term {self.persistent_state.current_term}")
            return {
                "term": self.persistent_state.current_term,
                "success": False
            }
        
        # Update state based on the valid AppendEntries
        self.volatile_state.update_heartbeat()
        
        # Very important! Update leader information
        previous_leader = self.volatile_state.leader_id
        self.volatile_state.leader_id = leader_id
        
        # If the term is newer, update our term
        if term > self.persistent_state.current_term:
            logger.debug(f"Updating term from AppendEntries: {self.persistent_state.current_term} -> {term}")
            self.become_follower(term)
        elif self.volatile_state.state != NodeState.FOLLOWER:
            # Make sure we're a follower
            logger.info(f"Node {self.node_id} changing from {self.volatile_state.state} to follower due to AppendEntries")
            self.become_follower(term)
        else:
            # Reset election timer
            self.reset_election_timer()
        
        # If the leader changed, log it
        if previous_leader != leader_id:
            logger.info(f"Node {self.node_id} recognized new leader: {leader_id} for term {term}")
        
        # Check log consistency
        if not self.log.check_consistency(prev_log_index, prev_log_term):
            logger.debug(f"Log inconsistency: prev_log_index={prev_log_index}, prev_log_term={prev_log_term}")
            return {
                "term": self.persistent_state.current_term,
                "success": False
            }
        
        # Convert entries to LogEntry objects
        log_entries = []
        for i, entry_dict in enumerate(entries):
            log_entry = LogEntry(
                term=entry_dict["term"],
                index=prev_log_index + 1 + i,
                command=entry_dict["command"]
            )
            log_entries.append(log_entry)
        
        # Append entries to log
        if log_entries:
            success = self.log.append_entries(prev_log_index, log_entries)
            if success:
                logger.debug(f"Appended {len(log_entries)} entries to log, now has {len(self.log.entries)} entries")
            else:
                logger.warning(f"Failed to append entries to log")
                return {
                    "term": self.persistent_state.current_term, 
                    "success": False
                }
        
        # Update commit index
        if leader_commit > self.volatile_state.commit_index:
            old_commit_index = self.volatile_state.commit_index
            self.volatile_state.commit_index = min(
                leader_commit, self.log.last_index
            )
            logger.debug(f"Updated commit index: {old_commit_index} -> {self.volatile_state.commit_index}")
        
        # Update cluster state for UI
        self.update_cluster_state()
        
        return {
            "term": self.persistent_state.current_term,
            "success": True
        }
    
    async def client_request(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a client request.
        If leader, append to log and replicate.
        If follower, redirect to leader.
        """
        # Check if we're the leader
        if self.volatile_state.state != NodeState.LEADER:
            # Redirect to leader if known
            if self.volatile_state.leader_id:
                logger.info(f"Redirecting client request to leader {self.volatile_state.leader_id}")
                return {
                    "success": False,
                    "leader": self.volatile_state.leader_id,
                    "message": "Please retry with the leader node"
                }
            else:
                return {
                    "success": False,
                    "error": "No leader known - please try again later",
                    "retry": True
                }
        
        # Handle the request as leader
        logger.info(f"Leader {self.node_id} handling client request: {command}")
        
        try:
            # Append to log
            entry = self.log.append(self.persistent_state.current_term, command)
            
            # After appending to our log, we already know the result but need to replicate
            result = await self.apply_command(command)
            
            # Update commit index for ourselves
            self.update_commit_index()
            
            # Client request is successful as soon as we've processed it
            # Eventual consistency will ensure it propagates to followers
            return {
                "success": True,
                "index": entry.index,
                "result": result
            }
        except Exception as e:
            logger.error(f"Error handling client request: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error: {str(e)}",
                "retry": True
            }
    
    def become_follower(self, term: int) -> None:
        """Transition to follower state."""
        previous_state = self.volatile_state.state
        logger.info(f"Node {self.node_id} becoming follower for term {term}")
        
        # Update term if needed
        if term > self.persistent_state.current_term:
            self.persistent_state.update_term(term)
            # Clear vote when term changes
            self.persistent_state.voted_for = None
        
        # Update state
        self.volatile_state.state = NodeState.FOLLOWER
        
        # Cancel leader heartbeat timer if active
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None
        
        # Reset leader state
        self.leader_state = None
        
        # Reset consecutive elections only if becoming follower from another state
        if previous_state != NodeState.FOLLOWER:
            self.consecutive_elections = 0
        
        # Reset election timer
        self.reset_election_timer()
        
        # Update cluster state for UI
        self.update_cluster_state()
    
    def become_candidate(self) -> None:
        """Transition to candidate state."""
        logger.info(f"Node {self.node_id} becoming candidate for term {self.persistent_state.current_term}")
        
        # Update state
        self.volatile_state.state = NodeState.CANDIDATE
        
        # ΔΙΟΡΘΩΣΗ: Αφαιρέθηκε ο επαναπροσδιορισμός του election timer
        # ΔΕΝ κάνουμε reset του timer εδώ, για να μην διακόπτεται η εκλογή
        # self.reset_election_timer()
        
        # Update cluster state for UI
        self.update_cluster_state()
    
    def become_leader(self) -> None:
        """Transition to leader state."""
        logger.info(f"Node {self.node_id} becoming leader for term {self.persistent_state.current_term}")
        
        # Update state
        self.volatile_state.state = NodeState.LEADER
        self.volatile_state.leader_id = self.node_id
        
        # Initialize leader state with all peers
        self.leader_state = LeaderState(self.peers)
        
        # Populate nextIndex with last log index + 1
        last_log_index = self.log.last_index
        for peer in self.peers:
            self.leader_state.next_index[peer] = last_log_index + 1
            self.leader_state.match_index[peer] = 0
        
        # Cancel election timer
        if self.election_timer:
            self.election_timer.cancel()
            self.election_timer = None
        
        # Append a no-op entry to establish leadership
        no_op_entry = self.log.append(self.persistent_state.current_term, {"operation": "no-op"})
        
        # Reset consecutive elections
        self.consecutive_elections = 0
        
        # Start sending heartbeats
        self.heartbeat_timer = asyncio.create_task(self.send_heartbeats())
        
        # Update cluster state for UI
        self.update_cluster_state()
    
    def update_cluster_state(self) -> None:
        """Update cluster state information for UI."""
        self.cluster_state.state = self.volatile_state.state
        self.cluster_state.current_term = self.persistent_state.current_term
        self.cluster_state.voted_for = self.persistent_state.voted_for
        self.cluster_state.leader_id = self.volatile_state.leader_id
        self.cluster_state.last_heartbeat = self.volatile_state.last_heartbeat_time
        self.cluster_state.log_size = self.log.size
        self.cluster_state.commit_index = self.volatile_state.commit_index
        self.cluster_state.last_applied = self.volatile_state.last_applied
        
        # Clear and update peer information
        self.cluster_state.peers_status = {}
        
        # Update peer information (for all states, not just leader)
        for peer in self.peers:
            if self.volatile_state.state == NodeState.LEADER and self.leader_state:
                # Include leader-specific info
                self.cluster_state.peers_status[peer] = {
                    "next_index": self.leader_state.next_index.get(peer, 0),
                    "match_index": self.leader_state.match_index.get(peer, 0),
                }
            else:
                # Basic info for followers and candidates
                self.cluster_state.peers_status[peer] = {
                    "active": True  # Assume peer is active
                }