"""Raft consensus node implementation."""
import asyncio
import logging
import random
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
        self.peers = [node for node in config.cluster_nodes if node != self.node_id]
        
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
        self.update_cluster_state()
        
        # Protection against simultaneous elections
        self.election_in_progress = False
        self.last_election_time = 0.0
        
        # Mechanism to avoid consecutive elections from the same node
        self.consecutive_elections = 0
        self.max_consecutive_elections = 5
        
        # Time of last successful election
        self.last_successful_election_time = 0.0
        
        # Election stability
        self.election_stability_factor = 1.0
    
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
        
        # Use the fixed random timeout that depends on the node_id
        timeout = self.config.random_election_timeout
        
        # Log for diagnostic purposes
        logger.debug(f"Node {self.node_id} setting election timeout: {timeout:.2f}s")
        
        self.election_timer = asyncio.create_task(self.election_timeout(timeout))
    
    async def election_timeout(self, timeout: float) -> None:
        """
        Election timeout handler.
        When this timeout triggers, the node becomes a candidate and starts an election.
        """
        try:
            # Add a small jitter to avoid simultaneous timeouts
            jitter = random.uniform(0, 0.1 * timeout)
            await asyncio.sleep(timeout + jitter)
            
            # Protection against too frequent elections
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_election_time < 2.0:
                logger.debug(f"Node {self.node_id} skipping election, too soon after last one")
                self.reset_election_timer()
                return
            
            if self.election_in_progress:
                logger.debug(f"Node {self.node_id} skipping election, another one in progress")
                self.reset_election_timer()
                return
                
            if self.consecutive_elections >= self.max_consecutive_elections:
                logger.debug(f"Node {self.node_id} has initiated too many consecutive elections, backing off")
                # Increased delay when reaching consecutive elections limit
                await asyncio.sleep(random.uniform(3.0, 6.0))
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
        # Mark that an election is in progress
        self.election_in_progress = True
        self.last_election_time = asyncio.get_event_loop().time()
        self.consecutive_elections += 1
        
        try:
            # Calculate stability factor - increases with each consecutive election
            self.election_stability_factor = min(1.0 + (self.consecutive_elections * 0.2), 3.0)
            
            # Increment current term
            self.persistent_state.current_term += 1
            new_term = self.persistent_state.current_term
            
            # Change to candidate state
            self.become_candidate()
            
            # Vote for self
            self.persistent_state.record_vote(self.node_id)
            
            # Get last log info
            last_log_term, last_log_index = self.log.get_last_log_term_and_index()
            
            # Track votes
            votes_received = 1  # Vote for self
            votes_needed = (len(self.peers) + 1) // 2 + 1
            
            # Request votes from all peers
            vote_tasks = []
            for peer in self.peers:
                peer_address = peer
                task = asyncio.create_task(
                    self.rpc.request_vote(
                        peer_address,
                        new_term,
                        self.node_id,
                        last_log_index,
                        last_log_term
                    )
                )
                vote_tasks.append(task)
            
            # Wait for votes - use gather with return_exceptions=True to avoid errors
            responses = await asyncio.gather(*vote_tasks, return_exceptions=True)
            
            # Process responses
            for response in responses:
                if isinstance(response, Exception):
                    logger.warning(f"Error during vote request: {response}")
                    continue
                    
                if response.get("vote_granted", False):
                    votes_received += 1
                    logger.info(f"Node {self.node_id} received vote - now has {votes_received}/{votes_needed}")
                
                # If we got a higher term, revert to follower
                if response.get("term", 0) > self.persistent_state.current_term:
                    logger.info(f"Node {self.node_id} discovered higher term during election")
                    self.become_follower(response["term"])
                    return
                
                # If we have enough votes, become leader
                if votes_received >= votes_needed:
                    logger.info(f"Node {self.node_id} won election with {votes_received} votes")
                    # Record successful election
                    self.last_successful_election_time = asyncio.get_event_loop().time()
                    self.consecutive_elections = 0  # Reset counter
                    self.become_leader()
                    return
            
            # If we get here, we didn't win the election
            logger.info(f"Node {self.node_id} lost election, returning to follower state")
            # Add random delay after failed election
            # Delay increases based on stability factor
            await asyncio.sleep(random.uniform(1.0, 3.0) * self.election_stability_factor)
            self.become_follower(self.persistent_state.current_term)
        finally:
            # Mark that the election is complete
            self.election_in_progress = False
    
    async def send_heartbeats(self) -> None:
        """Send heartbeats (empty AppendEntries) to all peers."""
        heartbeat_delay = 0.01  # Short delay between heartbeats
        
        while (
            not self.shutdown_event.is_set() and 
            self.volatile_state.state == NodeState.LEADER
        ):
            try:
                # Log for debugging
                logger.debug(f"Leader {self.node_id} sending heartbeats to {len(self.peers)} peers")
                
                # Send heartbeats to all peers - use gather for parallel sending
                heartbeat_tasks = []
                for peer in self.peers:
                    peer_address = peer
                    prev_log_index = self.leader_state.next_index[peer] - 1
                    prev_log_term = 0
                    
                    if prev_log_index > 0:
                        entry = self.log.get_entry(prev_log_index)
                        if entry:
                            prev_log_term = entry.term
                    
                    task = asyncio.create_task(
                        self.rpc.append_entries(
                            peer_address,
                            self.persistent_state.current_term,
                            self.node_id,
                            prev_log_index,
                            prev_log_term,
                            [],  # Empty entries for heartbeat
                            self.volatile_state.commit_index
                        )
                    )
                    heartbeat_tasks.append(task)
                
                # Wait for responses - use gather with return_exceptions to avoid errors
                responses = await asyncio.gather(*heartbeat_tasks, return_exceptions=True)
                
                # Process responses
                for i, response in enumerate(responses):
                    if isinstance(response, Exception):
                        logger.warning(f"Error sending heartbeat: {response}")
                        continue
                    
                    # If we got a higher term, revert to follower
                    if response.get("term", 0) > self.persistent_state.current_term:
                        logger.info(f"Node {self.node_id} discovered higher term during heartbeat")
                        self.become_follower(response["term"])
                        return
                    
                    # If successful, check for pending entries to replicate
                    peer = self.peers[i]
                    if response.get("success", False) and self.needs_replication(peer):
                        asyncio.create_task(self.replicate_log(peer))
                
                # Update cluster state for UI
                self.update_cluster_state()
                
                # Wait before sending next heartbeat
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending heartbeats: {e}")
                await asyncio.sleep(0.1)
    
    def needs_replication(self, peer: str) -> bool:
        """Check if a peer needs log replication."""
        if not self.leader_state:
            return False
            
        return self.log.last_index >= self.leader_state.next_index[peer]
    
    async def replicate_log(self, peer: str) -> None:
        """Replicate log entries to a specific peer."""
        if not self.leader_state:
            logger.warning(f"Cannot replicate logs - no leader state")
            return
            
        peer_address = peer
        next_index = self.leader_state.next_index[peer]
        
        # Get the entries to send
        entries_to_send = self.log.get_entries_from(next_index)
        if not entries_to_send:
            # No entries to send, this is just a heartbeat
            return
        
        # Calculate previous log info
        prev_log_index = next_index - 1
        prev_log_term = 0
        
        if prev_log_index > 0:
            entry = self.log.get_entry(prev_log_index)
            if entry:
                prev_log_term = entry.term
        
        # Convert entries to dicts for transmission
        entries_dict = [entry.to_dict() for entry in entries_to_send]
        
        try:
            # Send append entries RPC
            response = await self.rpc.append_entries(
                peer_address,
                self.persistent_state.current_term,
                self.node_id,
                prev_log_index,
                prev_log_term,
                entries_dict,
                self.volatile_state.commit_index
            )
            
            # Handle response
            if response.get("term", 0) > self.persistent_state.current_term:
                logger.info(f"Node {self.node_id} discovered higher term during replication")
                self.become_follower(response["term"])
                return
            
            if response.get("success", False):
                # Update follower's progress
                match_index = prev_log_index + len(entries_to_send)
                if self.leader_state:  # Double-check leader state still exists
                    self.leader_state.update_follower_progress(peer, match_index)
                
                # Try to advance commit index
                self.update_commit_index()
                logger.debug(f"Successfully replicated {len(entries_to_send)} entries to {peer}")
            else:
                # If failed, decrement nextIndex and try again
                if self.leader_state and self.leader_state.next_index[peer] > 1:
                    self.leader_state.next_index[peer] -= 1
                    # Try again immediately
                    await self.replicate_log(peer)
        except Exception as e:
            logger.error(f"Error replicating log to {peer}: {e}")
    
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
        new_commit_index = match_indices[majority_index]
        
        # Only advance commit index for entries from current term or earlier terms
        # that haven't been committed yet
        if new_commit_index > self.volatile_state.commit_index:
            entry = self.log.get_entry(new_commit_index)
            if entry:
                logger.info(f"Advancing commit index to {new_commit_index}")
                self.volatile_state.commit_index = new_commit_index
    
    async def apply_committed_entries(self) -> None:
        """Apply committed log entries to the state machine."""
        while self.volatile_state.last_applied < self.volatile_state.commit_index:
            self.volatile_state.last_applied += 1
            entry = self.log.get_entry(self.volatile_state.last_applied)
            
            if entry:
                # Apply command to state machine
                await self.apply_command(entry.command)
                logger.info(f"Applied entry {self.volatile_state.last_applied} to state machine: {entry.command}")
    
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
        
        # Log for debugging
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
        self.volatile_state.leader_id = leader_id
        
        # If the term is newer, update our term
        if term > self.persistent_state.current_term:
            logger.debug(f"Updating term from AppendEntries: {self.persistent_state.current_term} -> {term}")
            self.become_follower(term)
        else:
            # Reset election timer
            self.reset_election_timer()
            
            # Make sure we're a follower
            if self.volatile_state.state != NodeState.FOLLOWER:
                logger.info(f"Node {self.node_id} changing from {self.volatile_state.state} to follower due to AppendEntries")
                self.become_follower(term)
        
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
            self.log.append_entries(prev_log_index, log_entries)
            logger.debug(f"Appended {len(log_entries)} entries to log, now has {len(self.log.entries)} entries")
        
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
        # Add retry logic
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            if self.volatile_state.state != NodeState.LEADER:
                # Redirect to leader if known
                if self.volatile_state.leader_id:
                    logger.info(f"Redirecting client request to leader {self.volatile_state.leader_id}")
                    # Here we could have forwarding code, but for simplicity
                    # we just return the leader info
                    return {
                        "success": False,
                        "leader": self.volatile_state.leader_id,
                        "message": "Please retry with the leader node"
                    }
                else:
                    # If there's no known leader, wait a bit and try again
                    if attempt < max_retries - 1:
                        logger.debug(f"No known leader, retrying ({attempt+1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        continue
                    return {
                        "success": False,
                        "error": "No leader known - please try again later",
                        "retry": True
                    }
            
            # If we get here, we're the leader
            logger.info(f"Leader {self.node_id} handling client request: {command}")
            
            try:
                # Append to log
                entry = self.log.append(self.persistent_state.current_term, command)
                
                # Replicate to followers
                replication_tasks = []
                for peer in self.peers:
                    task = asyncio.create_task(self.replicate_log(peer))
                    replication_tasks.append(task)
                
                # Wait for replication with timeout
                await asyncio.wait(replication_tasks, timeout=2.0)
                
                # Wait for command to be applied
                max_wait = 5.0  # seconds
                wait_start = asyncio.get_event_loop().time()
                
                while (
                    self.volatile_state.last_applied < entry.index and
                    asyncio.get_event_loop().time() - wait_start < max_wait
                ):
                    await asyncio.sleep(0.05)
                
                # Check if the command was applied
                if self.volatile_state.last_applied >= entry.index:
                    # Get result from state machine
                    result = await self.apply_command(command)
                    logger.info(f"Client request successful, applied to state machine: {command}")
                    return {
                        "success": True,
                        "index": entry.index,
                        "result": result
                    }
                else:
                    logger.warning(f"Timeout waiting for replication of {command}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return {
                        "success": False,
                        "error": "Timeout waiting for replication",
                        "retry": True
                    }
            except Exception as e:
                logger.error(f"Error handling client request: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return {
                    "success": False,
                    "error": f"Error: {str(e)}",
                    "retry": True
                }
        
        # If we get here, all retries have failed
        return {
            "success": False,
            "error": "All retries failed",
            "retry": True
        }
    
    def become_follower(self, term: int) -> None:
        """Transition to follower state."""
        logger.info(f"Node {self.node_id} becoming follower for term {term}")
        
        # Update term if needed
        if term > self.persistent_state.current_term:
            self.persistent_state.update_term(term)
        
        # Update state
        self.volatile_state.state = NodeState.FOLLOWER
        
        # Cancel leader heartbeat timer if active
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None
        
        # Reset leader state
        self.leader_state = None
        
        # Reset consecutive elections counter when becoming follower
        # only if enough time has passed
        current_time = asyncio.get_event_loop().time()
        if current_time - self.last_election_time > 5.0:
            self.consecutive_elections = 0
        
        # Reset election timer with longer timeout when becoming follower
        # to give the system time to stabilize
        if self.election_timer:
            self.election_timer.cancel()

        timeout = self.config.random_election_timeout * self.election_stability_factor
        logger.debug(f"Node {self.node_id} setting election timeout as follower: {timeout:.2f}s")
        
        self.election_timer = asyncio.create_task(self.election_timeout(timeout))
        
        # Update cluster state for UI
        self.update_cluster_state()
    
    def become_candidate(self) -> None:
        """Transition to candidate state."""
        logger.info(f"Node {self.node_id} becoming candidate for term {self.persistent_state.current_term}")
        
        # Update state
        self.volatile_state.state = NodeState.CANDIDATE
        
        # Reset election timer
        self.reset_election_timer()
        
        # Update cluster state for UI
        self.update_cluster_state()
    
    def become_leader(self) -> None:
        """Transition to leader state."""
        logger.info(f"Node {self.node_id} becoming leader for term {self.persistent_state.current_term}")
        
        # Update state
        self.volatile_state.state = NodeState.LEADER
        self.volatile_state.leader_id = self.node_id
        
        # Initialize leader state
        self.leader_state = LeaderState(self.peers)
        
        # Populate nextIndex with last log index + 1
        last_log_index = self.log.last_index
        for peer in self.peers:
            self.leader_state.next_index[peer] = last_log_index + 1
        
        # Cancel election timer
        if self.election_timer:
            self.election_timer.cancel()
            self.election_timer = None
        
        # Append a no-op entry to commit any previous entries
        self.log.append(self.persistent_state.current_term, {"operation": "no-op"})
        
        # Reset consecutive elections counter when becoming leader
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
        
        # Update peer information if we're the leader
        if self.volatile_state.state == NodeState.LEADER and self.leader_state:
            for peer in self.peers:
                self.cluster_state.peers_status[peer] = {
                    "next_index": self.leader_state.next_index.get(peer),
                    "match_index": self.leader_state.match_index.get(peer),
                }