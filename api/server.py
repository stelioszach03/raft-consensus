"""API server for the Raft cluster UI."""
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")


class RaftAPI:
    """API server for the Raft cluster UI."""
    
    def __init__(self, node: RaftNode, port: int):
        self.node = node
        self.port = port
        self.app = FastAPI(title="Raft Consensus API")
        self.websocket_manager = WebSocketManager()
        
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
        
        # ΠΡΟΒΛΗΜΑ: Το frontend/build δεν υπάρχει, οπότε σχολιάζουμε αυτή τη γραμμή
        # self.app.mount("/", StaticFiles(directory="frontend/build", html=True), name="frontend")
        
        logger.info("API routes set up successfully")
    
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