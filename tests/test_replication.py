"""Tests for log replication in the Raft consensus algorithm."""
import asyncio
import pytest
import logging

from raft.state import NodeState

# Configure logging
logging.basicConfig(level=logging.INFO)


@pytest.mark.asyncio
async def test_log_replication(raft_cluster, wait_for_leader):
    """Test that log entries are properly replicated to followers."""
    # Get the leader
    leader = wait_for_leader
    
    # Submit a command to the leader
    command = {"operation": "set", "key": "test", "value": "value1"}
    result = await leader.client_request(command)
    
    assert result["success"] is True, "Command should succeed"
    
    # Give some time for replication
    await asyncio.sleep(1)
    
    # Verify that the command is replicated to all nodes
    for node, _ in raft_cluster:
        # Get the last log entry from each node
        if node.log.entries:
            last_entry = node.log.entries[-1]
            assert last_entry.command == command, f"Node {node.node_id} should have the command in its log"
        else:
            pytest.fail(f"Node {node.node_id} has an empty log")
        
        # Check that the command was applied to the state machine
        assert node.state_machine.get("test") == "value1", "Command should be applied to state machine"


@pytest.mark.asyncio
async def test_multiple_commands_replication(raft_cluster, wait_for_leader):
    """Test replication of multiple commands."""
    # Get the leader
    leader = wait_for_leader
    
    # Submit multiple commands
    commands = [
        {"operation": "set", "key": f"key{i}", "value": f"value{i}"} 
        for i in range(5)
    ]
    
    for command in commands:
        result = await leader.client_request(command)
        assert result["success"] is True, f"Command {command} should succeed"
    
    # Give some time for replication
    await asyncio.sleep(1)
    
    # Verify all commands were replicated
    for node, _ in raft_cluster:
        assert len(node.log.entries) >= 5, f"Node {node.node_id} should have at least 5 log entries"
        
        # Check state machine
        for i in range(5):
            assert node.state_machine.get(f"key{i}") == f"value{i}", f"Command for key{i} should be applied"


@pytest.mark.asyncio
async def test_old_leader_rejoins(raft_cluster, wait_for_leader):
    """Test that a former leader can rejoin as a follower and catch up."""
    # Get the current leader
    leader = wait_for_leader
    leader_id = leader.node_id
    leader_idx = None
    
    # Find the leader in the cluster
    for i, (node, _) in enumerate(raft_cluster):
        if node.node_id == leader_id:
            leader_idx = i
            break
    
    assert leader_idx is not None, "Leader should be in the cluster"
    
    # Disconnect the leader temporarily
    leader_node, leader_task = raft_cluster.pop(leader_idx)
    leader_node.shutdown_event.set()
    leader_task.cancel()
    try:
        await leader_task
    except asyncio.CancelledError:
        pass
    
    # Wait for a new leader to be elected
    new_leader = None
    max_wait = 5  # seconds
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
    assert new_leader.node_id != leader_id, "The new leader should be different from the old leader"
    
    # Add some entries to the log while the old leader is disconnected
    for i in range(3):
        command = {"operation": "set", "key": f"after_disconnect_{i}", "value": i}
        result = await new_leader.client_request(command)
        assert result["success"] is True
    
    # Restart the old leader
    config = leader_node.config
    new_leader_node = RaftNode(config)
    new_task = asyncio.create_task(new_leader_node.start())
    raft_cluster.append((new_leader_node, new_task))
    
    # Give time for the old leader to catch up
    await asyncio.sleep(2)
    
    # Check that the old leader got the new entries
    assert len(new_leader_node.log.entries) >= 3, "Old leader should have caught up with new entries"
    
    # Check that it's now a follower
    assert (new_leader_node.volatile_state.state == NodeState.FOLLOWER), "Old leader should now be a follower"
    
    # Check that it recognizes the new leader
    assert new_leader_node.volatile_state.leader_id == new_leader.node_id