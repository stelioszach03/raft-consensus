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
    election_timeout_min: int = 1500   # Αυξημένο για προστασία από split votes
    election_timeout_max: int = 3000   # Μεγαλύτερο εύρος για καλύτερη διαφοροποίηση
    heartbeat_interval: int = 300      # Αυξημένο για σταθερότερα heartbeats
    
    # Storage settings
    storage_dir: str = "data"
    
    # API settings
    api_port: Optional[int] = None
    
    @property
    def random_election_timeout(self) -> float:
        """Generate a random election timeout in the configured range.
        
        Returns a node-specific timeout to prevent simultaneous elections.
        """
        # Χρήση του node_id για σταθερή διαφοροποίηση μεταξύ κόμβων
        node_num = int(self.node_id.replace('node', '')) if self.node_id.startswith('node') else 0
        
        # Διαφοροποίηση βάσει node_id - κάθε κόμβος έχει διαφορετικό εύρος
        node_offset = node_num * 500  # Αρκετά μεγάλο offset (500ms) μεταξύ κόμβων
        
        # Τυχαία τιμή μέσα στο εύρος, με προσθήκη του offset
        base_timeout = self.election_timeout_min 
        max_random = self.election_timeout_max - self.election_timeout_min
        random_component = random.uniform(0, max_random)
        
        # Εξασφάλιση ότι ο node0 έχει το μικρότερο timeout και άρα πιο πιθανό να γίνει leader
        if node_num == 0:
            random_component = random.uniform(0, max_random * 0.5)  # Μισό εύρος για node0
            
        timeout = (base_timeout + node_offset + random_component) / 1000
        
        # Βεβαιωνόμαστε ότι οι κόμβοι έχουν επαρκώς διαφορετικά timeouts
        min_recommended = self.heartbeat_interval_seconds * 10
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