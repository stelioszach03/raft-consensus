"""Log management for Raft consensus."""
import dataclasses
import json
import os
from typing import List, Dict, Any, Optional, Tuple


@dataclasses.dataclass
class LogEntry:
    """A single entry in the Raft log."""
    term: int
    index: int
    command: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "term": self.term,
            "index": self.index,
            "command": self.command,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogEntry':
        """Create a LogEntry from a dictionary."""
        return cls(
            term=data["term"],
            index=data["index"],
            command=data["command"],
        )


class RaftLog:
    """Append-only log for the Raft consensus algorithm."""
    
    def __init__(self, log_path: str):
        self.log_path = log_path
        self.entries: List[LogEntry] = []
        self._load()
    
    def _load(self) -> None:
        """Load log entries from disk."""
        if not os.path.exists(self.log_path):
            return
        
        try:
            with open(self.log_path, "r") as f:
                for line in f:
                    if line.strip():
                        entry_data = json.loads(line)
                        self.entries.append(LogEntry.from_dict(entry_data))
        except (json.JSONDecodeError, KeyError):
            # Log file might be corrupted, we'll start with an empty log
            self.entries = []
    
    def append(self, term: int, command: Dict[str, Any]) -> LogEntry:
        """Append a new entry to the log."""
        index = len(self.entries) + 1
        entry = LogEntry(term=term, index=index, command=command)
        self.entries.append(entry)
        
        # Persist to disk
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
        
        return entry
    
    def get_last_log_term_and_index(self) -> Tuple[int, int]:
        """Get the term and index of the last log entry."""
        if not self.entries:
            return 0, 0
        last_entry = self.entries[-1]
        return last_entry.term, last_entry.index
    
    def get_entry(self, index: int) -> Optional[LogEntry]:
        """Get a log entry by index (1-based)."""
        if 1 <= index <= len(self.entries):
            return self.entries[index - 1]
        return None
    
    def get_entries_from(self, start_index: int) -> List[LogEntry]:
        """Get all entries starting from the given index (inclusive)."""
        if start_index <= len(self.entries):
            return self.entries[start_index - 1:]
        return []
    
    def check_consistency(self, prev_log_index: int, prev_log_term: int) -> bool:
        """
        Check if the log contains an entry at prev_log_index with term prev_log_term.
        Used for consistency check in AppendEntries RPC.
        """
        if prev_log_index == 0:
            # Special case: empty log is always consistent
            return True
        
        entry = self.get_entry(prev_log_index)
        return entry is not None and entry.term == prev_log_term
    
    def append_entries(self, prev_log_index: int, entries: List[LogEntry]) -> bool:
        """
        Append entries from leader to the log.
        Returns success or failure.
        """
        # If we don't have the previous log entry, we can't append
        if prev_log_index > 0 and prev_log_index > len(self.entries):
            return False
        
        # If there are no entries to append, it's a heartbeat
        if not entries:
            return True
        
        # Find where to start appending
        start_idx = prev_log_index
        
        # Delete any conflicting entries
        if start_idx < len(self.entries):
            self.entries = self.entries[:start_idx]
        
        # Append the new entries
        self.entries.extend(entries)
        
        # Persist to disk
        self._rewrite_log()
        
        return True
    
    def _rewrite_log(self) -> None:
        """Rewrite the entire log file with current entries."""
        with open(self.log_path, "w") as f:
            for entry in self.entries:
                f.write(json.dumps(entry.to_dict()) + "\n")
    
    @property
    def last_index(self) -> int:
        """Get the index of the last entry in the log."""
        if not self.entries:
            return 0
        return self.entries[-1].index
    
    @property
    def size(self) -> int:
        """Get the number of entries in the log."""
        return len(self.entries)