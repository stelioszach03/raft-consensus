"""RPC mechanisms for Raft consensus."""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable, Set

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
        
        # Προσθήκα για τις προσομοιώσεις
        self.disable_network = False
        self.disconnected_peers: Set[str] = set()
        
        # Register RPC handlers
        self.vote_handler: Optional[Callable] = None
        self.append_entries_handler: Optional[Callable] = None
        
        # Αποθήκευση των χρόνων τελευταίας επικοινωνίας με κάθε peer
        self.last_communication: Dict[str, float] = {}
        
        # Αποτυχίες επικοινωνίας
        self.communication_failures: Dict[str, int] = {}
        self.max_failures = 5  # Μέγιστος αριθμός αποτυχιών πριν θεωρήσουμε τον peer αποσυνδεδεμένο
    
    async def start(self) -> None:
        """Start the RPC server."""
        # Set up routes
        self.app.add_routes([
            web.post('/raft/vote', self._handle_vote_request),
            web.post('/raft/append', self._handle_append_entries),
        ])
        
        # Create client session with longer timeout
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0))
        
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
    
    def disconnect_peers(self, peers: List[str]) -> None:
        """Disconnect from specific peers."""
        for peer in peers:
            self.disconnected_peers.add(peer)
        logger.info(f"Disconnected from peers: {peers}")
    
    def reconnect_all_peers(self) -> None:
        """Reconnect to all peers."""
        self.disconnected_peers.clear()
        self.disable_network = False  # Make sure network is enabled
        self.communication_failures.clear()  # Reset failure counts
        logger.info("Reconnected to all peers")
    
    async def request_vote(self, node_address: str, term: int, 
                          candidate_id: str, last_log_index: int, 
                          last_log_term: int) -> Dict[str, Any]:
        """Send a RequestVote RPC to a node."""
        # Έλεγχος κατάστασης δικτύου για προσομοιώσεις
        if self.disable_network:
            logger.info(f"Network disabled, vote request to {node_address} failed")
            return {"term": term, "vote_granted": False}
            
        if node_address in self.disconnected_peers:
            logger.info(f"Peer {node_address} disconnected, vote request failed")
            return {"term": term, "vote_granted": False}
            
        url = f"http://{node_address}/raft/vote"
        data = {
            "term": term,
            "candidate_id": candidate_id,
            "last_log_index": last_log_index,
            "last_log_term": last_log_term,
        }
        
        try:
            # Χρήση μεγαλύτερου timeout
            async with self.session.post(url, json=data, timeout=1.0) as resp:
                if resp.status == 200:
                    response_data = await resp.json()
                    # Ενημέρωση του χρόνου τελευταίας επικοινωνίας
                    self.last_communication[node_address] = asyncio.get_event_loop().time()
                    # Μηδενισμός μετρητή αποτυχιών
                    self.communication_failures[node_address] = 0
                    return response_data
                else:
                    logger.warning(f"Failed to request vote from {node_address}: {resp.status}")
                    self._record_communication_failure(node_address)
                    return {"term": term, "vote_granted": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout requesting vote from {node_address}")
            self._record_communication_failure(node_address)
            return {"term": term, "vote_granted": False}
        except Exception as e:
            logger.error(f"Error requesting vote from {node_address}: {e}")
            self._record_communication_failure(node_address)
            return {"term": term, "vote_granted": False}
    
    async def append_entries(self, node_address: str, term: int, 
                            leader_id: str, prev_log_index: int,
                            prev_log_term: int, entries: List[Dict[str, Any]],
                            leader_commit: int) -> Dict[str, Any]:
        """Send an AppendEntries RPC to a node."""
        # Έλεγχος κατάστασης δικτύου για προσομοιώσεις
        if self.disable_network:
            logger.info(f"Network disabled, append entries to {node_address} failed")
            return {"term": term, "success": False}
            
        if node_address in self.disconnected_peers:
            logger.info(f"Peer {node_address} disconnected, append entries failed")
            return {"term": term, "success": False}
            
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
            # Χρήση μεγαλύτερου timeout
            async with self.session.post(url, json=data, timeout=1.0) as resp:
                if resp.status == 200:
                    response_data = await resp.json()
                    # Ενημέρωση του χρόνου τελευταίας επικοινωνίας
                    self.last_communication[node_address] = asyncio.get_event_loop().time()
                    # Μηδενισμός μετρητή αποτυχιών
                    self.communication_failures[node_address] = 0
                    return response_data
                else:
                    logger.warning(f"Failed to append entries to {node_address}: {resp.status}")
                    self._record_communication_failure(node_address)
                    return {"term": term, "success": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout appending entries to {node_address}")
            self._record_communication_failure(node_address)
            return {"term": term, "success": False}
        except Exception as e:
            logger.error(f"Error appending entries to {node_address}: {e}")
            self._record_communication_failure(node_address)
            return {"term": term, "success": False}
    
    def _record_communication_failure(self, node_address: str) -> None:
        """Record a communication failure with a peer."""
        count = self.communication_failures.get(node_address, 0) + 1
        self.communication_failures[node_address] = count
        
        if count >= self.max_failures:
            logger.warning(f"Peer {node_address} has failed {count} times, treating as disconnected")