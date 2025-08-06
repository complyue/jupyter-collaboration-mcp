"""
Main MCP Server application for Jupyter Collaboration.

This module implements the core MCP server that exposes Jupyter Collaboration's
real-time collaboration (RTC) functionalities to AI agents.
"""

import json
import logging
import sys
from typing import Any, Dict, Optional

import mcp.types as types
from jupyter_server.extension.application import ExtensionApp
from mcp.server.lowlevel import Server
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

from .auth import authenticate_mcp_request, configure_auth_with_token
from .handlers import AwarenessHandlers, DocumentHandlers, NotebookHandlers
from .rtc_adapter import RTCAdapter
from .tornado_event_store import TornadoEventStore
from .tornado_session_manager import TornadoSessionManager

logger = logging.getLogger(__name__)


class MCPHandler(RequestHandler):
    """Tornado request handler for MCP requests."""

    SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")

    def initialize(self, session_manager: TornadoSessionManager, serverapp: Optional[Any] = None):
        """Initialize the handler with required dependencies."""
        self.session_manager = session_manager
        self.serverapp = serverapp

    def check_xsrf_cookie(self):
        # Skip XSRF check for MCP endpoints
        return

    def xsrf_token(self):
        # Override xsrf_token to disable CSRF token generation.
        return None

    def set_default_headers(self):
        """Set default headers for all responses."""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    async def prepare(self):
        """Prepare the request handler."""
        # Authenticate the request
        try:
            # Convert Tornado request to ASGI scope-like structure for authentication
            scope = {
                "headers": [
                    (k.lower().encode(), v.encode()) for k, v in self.request.headers.get_all()
                ],
                "method": self.request.method,
                "path": self.request.path,
            }
            user = await authenticate_mcp_request(scope)
            # Add user to context for handlers
            self.request.user = user
        except Exception as e:
            logger.error(f"Error authenticating MCP request: {e}", exc_info=True)
            self.set_status(401)
            self.finish("Unauthorized")
            return

    async def get(self, path: str = ""):
        """Handle GET requests for SSE streams."""
        try:
            # Print debug info to stderr
            print(f"DEBUG: Received MCP GET request: {self.request.method} {self.request.path}", file=sys.stderr)
            print(f"DEBUG: Request headers:", file=sys.stderr)
            for name, value in self.request.headers.get_all():
                print(f"DEBUG:   {name}: {value}", file=sys.stderr)
            
            # Handle the request with the session manager
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP GET request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    async def post(self, path: str = ""):
        """Handle POST requests containing MCP messages."""
        try:
            # Print debug info to stderr
            print(f"DEBUG: Received MCP POST request: {self.request.method} {self.request.path}", file=sys.stderr)
            print(f"DEBUG: Request headers:", file=sys.stderr)
            for name, value in self.request.headers.get_all():
                print(f"DEBUG:   {name}: {value}", file=sys.stderr)
            print(f"DEBUG: Request body: {self.request.body}", file=sys.stderr)
            
            # Handle the request with the session manager
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP POST request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    async def put(self, path: str = ""):
        """Handle PUT requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP PUT request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    async def delete(self, path: str = ""):
        """Handle DELETE requests for session termination."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP DELETE request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    async def patch(self, path: str = ""):
        """Handle PATCH requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP PATCH request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    async def head(self, path: str = ""):
        """Handle HEAD requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP HEAD request: {e}", exc_info=True)
            self.set_status(500)
            self.finish("Internal server error")

    def options(self, *args, **kwargs):
        """Handle OPTIONS requests for CORS preflight."""
        self.set_status(204)
        self.finish()


