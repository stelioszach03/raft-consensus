"""Tests for leader election in the Raft consensus algorithm."""
import asyncio
import pytest
import logging

from raft.state import NodeState

# Configure logging
logging.basicConfig(level=logging.INFO)


@pytest.mark.asyncio
async def test_leader_election(raft_cluster, wait_for_leader):
    """Test that a leader is elected."""
    # A leader should have been elected
    leader = wait_for_leader
    
    # Verify we have exactly one leader
    leader_count = 0
    for node, _ in raft_cluster:
        if node.volatile_state.state == NodeState.LEADER:
            leader_count += 1
    
    assert leader_count == 1, "Expected exactly one leader"
    
    # All nodes should have the same term
    term = leader.persistent_state.current_term
    for node, _ in raft_cluster:
        assert node.persistent_state.current_term == term, "Terms should match across nodes"
    
    # All nodes should recognize the same leader
    leader_id = leader.node_id
    for node, _ in raft_cluster:
        if node.volatile_state.state != NodeState.LEADER:
            assert node.volatile_state.leader_id == leader_id, "All nodes should recognize the same leader"


@pytest.mark.asyncio
async def test_election_after_leader_failure(raft_cluster, wait_for_leader):
    """Test that a new leader is elected if the current leader fails."""
    # Get the current leader
    leader = wait_for_leader
    old_leader_id = leader.node_id
    old_term = leader.persistent_state.current_term
    
    # Simulate leader failure by stopping it
    for i, (node, task) in enumerate(raft_cluster):
        if node.node_id == old_leader_id:
            node.shutdown_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raft_cluster.pop(i)
            break
    
    # Wait for a new leader to be elected
    max_wait = 5  # seconds
    new_leader = None
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < max_wait:
        for node, _ in raft_cluster:
            if node.volatile_state.state == NodeState.LEADER:
                new_leader = node
                break
        
        if new_leader:
            break
        
        await asyncio.sleep(0.1)
    
    assert new_leader is not None, "A new leader should be elected"
    assert new_leader.node_id != old_leader_id, "The new leader should be different from the old leader"
    assert new_leader.persistent_state.current_term > old_term, "The new term should be higher"