"""RPC mechanisms for Raft consensus."""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class RaftRPC:
    """RPC server and client for Raft consensus."""
    
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.server = None
        self.app = web.Application()
        self.session = None
        
        # Register RPC handlers
        self.vote_handler: Optional[Callable] = None
        self.append_entries_handler: Optional[Callable] = None
    
    async def start(self) -> None:
        """Start the RPC server."""
        # Set up routes
        self.app.add_routes([
            web.post('/raft/vote', self._handle_vote_request),
            web.post('/raft/append', self._handle_append_entries),
        ])
        
        # Create client session
        self.session = aiohttp.ClientSession()
        
        # Start server
        self.server = await asyncio.get_event_loop().create_server(
            self.app.make_handler(), self.host, self.port
        )
        
        logger.info(f"RPC server started on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the RPC server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        if self.session:
            await self.session.close()
        
        logger.info("RPC server stopped")
    
    def register_vote_handler(self, handler: Callable) -> None:
        """Register a handler for vote requests."""
        self.vote_handler = handler
    
    def register_append_entries_handler(self, handler: Callable) -> None:
        """Register a handler for append entries requests."""
        self.append_entries_handler = handler
    
    async def _handle_vote_request(self, request: web.Request) -> web.Response:
        """Handle incoming vote requests."""
        if not self.vote_handler:
            return web.Response(status=501, text="Not implemented")
        
        try:
            data = await request.json()
            result = await self.vote_handler(data)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Error handling vote request: {e}")
            return web.Response(status=500, text=str(e))
    
    async def _handle_append_entries(self, request: web.Request) -> web.Response:
        """Handle incoming append entries requests."""
        if not self.append_entries_handler:
            return web.Response(status=501, text="Not implemented")
        
        try:
            data = await request.json()
            result = await self.append_entries_handler(data)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Error handling append entries: {e}")
            return web.Response(status=500, text=str(e))
    
    async def request_vote(self, node_address: str, term: int, 
                          candidate_id: str, last_log_index: int, 
                          last_log_term: int) -> Dict[str, Any]:
        """Send a RequestVote RPC to a node."""
        url = f"http://{node_address}/raft/vote"
        data = {
            "term": term,
            "candidate_id": candidate_id,
            "last_log_index": last_log_index,
            "last_log_term": last_log_term,
        }
        
        try:
            async with self.session.post(url, json=data, timeout=0.5) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"Failed to request vote from {node_address}: {resp.status}")
                    return {"term": term, "vote_granted": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout requesting vote from {node_address}")
            return {"term": term, "vote_granted": False}
        except Exception as e:
            logger.error(f"Error requesting vote from {node_address}: {e}")
            return {"term": term, "vote_granted": False}
    
    async def append_entries(self, node_address: str, term: int, 
                            leader_id: str, prev_log_index: int,
                            prev_log_term: int, entries: List[Dict[str, Any]],
                            leader_commit: int) -> Dict[str, Any]:
        """Send an AppendEntries RPC to a node."""
        url = f"http://{node_address}/raft/append"
        data = {
            "term": term,
            "leader_id": leader_id,
            "prev_log_index": prev_log_index,
            "prev_log_term": prev_log_term,
            "entries": entries,
            "leader_commit": leader_commit,
        }
        
        try:
            async with self.session.post(url, json=data, timeout=0.5) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"Failed to append entries to {node_address}: {resp.status}")
                    return {"term": term, "success": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout appending entries to {node_address}")
            return {"term": term, "success": False}
        except Exception as e:
            logger.error(f"Error appending entries to {node_address}: {e}")
            return {"term": term, "success": False}