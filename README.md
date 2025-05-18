Raft Consensus Algorithm Implementation
A Python library implementing the Raft consensus algorithm using asyncio. This implementation follows the protocol described in the paper "In Search of an Understandable Consensus Algorithm" by Diego Ongaro and John Ousterhout.
Architecture
mermaidgraph TD
    Client[Client] --> API[API Server]
    API --> Node[Raft Node]
    Node --> RPC[RPC Communication]
    Node --> Log[Log Management]
    Node --> State[State Management]
    RPC --- Node1[Raft Node 1]
    RPC --- Node2[Raft Node 2]
    RPC --- Node3[Raft Node 3]
    subgraph "Raft Cluster"
        Node1
        Node2
        Node3
    end
    UI[Web UI] --> API
    style Node fill:#f9f,stroke:#333,stroke-width:2px
    style Log fill:#bbf,stroke:#333,stroke-width:1px
    style RPC fill:#bbf,stroke:#333,stroke-width:1px
    style State fill:#bbf,stroke:#333,stroke-width:1px
Raft Consensus Sequence
mermaidsequenceDiagram
    participant C as Client
    participant L as Leader
    participant F1 as Follower 1
    participant F2 as Follower 2
    
    C->>L: Client Request
    L->>L: Append to log
    par Leader to Follower 1
        L->>F1: AppendEntries RPC
        F1->>F1: Verify log consistency
        F1->>L: Success response
    and Leader to Follower 2
        L->>F2: AppendEntries RPC
        F2->>F2: Verify log consistency
        F2->>L: Success response
    end
    L->>L: Wait for majority commit
    L->>L: Apply to state machine
    L->>C: Response
Leader Election Sequence
mermaidsequenceDiagram
    participant F1 as Follower 1
    participant C as Candidate
    participant F2 as Follower 2
    
    Note over F1,F2: Follower timeout
    F1->>F1: Convert to candidate
    F1->>C: Increment term<br/>Vote for self
    
    par Candidate to Follower 1
        C->>F1: RequestVote RPC
        F1->>C: Vote granted
    and Candidate to Follower 2
        C->>F2: RequestVote RPC
        F2->>C: Vote granted
    end
    
    C->>C: Received majority votes
    C->>C: Become leader
    C->>F1: AppendEntries (heartbeat)
    C->>F2: AppendEntries (heartbeat)
Features

Complete implementation of the Raft consensus algorithm
Leader election with randomized timeouts
Log replication across the cluster
Cluster membership management
Persistent state using append-only logs
REST API for client interaction
WebSocket-based real-time UI
CLI for node management
Containerized deployment with Docker

Installation
Using pip
bashpip install raft-consensus
Using Docker
bash# Clone the repository
git clone https://github.com/yourusername/raft-consensus.git
cd raft-consensus

# Build and run with Docker Compose
docker-compose -f docker/docker-compose.yml up
Usage
Starting a Raft node
bash# Start the first node
python -m cli.main --id node0 --host localhost --port 7000 --cluster "localhost:7000,localhost:7001,localhost:7002" --api-port 8000

# Start the second node
python -m cli.main --id node1 --host localhost --port 7001 --cluster "localhost:7000,localhost:7001,localhost:7002" --api-port 8001

# Start the third node
python -m cli.main --id node2 --host localhost --port 7002 --cluster "localhost:7000,localhost:7001,localhost:7002" --api-port 8002
Using the API
pythonimport asyncio
import aiohttp

async def set_value():
    async with aiohttp.ClientSession() as session:
        # Set a key-value pair
        async with session.post('http://localhost:8000/command', 
                              json={'operation': 'set', 'key': 'mykey', 'value': 'myvalue'}) as resp:
            print(await resp.json())
        
        # Get the value
        async with session.post('http://localhost:8000/command', 
                              json={'operation': 'get', 'key': 'mykey'}) as resp:
            print(await resp.json())

asyncio.run(set_value())
Using the Web UI
The web UI is available at http://localhost:8000 when a node is started with the --api-port option.
Development
Prerequisites

Python 3.8+
Node.js 14+ (for UI development)

Setting up the development environment
bash# Clone the repository
git clone https://github.com/yourusername/raft-consensus.git
cd raft-consensus

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
Running tests
bash# Run the Python tests
pytest

# Run the UI tests
cd frontend
npm test
Project Structure

raft/: Core implementation

node.py: Raft node implementation
log.py: Log storage and management
rpc.py: Network communication
state.py: State management
config.py: Configuration handling


cli/: Command-line interface
api/: HTTP API server
tests/: Test suite
frontend/: Web UI
docker/: Docker configuration

Contributing

Fork the repository
Create your feature branch (git checkout -b feature/my-feature)
Commit your changes (git commit -am 'Add some feature')
Push to the branch (git push origin feature/my-feature)
Create a new Pull Request

License
This project is licensed under the MIT License - see the LICENSE file for details.