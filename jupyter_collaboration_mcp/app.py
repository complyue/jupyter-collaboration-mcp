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
from mcp.server import FastMCP
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

from .auth import authenticate_mcp_request, configure_auth_with_token
from .rtc_adapter import RTCAdapter
from .tools import define_awareness_tools, define_document_tools, define_notebook_tools
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
            # Handle the request with the session manager
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP GET request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

    async def post(self, path: str = ""):
        """Handle POST requests containing MCP messages."""
        try:
            # Handle the request with the session manager
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP POST request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

    async def put(self, path: str = ""):
        """Handle PUT requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP PUT request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

    async def delete(self, path: str = ""):
        """Handle DELETE requests for session termination."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP DELETE request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

    async def patch(self, path: str = ""):
        """Handle PATCH requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP PATCH request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

    async def head(self, path: str = ""):
        """Handle HEAD requests."""
        try:
            await self.session_manager.handle_request(self)
        except Exception as e:
            logger.error(f"Error handling MCP HEAD request: {e}", exc_info=True)
            self.set_status(500)
            self.finish(f"Internal server error: {e}")

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
            self.log.warning(
                "No token found in Jupyter configuration, using default authentication"
            )

        self.log.info("Jupyter Collaboration MCP Server extension initialized")

    def stop_extension(self):
        """Stop the extension and clean up resources."""
        if hasattr(self, "fastmcp"):
            self.log.info("Stopping MCP server")
            # Clean up sessions
            IOLoop.current().add_callback(self._cleanup_sessions)

    async def _cleanup_sessions(self):
        """Clean up all active sessions."""
        try:
            if hasattr(self, "session_manager"):
                for session_id in list(self.session_manager._sessions.keys()):
                    await self.session_manager.end_session(session_id)
                self.log.info("All sessions cleaned up")
        except Exception as e:
            self.log.error(f"Error cleaning up sessions: {e}", exc_info=True)

    def initialize_handlers(self):
        """Initialize the handlers for the extension."""

        event_store = TornadoEventStore()

        rtc_adapter = RTCAdapter()
        logger.info(f"DEBUG: Initializing RTC adapter with server app")
        IOLoop.current().add_callback(rtc_adapter.initialize, self.serverapp)

        fastmcp = FastMCP("jupyter-collaboration-mcp")

        define_notebook_tools(fastmcp, rtc_adapter)
        define_document_tools(fastmcp, rtc_adapter)
        define_awareness_tools(fastmcp, rtc_adapter)

        session_manager = TornadoSessionManager(fastmcp, event_store)

        # Add the MCP server to the Jupyter server app using a Tornado handler
        self.serverapp.web_app.add_handlers(
            ".*",
            [
                (
                    r"/mcp.*",
                    MCPHandler,
                    {
                        "session_manager": session_manager,
                        "serverapp": self.serverapp,
                    },
                )
            ],
        )

        self.session_manager = session_manager

        self.log.info("Jupyter Collaboration MCP Server extension handlers initialized")
