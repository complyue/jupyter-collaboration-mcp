"""
MCP request handlers for Jupyter Collaboration features.

This module implements handlers for notebook, document, and awareness operations
through the MCP protocol.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.server.lowlevel import Server

from .rtc_adapter import RTCAdapter

logger = logging.getLogger(__name__)


class NotebookHandlers:
    """Handlers for notebook collaboration operations."""

    def __init__(self, server: Server, rtc_adapter: RTCAdapter):
        """Initialize notebook handlers."""
        self.server = server
        self.rtc_adapter = rtc_adapter
        self._register_handlers()

    def _register_handlers(self):
        """Register all notebook-related MCP tools."""

        @self.server.call_tool()
        async def list_notebooks(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """List available notebooks for collaboration."""
            if name != "list_notebooks":
                raise ValueError(f"Unknown tool: {name}")

            path_filter = arguments.get("path")
            notebooks = await self.rtc_adapter.list_notebooks(path_filter)

            return [types.TextContent(type="text", text=json.dumps(notebooks, indent=2))]

        @self.server.call_tool()
        async def get_notebook(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Get a notebook's content."""
            if name != "get_notebook":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            include_collaboration_state = arguments.get("include_collaboration_state", True)
            notebook = await self.rtc_adapter.get_notebook(path, include_collaboration_state)

            if not notebook:
                return [types.TextContent(type="text", text=f"Notebook not found: {path}")]

            return [types.TextContent(type="text", text=json.dumps(notebook, indent=2))]

        @self.server.call_tool()
        async def create_notebook_session(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Create or retrieve a collaboration session for a notebook."""
            if name != "create_notebook_session":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            session = await self.rtc_adapter.create_notebook_session(path)

            return [types.TextContent(type="text", text=json.dumps(session, indent=2))]

        @self.server.call_tool()
        async def update_notebook_cell(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Update a notebook cell's content."""
            if name != "update_notebook_cell":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            cell_id = arguments.get("cell_id")
            content = arguments.get("content")
            cell_type = arguments.get("cell_type")

            if not all([path, cell_id, content]):
                raise ValueError("Path, cell_id, and content are required")

            result = await self.rtc_adapter.update_notebook_cell(path, cell_id, content, cell_type)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def insert_notebook_cell(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Insert a new cell into a notebook."""
            if name != "insert_notebook_cell":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            content = arguments.get("content")
            position = arguments.get("position")
            cell_type = arguments.get("cell_type", "code")

            if not all([path, content, position is not None]):
                raise ValueError("Path, content, and position are required")

            result = await self.rtc_adapter.insert_notebook_cell(path, content, position, cell_type)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def delete_notebook_cell(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Delete a cell from a notebook."""
            if name != "delete_notebook_cell":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            cell_id = arguments.get("cell_id")

            if not all([path, cell_id]):
                raise ValueError("Path and cell_id are required")

            result = await self.rtc_adapter.delete_notebook_cell(path, cell_id)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def execute_notebook_cell(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Execute a notebook cell."""
            if name != "execute_notebook_cell":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            cell_id = arguments.get("cell_id")
            timeout = arguments.get("timeout", 30)

            if not all([path, cell_id]):
                raise ValueError("Path and cell_id are required")

            result = await self.rtc_adapter.execute_notebook_cell(path, cell_id, timeout)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


class DocumentHandlers:
    """Handlers for document collaboration operations."""

    def __init__(self, server: Server, rtc_adapter: RTCAdapter):
        """Initialize document handlers."""
        self.server = server
        self.rtc_adapter = rtc_adapter
        self._register_handlers()

    def _register_handlers(self):
        """Register all document-related MCP tools."""

        @self.server.call_tool()
        async def list_documents(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """List available documents for collaboration."""
            if name != "list_documents":
                raise ValueError(f"Unknown tool: {name}")

            path_filter = arguments.get("path")
            file_type = arguments.get("file_type")
            documents = await self.rtc_adapter.list_documents(path_filter, file_type)

            return [types.TextContent(type="text", text=json.dumps(documents, indent=2))]

        @self.server.call_tool()
        async def get_document(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Get a document's content."""
            if name != "get_document":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            include_collaboration_state = arguments.get("include_collaboration_state", True)
            document = await self.rtc_adapter.get_document(path, include_collaboration_state)

            if not document:
                return [types.TextContent(type="text", text=f"Document not found: {path}")]

            return [types.TextContent(type="text", text=json.dumps(document, indent=2))]

        @self.server.call_tool()
        async def create_document_session(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Create or retrieve a collaboration session for a document."""
            if name != "create_document_session":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            file_type = arguments.get("file_type")
            session = await self.rtc_adapter.create_document_session(path, file_type)

            return [types.TextContent(type="text", text=json.dumps(session, indent=2))]

        @self.server.call_tool()
        async def update_document(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Update a document's content."""
            if name != "update_document":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            content = arguments.get("content")
            position = arguments.get("position", -1)
            length = arguments.get("length", 0)

            if not all([path, content]):
                raise ValueError("Path and content are required")

            result = await self.rtc_adapter.update_document(path, content, position, length)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def insert_text(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Insert text into a document."""
            if name != "insert_text":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            text = arguments.get("text")
            position = arguments.get("position")

            if not all([path, text, position is not None]):
                raise ValueError("Path, text, and position are required")

            result = await self.rtc_adapter.insert_text(path, text, position)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def delete_text(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Delete text from a document."""
            if name != "delete_text":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            position = arguments.get("position")
            length = arguments.get("length")

            if not all([path, position is not None, length is not None]):
                raise ValueError("Path, position, and length are required")

            result = await self.rtc_adapter.delete_text(path, position, length)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def get_document_history(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get a document's version history."""
            if name != "get_document_history":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            limit = arguments.get("limit", 10)
            history = await self.rtc_adapter.get_document_history(path, limit)

            return [types.TextContent(type="text", text=json.dumps(history, indent=2))]

        @self.server.call_tool()
        async def restore_document_version(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Restore a document to a previous version."""
            if name != "restore_document_version":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            version_id = arguments.get("version_id")

            if not all([path, version_id]):
                raise ValueError("Path and version_id are required")

            result = await self.rtc_adapter.restore_document_version(path, version_id)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def fork_document(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Create a fork of a document."""
            if name != "fork_document":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            if not path:
                raise ValueError("Path is required")

            title = arguments.get("title")
            description = arguments.get("description")
            synchronize = arguments.get("synchronize", False)

            result = await self.rtc_adapter.fork_document(path, title, description, synchronize)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def merge_document_fork(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Merge a fork back into the original document."""
            if name != "merge_document_fork":
                raise ValueError(f"Unknown tool: {name}")

            path = arguments.get("path")
            fork_id = arguments.get("fork_id")

            if not all([path, fork_id]):
                raise ValueError("Path and fork_id are required")

            result = await self.rtc_adapter.merge_document_fork(path, fork_id)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


class AwarenessHandlers:
    """Handlers for user awareness and presence operations."""

    def __init__(self, server: Server, rtc_adapter: RTCAdapter):
        """Initialize awareness handlers."""
        self.server = server
        self.rtc_adapter = rtc_adapter
        self._register_handlers()

    def _register_handlers(self):
        """Register all awareness-related MCP tools."""

        @self.server.call_tool()
        async def get_online_users(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get a list of users currently online."""
            if name != "get_online_users":
                raise ValueError(f"Unknown tool: {name}")

            document_path = arguments.get("document_path")
            users = await self.rtc_adapter.get_online_users(document_path)

            return [types.TextContent(type="text", text=json.dumps(users, indent=2))]

        @self.server.call_tool()
        async def get_user_presence(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get presence information for a specific user."""
            if name != "get_user_presence":
                raise ValueError(f"Unknown tool: {name}")

            user_id = arguments.get("user_id")
            if not user_id:
                raise ValueError("User ID is required")

            document_path = arguments.get("document_path")
            presence = await self.rtc_adapter.get_user_presence(user_id, document_path)

            return [types.TextContent(type="text", text=json.dumps(presence, indent=2))]

        @self.server.call_tool()
        async def set_user_presence(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Set the current user's presence status."""
            if name != "set_user_presence":
                raise ValueError(f"Unknown tool: {name}")

            status = arguments.get("status", "online")
            message = arguments.get("message")

            result = await self.rtc_adapter.set_user_presence(status, message)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def get_user_cursors(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get cursor positions of users in a document."""
            if name != "get_user_cursors":
                raise ValueError(f"Unknown tool: {name}")

            document_path = arguments.get("document_path")
            if not document_path:
                raise ValueError("Document path is required")

            cursors = await self.rtc_adapter.get_user_cursors(document_path)

            return [types.TextContent(type="text", text=json.dumps(cursors, indent=2))]

        @self.server.call_tool()
        async def update_cursor_position(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Update the current user's cursor position."""
            if name != "update_cursor_position":
                raise ValueError(f"Unknown tool: {name}")

            document_path = arguments.get("document_path")
            position = arguments.get("position")
            selection = arguments.get("selection")

            if not all([document_path, position]):
                raise ValueError("Document path and position are required")

            result = await self.rtc_adapter.update_cursor_position(
                document_path, position, selection
            )

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def get_user_activity(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get recent activity for users."""
            if name != "get_user_activity":
                raise ValueError(f"Unknown tool: {name}")

            document_path = arguments.get("document_path")
            limit = arguments.get("limit", 20)

            activity = await self.rtc_adapter.get_user_activity(document_path, limit)

            return [types.TextContent(type="text", text=json.dumps(activity, indent=2))]

        @self.server.call_tool()
        async def broadcast_user_activity(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Broadcast a user activity to other collaborators."""
            if name != "broadcast_user_activity":
                raise ValueError(f"Unknown tool: {name}")

            activity_type = arguments.get("activity_type")
            description = arguments.get("description")

            if not all([activity_type, description]):
                raise ValueError("Activity type and description are required")

            document_path = arguments.get("document_path")
            metadata = arguments.get("metadata", {})

            result = await self.rtc_adapter.broadcast_user_activity(
                activity_type, description, document_path, metadata
            )

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def get_active_sessions(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.ContentBlock]:
            """Get active collaboration sessions."""
            if name != "get_active_sessions":
                raise ValueError(f"Unknown tool: {name}")

            document_path = arguments.get("document_path")
            sessions = await self.rtc_adapter.get_active_sessions(document_path)

            return [types.TextContent(type="text", text=json.dumps(sessions, indent=2))]

        @self.server.call_tool()
        async def join_session(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Join an existing collaboration session."""
            if name != "join_session":
                raise ValueError(f"Unknown tool: {name}")

            session_id = arguments.get("session_id")
            if not session_id:
                raise ValueError("Session ID is required")

            result = await self.rtc_adapter.join_session(session_id)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        @self.server.call_tool()
        async def leave_session(name: str, arguments: Dict[str, Any]) -> List[types.ContentBlock]:
            """Leave a collaboration session."""
            if name != "leave_session":
                raise ValueError(f"Unknown tool: {name}")

            session_id = arguments.get("session_id")
            if not session_id:
                raise ValueError("Session ID is required")

            result = await self.rtc_adapter.leave_session(session_id)

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
