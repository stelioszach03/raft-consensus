"""End-to-end tests for the Raft consensus system."""
import asyncio
import subprocess
import time
import pytest
import aiohttp
import json
import os
from typing import Dict, Any, List, Tuple

# Πόρτες για τους κόμβους του Raft
NODE_PORTS = [8100, 8101, 8102]

@pytest.fixture
async def setup_raft_cluster():
    """Set up a Raft cluster for testing."""
    # Εκκαθάριση και επανεκκίνηση του cluster
    subprocess.run(["docker-compose", "down"], check=True)
    subprocess.run(["docker", "volume", "rm", "docker_raft_data"], check=False)
    subprocess.run(["docker-compose", "up", "-d"], check=True)
    
    # Αναμονή για την εκκίνηση του συστήματος
    time.sleep(15)
    
    # Επιστροφή session για HTTP requests
    async with aiohttp.ClientSession() as session:
        yield session
    
    # Καθαρισμός μετά το τέλος των tests
    subprocess.run(["docker-compose", "down"], check=True)

async def get_leader_port(session: aiohttp.ClientSession) -> int:
    """Εύρεση του leader."""
    for port in NODE_PORTS:
        async with session.get(f"http://localhost:{port}/status") as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("state") == "leader":
                    return port
    
    raise Exception("No leader found in the cluster")

@pytest.mark.asyncio
async def test_basic_replication(setup_raft_cluster):
    """Test the basic replication of data in a Raft cluster."""
    session = setup_raft_cluster
    
    # Εύρεση του leader
    leader_port = await get_leader_port(session)
    
    # Εκτέλεση ενός write
    test_key = "test_key"
    test_value = "test_value"
    command = {"operation": "set", "key": test_key, "value": test_value}
    
    async with session.post(
        f"http://localhost:{leader_port}/command", 
        json=command
    ) as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result["success"] is True
    
    # Αναμονή για αντιγραφή
    await asyncio.sleep(2)
    
    # Επαλήθευση στον leader
    leader_cmd = {"operation": "get", "key": test_key}
    async with session.post(
        f"http://localhost:{leader_port}/command", 
        json=leader_cmd
    ) as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result["success"] is True
        assert result["result"] == test_value
    
    # Έλεγχος logs σε όλους τους κόμβους - πρέπει να περιέχουν την εντολή
    for port in NODE_PORTS:
        async with session.get(f"http://localhost:{port}/log") as resp:
            assert resp.status == 200
            log_data = await resp.json()
            
            found = False
            for entry in log_data["entries"]:
                if entry["command"].get("operation") == "set" and \
                   entry["command"].get("key") == test_key and \
                   entry["command"].get("value") == test_value:
                    found = True
                    break
            
            assert found, f"Log entry not found in node on port {port}"

@pytest.mark.asyncio
async def test_leader_failure(setup_raft_cluster):
    """Test leader failure and election of a new leader."""
    session = setup_raft_cluster
    
    # Εύρεση του αρχικού leader
    original_leader_port = await get_leader_port(session)
    
    # Αποθήκευση του container name του leader
    leader_index = NODE_PORTS.index(original_leader_port)
    leader_container = f"raft-node{leader_index}"
    
    # Τερματισμός του leader
    subprocess.run(["docker", "stop", leader_container], check=True)
    
    # Αναμονή για εκλογή νέου leader
    await asyncio.sleep(15)
    
    # Εύρεση του νέου leader
    new_leader_port = None
    for port in NODE_PORTS:
        if port != original_leader_port:
            try:
                async with session.get(f"http://localhost:{port}/status") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("state") == "leader":
                            new_leader_port = port
                            break
            except:
                continue
    
    assert new_leader_port is not None, "No new leader elected after failure"
    assert new_leader_port != original_leader_port, "New leader should be different from the original"
    
    # Επαλήθευση ότι ο νέος leader μπορεί να δεχτεί εντολές
    test_key = "after_failure"
    test_value = "still_works"
    command = {"operation": "set", "key": test_key, "value": test_value}
    
    async with session.post(
        f"http://localhost:{new_leader_port}/command", 
        json=command
    ) as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result["success"] is True