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

from .tornado_event_store import TornadoEventStore
from .tornado_sse_handler import TornadoSSEHandler

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

                if self.json_response or not self._sse_handlers.get(session_id):
                    # Send JSON response
                    json_response_str = json.dumps(result)
                    request_handler.set_header("Content-Type", "application/json")
                    request_handler.finish(json_response_str)
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
                    json_response_str = json.dumps(result)
                    request_handler.set_header("Content-Type", "application/json")
                    request_handler.finish(json_response_str)
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

            if isinstance(e, ErrorData):
                error_data = e
            else:
                error_data = ErrorData(
                    code=INTERNAL_ERROR,
                    message=str(e),
                )

            error_id = request_data.get("id")
            logger.debug(
                f"DEBUG: Creating JSONRPCError with id: {error_id} (type: {type(error_id)})"
            )
            logger.debug(f"DEBUG: request_data in error handler: {request_data}")

            # Check if this is a notification (no id field) - notifications don't get error responses
            if error_id is None:
                logger.debug(f"DEBUG: Error occurred for notification - no error response needed")
                if self.json_response or not self._sse_handlers.get(session_id):
                    request_handler.finish("{}")  # Return empty JSON for notifications
                else:
                    request_handler.finish()
                return

            error_response = JSONRPCError(
                jsonrpc="2.0",
                id=error_id,
                error=error_data,
            )
            error_response = error_response.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )

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
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Tool name is required",
            )

        # Use FastMCP's built-in tool calling mechanism
        try:
            result = await self.fastmcp.call_tool(tool_name, arguments)
        except Exception as e:
            if isinstance(e, ErrorData):
                raise e
            else:
                raise ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Error calling tool {tool_name}: {str(e)}",
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
        logger.debug(
            f"DEBUG: Creating JSONRPCResponse for tool call with id: {tool_call_id} (type: {type(tool_call_id)})"
        )
        logger.debug(f"DEBUG: request_data in tool call handler: {request_data}")
        # Check if this is a notification (no id field) - notifications don't get responses
        if tool_call_id is None:
            logger.debug(f"DEBUG: Received tool call notification - no response needed")
            return {}  # Return empty dict for notifications

        logger.debug(
            f"DEBUG: Creating JSONRPCResponse for tool call with id: {tool_call_id} (type: {type(tool_call_id)})"
        )
        logger.debug(f"DEBUG: request_data in tool call handler: {request_data}")
        logger.debug(f"DEBUG: result type: {type(result)}")
        logger.debug(f"DEBUG: result value: {result}")
        logger.debug(f"DEBUG: hasattr(result, 'model_dump'): {hasattr(result, 'model_dump')}")

        # Handle FastMCP result format properly
        logger.debug(f"DEBUG: Checking if result has model_dump attribute")
        if hasattr(result, "model_dump"):
            logger.debug(f"DEBUG: result has model_dump, calling it")
            model_dump_result = result.model_dump(by_alias=True, mode="json", exclude_none=True)
            logger.debug(f"DEBUG: model_dump_result type: {type(model_dump_result)}")
            logger.debug(f"DEBUG: model_dump_result value: {model_dump_result}")

            # FastMCP returns a tuple of (content, metadata) for some tools
            # We need to extract the actual content for the JSONRPCResponse
            if isinstance(model_dump_result, tuple) and len(model_dump_result) > 0:
                logger.debug(f"DEBUG: model_dump_result is a tuple, extracting content")
                # If the first element is a list with content items, use that
                if isinstance(model_dump_result[0], list):
                    logger.debug(f"DEBUG: Using first element of tuple as content")
                    response_content = {"content": model_dump_result[0]}
                else:
                    logger.debug(f"DEBUG: Using entire tuple as content")
                    response_content = {"content": list(model_dump_result)}
            else:
                logger.debug(f"DEBUG: model_dump_result is not a tuple, using as-is")
                response_content = model_dump_result
        else:
            logger.debug(f"DEBUG: result doesn't have model_dump, checking if it's a tuple")
            # Check if the result itself is a tuple (which seems to be the case based on logs)
            if isinstance(result, tuple) and len(result) > 0:
                logger.debug(f"DEBUG: result is a tuple with {len(result)} elements")
                logger.debug(f"DEBUG: result[0] type: {type(result[0])}")
                logger.debug(f"DEBUG: result[0] value: {result[0]}")
                logger.debug(f"DEBUG: result[1] type: {type(result[1])}")
                logger.debug(f"DEBUG: result[1] value: {result[1]}")

                # Based on the logs, result[1] contains the actual data we want
                if len(result) > 1 and isinstance(result[1], dict):
                    logger.debug(f"DEBUG: Using second element of tuple as response content")
                    # Check if the dictionary has a 'result' key (which contains the actual data)
                    if "result" in result[1]:
                        logger.debug(f"DEBUG: Extracting data from 'result' key in second element")
                        # MCP protocol expects the response to have a 'content' field
                        # The content should be a list of TextContent objects
                        response_content = {
                            "content": result[0]  # Use the TextContent list from the first element
                        }
                    else:
                        logger.debug(f"DEBUG: Using entire second element as response content")
                        # Still structure it properly for MCP protocol
                        response_content = {
                            "content": result[0]  # Use the TextContent list from the first element
                        }
                else:
                    logger.debug(f"DEBUG: Using first element of tuple as response content")
                    response_content = {"content": result[0]}
            else:
                logger.debug(f"DEBUG: result is not a tuple, using as-is")
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

        # DEBUG: Log the request data and id to diagnose the issue
        logger.debug(f"DEBUG: _handle_mcp_message called with request_data: {request_data}")
        logger.debug(f"DEBUG: request_id extracted: {request_id} (type: {type(request_id)})")
        logger.debug(f"DEBUG: 'id' key exists in request_data: {'id' in request_data}")

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
                "protocolVersion": "2024-11-05",
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
            logger.debug(f"DEBUG: Received notification '{method}' - no response needed")
            return {}  # Return empty dict for notifications

        logger.debug(
            f"DEBUG: Creating JSONRPCResponse with id: {request_id} (type: {type(request_id)})"
        )
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
