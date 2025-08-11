"""
RTC Adapter for Jupyter Collaboration.

This module provides an adapter between MCP requests and Jupyter Collaboration's
real-time collaboration (RTC) functionality using YDoc.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Union

from jupyter_server_ydoc.app import YDocExtension
from jupyter_server_ydoc.rooms import DocumentRoom
from tornado import gen
from tornado.ioloop import IOLoop

logger = logging.getLogger(__name__)


class RTCAdapter:
    """Adapter between MCP requests and Jupyter Collaboration functionality."""

    def __init__(self, server_app, ydoc_extension):
        self._server_app = server_app
        self.ydoc_extension = ydoc_extension

        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._user_presence: Dict[str, Dict[str, Any]] = {}
        self._document_forks: Dict[str, Dict[str, Any]] = {}

        logger.info("RTC adapter initialized successfully")

    # Notebook operations

    async def list_notebooks(self, path_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available notebooks for collaboration."""
        # Get the contents manager from the server app
        contents_manager = self._server_app.contents_manager
        contents = await contents_manager.get("", content=True)
        notebooks = []

        async def process_contents(contents_item, path=""):
            if contents_item["type"] == "notebook":
                notebook_path = f"{path}/{contents_item['name']}" if path else contents_item["name"]

                # Check if there's an active collaboration session for this notebook
                collaborators = await self._get_collaborator_count(f"json:notebook:{notebook_path}")

                notebook_info = {
                    "path": notebook_path,
                    "name": contents_item["name"],
                    "collaborative": collaborators > 0,
                    "last_modified": contents_item["last_modified"],
                    "collaborators": max(0, collaborators),
                    "size": contents_item.get("size", 0),
                }
                notebooks.append(notebook_info)

            # Process directories recursively
            if contents_item["type"] == "directory":
                dir_path = f"{path}/{contents_item['name']}" if path else contents_item["name"]
                try:
                    dir_contents = await contents_manager.get(dir_path, content=True)
                    if "content" in dir_contents:
                        for item in dir_contents["content"]:
                            await process_contents(item, dir_path)
                except Exception as e:
                    logger.warning(f"Error listing contents of {dir_path}", exc_info=True)

        # Process all contents
        if "content" in contents:
            for item in contents["content"]:
                await process_contents(item)

        # Apply filters and sort
        filtered_notebooks = self._filter_and_sort_items(notebooks, path_prefix)
        return filtered_notebooks

    async def get_notebook(
        self, path: str, include_collaboration_state: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a notebook's content."""
        # Get the document room for this notebook
        room = await self.ydoc_extension.get_room(path, "notebook")
        if not room:
            return None

        # Get the document content
        content = await room.get_content()

        result = {"path": path, "content": content, "format": "json", "type": "notebook"}

        if include_collaboration_state:
            result["collaboration_state"] = await self._get_collaboration_state(room)

        return result

    async def create_notebook_session(self, path: str) -> Dict[str, Any]:
        """Create or retrieve a collaboration session for a notebook."""
        session_id = str(uuid.uuid4())
        room_id = f"notebook:{path}"

        # Get or create the room
        room = await self.ydoc_extension.get_room(path, "notebook")

        # Store session information
        self._sessions[session_id] = {
            "id": session_id,
            "room_id": room_id,
            "path": path,
            "type": "notebook",
            "created_at": IOLoop.current().time(),
        }

        return {"session_id": session_id, "room_id": room_id, "path": path, "status": "active"}

    async def update_notebook_cell(
        self,
        path: str,
        cell_id: str,
        content: str,
        cell_type: Optional[str] = None,
        exec: bool = True,
    ) -> Dict[str, Any]:
        """Update a notebook cell's content."""
        room = await self.ydoc_extension.get_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found: {path}")

        # Update the cell content
        await room.update_cell(cell_id, content, cell_type)

        # Execute the cell if requested
        exec_result = None
        if exec:
            try:
                exec_result = await room.execute_cell(cell_id, 30)
            except Exception as exec_e:
                logger.warning(f"Error executing cell {cell_id} after update", exc_info=True)
                exec_result = {"error": str(exec_e)}

        return {
            "success": True,
            "cell_id": cell_id,
            "timestamp": IOLoop.current().time(),
            "executed": exec,
            "execution_result": exec_result,
        }

    async def insert_notebook_cell(
        self, path: str, content: str, position: int, cell_type: str = "code", exec: bool = True
    ) -> Dict[str, Any]:
        """Insert a new cell into a notebook."""
        room = await self.ydoc_extension.get_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found: {path}")

        # Insert the new cell
        cell_id = await room.insert_cell(content, position, cell_type)

        # Execute the cell if requested
        exec_result = None
        if exec:
            try:
                exec_result = await room.execute_cell(cell_id, 30)
            except Exception as exec_e:
                logger.warning(f"Error executing cell {cell_id} after insertion", exc_info=True)
                exec_result = {"error": str(exec_e)}

        return {
            "success": True,
            "cell_id": cell_id,
            "position": position,
            "timestamp": IOLoop.current().time(),
            "executed": exec,
            "execution_result": exec_result,
        }

    async def delete_notebook_cell(
        self, path: str, cell_id: str, exec: bool = True
    ) -> Dict[str, Any]:
        """Delete a cell from a notebook."""
        room = await self.ydoc_extension.get_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found: {path}")

        # Execute the cell before deletion if requested
        exec_result = None
        if exec:
            try:
                exec_result = await room.execute_cell(cell_id, 30)
            except Exception as exec_e:
                logger.warning(f"Error executing cell {cell_id} before deletion", exc_info=True)
                exec_result = {"error": str(exec_e)}

        # Delete the cell
        await room.delete_cell(cell_id)
        return {
            "success": True,
            "cell_id": cell_id,
            "timestamp": IOLoop.current().time(),
            "executed": exec,
            "execution_result": exec_result,
        }

    async def execute_notebook_cell(
        self, path: str, cell_id: str, timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute a notebook cell."""
        room = await self.ydoc_extension.get_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found: {path}")

        # Execute the cell
        result = await room.execute_cell(cell_id, timeout)
        return {
            "success": True,
            "cell_id": cell_id,
            "result": result,
            "timestamp": IOLoop.current().time(),
        }

    # Document operations

    async def list_documents(
        self, path_prefix: Optional[str] = None, file_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List available documents for collaboration."""
        # Get the contents manager from the server app
        contents_manager = self._server_app.contents_manager
        contents = await contents_manager.get("", content=True)
        documents = []

        async def process_contents(contents_item, path=""):
            if contents_item["type"] == "file":
                file_path = f"{path}/{contents_item['name']}" if path else contents_item["name"]

                # Skip notebooks (they're handled by list_notebooks)
                if file_path.endswith(".ipynb"):
                    return

                # Determine file type and check collaboration
                doc_file_type = self._get_file_type(file_path)
                collaborators = await self._get_collaborator_count(
                    f"json:{doc_file_type}:{file_path}"
                )

                documents.append(
                    {
                        "path": file_path,
                        "name": contents_item["name"],
                        "file_type": doc_file_type,
                        "collaborative": collaborators > 0,
                        "last_modified": contents_item["last_modified"],
                        "collaborators": max(0, collaborators),
                        "size": contents_item.get("size", 0),
                    }
                )

            # Process directories recursively
            if contents_item["type"] == "directory":
                dir_path = f"{path}/{contents_item['name']}" if path else contents_item["name"]
                try:
                    dir_contents = await contents_manager.get(dir_path, content=True)
                    if "content" in dir_contents:
                        for item in dir_contents["content"]:
                            await process_contents(item, dir_path)
                except Exception as e:
                    logger.warning(f"Error listing contents of {dir_path}", exc_info=True)

        # Process all contents
        if "content" in contents:
            for item in contents["content"]:
                await process_contents(item)

        # Apply filters and sort
        documents = self._filter_and_sort_items(documents, path_prefix)

        # Apply file type filter if provided
        if file_type:
            documents = [d for d in documents if d["file_type"] == file_type]

        return documents

    async def get_document(
        self, path: str, include_collaboration_state: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a document's content."""
        # Determine file type from path
        file_type = self._get_file_type(path)

        # Get the document room
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            return None

        # Get the document content
        content = await room.get_content()

        result = {"path": path, "content": content, "file_type": file_type, "type": "document"}

        if include_collaboration_state:
            result["collaboration_state"] = await self._get_collaboration_state(room)

        return result

    async def create_document_session(
        self, path: str, file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create or retrieve a collaboration session for a document."""
        if not file_type:
            file_type = self._get_file_type(path)

        session_id = str(uuid.uuid4())
        room_id = f"document:{path}"

        # Get or create the room
        room = await self.ydoc_extension.get_room(path, file_type)

        # Store session information
        self._sessions[session_id] = {
            "id": session_id,
            "room_id": room_id,
            "path": path,
            "type": "document",
            "file_type": file_type,
            "created_at": IOLoop.current().time(),
        }

        return {
            "session_id": session_id,
            "room_id": room_id,
            "path": path,
            "file_type": file_type,
            "status": "active",
        }

    async def update_document(
        self, path: str, content: str, position: int = -1, length: int = 0
    ) -> Dict[str, Any]:
        """Update a document's content."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Update the document content
        await room.update_content(content, position, length)
        return {
            "success": True,
            "path": path,
            "version": await room.get_version(),
            "timestamp": IOLoop.current().time(),
        }

    async def insert_text(self, path: str, text: str, position: int) -> Dict[str, Any]:
        """Insert text into a document."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Insert the text
        new_length = await room.insert_text(text, position)
        return {
            "success": True,
            "path": path,
            "new_length": new_length,
            "timestamp": IOLoop.current().time(),
        }

    async def delete_text(self, path: str, position: int, length: int) -> Dict[str, Any]:
        """Delete text from a document."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Delete the text
        new_length = await room.delete_text(position, length)

        return {
            "success": True,
            "path": path,
            "new_length": new_length,
            "timestamp": IOLoop.current().time(),
        }

    async def get_document_history(self, path: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get a document's version history."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Get the document history
        history = await room.get_history(limit)

        return history

    async def restore_document_version(self, path: str, version_id: str) -> Dict[str, Any]:
        """Restore a document to a previous version."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Restore the version
        await room.restore_version(version_id)
        return {
            "success": True,
            "path": path,
            "version_id": version_id,
            "timestamp": IOLoop.current().time(),
        }

    async def fork_document(
        self,
        path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        synchronize: bool = False,
    ) -> Dict[str, Any]:
        """Create a fork of a document."""
        file_type = self._get_file_type(path)
        room = await self.ydoc_extension.get_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found: {path}")

        # Create the fork
        fork_id = str(uuid.uuid4())
        fork_path = f"{path}.fork-{fork_id}"

        # Copy the document content
        content = await room.get_content()
        fork_room = await self.ydoc_extension.get_room(fork_path, file_type)
        await fork_room.update_content(content)

        # Store fork information
        self._document_forks[fork_id] = {
            "id": fork_id,
            "original_path": path,
            "fork_path": fork_path,
            "title": title or f"Fork of {path}",
            "description": description or "",
            "synchronize": synchronize,
            "created_at": IOLoop.current().time(),
        }

        return {
            "success": True,
            "fork_id": fork_id,
            "fork_path": fork_path,
            "title": title or f"Fork of {path}",
            "timestamp": IOLoop.current().time(),
        }

    async def merge_document_fork(self, path: str, fork_id: str) -> Dict[str, Any]:
        """Merge a fork back into the original document."""
        if fork_id not in self._document_forks:
            raise ValueError(f"Fork not found: {fork_id}")

        fork_info = self._document_forks[fork_id]
        if fork_info["original_path"] != path:
            raise ValueError(f"Fork {fork_id} does not belong to document {path}")

        file_type = self._get_file_type(path)

        # Get both rooms
        original_room = await self.ydoc_extension.get_room(path, file_type)
        fork_room = await self.ydoc_extension.get_room(fork_info["fork_path"], file_type)

        if not original_room or not fork_room:
            raise ValueError("Could not access document or fork")

        # Get fork content
        fork_content = await fork_room.get_content()

        # Merge into original
        await original_room.update_content(fork_content)

        # Clean up fork if not synchronized
        if not fork_info["synchronize"]:
            del self._document_forks[fork_id]

        return {
            "success": True,
            "path": path,
            "fork_id": fork_id,
            "timestamp": IOLoop.current().time(),
        }

    # Awareness operations

    async def get_online_users(self, document_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get a list of users currently online."""
        # Query the awareness system for online users
        users = []

        if hasattr(self.ydoc_extension, "ywebsocket_server"):
            # Get all rooms to check for active users
            try:
                # This is a simplified implementation - in a real scenario,
                # we would query the awareness system more directly
                if document_path:
                    room_id = f"json:notebook:{document_path}"
                    if not document_path.endswith(".ipynb"):
                        file_type = self._get_file_type(document_path)
                        room_id = f"json:{file_type}:{document_path}"

                    room = await self.ydoc_extension.ywebsocket_server.get_room(room_id)
                    if room and hasattr(room, "awareness"):
                        for client_id, state in room.awareness.states.items():
                            users.append(
                                {
                                    "id": str(client_id),
                                    "name": state.get("user", {}).get("name", f"User {client_id}"),
                                    "status": "online",
                                    "last_activity": IOLoop.current().time(),
                                    "current_document": document_path,
                                }
                            )
                else:
                    # Return a generic response for now
                    # In a real implementation, we would aggregate across all rooms
                    users = [
                        {
                            "id": "user1",
                            "name": "User 1",
                            "status": "online",
                            "last_activity": IOLoop.current().time(),
                            "current_document": "/example.ipynb",
                        }
                    ]
            except Exception as e:
                logger.warning(f"Error querying awareness system", exc_info=True)
                # Fallback to empty list
                users = []

        return users

    async def get_user_presence(
        self, user_id: str, document_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get presence information for a specific user."""
        # Check cached presence first
        if user_id in self._user_presence:
            presence = self._user_presence[user_id]
            if document_path and presence.get("current_document") != document_path:
                return {"error": "User not present in specified document"}
            return presence

        # Query the awareness system for user presence
        if hasattr(self.ydoc_extension, "ywebsocket_server"):
            # In a real implementation, we would query the awareness system directly
            # For now, return a default presence
            return {
                "user_id": user_id,
                "status": "offline",
                "last_activity": 0,
                "current_document": None,
            }
        else:
            return {
                "user_id": user_id,
                "status": "offline",
                "last_activity": 0,
                "current_document": None,
            }

    async def set_user_presence(
        self, status: str = "online", message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Set the current user's presence status."""
        # In a real implementation, this would update the presence system
        user_id = "current_user"  # Would get from authenticated context
        self._user_presence[user_id] = {
            "user_id": user_id,
            "status": status,
            "message": message,
            "last_activity": IOLoop.current().time(),
        }

        return {
            "success": True,
            "user_id": user_id,
            "status": status,
            "timestamp": IOLoop.current().time(),
        }

    async def get_user_cursors(self, document_path: str) -> List[Dict[str, Any]]:
        """Get cursor positions of users in a document."""
        # Query the awareness system for cursor positions
        cursors = []

        if hasattr(self.ydoc_extension, "ywebsocket_server"):
            # Determine room ID based on document type
            room_id = f"json:notebook:{document_path}"
            if not document_path.endswith(".ipynb"):
                file_type = self._get_file_type(document_path)
                room_id = f"json:{file_type}:{document_path}"

            try:
                room = await self.ydoc_extension.ywebsocket_server.get_room(room_id)
                if room and hasattr(room, "awareness"):
                    for client_id, state in room.awareness.states.items():
                        cursor = state.get("cursor")
                        if cursor:
                            cursors.append(
                                {
                                    "user_id": str(client_id),
                                    "position": cursor.get("position", {"line": 0, "column": 0}),
                                    "selection": cursor.get("selection"),
                                }
                            )
            except Exception as e:
                logger.warning(f"Error querying cursor positions", exc_info=True)

        return cursors

    async def update_cursor_position(
        self,
        document_path: str,
        position: Dict[str, int],
        selection: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update the current user's cursor position."""
        # In a real implementation, this would update the awareness system
        user_id = "current_user"  # Would get from authenticated context

        # For now, just return success
        return {
            "success": True,
            "user_id": user_id,
            "document_path": document_path,
            "position": position,
            "timestamp": IOLoop.current().time(),
        }

    async def get_user_activity(
        self, document_path: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent activity for users."""
        # In a real implementation, this would query the activity system
        # For now, return a basic implementation
        activities = []

        # We could track basic activities in the sessions
        for session_id, session in self._sessions.items():
            if document_path and session.get("path") != document_path:
                continue

            activities.append(
                {
                    "user_id": session.get("user_id", "unknown"),
                    "activity_type": "session",
                    "description": f"Joined {session.get('type')} session",
                    "document_path": session.get("path"),
                    "timestamp": session.get("created_at", 0),
                }
            )

        # Sort by timestamp (newest first)
        activities.sort(key=lambda x: x["timestamp"], reverse=True)

        return activities[:limit]

    async def broadcast_user_activity(
        self,
        activity_type: str,
        description: str,
        document_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Broadcast a user activity to other collaborators."""
        # In a real implementation, this would broadcast to the activity system
        user_id = "current_user"  # Would get from authenticated context

        activity = {
            "user_id": user_id,
            "activity_type": activity_type,
            "description": description,
            "document_path": document_path,
            "metadata": metadata or {},
            "timestamp": IOLoop.current().time(),
        }

        # For now, just return success
        return {"success": True, "activity": activity}

    async def get_active_sessions(
        self, document_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get active collaboration sessions."""
        sessions = list(self._sessions.values())
        if document_path:
            sessions = [s for s in sessions if s.get("path") == document_path]
        return sessions

    async def join_session(self, session_id: str) -> Dict[str, Any]:
        """Join an existing collaboration session."""
        if session_id not in self._sessions:
            return {"success": False, "error": f"Session not found: {session_id}"}

        session = self._sessions[session_id]
        session["joined_at"] = IOLoop.current().time()
        return {
            "success": True,
            "session_id": session_id,
            "timestamp": IOLoop.current().time(),
        }

    async def leave_session(self, session_id: str) -> Dict[str, Any]:
        """Leave a collaboration session."""
        if session_id not in self._sessions:
            return {"success": False, "error": f"Session not found: {session_id}"}

        session = self._sessions[session_id]
        session["left_at"] = IOLoop.current().time()
        return {
            "success": True,
            "session_id": session_id,
            "timestamp": IOLoop.current().time(),
        }

    # Helper methods

    async def _get_collaborator_count(self, room_id: str) -> int:
        """Get the number of collaborators in a room."""
        if not hasattr(self.ydoc_extension, "ywebsocket_server"):
            return 0

        room = await self.ydoc_extension.ywebsocket_server.get_room(room_id)
        if room and hasattr(room, "awareness"):
            # Count connected users (excluding local user)
            return max(0, len(room.awareness.states) - 1)

    def _filter_and_sort_items(
        self, items: List[Dict[str, Any]], path_prefix: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Apply path prefix filter and sort items by last modified date."""
        # Apply path prefix filter if provided
        if path_prefix:
            items = [item for item in items if item["path"].startswith(path_prefix)]

        # Sort by last modified date (newest first)
        items.sort(key=lambda x: x["last_modified"], reverse=True)
        return items

    def _get_file_type(self, path: str) -> str:
        """Determine file type from path."""
        if path.endswith(".ipynb"):
            return "notebook"
        elif path.endswith(".md"):
            return "markdown"
        else:
            return "text"

    async def _get_collaboration_state(self, room: DocumentRoom) -> Dict[str, Any]:
        """Get collaboration state for a room."""
        # In a real implementation, this would query the room's collaboration state
        return {
            "collaborators": 1,
            "version": await room.get_version(),
            "last_activity": IOLoop.current().time(),
        }

    # Methods for app.py integration

    async def get_notebook_content(self, path: str) -> str:
        """Get notebook content as JSON string."""
        notebook = await self.get_notebook(path)
        if notebook:
            return json.dumps(notebook["content"], indent=2)
        return "{}"

    async def get_document_content(self, path: str) -> str:
        """Get document content as string."""
        document = await self.get_document(path)
        if document:
            return document["content"]
        return ""

    async def get_awareness_info(self, resource_type: str) -> str:
        """Get awareness information as JSON string."""
        if resource_type == "presence":
            users = await self.get_online_users()
            return json.dumps(users, indent=2)
        elif resource_type == "activity":
            activities = await self.get_user_activity()
            return json.dumps(activities, indent=2)
        else:
            return "{}"
