"""Raft consensus node implementation."""
import asyncio
import logging
import random
from typing import Dict, List, Any, Optional, Set

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
        
        timeout = self.config.random_election_timeout
        self.election_timer = asyncio.create_task(self.election_timeout(timeout))
    
    async def election_timeout(self, timeout: float) -> None:
        """
        Election timeout handler.
        When this timeout triggers, the node becomes a candidate and starts an election.
        """
        try:
            await asyncio.sleep(timeout)
            if self.volatile_state.state != NodeState.LEADER:
                logger.info(f"Node {self.node_id} election timeout - starting election")
                await self.start_election()
        except asyncio.CancelledError:
            # Timer was cancelled
            pass
    
    async def start_election(self) -> None:
        """Start a leader election."""
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
        
        # Wait for votes
        for task in asyncio.as_completed(vote_tasks):
            response = await task
            if response.get("vote_granted", False):
                votes_received += 1
                logger.info(f"Node {self.node_id} received vote - now has {votes_received}/{votes_needed}")
            
            # If we got a higher term, revert to follower
            if response.get("term", 0) > self.persistent_state.current_term:
                self.become_follower(response["term"])
                return
            
            # If we have enough votes, become leader
            if votes_received >= votes_needed:
                logger.info(f"Node {self.node_id} won election with {votes_received} votes")
                self.become_leader()
                return
        
        # If we get here, we didn't win the election
        self.become_follower(self.persistent_state.current_term)
    
    async def send_heartbeats(self) -> None:
        """Send heartbeats (empty AppendEntries) to all peers."""
        while (
            not self.shutdown_event.is_set() and 
            self.volatile_state.state == NodeState.LEADER
        ):
            try:
                # Send heartbeats to all peers
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
                
                # Wait for responses
                for task in asyncio.as_completed(heartbeat_tasks):
                    response = await task
                    
                    # If we got a higher term, revert to follower
                    if response.get("term", 0) > self.persistent_state.current_term:
                        self.become_follower(response["term"])
                        return
                
                # Update cluster state for UI
                self.update_cluster_state()
                
                # Wait before sending next heartbeat
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending heartbeats: {e}")
                await asyncio.sleep(0.1)
    
    async def replicate_log(self, peer: str) -> None:
        """Replicate log entries to a specific peer."""
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
            self.become_follower(response["term"])
            return
        
        if response.get("success", False):
            # Update follower's progress
            match_index = prev_log_index + len(entries_to_send)
            self.leader_state.update_follower_progress(peer, match_index)
            
            # Try to advance commit index
            self.update_commit_index()
        else:
            # If failed, decrement nextIndex and try again
            if self.leader_state.next_index[peer] > 1:
                self.leader_state.next_index[peer] -= 1
                # Try again immediately
                await self.replicate_log(peer)
    
    def update_commit_index(self) -> None:
        """
        Update commit index if there exists a majority-replicated index in current term.
        Called when a follower successfully replicates entries.
        """
        if self.volatile_state.state != NodeState.LEADER:
            return
        
        # Get the sorted match indices for all peers
        match_indices = sorted(self.leader_state.match_index.values())
        
        # Find the median (majority-replicated) index
        majority_index = len(match_indices) // 2
        new_commit_index = match_indices[majority_index]
        
        # Only advance commit index for entries from current term
        if (new_commit_index > self.volatile_state.commit_index and
            self.log.get_entry(new_commit_index) and
            self.log.get_entry(new_commit_index).term == self.persistent_state.current_term):
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
                logger.info(f"Applied entry {self.volatile_state.last_applied} to state machine")
    
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
        
        # If the term is outdated, reject vote
        if term < self.persistent_state.current_term:
            return {
                "term": self.persistent_state.current_term,
                "vote_granted": False
            }
        
        # If the term is newer, update our term and become follower
        if term > self.persistent_state.current_term:
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
            
            if (last_log_term > our_last_term or
                (last_log_term == our_last_term and last_log_index >= our_last_index)):
                # Grant vote
                vote_granted = True
                self.persistent_state.record_vote(candidate_id)
                
                # Reset election timer since we're granting a vote
                self.reset_election_timer()
        
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
        
        # If the term is outdated, reject
        if term < self.persistent_state.current_term:
            return {
                "term": self.persistent_state.current_term,
                "success": False
            }
        
        # Update state based on the valid AppendEntries
        self.volatile_state.update_heartbeat()
        self.volatile_state.leader_id = leader_id
        
        # If the term is newer, update our term
        if term > self.persistent_state.current_term:
            self.become_follower(term)
        else:
            # Reset election timer
            self.reset_election_timer()
            
            # Make sure we're a follower
            if self.volatile_state.state != NodeState.FOLLOWER:
                self.become_follower(term)
        
        # Check log consistency
        if not self.log.check_consistency(prev_log_index, prev_log_term):
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
        
        # Update commit index
        if leader_commit > self.volatile_state.commit_index:
            self.volatile_state.commit_index = min(
                leader_commit, self.log.last_index
            )
        
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
        if self.volatile_state.state != NodeState.LEADER:
            # Redirect to leader if known
            if self.volatile_state.leader_id:
                return {
                    "success": False,
                    "leader": self.volatile_state.leader_id
                }
            else:
                return {
                    "success": False,
                    "error": "No leader known"
                }
        
        # Append to log
        entry = self.log.append(self.persistent_state.current_term, command)
        
        # Replicate to followers
        replication_tasks = []
        for peer in self.peers:
            task = asyncio.create_task(self.replicate_log(peer))
            replication_tasks.append(task)
        
        await asyncio.gather(*replication_tasks)
        
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
            return {
                "success": True,
                "index": entry.index,
                "result": result
            }
        else:
            return {
                "success": False,
                "error": "Timeout waiting for replication"
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
        
        # Reset election timer
        self.reset_election_timer()
        
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