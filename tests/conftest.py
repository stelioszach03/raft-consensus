"""Test fixtures for Raft consensus tests."""
import asyncio
import os
import shutil
import pytest
from typing import List, Dict, Any, Callable, Awaitable

from raft.config import RaftConfig
from raft.node import RaftNode


@pytest.fixture
def event_loop():
    """Create and yield an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_storage_dir(tmpdir):
    """Create a temporary directory for test storage."""
    storage_dir = os.path.join(tmpdir, "raft_test")
    os.makedirs(storage_dir, exist_ok=True)
    yield storage_dir
    shutil.rmtree(storage_dir)


@pytest.fixture
async def raft_cluster(test_storage_dir):
    """Create a cluster of Raft nodes for testing."""
    # Configuration for a 3-node cluster
    base_port = 50000
    node_configs = []
    nodes = []
    
    # Create configurations
    for i in range(3):
        node_id = f"node{i}"
        port = base_port + i
        
        cluster_nodes = [f"localhost:{base_port + j}" for j in range(3)]
        
        config = RaftConfig(
            node_id=node_id,
            cluster_nodes=cluster_nodes,
            host="localhost",
            port=port,
            storage_dir=test_storage_dir
        )
        
        node_configs.append(config)
    
    # Create and start nodes
    for config in node_configs:
        node = RaftNode(config)
        task = asyncio.create_task(node.start())
        nodes.append((node, task))
    
    # Wait for nodes to initialize
    await asyncio.sleep(0.5)
    
    yield nodes
    
    # Shutdown nodes
    for node, task in nodes:
        node.shutdown_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.fixture
async def wait_for_leader(raft_cluster):
    """Wait for a leader to be elected and return it."""
    max_wait = 5  # seconds
    
    async def wait():
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < max_wait:
            for node, _ in raft_cluster:
                if node.volatile_state.state.value == "leader":
                    return node
            
            await asyncio.sleep(0.1)
        
        raise TimeoutError("No leader elected within timeout")
    
    return await wait()