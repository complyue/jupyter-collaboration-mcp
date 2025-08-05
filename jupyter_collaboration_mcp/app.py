"""
Main MCP Server application for Jupyter Collaboration.

This module implements the core MCP server that exposes Jupyter Collaboration's
real-time collaboration (RTC) functionalities to AI agents.
"""

import logging
from typing import AsyncIterator

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount

from .event_store import InMemoryEventStore
from .auth import authenticate_mcp_request
from .rtc_adapter import RTCAdapter
from .handlers import NotebookHandlers, DocumentHandlers, AwarenessHandlers

logger = logging.getLogger(__name__)


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
        """Register all MCP tools and resources."""
        # Initialize handlers
        notebook_handlers = NotebookHandlers(self.server, self.rtc_adapter)
        document_handlers = DocumentHandlers(self.server, self.rtc_adapter)
        awareness_handlers = AwarenessHandlers(self.server, self.rtc_adapter)
        
        # Register resources
        self._register_resources()
    
    def _register_resources(self):
        """Register all MCP resources."""
        
        @self.server.list_resources()
        async def handle_list_resources() -> list[types.Resource]:
            """List available collaboration resources."""
            return [
                types.Resource(
                    uri="collaboration://notebooks",
                    name="Jupyter Notebooks",
                    description="Collaborative Jupyter notebooks",
                    mimeType="application/json"
                ),
                types.Resource(
                    uri="collaboration://documents",
                    name="Shared Documents",
                    description="Collaborative documents",
                    mimeType="application/json"
                ),
                types.Resource(
                    uri="collaboration://awareness",
                    name="User Awareness",
                    description="User presence and activity information",
                    mimeType="application/json"
                ),
            ]
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> types.ReadResourceResult:
            """Read a collaboration resource."""
            if uri.startswith("collaboration://notebooks/"):
                # Handle notebook resources
                path = uri.replace("collaboration://notebooks/", "")
                content = await self.rtc_adapter.get_notebook_content(path)
                return types.ReadResourceResult(
                    contents=[
                        types.TextResourceContents(
                            uri=uri,
                            text=content,
                            mimeType="application/json"
                        )
                    ]
                )
            elif uri.startswith("collaboration://documents/"):
                # Handle document resources
                path = uri.replace("collaboration://documents/", "")
                content = await self.rtc_adapter.get_document_content(path)
                return types.ReadResourceResult(
                    contents=[
                        types.TextResourceContents(
                            uri=uri,
                            text=content,
                            mimeType="text/plain"
                        )
                    ]
                )
            elif uri.startswith("collaboration://awareness/"):
                # Handle awareness resources
                resource_type = uri.replace("collaboration://awareness/", "")
                content = await self.rtc_adapter.get_awareness_info(resource_type)
                return types.ReadResourceResult(
                    contents=[
                        types.TextResourceContents(
                            uri=uri,
                            text=content,
                            mimeType="application/json"
                        )
                    ]
                )
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
        
        @self.server.subscribe_resource()
        async def handle_subscribe_resource(uri: str) -> types.SubscribeResourceResult:
            """Subscribe to resource changes."""
            # Create a stream ID for this subscription
            stream_id = f"resource:{uri}"
            
            # Return the subscription result
            return types.SubscribeResourceResult(streamId=stream_id)
    
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