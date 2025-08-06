"""
Main MCP Server application for Jupyter Collaboration.

This module implements the core MCP server that exposes Jupyter Collaboration's
real-time collaboration (RTC) functionalities to AI agents.
"""

import asyncio
import contextlib
import logging
import sys
from typing import AsyncIterator

import anyio
import mcp.types as types
from jupyter_server.extension.application import ExtensionApp
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from tornado import httputil
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

from .auth import authenticate_mcp_request, configure_auth_with_token
from .event_store import InMemoryEventStore
from .handlers import AwarenessHandlers, DocumentHandlers, NotebookHandlers
from .rtc_adapter import RTCAdapter

logger = logging.getLogger(__name__)


class MCPHandler(RequestHandler):
    """Tornado request handler for MCP requests."""

    SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")

    def initialize(self, mcp_server):
        self.mcp_server = mcp_server


    def check_xsrf_cookie(self):
        # Skip XSRF check for MCP endpoints
        return

    def xsrf_token(self):
        # Override xsrf_token to disable CSRF token generation.
        return None

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
            # Print debug info to stderr
            print(f"DEBUG: Received MCP request: {self.request.method} {self.request.path}", file=sys.stderr)
            print(f"DEBUG: Request headers:", file=sys.stderr)
            for name, value in self.request.headers.get_all():
                print(f"DEBUG:   {name}: {value}", file=sys.stderr)
            print(f"DEBUG: Request body: {self.request.body}", file=sys.stderr)
            
            # Create a scope for the ASGI application
            scope = {
                "type": "http",
                "method": self.request.method,
                "path": self.request.path,
                "query_string": self.request.query.encode(),
                "headers": [
                    (k.lower().encode(), v.encode()) for k, v in self.request.headers.get_all()
                ],
                "server": self.request.host,
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
                print(f"DEBUG: Sending response: {message}", file=sys.stderr)
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

            # Initialize the session manager for this request if needed
            if not self.mcp_server._session_manager_started:
                print("DEBUG: Starting session manager for the first request", file=sys.stderr)
                # Start the session manager context and keep it running
                self.mcp_server._session_manager_context = self.mcp_server.session_manager.run()
                await self.mcp_server._session_manager_context.__aenter__()
                self.mcp_server._session_manager_started = True

            # Process the request through the session manager
            await self.mcp_server.session_manager.handle_request(scope, receive, send)
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}", exc_info=True)
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
        
        # Configure authentication with token from Jupyter's command line
        token = getattr(self.serverapp.identity_provider, "token", None)
        if token:
            configure_auth_with_token(token)
            self.log.info(f"Configured authentication with token from command line")
        else:
            self.log.warning("No token found in Jupyter configuration, using default authentication")
            
        self.mcp_server = MCPServer()
        
        # Start the session manager using Tornado's IOLoop
        IOLoop.current().add_callback(self._start_session_manager)
        
        self.log.info("Jupyter Collaboration MCP Server extension initialized")
    
    async def _start_session_manager(self):
        """Start the session manager and keep it running."""
        try:
            async with self.mcp_server.session_manager.run():
                self.log.info("Session manager started successfully")
                # Keep the session manager running indefinitely
                while True:
                    await asyncio.sleep(3600)  # Sleep for an hour
        except Exception as e:
            self.log.error(f"Error in session manager: {e}", exc_info=True)
    
    def stop_extension(self):
        """Stop the extension and clean up resources."""
        if hasattr(self, 'mcp_server') and self.mcp_server._session_manager_started:
            self.log.info("Stopping session manager")
            # Properly exit the context manager
            if hasattr(self.mcp_server, '_session_manager_context'):
                IOLoop.current().add_callback(self._stop_session_manager)
    
    async def _stop_session_manager(self):
        """Stop the session manager and clean up resources."""
        try:
            if hasattr(self.mcp_server, '_session_manager_context'):
                await self.mcp_server._session_manager_context.__aexit__(None, None, None)
                self.mcp_server._session_manager_started = False
                self.log.info("Session manager stopped successfully")
        except Exception as e:
            self.log.error(f"Error stopping session manager: {e}", exc_info=True)

    def initialize_handlers(self):
        """Initialize the handlers for the extension."""
        # Ensure mcp_server is initialized
        if not hasattr(self, "mcp_server"):
            self.mcp_server = MCPServer()

        # Create the app
        app = self.mcp_server.create_app()

        # Add the MCP server to the Jupyter server app using a Tornado handler
        self.serverapp.web_app.add_handlers(
            ".*", [(r"/mcp.*", MCPHandler, {"mcp_server": self.mcp_server})]
        )

        # RTC adapter initialization will be deferred until first use

        self.log.info("Jupyter Collaboration MCP Server extension handlers initialized")


class MCPServer:
    """Main MCP Server for Jupyter Collaboration."""

    def __init__(self):
        """Initialize the MCP server."""
        self.server = Server("jupyter-collaboration-mcp")
        self.rtc_adapter = RTCAdapter()
        self.event_store = InMemoryEventStore()
        # Create a single session manager for the entire application
        self.session_manager = StreamableHTTPSessionManager(
            app=self.server,
            event_store=self.event_store,
        )
        self._session_manager_started = False
        self._setup_handlers()

    def _setup_handlers(self):
        """Register all MCP tools."""
        # Initialize handlers and store them as instance variables
        self.notebook_handlers = NotebookHandlers(self.server, self.rtc_adapter)
        self.document_handlers = DocumentHandlers(self.server, self.rtc_adapter)
        self.awareness_handlers = AwarenessHandlers(self.server, self.rtc_adapter)

    def create_app(self):
        """Create the Starlette application with MCP endpoints."""

        async def handle_mcp_request(scope, receive, send):
            """Handle MCP requests with authentication."""
            try:
                # Authenticate the request
                user = await authenticate_mcp_request(scope)
                # Add user to context for handlers
                scope["user"] = user

                # Initialize the session manager for this request if needed
                if not self._session_manager_started:
                    logger.info("Starting session manager for the first request (Starlette)")
                    # Start the session manager context and keep it running
                    self._session_manager_context = self.session_manager.run()
                    await self._session_manager_context.__aenter__()
                    self._session_manager_started = True

                # Process the request with the shared session manager
                await self.session_manager.handle_request(scope, receive, send)
            except Exception as e:
                logger.error(f"Error handling MCP request: {e}", exc_info=True)
                # Send error response
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [[b"content-type", b"text/plain"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Internal server error",
                    }
                )

        app = Starlette(
            routes=[
                Mount("/mcp", app=handle_mcp_request),
            ],
        )
        return app

    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast an event to all connected clients."""
        event_message = {"type": event_type, "data": data, "timestamp": anyio.current_time()}

        # Store the event
        await self.event_store.store_event(stream_id="broadcast", message=event_message)

        # Note: With a shared session manager, broadcasting is now possible
        # This functionality can be implemented in the future if needed
        logger.info(f"Broadcast event stored: {event_type}")

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
