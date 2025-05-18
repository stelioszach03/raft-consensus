"""Configuration management for Raft nodes."""
import dataclasses
import os
import random
from typing import List, Optional


@dataclasses.dataclass
class RaftConfig:
    """Configuration for a Raft node."""
    
    # Node identification
    node_id: str
    cluster_nodes: List[str]
    
    # Network settings
    host: str
    port: int
    
    # Timing settings (in milliseconds)
    election_timeout_min: int = 500
    election_timeout_max: int = 2000  # Αυξημένο από 1000 σε 2000
    heartbeat_interval: int = 100     # Αυξημένο από 50 σε 100
    
    # Storage settings
    storage_dir: str = "data"
    
    # API settings
    api_port: Optional[int] = None
    
    @property
    def random_election_timeout(self) -> float:
        """Generate a random election timeout in the configured range."""
        return random.uniform(self.election_timeout_min / 1000,
                              self.election_timeout_max / 1000)
    
    @property
    def heartbeat_interval_seconds(self) -> float:
        """Convert heartbeat interval to seconds."""
        return self.heartbeat_interval / 1000
    
    @property
    def node_address(self) -> str:
        """Get the full address of this node."""
        return f"{self.host}:{self.port}"
    
    @property
    def storage_path(self) -> str:
        """Get the storage path for this node."""
        path = os.path.join(self.storage_dir, self.node_id)
        os.makedirs(path, exist_ok=True)
        return path
    
    @property
    def log_path(self) -> str:
        """Get the log file path for this node."""
        return os.path.join(self.storage_path, "raft.log")
    
    @property
    def state_path(self) -> str:
        """Get the state file path for this node."""
        return os.path.join(self.storage_path, "state.json")