class MCPServerExtension(ExtensionApp):
    """Jupyter Server Extension for MCP Server."""

    name = "jupyter_collaboration_mcp"
    app_name = "Jupyter Collaboration MCP"
    description = "MCP server for Jupyter Collaboration features"

    def initialize(self):
        """Initialize the extension."""
        super().initialize()
        
        # Configure authentication with token from Jupyter's command line
        token = getattr(self.serverapp.identity_provider, "token", None)
        if token:
            configure_auth_with_token(token)
            self.log.info(f"Configured authentication with token from command line")
        else:
            self.log.warning("No token found in Jupyter configuration, using default authentication")
            
        self.mcp_server = MCPServer()
        
        self.log.info("Jupyter Collaboration MCP Server extension initialized")
    
    def stop_extension(self):
        """Stop the extension and clean up resources."""
        if hasattr(self, 'mcp_server'):
            self.log.info("Stopping MCP server")
            # Clean up sessions
            IOLoop.current().add_callback(self._cleanup_sessions)
    
    async def _cleanup_sessions(self):
        """Clean up all active sessions."""
        try:
            if hasattr(self.mcp_server, 'session_manager'):
                # End all active sessions
                for session_id in list(self.mcp_server.session_manager._sessions.keys()):
                    await self.mcp_server.session_manager.end_session(session_id)
                self.log.info("All sessions cleaned up")
        except Exception as e:
            self.log.error(f"Error cleaning up sessions: {e}", exc_info=True)

    def initialize_handlers(self):
        """Initialize the handlers for the extension."""
        # Ensure mcp_server is initialized
        if not hasattr(self, "mcp_server"):
            self.mcp_server = MCPServer()

        # Initialize the RTC adapter with the server app
        if not self.mcp_server.rtc_adapter._initialized:
            print(f"DEBUG: Initializing RTC adapter with server app", file=sys.stderr)
            IOLoop.current().add_callback(self.mcp_server.rtc_adapter.initialize, self.serverapp)

        # Add the MCP server to the Jupyter server app using a Tornado handler
        self.serverapp.web_app.add_handlers(
            ".*", [(r"/mcp.*", MCPHandler, {"session_manager": self.mcp_server.session_manager, "serverapp": self.serverapp})]
        )

        self.log.info("Jupyter Collaboration MCP Server extension handlers initialized")


class MCPServer:
    """Main MCP Server for Jupyter Collaboration."""

    def __init__(self):
        """Initialize the MCP server."""
        self.server = Server("jupyter-collaboration-mcp")
        self.rtc_adapter = RTCAdapter()
        self.event_store = TornadoEventStore()
        # Set up handlers first to populate tool_handlers
        self._setup_handlers()
        
        # Create a single session manager for the entire application
        self.session_manager = TornadoSessionManager(
            mcp_server=self,  # Pass self (MCPServer) instead of self.server (MCP Server)
            event_store=self.event_store,
        )

    def _setup_handlers(self):
        """Register all MCP tools."""
        # Initialize handlers and store them as instance variables
        print(f"DEBUG: Setting up handlers, rtc_adapter initialized: {self.rtc_adapter._initialized}", file=sys.stderr)
        self.notebook_handlers = NotebookHandlers(self.server, self.rtc_adapter)
        self.document_handlers = DocumentHandlers(self.server, self.rtc_adapter)
        self.awareness_handlers = AwarenessHandlers(self.server, self.rtc_adapter)
        
        # Collect all tool handlers for direct access
        self.tool_handlers = {}
        self.tool_handlers.update(self.notebook_handlers.tool_handlers)
        self.tool_handlers.update(self.document_handlers.tool_handlers)
        self.tool_handlers.update(self.awareness_handlers.tool_handlers)
        print(f"DEBUG: Tool handlers set up: {list(self.tool_handlers.keys())}", file=sys.stderr)

    def create_app(self):
        """Create a simple Tornado application with MCP endpoints."""
        # This method is kept for compatibility but is not used in the Tornado-native implementation
        # The actual handling is done by the MCPHandler class
        return None

    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all connected clients."""
        event_message = {"type": event_type, "data": data, "timestamp": IOLoop.current().time()}

        # Store the event
        await self.event_store.store_event(stream_id="broadcast", message=event_message)

        # Broadcast to all active sessions
        await self.session_manager.broadcast_event(event_type, data)
        
        logger.info(f"Broadcast event sent: {event_type}")

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
                "realtime": True,
            },
        }