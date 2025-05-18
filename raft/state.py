"""State management for Raft nodes."""
import enum
import json
import time
import random
from typing import Dict, Optional, Any, List


class NodeState(enum.Enum):
    """Possible states for a Raft node."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class PersistentState:
    """Persistent state on all servers."""
    
    def __init__(self, path: str):
        self.path = path
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self._load()
    
    def _load(self) -> None:
        """Load state from disk if it exists."""
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
                self.current_term = data.get("current_term", 0)
                self.voted_for = data.get("voted_for")
        except (FileNotFoundError, json.JSONDecodeError):
            # Initialize with defaults if file doesn't exist or is invalid
            pass
    
    def save(self) -> None:
        """Save state to disk."""
        with open(self.path, "w") as f:
            json.dump({
                "current_term": self.current_term,
                "voted_for": self.voted_for,
            }, f)
    
    def update_term(self, term: int) -> bool:
        """Update the current term if the new term is higher."""
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.save()
            return True
        return False
    
    def record_vote(self, candidate_id: str) -> None:
        """Record that this node voted for a candidate in the current term."""
        self.voted_for = candidate_id
        self.save()


class VolatileState:
    """Volatile state on all servers."""
    
    def __init__(self):
        self.commit_index = 0
        self.last_applied = 0
        self.state = NodeState.FOLLOWER
        self.leader_id: Optional[str] = None
        self.last_heartbeat_time = 0.0
        
        # Προσθέστε διαφορετική καθυστέρηση για κάθε κόμβο για να αποφύγετε ταυτόχρονες εκλογές
        time.sleep(random.uniform(0.1, 0.3))
    
    def update_heartbeat(self) -> None:
        """Update the last time a heartbeat was received."""
        self.last_heartbeat_time = time.time()
    
    def time_since_last_heartbeat(self) -> float:
        """Get the time elapsed since the last heartbeat in seconds."""
        return time.time() - self.last_heartbeat_time


class LeaderState:
    """Volatile state on leaders."""
    
    def __init__(self, cluster_nodes: List[str]):
        # Initialize tracking for each follower
        self.next_index: Dict[str, int] = {node: 1 for node in cluster_nodes}
        self.match_index: Dict[str, int] = {node: 0 for node in cluster_nodes}
    
    def update_follower_progress(self, follower_id: str, last_log_index: int) -> None:
        """Update the progress of a follower after successful replication."""
        self.match_index[follower_id] = last_log_index
        self.next_index[follower_id] = last_log_index + 1


class ClusterState:
    """Aggregated state information for the cluster UI."""
    
    def __init__(self, node_id: str, config):
        self.node_id = node_id
        self.config = config
        self.state = NodeState.FOLLOWER
        self.current_term = 0
        self.voted_for = None
        self.leader_id = None
        self.last_heartbeat = 0
        self.log_size = 0
        self.commit_index = 0
        self.last_applied = 0
        self.peers_status: Dict[str, Dict[str, Any]] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to a dictionary for API responses."""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "leader_id": self.leader_id,
            "last_heartbeat": self.last_heartbeat,
            "log_size": self.log_size,
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
            "peers": self.peers_status,
        }