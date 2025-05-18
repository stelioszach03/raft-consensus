"""API server for the Raft cluster UI."""
import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from raft.node import RaftNode

logger = logging.getLogger(__name__)


class Command(BaseModel):
    """Model for client commands."""
    operation: str
    key: Optional[str] = None
    value: Optional[Any] = None


class WebSocketManager:
    """Manages active WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket) -> None:
        """Connect a new WebSocket client."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect a WebSocket client."""
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            logger.debug("No active connections for broadcasting")
            return
            
        logger.debug(f"Broadcasting to {len(self.active_connections)} clients")
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.active_connections.remove(connection)


class RaftAPI:
    """API server for the Raft cluster UI."""
    
    def __init__(self, node: RaftNode, port: int):
        self.node = node
        self.port = port
        self.app = FastAPI(title="Raft Consensus API")
        self.websocket_manager = WebSocketManager()
        
        # Προστασία από ταυτόχρονες προσομοιώσεις
        self.simulation_lock = asyncio.Lock()
        self.simulation_in_progress = False
        
        # Set up CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Set up routes
        self.setup_routes()
        
        # Background tasks
        self.background_tasks = set()
        
        logger.info(f"Initialized RaftAPI server on port {port}")
    
    def setup_routes(self) -> None:
        """Set up API routes."""
        
        @self.app.get("/status")
        async def get_status() -> Dict[str, Any]:
            """Get the current status of the node."""
            status = self.node.cluster_state.to_dict()
            logger.debug(f"Returning status: {status}")
            return status
        
        @self.app.get("/log")
        async def get_log() -> Dict[str, Any]:
            """Get the log entries."""
            entries = [
                {
                    "index": entry.index,
                    "term": entry.term,
                    "command": entry.command
                }
                for entry in self.node.log.entries
            ]
            logger.debug(f"Returning {len(entries)} log entries")
            return {"entries": entries}
        
        @self.app.post("/command")
        async def client_command(command: Command) -> Dict[str, Any]:
            """Execute a client command."""
            logger.info(f"Executing command: {command}")
            result = await self.node.client_request(command.dict())
            
            # Broadcast update to websocket clients
            task = asyncio.create_task(self.broadcast_update())
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
            
            return result
        
        @self.app.post("/simulation/node-failure")
        async def simulate_node_failure() -> Dict[str, Any]:
            """Simulate a node failure."""
            # Έλεγχος αν υπάρχει ήδη προσομοίωση σε εξέλιξη
            if self.simulation_in_progress:
                return {
                    "success": False,
                    "message": "Another simulation is already in progress"
                }
                
            async with self.simulation_lock:
                self.simulation_in_progress = True
                try:
                    logger.info(f"Simulating node failure for node {self.node.node_id}")
                    # Αποσύνδεση προσωρινά από το δίκτυο
                    self.node.rpc.disable_network = True
                    # Επανασύνδεση μετά από καθυστέρηση
                    task = asyncio.create_task(self._reconnect_after_delay(5))
                    self.background_tasks.add(task)
                    task.add_done_callback(self.background_tasks.discard)
                    return {"success": True, "message": "Node network disabled temporarily"}
                finally:
                    # Απελευθέρωση του lock μετά από καθυστέρηση
                    asyncio.create_task(self._release_simulation_lock(5))
        
        @self.app.post("/simulation/network-partition")
        async def simulate_network_partition() -> Dict[str, Any]:
            """Simulate a network partition."""
            # Έλεγχος αν υπάρχει ήδη προσομοίωση σε εξέλιξη
            if self.simulation_in_progress:
                return {
                    "success": False,
                    "message": "Another simulation is already in progress"
                }
                
            async with self.simulation_lock:
                self.simulation_in_progress = True
                try:
                    if not self.node.peers:
                        return {"success": False, "message": "No peers available for partition"}
                    
                    # Αποσύνδεση από έναν τυχαίο peer
                    # Προτιμάμε σταθερή επιλογή αντί για τυχαία
                    peers_to_disconnect = [self.node.peers[0]] if self.node.peers else []
                    
                    if not peers_to_disconnect:
                        return {"success": False, "message": "No peers available for partition"}
                        
                    logger.info(f"Simulating network partition: disconnecting from {peers_to_disconnect}")
                    self.node.rpc.disconnect_peers(peers_to_disconnect)
                    
                    # Επανασύνδεση μετά από καθυστέρηση
                    task = asyncio.create_task(self._reconnect_all_peers_after_delay(10))
                    self.background_tasks.add(task)
                    task.add_done_callback(self.background_tasks.discard)
                    
                    return {"success": True, "message": f"Network partition simulated, disconnected from {peers_to_disconnect}"}
                finally:
                    # Απελευθέρωση του lock μετά από καθυστέρηση
                    asyncio.create_task(self._release_simulation_lock(10))
        
        @self.app.post("/simulation/force-election")
        async def force_election_timeout() -> Dict[str, Any]:
            """Force an election timeout."""
            # Έλεγχος αν υπάρχει ήδη προσομοίωση σε εξέλιξη
            if self.simulation_in_progress:
                return {
                    "success": False,
                    "message": "Another simulation is already in progress"
                }
                
            async with self.simulation_lock:
                self.simulation_in_progress = True
                try:
                    logger.info(f"Forcing election timeout for node {self.node.node_id}")
                    # Εξαναγκάστε τον κόμβο να ξεκινήσει εκλογή
                    await self.node.start_election()
                    return {"success": True, "message": "Election timeout forced"}
                finally:
                    # Απελευθέρωση του lock μετά από καθυστέρηση
                    asyncio.create_task(self._release_simulation_lock(5))
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time updates."""
            logger.info("New WebSocket connection")
            await self.websocket_manager.connect(websocket)
            
            # Send initial state
            state_data = self.node.cluster_state.to_dict()
            logger.debug(f"Sending initial state: {state_data}")
            await websocket.send_json({
                "type": "state",
                "data": state_data
            })
            
            # Send log entries
            entries = [
                {
                    "index": entry.index,
                    "term": entry.term,
                    "command": entry.command
                }
                for entry in self.node.log.entries
            ]
            logger.debug(f"Sending {len(entries)} initial log entries")
            await websocket.send_json({
                "type": "log",
                "data": {"entries": entries}
            })
            
            try:
                while True:
                    # Keep connection alive
                    await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                self.websocket_manager.disconnect(websocket)
        
        # Check multiple possible frontend directories
        frontend_dirs = ["frontend/out", "frontend/.next", "frontend/build"]
        frontend_dir = None
        
        for dir_path in frontend_dirs:
            if os.path.exists(dir_path):
                frontend_dir = dir_path
                logger.info(f"Found frontend files in {frontend_dir}")
                break
                
        if frontend_dir:
            logger.info(f"Mounting frontend static files from {frontend_dir}")
            self.app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
        else:
            logger.warning(f"No frontend directory found. Static file serving disabled.")
        
        logger.info("API routes set up successfully")
    
    async def _reconnect_after_delay(self, delay: int) -> None:
        """Re-enable network after a delay."""
        logger.info(f"Will reconnect node {self.node.node_id} to network after {delay} seconds")
        await asyncio.sleep(delay)
        self.node.rpc.disable_network = False
        logger.info(f"Node {self.node.node_id} network reconnected")
        await self.broadcast_update()
    
    async def _reconnect_all_peers_after_delay(self, delay: int) -> None:
        """Reconnect all peers after a delay."""
        logger.info(f"Will reconnect all peers for node {self.node.node_id} after {delay} seconds")
        await asyncio.sleep(delay)
        self.node.rpc.reconnect_all_peers()
        logger.info(f"All peers reconnected for node {self.node.node_id}")
        await self.broadcast_update()
    
    async def _release_simulation_lock(self, delay: int) -> None:
        """Release simulation lock after a delay."""
        await asyncio.sleep(delay)
        self.simulation_in_progress = False
        logger.info("Simulation lock released")
    
    async def broadcast_update(self) -> None:
        """Broadcast current state to all websocket clients."""
        # Send state update
        await self.websocket_manager.broadcast({
            "type": "state",
            "data": self.node.cluster_state.to_dict()
        })
        
        # Send log update
        entries = [
            {
                "index": entry.index,
                "term": entry.term,
                "command": entry.command
            }
            for entry in self.node.log.entries
        ]
        await self.websocket_manager.broadcast({
            "type": "log",
            "data": {"entries": entries}
        })
    
    async def start_periodic_updates(self) -> None:
        """Start periodic state updates to websocket clients."""
        logger.info("Starting periodic updates")
        while True:
            await self.broadcast_update()
            await asyncio.sleep(1)
    
    async def start(self) -> None:
        """Start the API server."""
        import uvicorn
        
        logger.info(f"Starting API server on port {self.port}")
        
        # Start periodic updates
        update_task = asyncio.create_task(self.start_periodic_updates())
        self.background_tasks.add(update_task)
        
        # Start the server
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()