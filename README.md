Here’s a polished, professional README for your Raft Consensus project:

---

# Raft-Consensus

A production-grade, interactive implementation of the Raft consensus algorithm, complete with real-time visualization, fault-injection controls, and Dockerized cluster deployment.

![Raft Consensus UI](https://raw.githubusercontent.com/stelioszach03/raft-consensus/main/docs/images/raft-ui.png)

---

## 🚀 Quick Start

### 1. Clone & Launch with Docker

```bash
git clone https://github.com/stelioszach03/raft-consensus.git
cd raft-consensus/docker
docker-compose up -d
```

Give the cluster 15 seconds to stabilize, then open:

* Leader UI → [http://localhost:8100](http://localhost:8100)
* Follower UIs → [http://localhost:8101](http://localhost:8101), [http://localhost:8102](http://localhost:8102)

### 2. Manual Build & Run

```bash
# 1. Backend dependencies
pip install -r requirements.txt

# 2. Frontend
cd frontend
npm ci
npm run build
cd ..

# 3. Start three nodes in separate terminals
python -m cli.main \
  --id node0 --host localhost --port 7000 \
  --cluster localhost:7000,localhost:7001,localhost:7002 \
  --api-port 8100 --debug

# Repeat for node1 (port 7001/8101) and node2 (7002/8102)

# 4. Browse UIs on ports 8100, 8101, 8102
```

---

## 🔍 Overview

This project demonstrates a **strongly-consistent** key-value store using Raft. It highlights:

* **Leader election** with randomized timeouts
* **Log replication** and commitment only after majority acknowledgment
* **Safety guarantees**: never overwriting committed entries
* **Fault tolerance**: automatic re-elections after node/network failures
* **Interactive UI**: visualize state, logs, elections, and inject failures

For in-depth protocol details, see the original Raft paper:

> Diego Ongaro & John Ousterhout, “In Search of an Understandable Consensus Algorithm”
> [https://raft.github.io/raft.pdf](https://raft.github.io/raft.pdf)

---

## ⚙️ Architecture

```
┌────────────┐    AppendEntries    ┌────────────┐    
│  Leader    │ ─────────────────► │  Follower  │    
│  (node0)   │                     │  (node1)   │    
└────────────┘ ◄───────────────── └────────────┘    
       │        RequestVote           ▲             
       ▼                             │             
┌────────────┐    AppendEntries    ┌────────────┐    
│  Follower  │ ◄───────────────── │  Follower  │    
│  (node2)   │ ─────────────────► │  (node1)   │    
└────────────┘    RequestVote      └────────────┘    
```

Each node maintains:

* A persistent **log** of commands
* A **state machine** (in-memory KV store)
* Timers for election/heartbeat

RPCs (`/raft/vote`, `/raft/append`) ensure consensus; a REST API (`/command`, `/status`, `/log`) exposes client operations and monitoring.

---

## 📦 Features

* **Complete Raft**: election, pre-vote, log replication, commit indexing
* **Fault Injection**: simulate network partitions and node crashes
* **Real-time Dashboard**: cluster topology, log streams, per-node metrics
* **RESTful Client API**: `set`, `get`, `delete` operations
* **Dockerized Deployment**: one-line cluster spin-up

---

## 🧪 Testing

Run end-to-end scenarios (leader election, replication) with pytest:

```bash
# From project root (requires Docker running)
pytest -xvs tests/test_end_to_end.py
```

---

## 🛠️ Development

```
raft-consensus/
├── api/          # FastAPI/AioHTTP server
├── cli/          # Node launcher & configuration
├── docker/       # Docker Compose setup
├── frontend/     # Next.js React UI
└── raft/         # Core Raft implementation
    ├── config.py
    ├── log.py
    ├── node.py
    ├── rpc.py
    └── state.py
```

* **Add a new feature** → implement in `raft/node.py` + expose in API
* **UI tweaks** → modify React components under `frontend/src/components`

---

## 📖 License

Licensed under **MIT**. See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

* **Raft paper** by Ongaro & Ousterhout
* [raft.github.io](https://raft.github.io) for the canonical visualization
* Community contributions and feedback

---

Feel free to open issues or pull requests—your improvements are welcome!
