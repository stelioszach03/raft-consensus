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
    # Βελτιωμένες τιμές για αποφυγή split vote
    election_timeout_min: int = 500   # Μειωμένο από 1500
    election_timeout_max: int = 1000  # Μειωμένο από 3000
    heartbeat_interval: int = 250     # Ελαφρώς μειωμένο από 300
    
    # Storage settings
    storage_dir: str = "data"
    
    # API settings
    api_port: Optional[int] = None
    
    @property
    def random_election_timeout(self) -> float:
        """Generate a random election timeout in the configured range."""
        # Χρήση του node_id για σταθερή διαφοροποίηση
        node_num = int(self.node_id.replace('node', '')) if self.node_id.startswith('node') else 0
        
        # Μικρότερη διαφοροποίηση μεταξύ των κόμβων
        node_offset = node_num * 200  # Μειωμένο από 500ms
        
        # Τυχαία τιμή μέσα στο εύρος
        base_timeout = self.election_timeout_min 
        max_random = self.election_timeout_max - self.election_timeout_min
        random_component = random.uniform(0, max_random)
        
        # Εξασφάλιση ότι ο node0 έχει το μικρότερο timeout 
        if node_num == 0:
            random_component = random.uniform(0, max_random * 0.5)
            
        timeout = (base_timeout + node_offset + random_component) / 1000
        
        # Εξασφαλίζουμε ότι το timeout είναι αρκετά μεγαλύτερο από το heartbeat
        min_recommended = self.heartbeat_interval_seconds * 3
        if timeout < min_recommended:
            timeout = min_recommended * (1 + 0.5 * random.random())
            
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