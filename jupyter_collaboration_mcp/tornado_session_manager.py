"""
Tornado-native session manager for MCP server.

This module implements a session manager using Tornado's async patterns
without ASGI dependencies, handling MCP sessions and SSE streams.
"""

import json
import logging
import sys
from typing import Any, Dict, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

from .tornado_event_store import TornadoEventStore
from .tornado_sse_handler import TornadoSSEHandler

logger = logging.getLogger(__name__)


class TornadoSessionManager:
    """Tornado-native session manager for MCP server."""

    def __init__(
        self,
        mcp_server: Server,
        event_store: Optional[TornadoEventStore] = None,
        json_response: bool = False,
    ):
        """Initialize the session manager.

        Args:
            mcp_server: The MCP server instance
            event_store: Optional event store for resumability
            json_response: Whether to use JSON responses instead of SSE
        """
        self.mcp_server = mcp_server
        self.event_store = event_store or TornadoEventStore()
        self.json_response = json_response
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._sse_handlers: Dict[str, TornadoSSEHandler] = {}

    async def handle_request(self, request_handler: RequestHandler) -> None:
        """Handle MCP HTTP request directly without ASGI conversion.

        Args:
            request_handler: Tornado request handler
        """
        method = request_handler.request.method
        path = request_handler.request.path

        try:
            # Parse request body for POST requests
            request_data = None
            if method == "POST":
                content_type = request_handler.request.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    try:
                        request_data = json.loads(request_handler.request.body)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in request body: {e}")
                        request_handler.set_status(400)
                        request_handler.finish({"error": "Invalid JSON"})
                        return
                else:
                    logger.error(f"Unsupported content type: {content_type}")
                    request_handler.set_status(400)
                    request_handler.finish({"error": "Unsupported content type"})
                    return

            # Handle different HTTP methods
            if method == "GET":
                await self._handle_get(request_handler, path)
            elif method == "POST":
                await self._handle_post(request_handler, path, request_data)
            elif method == "DELETE":
                await self._handle_delete(request_handler, path)
            else:
                logger.warning(f"Unsupported HTTP method: {method}")
                request_handler.set_status(405)
                request_handler.finish({"error": "Method not allowed"})
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}", exc_info=True)
            request_handler.set_status(500)
            request_handler.finish({"error": "Internal server error"})

    async def _handle_get(self, request_handler: RequestHandler, path: str) -> None:
        """Handle GET requests for SSE streams.

        Args:
            request_handler: Tornado request handler
            path: Request path
        """
        # Get or create session ID from headers
        session_id = self._get_or_create_session_id(request_handler)

        # Create SSE handler
        sse_handler = TornadoSSEHandler(request_handler)
        self._sse_handlers[session_id] = sse_handler

        # Start heartbeat
        await sse_handler.start_heartbeat_loop()

        # Check for Last-Event-ID header for resumability
        last_event_id = request_handler.request.headers.get("Last-Event-ID")
        if last_event_id and self.event_store:
            try:
                await self.event_store.replay_events_after(
                    last_event_id,
                    lambda event: sse_handler.send_event(
                        event_type="message",
                        data=event.message,
                        event_id=event.event_id,
                    ),
                )
            except Exception as e:
                logger.error(f"Error replaying events: {e}")

        # Send initial session info
        session_info = self._sessions[session_id]
        await sse_handler.send_event(
            event_type="session_info",
            data={
                "session_id": session_id,
                "status": session_info.get("status", "active"),
            },
        )

        # Keep the connection open for SSE
        # The connection will be closed when the client disconnects
        # or when the session is ended

    async def _handle_post(self, request_handler: RequestHandler, path: str, request_data: Any) -> None:
        """Handle POST requests containing MCP messages.

        Args:
            request_handler: Tornado request handler
            path: Request path
            request_data: Parsed request data
        """
        # Get or create session ID from headers
        session_id = self._get_or_create_session_id(request_handler)

        # Process MCP message
        try:
            # Handle tool calls
            if "method" in request_data and request_data["method"] == "tools/call":
                result = await self._handle_tool_call(session_id, request_data)
                
                if self.json_response or not self._sse_handlers.get(session_id):
                    # Send JSON response
                    request_handler.set_header("Content-Type", "application/json")
                    request_handler.finish(json.dumps(result))
                else:
                    # Send via SSE
                    sse_handler = self._sse_handlers[session_id]
                    await sse_handler.send_event(
                        event_type="tool_result",
                        data=result,
                    )
                    request_handler.finish()
            else:
                # Handle other MCP messages
                result = await self._handle_mcp_message(session_id, request_data)
                
                if self.json_response or not self._sse_handlers.get(session_id):
                    # Send JSON response
                    request_handler.set_header("Content-Type", "application/json")
                    request_handler.finish(json.dumps(result))
                else:
                    # Send via SSE
                    sse_handler = self._sse_handlers[session_id]
                    await sse_handler.send_event(
                        event_type="mcp_response",
                        data=result,
                    )
                    request_handler.finish()
        except Exception as e:
            logger.error(f"Error processing MCP message: {e}", exc_info=True)
            
            error_response = {
                "jsonrpc": "2.0",
                "id": request_data.get("id"),
                "error": {
                    "code": -32000,
                    "message": str(e),
                },
            }
            
            if self.json_response or not self._sse_handlers.get(session_id):
                request_handler.set_header("Content-Type", "application/json")
                request_handler.finish(json.dumps(error_response))
            else:
                sse_handler = self._sse_handlers.get(session_id)
                if sse_handler:
                    await sse_handler.send_event(
                        event_type="error",
                        data=error_response,
                    )
                request_handler.finish()

    async def _handle_delete(self, request_handler: RequestHandler, path: str) -> None:
        """Handle DELETE requests for session termination.

        Args:
            request_handler: Tornado request handler
            path: Request path
        """
        # Get session ID from headers
        session_id = self._get_session_id(request_handler)
        if session_id:
            await self.end_session(session_id)
            request_handler.finish({"status": "Session ended"})
        else:
            request_handler.set_status(404)
            request_handler.finish({"error": "Session not found"})

    async def start_session(self, session_id: Optional[str] = None) -> str:
        """Start a new MCP session.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            The session ID
        """
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())

        self._sessions[session_id] = {
            "id": session_id,
            "status": "active",
            "created_at": IOLoop.current().time(),
        }

        logger.info(f"Started MCP session: {session_id}")
        return session_id

    async def end_session(self, session_id: str) -> None:
        """End an MCP session.

        Args:
            session_id: ID of the session to end
        """
        if session_id in self._sessions:
            # Close SSE handler if exists
            if session_id in self._sse_handlers:
                self._sse_handlers[session_id].close()
                del self._sse_handlers[session_id]

            # Update session status
            self._sessions[session_id]["status"] = "ended"
            self._sessions[session_id]["ended_at"] = IOLoop.current().time()

            logger.info(f"Ended MCP session: {session_id}")

    def create_sse_stream(self, request_handler: RequestHandler) -> None:
        """Create SSE stream for server-initiated messages.

        Args:
            request_handler: Tornado request handler
        """
        session_id = self._get_or_create_session_id(request_handler)
        sse_handler = TornadoSSEHandler(request_handler)
        self._sse_handlers[session_id] = sse_handler

        # Start heartbeat
        IOLoop.current().add_callback(sse_handler.start_heartbeat_loop)

    async def _handle_tool_call(self, session_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a tool call request.

        Args:
            session_id: Session ID
            request_data: Request data

        Returns:
            Tool call result
        """
        tool_name = request_data.get("params", {}).get("name")
        arguments = request_data.get("params", {}).get("arguments", {})

        if not tool_name:
            raise ValueError("Tool name is required")

        # Call the tool through the MCP server
        result = await self.mcp_server.call_tool(tool_name, arguments)

        # Store event if event store is available
        if self.event_store:
            await self.event_store.store_event(
                stream_id=session_id,
                message={
                    "type": "tool_call",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                },
            )

        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "result": result,
        }

    async def _handle_mcp_message(self, session_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a generic MCP message.

        Args:
            session_id: Session ID
            request_data: Request data

        Returns:
            MCP response
        """
        method = request_data.get("method")
        request_id = request_data.get("id")
        
        # Add debug logging
        print(f"DEBUG: Handling MCP message: method={method}, id={request_id}", file=sys.stderr)
        print(f"DEBUG: Request data: {request_data}", file=sys.stderr)
        
        # Store event if event store is available
        if self.event_store:
            await self.event_store.store_event(
                stream_id=session_id,
                message={
                    "type": "mcp_message",
                    "data": request_data,
                },
            )

        # Handle MCP initialization
        if method == "initialize":
            print(f"DEBUG: Handling MCP initialization request", file=sys.stderr)
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "listChanged": True
                    }
                },
                "serverInfo": {
                    "name": "jupyter-collaboration-mcp",
                    "version": "0.1.0"
                }
            }
            print(f"DEBUG: Returning initialization result: {result}", file=sys.stderr)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        
        # Handle tools/list request
        elif method == "tools/list":
            print(f"DEBUG: Handling tools/list request", file=sys.stderr)
            print(f"DEBUG: About to construct tools list with boolean values", file=sys.stderr)
            result = {
                "tools": [
                    {
                        "name": "list_notebooks",
                        "description": "List available notebooks for collaboration",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path filter for notebooks"
                                }
                            }
                        }
                    },
                    {
                        "name": "get_notebook",
                        "description": "Get a notebook's content",
                        "inputSchema": {
                            "type": "object",
                            "required": ["path"],
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the notebook"
                                },
                                "include_collaboration_state": {
                                    "type": "boolean",
                                    "description": "Include collaboration state",
                                    "default": True
                                }
                            }
                        }
                    },
                    {
                        "name": "create_notebook_session",
                        "description": "Create or retrieve a collaboration session for a notebook",
                        "inputSchema": {
                            "type": "object",
                            "required": ["path"],
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "Path to the notebook"
                                }
                            }
                        }
                    }
                ]
            }
            print(f"DEBUG: Returning tools/list result: {result}", file=sys.stderr)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        
        # For other methods, just return a basic response
        print(f"DEBUG: Handling unknown method: {method}", file=sys.stderr)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"status": "ok"},
        }

    def _get_or_create_session_id(self, request_handler: RequestHandler) -> str:
        """Get existing session ID or create a new one."""
        session_id = request_handler.request.headers.get("mcp-session-id")
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {"created_at": IOLoop.current().time()}
        return session_id

    def _get_session_id(self, request_handler: RequestHandler) -> Optional[str]:
        """Get existing session ID."""
        return request_handler.request.headers.get("mcp-session-id")

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all active sessions.

        Args:
            event_type: Type of the event
            data: Event data
        """
        for session_id, sse_handler in self._sse_handlers.items():
            try:
                await sse_handler.send_event(event_type=event_type, data=data)
            except Exception as e:
                logger.error(f"Error broadcasting event to session {session_id}: {e}")