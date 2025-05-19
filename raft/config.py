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
    election_timeout_min: int = 1500
    election_timeout_max: int = 4000
    heartbeat_interval: int = 750
    
    # Storage settings
    storage_dir: str = "data"
    
    # API settings
    api_port: Optional[int] = None
    
    @property
    def random_election_timeout(self) -> float:
        """Generate a random election timeout in the configured range.
        
        Returns a node-specific timeout to prevent simultaneous elections.
        """
        # Use node_id for stable differentiation between nodes
        node_num = int(self.node_id.replace('node', '')) if self.node_id.startswith('node') else 0
        node_offset = node_num * 500
        
        # Random value within range, with offset added
        base_timeout = self.election_timeout_min 
        max_random = self.election_timeout_max - self.election_timeout_min
        timeout = (base_timeout + node_offset + random.uniform(0, max_random)) / 1000
        
        return timeout
    
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