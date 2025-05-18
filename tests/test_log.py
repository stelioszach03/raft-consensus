"""Tests for log operations in the Raft consensus algorithm."""
import asyncio
import pytest
import os
import json

from raft.log import RaftLog, LogEntry


@pytest.fixture
def empty_log(tmpdir):
    """Create an empty log for testing."""
    log_path = os.path.join(tmpdir, "test.log")
    return RaftLog(log_path)


@pytest.fixture
def populated_log(tmpdir):
    """Create a log with some entries for testing."""
    log_path = os.path.join(tmpdir, "test.log")
    log = RaftLog(log_path)
    
    log.append(1, {"operation": "set", "key": "foo", "value": "bar"})
    log.append(1, {"operation": "set", "key": "baz", "value": 42})
    log.append(2, {"operation": "delete", "key": "foo"})
    
    return log


def test_append_and_get(empty_log):
    """Test appending entries to the log and retrieving them."""
    # Append some entries
    entry1 = empty_log.append(1, {"op": "set", "key": "x", "value": 1})
    entry2 = empty_log.append(1, {"op": "set", "key": "y", "value": 2})
    
    # Check entries were added correctly
    assert len(empty_log.entries) == 2
    assert empty_log.entries[0].term == 1
    assert empty_log.entries[0].index == 1
    assert empty_log.entries[0].command == {"op": "set", "key": "x", "value": 1}
    assert empty_log.entries[1].term == 1
    assert empty_log.entries[1].index == 2
    assert empty_log.entries[1].command == {"op": "set", "key": "y", "value": 2}
    
    # Test getting entries by index
    assert empty_log.get_entry(1) == entry1
    assert empty_log.get_entry(2) == entry2
    assert empty_log.get_entry(3) is None
    
    # Test getting entries from a starting index
    entries_from_1 = empty_log.get_entries_from(1)
    assert len(entries_from_1) == 2
    assert entries_from_1[0] == entry1
    assert entries_from_1[1] == entry2
    
    entries_from_2 = empty_log.get_entries_from(2)
    assert len(entries_from_2) == 1
    assert entries_from_2[0] == entry2
    
    entries_from_3 = empty_log.get_entries_from(3)
    assert len(entries_from_3) == 0


def test_persistence(tmpdir):
    """Test that logs are properly persisted and can be reloaded."""
    log_path = os.path.join(tmpdir, "persist_test.log")
    
    # Create a log and add some entries
    log1 = RaftLog(log_path)
    log1.append(1, {"op": "set", "key": "x", "value": 1})
    log1.append(2, {"op": "set", "key": "y", "value": 2})
    
    # Create a new log instance that should load the existing entries
    log2 = RaftLog(log_path)
    
    # Check that the entries were loaded correctly
    assert len(log2.entries) == 2
    assert log2.entries[0].term == 1
    assert log2.entries[0].index == 1
    assert log2.entries[0].command == {"op": "set", "key": "x", "value": 1}
    assert log2.entries[1].term == 2
    assert log2.entries[1].index == 2
    assert log2.entries[1].command == {"op": "set", "key": "y", "value": 2}


def test_consistency_check(populated_log):
    """Test the log consistency check."""
    # Valid consistency checks
    assert populated_log.check_consistency(0, 0), "Empty log should be consistent"
    assert populated_log.check_consistency(1, 1), "Entry 1 should have term 1"
    assert populated_log.check_consistency(2, 1), "Entry 2 should have term 1"
    assert populated_log.check_consistency(3, 2), "Entry 3 should have term 2"
    
    # Invalid consistency checks
    assert not populated_log.check_consistency(1, 2), "Entry 1 has term 1, not 2"
    assert not populated_log.check_consistency(4, 2), "Entry 4 doesn't exist"


def test_append_entries(populated_log):
    """Test appending entries from a leader."""
    # Create entries to append
    new_entries = [
        LogEntry(term=2, index=4, command={"operation": "set", "key": "new", "value": "value"}),
        LogEntry(term=2, index=5, command={"operation": "get", "key": "new"})
    ]
    
    # Append the entries (should succeed)
    assert populated_log.append_entries(3, new_entries)
    
    # Check the log now has 5 entries
    assert len(populated_log.entries) == 5
    assert populated_log.entries[3].command == {"operation": "set", "key": "new", "value": "value"}
    assert populated_log.entries[4].command == {"operation": "get", "key": "new"}
    
    # Try to append with invalid prev_log_index
    assert not populated_log.append_entries(10, [LogEntry(term=3, index=11, command={})])
    
    # Check the log still has 5 entries
    assert len(populated_log.entries) == 5
    
    # Test overwriting part of the log (conflict resolution)
    conflict_entries = [
        LogEntry(term=3, index=4, command={"operation": "set", "key": "conflict", "value": True}),
        LogEntry(term=3, index=5, command={"operation": "set", "key": "another", "value": "entry"})
    ]
    
    # Append the conflicting entries (should succeed and overwrite)
    assert populated_log.append_entries(3, conflict_entries)
    
    # Check the log still has 5 entries but with updated content
    assert len(populated_log.entries) == 5
    assert populated_log.entries[3].term == 3
    assert populated_log.entries[3].command == {"operation": "set", "key": "conflict", "value": True}
    assert populated_log.entries[4].term == 3
    assert populated_log.entries[4].command == {"operation": "set", "key": "another", "value": "entry"}