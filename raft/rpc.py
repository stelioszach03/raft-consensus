"""RPC mechanisms for Raft consensus."""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Callable, Set

import aiohttp
from aiohttp import web
from aiohttp.resolver import AsyncResolver
from aiohttp import TCPConnector

logger = logging.getLogger(__name__)


class RaftRPC:
    """RPC server and client for Raft consensus."""
    
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.server = None
        self.site = None
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
            # Προσθήκη απλού endpoint για έλεγχο συνδεσιμότητας
            web.get('/status', self._handle_status_request),
        ])
        
        # Create client session with better DNS resolution and longer timeout
        # Χρήση AsyncResolver για καλύτερο DNS resolution και αποφυγή του CancelledError
        resolver = AsyncResolver()
        connector = TCPConnector(
            resolver=resolver,
            family=0,  # Επιτρέπει IPv4 και IPv6
            ssl=False,
            use_dns_cache=True,
            ttl_dns_cache=300,  # Cache DNS entries for 5 minutes
            limit=100  # Αύξηση του ορίου ταυτόχρονων συνδέσεων
        )
        
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10.0, connect=5.0),
            connector=connector
        )
        
        # Start server με τη σωστή μέθοδο της aiohttp
        runner = web.AppRunner(self.app)
        await runner.setup()
        self.site = web.TCPSite(runner, self.host, self.port)
        await self.site.start()
        
        logger.info(f"RPC server started on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the RPC server."""
        if self.site:
            await self.site.stop()
        
        if self.session:
            await self.session.close()
        
        logger.info("RPC server stopped")
    
    async def _handle_status_request(self, request: web.Request) -> web.Response:
        """Handle status check requests."""
        return web.json_response({
            "status": "ok", 
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port
        })
    
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
            logger.debug(f"Node {self.node_id} received vote request: {data}")
            
            result = await self.vote_handler(data)
            logger.debug(f"Node {self.node_id} vote response: {result}")
            
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Error handling vote request: {e}", exc_info=True)
            return web.Response(status=500, text=str(e))
    
    async def _handle_append_entries(self, request: web.Request) -> web.Response:
        """Handle incoming append entries requests."""
        if not self.append_entries_handler:
            return web.Response(status=501, text="Not implemented")
        
        try:
            data = await request.json()
            # Καταγραφή λιγότερων πληροφοριών για τα heartbeats
            if not data.get("entries"):
                logger.debug(f"Node {self.node_id} received heartbeat from {data.get('leader_id')}")
            else:
                logger.debug(f"Node {self.node_id} received append entries: {len(data.get('entries', []))} entries")
            
            result = await self.append_entries_handler(data)
            
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Error handling append entries: {e}", exc_info=True)
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
        
        # Χρήση σωστής μορφής URL - δοκιμή πολλαπλών hostnames
        if not node_address.startswith("http://"):
            url = f"http://{node_address}/raft/vote"
        else:
            url = f"{node_address}/raft/vote"
            
        logger.info(f"Sending vote request to {url} for term {term}")
            
        data = {
            "term": term,
            "candidate_id": candidate_id,
            "last_log_index": last_log_index,
            "last_log_term": last_log_term,
        }
        
        # Δοκιμή με διαφορετικούς hostnames αν αποτύχει
        for hostname_variant in self._get_hostname_variants(node_address):
            if hostname_variant != node_address:
                alt_url = f"http://{hostname_variant}/raft/vote"
                logger.debug(f"Will try alternative hostname {alt_url} if primary fails")
        
        try:
            # Προστασία του αιτήματος από ακύρωση με asyncio.shield
            # και αύξηση του timeout
            async with self.session.post(url, json=data, timeout=10.0) as resp:
                if resp.status == 200:
                    response_data = await resp.json()
                    # Ενημέρωση του χρόνου τελευταίας επικοινωνίας
                    self.last_communication[node_address] = asyncio.get_event_loop().time()
                    # Μηδενισμός μετρητή αποτυχιών
                    self.communication_failures[node_address] = 0
                    logger.info(f"Vote response from {node_address}: {response_data}")
                    return response_data
                else:
                    response_text = await resp.text()
                    logger.warning(f"Failed to request vote from {node_address}: {resp.status} - {response_text}")
                    self._record_communication_failure(node_address)
                    return {"term": term, "vote_granted": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout requesting vote from {node_address}")
            
            # Δοκιμή εναλλακτικών hostname αν υπάρχουν
            for hostname_variant in self._get_hostname_variants(node_address):
                if hostname_variant == node_address:
                    continue
                    
                alt_url = f"http://{hostname_variant}/raft/vote"
                logger.info(f"Trying alternative hostname {alt_url}")
                
                try:
                    async with self.session.post(alt_url, json=data, timeout=10.0) as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            logger.info(f"Vote response from alternative {hostname_variant}: {response_data}")
                            return response_data
                except Exception:
                    pass
            
            self._record_communication_failure(node_address)
            return {"term": term, "vote_granted": False}
        except Exception as e:
            logger.error(f"Error requesting vote from {node_address}: {e}", exc_info=True)
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
            
        # Χρήση σωστής μορφής URL
        if not node_address.startswith("http://"):
            url = f"http://{node_address}/raft/append"
        else:
            url = f"{node_address}/raft/append"
            
        # Καταγραφή πιο περιορισμένων πληροφοριών για τα heartbeats
        if not entries:
            logger.debug(f"Sending heartbeat to {node_address}")
        else:
            logger.info(f"Sending {len(entries)} entries to {node_address}")
        
        data = {
            "term": term,
            "leader_id": leader_id,
            "prev_log_index": prev_log_index,
            "prev_log_term": prev_log_term,
            "entries": entries,
            "leader_commit": leader_commit,
        }
        
        # Δοκιμή με διαφορετικούς hostnames αν αποτύχει
        for hostname_variant in self._get_hostname_variants(node_address):
            if hostname_variant != node_address:
                alt_url = f"http://{hostname_variant}/raft/append"
                logger.debug(f"Will try alternative hostname {alt_url} if primary fails")
        
        try:
            # Προστασία του αιτήματος από ακύρωση με asyncio.shield
            # και αύξηση του timeout
            request_task = self.session.post(url, json=data, timeout=10.0)
            shielded_task = asyncio.shield(request_task)
            
            async with await shielded_task as resp:
                if resp.status == 200:
                    response_data = await resp.json()
                    # Ενημέρωση του χρόνου τελευταίας επικοινωνίας
                    self.last_communication[node_address] = asyncio.get_event_loop().time()
                    # Μηδενισμός μετρητή αποτυχιών
                    self.communication_failures[node_address] = 0
                    return response_data
                else:
                    response_text = await resp.text()
                    logger.warning(f"Failed to append entries to {node_address}: {resp.status} - {response_text}")
                    self._record_communication_failure(node_address)
                    return {"term": term, "success": False}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout appending entries to {node_address}")
            
            # Δοκιμή εναλλακτικών hostname αν υπάρχουν
            for hostname_variant in self._get_hostname_variants(node_address):
                if hostname_variant == node_address:
                    continue
                    
                alt_url = f"http://{hostname_variant}/raft/append"
                logger.info(f"Trying alternative hostname {alt_url}")
                
                try:
                    async with self.session.post(alt_url, json=data, timeout=10.0) as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            logger.info(f"Append response from alternative {hostname_variant}: {response_data}")
                            return response_data
                except Exception:
                    pass
            
            self._record_communication_failure(node_address)
            return {"term": term, "success": False}
        except Exception as e:
            logger.error(f"Error appending entries to {node_address}: {e}", exc_info=True)
            self._record_communication_failure(node_address)
            return {"term": term, "success": False}
    
    def _get_hostname_variants(self, node_address: str) -> List[str]:
        """
        Δημιουργεί παραλλαγές hostname για δοκιμή εναλλακτικών ονομάτων.
        Για παράδειγμα, για node0:7000 δοκιμάζει επίσης raft-node0:7000.
        """
        variants = [node_address]
        
        # Εξαγωγή του hostname και του port
        if ':' in node_address:
            hostname, port = node_address.split(':', 1)
            
            # Δοκιμή με προθέματα/ονόματα container
            if hostname.startswith('node'):
                node_num = hostname[4:]
                variants.append(f"raft-{hostname}:{port}")
            elif hostname.startswith('raft-node'):
                node_num = hostname[9:]
                variants.append(f"node{node_num}:{port}")
        
        return variants
    
    def _record_communication_failure(self, node_address: str) -> None:
        """Record a communication failure with a peer."""
        count = self.communication_failures.get(node_address, 0) + 1
        self.communication_failures[node_address] = count
        
        if count >= self.max_failures:
            logger.warning(f"Peer {node_address} has failed {count} times, treating as disconnected")