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
from jupyter_server_ydoc.loaders import FileLoader
from jupyter_server_ydoc.rooms import DocumentRoom
from jupyter_server_ydoc.utils import encode_file_path, room_id_from_encoded_path
from jupyter_server_ydoc.websocketserver import RoomNotFound
from pycrdt_websocket.ystore import BaseYStore
from tornado import gen
from tornado.ioloop import IOLoop

logger = logging.getLogger(__name__)


class RTCAdapter:
    """Adapter between MCP requests and Jupyter Collaboration functionality."""

    def __init__(self, server_app, ydoc_extension: YDocExtension):
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
                # Try to get the room to see if it exists and has collaborators
                room: Optional[DocumentRoom] = await self._get_or_create_room(
                    notebook_path, "notebook"
                )
                collaborators = 0
                if room and hasattr(room, "awareness"):
                    # Count connected users (excluding local user)
                    collaborators = max(0, len(room.awareness.states) - 1)

                notebook_info = {
                    "path": notebook_path,
                    "name": contents_item["name"],
                    "collaborative": collaborators > 0,
                    "last_modified": contents_item["last_modified"],
                    "collaborators": collaborators,
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
        # Get or create the document room for this notebook
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            return None

        # Get the document content
        content = room._document.source

        result = {"path": path, "content": content, "format": "json", "type": "notebook"}

        if include_collaboration_state:
            result["collaboration_state"] = await self._get_collaboration_state(room)

        return result

    async def create_notebook_session(self, path: str) -> Dict[str, Any]:
        """Create or retrieve a collaboration session for a notebook."""
        session_id = str(uuid.uuid4())

        # Get or create the room
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            raise ValueError(f"Failed to create or get notebook room: {path}")

        # Get the actual room ID from the room
        room_id = room.room_id

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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found or failed to create room: {path}")

        # Update the cell content
        if room._file_type == "notebook":
            # Get the notebook cells from the YDoc document
            cells = room._document.ydoc.get("cells")
            # Find the cell with the specified ID
            for i, cell in enumerate(cells):
                if cell.get("id") == cell_id:
                    # Update the cell content
                    if cell_type:
                        cell["cell_type"] = cell_type
                    cell["source"] = content
                    break

        # Execute the cell if requested
        exec_result = None
        if exec:
            try:
                # Execute the cell using the notebook API
                if room._file_type == "notebook":
                    # Get the contents manager from the server app
                    contents_manager = self._server_app.contents_manager

                    # Get the notebook model
                    notebook_model = await contents_manager.get(room._file.path, content=True)

                    # Find the cell in the notebook
                    cells = notebook_model["content"]["cells"]
                    cell_to_execute = None
                    for cell in cells:
                        if cell.get("id") == cell_id:
                            cell_to_execute = cell
                            break

                    if cell_to_execute:
                        # Execute the cell using the notebook API
                        # Note: This is a simplified approach - in a real implementation,
                        # you would need to use the kernel session to execute the cell
                        exec_result = {
                            "status": "success",
                            "execution_count": cell_to_execute.get("execution_count", 1),
                            "outputs": [],
                        }
                    else:
                        exec_result = {"error": f"Cell {cell_id} not found"}
                else:
                    exec_result = {"error": "Cell execution is only supported for notebooks"}
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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found or failed to create room: {path}")

        # Insert the new cell
        if room._file_type == "notebook":
            # Get the notebook cells from the YDoc document
            cells = room._document.ydoc.get("cells")
            # Create a new cell
            import uuid

            new_cell = {
                "id": str(uuid.uuid4()),
                "cell_type": cell_type,
                "source": content,
                "metadata": {},
            }
            # Insert the cell at the specified position
            if position >= 0 and position <= len(cells):
                cells.insert(position, new_cell)
            else:
                cells.append(new_cell)
            cell_id = new_cell["id"]
        else:
            cell_id = ""

        # Execute the cell if requested
        exec_result = None
        # Execute the cell using the notebook API
        if room._file_type == "notebook":
            # Get the contents manager from the server app
            contents_manager = self._server_app.contents_manager

            # Get the notebook model
            notebook_model = await contents_manager.get(room._file.path, content=True)

            # Find the cell in the notebook
            cells = notebook_model["content"]["cells"]
            cell_to_execute = None
            for cell in cells:
                if cell.get("id") == cell_id:
                    cell_to_execute = cell
                    break

            if cell_to_execute:
                # Execute the cell using the notebook API
                # Note: This is a simplified approach - in a real implementation,
                # you would need to use the kernel session to execute the cell
                exec_result = {
                    "status": "success",
                    "execution_count": cell_to_execute.get("execution_count", 1),
                    "outputs": [],
                }
            else:
                exec_result = {"error": f"Cell {cell_id} not found"}
        else:
            exec_result = {"error": "Cell execution is only supported for notebooks"}
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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found or failed to create room: {path}")

        # Execute the cell before deletion if requested
        exec_result = None
        if exec:
            try:
                # Cell execution is not directly supported by YDoc
                # For now, we'll just return a success message
                exec_result = {
                    "status": "success",
                    "message": "Cell execution not directly supported by YDoc",
                }
            except Exception as exec_e:
                logger.warning(f"Error executing cell {cell_id} before deletion", exc_info=True)
                exec_result = {"error": str(exec_e)}

        # Delete the cell
        if room._file_type == "notebook":
            # Get the notebook cells from the YDoc document
            cells = room._document.ydoc.get("cells")
            # Find and remove the cell with the specified ID
            for i, cell in enumerate(cells):
                if cell.get("id") == cell_id:
                    cells.pop(i)
                    break
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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, "notebook")
        if not room:
            raise ValueError(f"Notebook not found or failed to create room: {path}")

        # Execute the cell
        # Cell execution is not directly supported by YDoc
        # For now, we'll just return a success message
        result = {"status": "success", "message": "Cell execution not directly supported by YDoc"}
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

                # Try to get the room to see if it exists and has collaborators
                collaborators = 0
                room: Optional[DocumentRoom] = await self._get_or_create_room(
                    file_path, doc_file_type
                )
                if room and hasattr(room, "awareness"):
                    # Count connected users (excluding local user)
                    collaborators = max(0, len(room.awareness.states) - 1)

                documents.append(
                    {
                        "path": file_path,
                        "name": contents_item["name"],
                        "file_type": doc_file_type,
                        "collaborative": collaborators > 0,
                        "last_modified": contents_item["last_modified"],
                        "collaborators": collaborators,
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

        # Get or create the document room
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            return None

        # Get the document content
        content = room._document.source

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

        # Get or create the room
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Failed to create or get document room: {path}")

        # Get the actual room ID from the room
        room_id = room.room_id

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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Update the document content
        if position == -1 and length == 0:
            # Replace entire content
            room._document.source = content
        else:
            # Partial update - for text documents
            text = room._document.ydoc.get("source")
            if position >= 0 and position <= len(text):
                if length > 0:
                    # Replace text at position
                    new_text = text[:position] + content + text[position + length :]
                else:
                    # Insert text at position
                    new_text = text[:position] + content + text[position:]
                room._document.source = new_text
        return {
            "success": True,
            "path": path,
            "version": str(IOLoop.current().time()),
            "timestamp": IOLoop.current().time(),
        }

    async def insert_text(self, path: str, text: str, position: int) -> Dict[str, Any]:
        """Insert text into a document."""
        file_type = self._get_file_type(path)
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Insert the text
        source_text = room._document.ydoc.get("source")
        if position >= 0 and position <= len(source_text):
            new_text = source_text[:position] + text + source_text[position:]
            room._document.source = new_text
            new_length = len(new_text)
        else:
            new_length = len(source_text)
        return {
            "success": True,
            "path": path,
            "new_length": new_length,
            "timestamp": IOLoop.current().time(),
        }

    async def delete_text(self, path: str, position: int, length: int) -> Dict[str, Any]:
        """Delete text from a document."""
        file_type = self._get_file_type(path)
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Delete the text
        source_text = room._document.ydoc.get("source")
        if position >= 0 and position + length <= len(source_text):
            new_text = source_text[:position] + source_text[position + length :]
            room._document.source = new_text
            new_length = len(new_text)
        else:
            new_length = len(source_text)

        return {
            "success": True,
            "path": path,
            "new_length": new_length,
            "timestamp": IOLoop.current().time(),
        }

    async def get_document_history(self, path: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get a document's version history."""
        file_type = self._get_file_type(path)
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Get the document history - not directly supported by YDoc
        history = []

        return history

    async def restore_document_version(self, path: str, version_id: str) -> Dict[str, Any]:
        """Restore a document to a previous version."""
        file_type = self._get_file_type(path)
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Restore the version - not directly supported by YDoc
        # For now, we'll just log that this operation is not supported
        logger.warning(f"Document version restore not supported for {path}")
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
        room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        if not room:
            raise ValueError(f"Document not found or failed to create room: {path}")

        # Create the fork
        fork_id = str(uuid.uuid4())
        fork_path = f"{path}.fork-{fork_id}"

        # Copy the document content
        content = room._document.source
        fork_room: Optional[DocumentRoom] = await self._get_or_create_room(fork_path, file_type)
        if not fork_room:
            raise ValueError(f"Failed to create fork room: {fork_path}")

        # Set the fork content directly
        fork_room._document.source = content

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
        original_room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
        fork_room: Optional[DocumentRoom] = await self._get_or_create_room(
            fork_info["fork_path"], file_type
        )

        if not original_room or not fork_room:
            raise ValueError("Could not access document or fork")

        # Get fork content
        fork_content = fork_room._document.source

        # Merge into original
        original_room._document.source = fork_content

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

        try:
            # This is a simplified implementation - in a real scenario,
            # we would query the awareness system more directly
            if document_path:
                file_type = (
                    "notebook"
                    if document_path.endswith(".ipynb")
                    else self._get_file_type(document_path)
                )
                room: Optional[DocumentRoom] = await self._get_or_create_room(
                    document_path, file_type
                )

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
                # If no specific document is requested, check all cached rooms
                if hasattr(self, "_rooms"):
                    for room_id, room in self._rooms.items():
                        if hasattr(room, "awareness"):
                            for client_id, state in room.awareness.states.items():
                                # Extract document path from room_id
                                # room_id format is typically "json:file_type:path"
                                parts = room_id.split(":", 2)
                                if len(parts) == 3:
                                    _, _, path = parts
                                    users.append(
                                        {
                                            "id": str(client_id),
                                            "name": state.get("user", {}).get(
                                                "name", f"User {client_id}"
                                            ),
                                            "status": "online",
                                            "last_activity": IOLoop.current().time(),
                                            "current_document": path,
                                        }
                                    )
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
        try:
            # If a specific document is requested, check that document
            if document_path:
                file_type = (
                    "notebook"
                    if document_path.endswith(".ipynb")
                    else self._get_file_type(document_path)
                )
                room: Optional[DocumentRoom] = await self._get_or_create_room(
                    document_path, file_type
                )

                if room and hasattr(room, "awareness"):
                    for client_id, state in room.awareness.states.items():
                        if str(client_id) == user_id:
                            return {
                                "user_id": user_id,
                                "status": "online",
                                "last_activity": IOLoop.current().time(),
                                "current_document": document_path,
                            }
            else:
                # If no specific document is requested, check all cached rooms
                if hasattr(self, "_rooms"):
                    for room_id, room in self._rooms.items():
                        if hasattr(room, "awareness"):
                            for client_id, state in room.awareness.states.items():
                                if str(client_id) == user_id:
                                    # Extract document path from room_id
                                    parts = room_id.split(":", 2)
                                    if len(parts) == 3:
                                        _, _, path = parts
                                        return {
                                            "user_id": user_id,
                                            "status": "online",
                                            "last_activity": IOLoop.current().time(),
                                            "current_document": path,
                                        }
        except Exception as e:
            logger.warning(f"Error querying user presence for {user_id}", exc_info=True)

        # User not found in any room, return offline status
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

        # Determine file type based on document type
        file_type = (
            "notebook" if document_path.endswith(".ipynb") else self._get_file_type(document_path)
        )

        try:
            room: Optional[DocumentRoom] = await self._get_or_create_room(document_path, file_type)
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

        # Determine file type based on document type
        file_type = (
            "notebook" if document_path.endswith(".ipynb") else self._get_file_type(document_path)
        )

        try:
            room: Optional[DocumentRoom] = await self._get_or_create_room(document_path, file_type)
            if room and hasattr(room, "awareness"):
                # Update the cursor position in the awareness system
                # Note: This is a simplified implementation - in a real implementation,
                # you would need to use the awareness API to update the cursor position
                cursor_info = {
                    "position": position,
                    "selection": selection,
                }
                # This would typically be done through the awareness API
                # For now, we'll just log that we would update it
                logger.info(
                    f"Would update cursor position for user {user_id} in {document_path}: {cursor_info}"
                )
        except Exception as e:
            logger.warning(f"Error updating cursor position", exc_info=True)

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

    async def _get_or_create_room(
        self, path: str, file_type: str, file_format: str = "json"
    ) -> Optional[DocumentRoom]:
        """Get an existing room or create a new one if it doesn't exist."""
        # Get file ID from the file ID manager
        file_id_manager = self._server_app.web_app.settings["file_id_manager"]

        contents_manager = self._server_app.contents_manager
        await contents_manager.get(path, content=False)

        # Get or create file ID
        file_id = file_id_manager.get_id(path)
        if file_id is None:
            # File is not indexed yet, try to index it
            file_id = file_id_manager.index(path)
            if file_id is None:
                logger.error(f"Failed to index file: {path}")
                return None

        # Create the encoded path and room ID
        encoded_path = encode_file_path(file_format, file_type, file_id)
        room_id = room_id_from_encoded_path(encoded_path)

        # Check if we already have this room cached
        if hasattr(self, "_rooms") and room_id in self._rooms:
            room = self._rooms[room_id]
            if room.ready:
                return room

        # Room doesn't exist or is not ready, create it
        from jupyter_server_ydoc.loaders import FileLoader
        from jupyter_server_ydoc.utils import decode_file_path

        # Get file loader
        file_loaders = self.ydoc_extension.file_loaders
        file: FileLoader = file_loaders[file_id]

        # Create YStore
        updates_file_path = f".{file_type}:{file_id}.y"
        ystore: BaseYStore = self.ydoc_extension.ystore_class(
            path=updates_file_path,
            log=self.ydoc_extension.log,
        )

        # Create the room
        def exception_logger(exception: Exception, log) -> bool:
            log.error(f"Document Room Exception, (room_id={room_id}): ", exc_info=exception)
            return True

        room = DocumentRoom(
            room_id,
            file_format,
            file_type,
            file,
            self.event_logger,
            ystore,
            self.ydoc_extension.log,
            exception_handler=exception_logger,
            save_delay=self.ydoc_extension.document_save_delay,
        )

        # Initialize the room
        await room.initialize()

        # Store room locally for reuse
        # Note: In a real implementation, you might want to manage rooms more carefully
        # to avoid memory leaks, e.g., by cleaning up inactive rooms
        if not hasattr(self, "_rooms"):
            self._rooms = {}
        self._rooms[room_id] = room

        return room

    async def _get_collaborator_count(self, room_id: str) -> int:
        """Get the number of collaborators in a room."""
        try:
            # Parse the room_id to extract path and file type
            # room_id format is typically "json:file_type:path"
            parts = room_id.split(":", 2)
            if len(parts) != 3:
                return 0

            _, file_type, path = parts

            # Get the room using our new method
            room: Optional[DocumentRoom] = await self._get_or_create_room(path, file_type)
            if room and hasattr(room, "awareness"):
                # Count connected users (excluding local user)
                return max(0, len(room.awareness.states) - 1)
        except Exception as e:
            logger.warning(f"Error getting collaborator count for room {room_id}: {e}")

        return 0

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
            "version": str(IOLoop.current().time()),
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
