"""
Main MCP Server application for Jupyter Collaboration.

This module implements the core MCP server that exposes Jupyter Collaboration's
real-time collaboration (RTC) functionalities to AI agents.
"""
import asyncio
import logging
from typing import AsyncIterator

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from jupyter_server.extension.application import ExtensionApp
from tornado.web import RequestHandler
from tornado import httputil

from .event_store import InMemoryEventStore
from .auth import authenticate_mcp_request
from .rtc_adapter import RTCAdapter
from .handlers import NotebookHandlers, DocumentHandlers, AwarenessHandlers

logger = logging.getLogger(__name__)


class MCPHandler(RequestHandler):
    """Tornado request handler for MCP requests."""
    
    SUPPORTED_METHODS = ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS')
    
    def initialize(self, mcp_server):
        self.mcp_server = mcp_server
    
    async def prepare(self):
        """Prepare the request handler."""
        # Authenticate the request
        try:
            user = await authenticate_mcp_request(self.request)
            # Add user to context for handlers
            self.request.user = user
        except Exception as e:
            logger.error(f"Error authenticating MCP request: {e}")
            self.set_status(401)
            self.finish("Unauthorized")
            return
    
    async def get(self):
        """Handle GET requests."""
        await self._handle_request()
    
    async def post(self):
        """Handle POST requests."""
        await self._handle_request()
    
    async def put(self):
        """Handle PUT requests."""
        await self._handle_request()
    
    async def delete(self):
        """Handle DELETE requests."""
        await self._handle_request()
    
    async def patch(self):
        """Handle PATCH requests."""
        await self._handle_request()
    
    async def head(self):
        """Handle HEAD requests."""
        await self._handle_request()
    
    async def options(self):
        """Handle OPTIONS requests."""
        await self._handle_request()
    
    async def _handle_request(self):
        """Handle the MCP request using the session manager."""
        try:
            # Create a scope for the ASGI application
            scope = {
                "type": "http",
                "method": self.request.method,
                "path": self.request.path,
                "query_string": self.request.query.encode(),
                "headers": [
                    (k.lower().encode(), v.encode())
                    for k, v in self.request.headers.get_all()
                ],
                "server": (self.request.host_name, self.request.port),
            }
            
            # Create receive and send functions
            async def receive():
                # Return the request body
                return {
                    "type": "http.request",
                    "body": self.request.body,
                    "more_body": False,
                }
            
            # Send the response back to Tornado
            async def send(message):
                if message["type"] == "http.response.start":
                    self.set_status(message["status"])
                    for name, value in message.get("headers", []):
                        name_str = name.decode()
                        value_str = value.decode()
                        if name_str.lower() == "content-type":
                            self.set_header(name_str, value_str)
                        else:
                            self.add_header(name_str, value_str)
                elif message["type"] == "http.response.body":
                    self.write(message.get("body", b""))
                    self.finish()
            
            # Process the request through the session manager
            await self.mcp_server.session_manager.handle_request(scope, receive, send)
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            self.set_status(500)
            self.finish("Internal server error")


class MCPServerExtension(ExtensionApp):
    """Jupyter Server Extension for MCP Server."""
    
    name = "jupyter_collaboration_mcp"
    app_name = "Jupyter Collaboration MCP"
    description = "MCP server for Jupyter Collaboration features"
    
    def initialize(self):
        """Initialize the extension."""
        super().initialize()
        self.mcp_server = MCPServer()
        self.log.info("Jupyter Collaboration MCP Server extension initialized")
    
    def initialize_handlers(self):
        """Initialize the handlers for the extension."""
        # Ensure mcp_server is initialized
        if not hasattr(self, 'mcp_server'):
            self.mcp_server = MCPServer()
        
        app = self.mcp_server.create_app()
        
        # Add the MCP server to the Jupyter server app using a Tornado handler
        self.serverapp.web_app.add_handlers('.*', [(r"/mcp/.*", MCPHandler, {'mcp_server': self.mcp_server})])
        
        # RTC adapter initialization will be deferred until first use
        
        self.log.info("Jupyter Collaboration MCP Server extension handlers initialized")


class MCPServer:
    """Main MCP Server for Jupyter Collaboration."""
    
    def __init__(self):
        """Initialize the MCP server."""
        self.server = Server("jupyter-collaboration-mcp")
        self.rtc_adapter = RTCAdapter()
        self.event_store = InMemoryEventStore()
        self.session_manager = None
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Register all MCP tools."""
        # Initialize handlers
        notebook_handlers = NotebookHandlers(self.server, self.rtc_adapter)
        document_handlers = DocumentHandlers(self.server, self.rtc_adapter)
        awareness_handlers = AwarenessHandlers(self.server, self.rtc_adapter)
    
    
    def create_app(self):
        """Create the Starlette application with MCP endpoints."""
        self.session_manager = StreamableHTTPSessionManager(
            app=self.server,
            event_store=self.event_store,
        )
        
        async def handle_mcp_request(scope, receive, send):
            """Handle MCP requests with authentication."""
            try:
                # Authenticate the request
                user = await authenticate_mcp_request(scope)
                # Add user to context for handlers
                scope["user"] = user
                
                # Process the request
                await self.session_manager.handle_request(scope, receive, send)
            except Exception as e:
                logger.error(f"Error handling MCP request: {e}")
                # Send error response
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"text/plain"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"Internal server error",
                })
        
        app = Starlette(
            routes=[
                Mount("/mcp", app=handle_mcp_request),
            ],
        )
        return app
    
    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all connected clients."""
        event_message = {
            "type": event_type,
            "data": data,
            "timestamp": anyio.current_time()
        }
        
        # Store the event
        await self.event_store.store_event(
            stream_id="broadcast",
            message=event_message
        )
        
        # Broadcast to all connected sessions
        if self.session_manager:
            await self.session_manager.broadcast_event(event_message)
    
    async def get_server_info(self) -> dict:
        """Get server information."""
        return {
            "name": "jupyter-collaboration-mcp",
            "version": "0.1.0",
            "description": "MCP server for Jupyter Collaboration features",
            "capabilities": {
                "notebooks": True,
                "documents": True,
                "awareness": True,
                "realtime": True
            }
        }