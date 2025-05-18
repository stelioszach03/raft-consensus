"""Command-line interface for the Raft consensus implementation."""
import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import List, Optional

import uvicorn

from raft.config import RaftConfig
from raft.node import RaftNode
from api.server import RaftAPI


def setup_logging(level: int = logging.INFO) -> None:
    """Set up logging configuration."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler()]
    )


async def run_node(config: RaftConfig) -> None:
    """Run a Raft node with the given configuration."""
    # Create the node
    node = RaftNode(config)
    
    # Start API server if configured
    api_server = None
    if config.api_port:
        api_server = RaftAPI(node, config.api_port)
        api_task = asyncio.create_task(api_server.start())
    
    # Start the node
    node_task = asyncio.create_task(node.start())
    
    # Set up signal handlers
    loop = asyncio.get_event_loop()
    
    def handle_signal():
        logging.info("Shutting down...")
        node.shutdown_event.set()
        node_task.cancel()
        if api_server:
            api_task.cancel()
    
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, handle_signal)
    
    # Wait for the node to exit
    try:
        await node_task
    except asyncio.CancelledError:
        pass
    finally:
        logging.info("Node stopped")


def parse_cluster_nodes(nodes_str: str) -> List[str]:
    """Parse the cluster nodes string into a list of node addresses."""
    return [node.strip() for node in nodes_str.split(",")]


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Raft Consensus Node")
    
    parser.add_argument("--id", required=True, help="Node ID")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, required=True, help="Port to bind to")
    parser.add_argument("--cluster", required=True, help="Comma-separated list of cluster nodes (host:port)")
    parser.add_argument("--storage-dir", default="data", help="Directory for persistent storage")
    parser.add_argument("--api-port", type=int, help="Port for the HTTP API server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)
    
    # Parse cluster nodes
    cluster_nodes = parse_cluster_nodes(args.cluster)
    
    # Create configuration
    config = RaftConfig(
        node_id=args.id,
        cluster_nodes=cluster_nodes,
        host=args.host,
        port=args.port,
        storage_dir=args.storage_dir,
        api_port=args.api_port
    )
    
    # Run the node
    asyncio.run(run_node(config))


if __name__ == "__main__":
    main()