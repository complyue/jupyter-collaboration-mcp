"""
Tornado-native session manager for MCP server.

This module implements a session manager using Tornado's async patterns
without ASGI dependencies, handling MCP sessions with streamable-http mode.
"""

import json
import logging
import sys
from typing import Any, Dict, Optional

import mcp.types as types
from mcp.server import FastMCP
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    ErrorData,
    JSONRPCError,
    JSONRPCResponse,
)
from tornado import gen
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler

from .exceptions import MCPError
from .tornado_event_store import TornadoEventStore

logger = logging.getLogger(__name__)


class TornadoSessionManager:
    """Tornado-native session manager for MCP server."""

    def __init__(
        self,
        fastmcp: FastMCP,
        event_store: Optional[TornadoEventStore] = None,
        json_response: bool = False,
    ):
        """Initialize the session manager.

        Args:
            fastmcp: The MCP server instance
            event_store: Optional event store for resumability
            json_response: Whether to use JSON responses instead of SSE
        """
        self.fastmcp = fastmcp
        self.event_store = event_store or TornadoEventStore()
        self.json_response = json_response
        self._sessions: Dict[str, Dict[str, Any]] = {}

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
        """Handle GET requests for streamable-http mode.

        Args:
            request_handler: Tornado request handler
            path: Request path
        """
        # Get or create session ID from headers
        session_id = self._get_or_create_session_id(request_handler)

        # Set headers for streamable-http mode
        request_handler.set_header("Content-Type", "application/json")
        request_handler.set_header("Cache-Control", "no-cache")
        request_handler.set_header("Connection", "keep-alive")

        # Send session info as JSON response
        session_info = self._sessions[session_id]
        response_data = {
            "session_id": session_id,
            "status": session_info.get("status", "active"),
        }

        # Check for Last-Event-ID header for resumability
        last_event_id = request_handler.request.headers.get("Last-Event-ID")
        if last_event_id and self.event_store:
            try:
                # Replay events after the specified event ID
                last_sent_id = await self.event_store.replay_events_after(
                    last_event_id,
                    lambda event: None,  # We don't need to send events during replay
                )

                if last_sent_id:
                    response_data["last_event_id"] = last_sent_id
            except Exception as e:
                logger.error(f"Error replaying events: {e}")

        # Send response
        response_json = json.dumps(response_data)
        request_handler.finish(response_json)

    async def _handle_post(
        self, request_handler: RequestHandler, path: str, request_data: Any
    ) -> None:
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
                response = json.dumps(result)
                request_handler.set_header("Content-Type", "application/json")
                request_handler.finish(response)
            else:
                # Handle other MCP messages
                result = await self._handle_mcp_message(session_id, request_data)
                response = json.dumps(result)
                request_handler.set_header("Content-Type", "application/json")
                request_handler.finish(response)
        except Exception as e:
            logger.error(f"Error processing MCP message: {e}", exc_info=True)

            if isinstance(e, MCPError):
                error_data = e.error_data
            elif isinstance(e, ErrorData):
                error_data = e
            else:
                error_data = ErrorData(
                    code=INTERNAL_ERROR,
                    message=str(e),
                )

            error_id = request_data.get("id")

            # Check if this is a notification (no id field) - notifications don't get error responses
            if error_id is None:
                request_handler.finish("{}")  # Return empty JSON for notifications
                return

            error_response = JSONRPCError(
                jsonrpc="2.0",
                id=error_id,
                error=error_data,
            )
            error_response = error_response.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )

            request_handler.set_header("Content-Type", "application/json")
            request_handler.finish(json.dumps(error_response))

    async def _handle_delete(self, request_handler: RequestHandler, path: str) -> None:
        """Handle DELETE requests for session termination.

        Args:
            request_handler: Tornado request handler
            path: Request path
        """
        # Get session ID from headers
        session_id = self._get_session_id(request_handler)
        if session_id:
            # Get transport for this session
            transport = self._transports.get(session_id)
            if transport:
                await transport.terminate()
                del self._transports[session_id]

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

    async def end_session(self, session_id: str) -> None:
        """End an MCP session.

        Args:
            session_id: ID of the session to end
        """
        if session_id in self._sessions:
            # Update session status
            self._sessions[session_id]["status"] = "ended"
            self._sessions[session_id]["ended_at"] = IOLoop.current().time()

            logger.info(f"Ended MCP session: {session_id}")

    async def _handle_tool_call(
        self, session_id: str, request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
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
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Tool name is required",
                )
            )

        # Use FastMCP's built-in tool calling mechanism
        try:
            result = await self.fastmcp.call_tool(tool_name, arguments)
        except Exception as e:
            if isinstance(e, MCPError):
                raise e.error_data
            elif isinstance(e, ErrorData):
                raise e
            else:
                raise MCPError(
                    ErrorData(
                        code=INTERNAL_ERROR,
                        message=f"Error calling tool {tool_name}: {str(e)}",
                    )
                )

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

        tool_call_id = request_data.get("id")
        # Check if this is a notification (no id field) - notifications don't get responses
        if tool_call_id is None:
            return {}  # Return empty dict for notifications

        # Handle FastMCP result format properly
        if hasattr(result, "model_dump"):
            model_dump_result = result.model_dump(by_alias=True, mode="json", exclude_none=True)

            # FastMCP returns a tuple of (content, metadata) for some tools
            # We need to extract the actual content for the JSONRPCResponse
            if isinstance(model_dump_result, tuple) and len(model_dump_result) > 0:
                # If the first element is a list with content items, use that
                if isinstance(model_dump_result[0], list):
                    response_content = {"content": model_dump_result[0]}
                else:
                    response_content = {"content": list(model_dump_result)}
            else:
                response_content = model_dump_result
        else:
            # Check if the result itself is a tuple (which seems to be the case based on logs)
            if isinstance(result, tuple) and len(result) > 0:
                # Based on the logs, result[1] contains the actual data we want
                if len(result) > 1 and isinstance(result[1], dict):
                    # Check if the dictionary has a 'result' key (which contains the actual data)
                    if "result" in result[1]:
                        # MCP protocol expects the response to have a 'content' field
                        # The content should be a list of TextContent objects
                        response_content = {
                            "content": result[0]  # Use the TextContent list from the first element
                        }
                    else:
                        # Still structure it properly for MCP protocol
                        response_content = {
                            "content": result[0]  # Use the TextContent list from the first element
                        }
                else:
                    response_content = {"content": result[0]}
            else:
                response_content = result

        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=tool_call_id,
            result=response_content,
        )

        return response.model_dump(by_alias=True, mode="json", exclude_none=True)

    async def _handle_mcp_message(
        self, session_id: str, request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle a generic MCP message.

        Args:
            session_id: Session ID
            request_data: Request data

        Returns:
            MCP response
        """
        method = request_data.get("method")
        request_id = request_data.get("id")

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
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "jupyter-collaboration-mcp", "version": "0.1.0"},
            }
            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=request_id,
                result=result,
            )
            return response.model_dump(by_alias=True, mode="json", exclude_none=True)

        # Handle tools/list request
        elif method == "tools/list":
            # Use FastMCP's built-in tool listing
            tools: list[types.Tool] = await self.fastmcp.list_tools()

            # Convert to the expected format
            tool_list = []
            for tool in tools:
                tool_info = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
                # Add optional fields if they exist
                if tool.title:
                    tool_info["title"] = tool.title
                tool_list.append(tool_info)

            result = {"tools": tool_list}
            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=request_id,
                result=result,
            )
            return response.model_dump(by_alias=True, mode="json", exclude_none=True)

        # For other methods, just return a basic response
        # Check if this is a notification (no id field) - notifications don't get responses
        if request_id is None:
            return {}  # Return empty dict for notifications

        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=request_id,
            result={"status": "ok"},
        )
        return response.model_dump(by_alias=True, mode="json", exclude_none=True)

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
