"""
RTC Adapter for Jupyter Collaboration.

This module provides an adapter between MCP requests and Jupyter Collaboration's
real-time collaboration (RTC) functionality using YDoc.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, List, Union

from jupyter_server_ydoc.app import YDocExtension
from jupyter_server_ydoc.rooms import DocumentRoom

logger = logging.getLogger(__name__)


class RTCAdapter:
    """Adapter between MCP requests and Jupyter Collaboration functionality."""
    
    def __init__(self):
        """Initialize the RTC adapter."""
        self.ydoc_extension: Optional[YDocExtension] = None
        self._initialized = False
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._user_presence: Dict[str, Dict[str, Any]] = {}
        self._document_forks: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self, server_app):
        """Initialize the adapter with the Jupyter server application."""
        if self._initialized:
            return
        
        # Get the YDocExtension from the server app
        if hasattr(server_app, 'extension_manager'):
            for extension in server_app.extension_manager.extensions:
                if isinstance(extension, YDocExtension):
                    self.ydoc_extension = extension
                    break
        
        if not self.ydoc_extension:
            logger.warning("YDocExtension not found, RTC functionality will be limited")
            # Create a minimal mock for development/testing
            self.ydoc_extension = MockYDocExtension()
        
        self._initialized = True
        logger.info("RTC adapter initialized")
    
    # Notebook operations
    
    async def list_notebooks(self, path_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available notebooks for collaboration."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would query the file system
        # and collaboration state
        notebooks = [
            {
                "path": "/example.ipynb",
                "name": "Example Notebook",
                "collaborative": True,
                "last_modified": "2023-01-01T00:00:00Z",
                "collaborators": 2
            }
        ]
        
        if path_filter:
            notebooks = [n for n in notebooks if path_filter in n["path"]]
        
        return notebooks
    
    async def get_notebook(self, path: str, include_collaboration_state: bool = True) -> Optional[Dict[str, Any]]:
        """Get a notebook's content."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            # Get the document room for this notebook
            room = await self.ydoc_extension.get_room(path, "notebook")
            if not room:
                return None
            
            # Get the document content
            content = await room.get_content()
            
            result = {
                "path": path,
                "content": content,
                "format": "json",
                "type": "notebook"
            }
            
            if include_collaboration_state:
                result["collaboration_state"] = await self._get_collaboration_state(room)
            
            return result
        except Exception as e:
            logger.error(f"Error getting notebook {path}: {e}")
            return None
    
    async def create_notebook_session(self, path: str) -> Dict[str, Any]:
        """Create or retrieve a collaboration session for a notebook."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
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
            "created_at": asyncio.get_event_loop().time()
        }
        
        return {
            "session_id": session_id,
            "room_id": room_id,
            "path": path,
            "status": "active"
        }
    
    async def update_notebook_cell(self, path: str, cell_id: str, content: str, cell_type: Optional[str] = None) -> Dict[str, Any]:
        """Update a notebook cell's content."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            room = await self.ydoc_extension.get_room(path, "notebook")
            if not room:
                raise ValueError(f"Notebook not found: {path}")
            
            # Update the cell content
            await room.update_cell(cell_id, content, cell_type)
            
            return {
                "success": True,
                "cell_id": cell_id,
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error updating notebook cell: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def insert_notebook_cell(self, path: str, content: str, position: int, cell_type: str = "code") -> Dict[str, Any]:
        """Insert a new cell into a notebook."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            room = await self.ydoc_extension.get_room(path, "notebook")
            if not room:
                raise ValueError(f"Notebook not found: {path}")
            
            # Insert the new cell
            cell_id = await room.insert_cell(content, position, cell_type)
            
            return {
                "success": True,
                "cell_id": cell_id,
                "position": position,
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error inserting notebook cell: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_notebook_cell(self, path: str, cell_id: str) -> Dict[str, Any]:
        """Delete a cell from a notebook."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            room = await self.ydoc_extension.get_room(path, "notebook")
            if not room:
                raise ValueError(f"Notebook not found: {path}")
            
            # Delete the cell
            await room.delete_cell(cell_id)
            
            return {
                "success": True,
                "cell_id": cell_id,
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error deleting notebook cell: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def execute_notebook_cell(self, path: str, cell_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute a notebook cell."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            room = await self.ydoc_extension.get_room(path, "notebook")
            if not room:
                raise ValueError(f"Notebook not found: {path}")
            
            # Execute the cell
            result = await room.execute_cell(cell_id, timeout)
            
            return {
                "success": True,
                "cell_id": cell_id,
                "result": result,
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error executing notebook cell: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # Document operations
    
    async def list_documents(self, path_filter: Optional[str] = None, file_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available documents for collaboration."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would query the file system
        # and collaboration state
        documents = [
            {
                "path": "/example.md",
                "name": "Example Document",
                "file_type": "markdown",
                "collaborative": True,
                "last_modified": "2023-01-01T00:00:00Z",
                "collaborators": 1
            },
            {
                "path": "/example.txt",
                "name": "Example Text File",
                "file_type": "text",
                "collaborative": True,
                "last_modified": "2023-01-01T00:00:00Z",
                "collaborators": 0
            }
        ]
        
        if path_filter:
            documents = [d for d in documents if path_filter in d["path"]]
        
        if file_type:
            documents = [d for d in documents if d["file_type"] == file_type]
        
        return documents
    
    async def get_document(self, path: str, include_collaboration_state: bool = True) -> Optional[Dict[str, Any]]:
        """Get a document's content."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            # Determine file type from path
            file_type = self._get_file_type(path)
            
            # Get the document room
            room = await self.ydoc_extension.get_room(path, file_type)
            if not room:
                return None
            
            # Get the document content
            content = await room.get_content()
            
            result = {
                "path": path,
                "content": content,
                "file_type": file_type,
                "type": "document"
            }
            
            if include_collaboration_state:
                result["collaboration_state"] = await self._get_collaboration_state(room)
            
            return result
        except Exception as e:
            logger.error(f"Error getting document {path}: {e}")
            return None
    
    async def create_document_session(self, path: str, file_type: Optional[str] = None) -> Dict[str, Any]:
        """Create or retrieve a collaboration session for a document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
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
            "created_at": asyncio.get_event_loop().time()
        }
        
        return {
            "session_id": session_id,
            "room_id": room_id,
            "path": path,
            "file_type": file_type,
            "status": "active"
        }
    
    async def update_document(self, path: str, content: str, position: int = -1, length: int = 0) -> Dict[str, Any]:
        """Update a document's content."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def insert_text(self, path: str, text: str, position: int) -> Dict[str, Any]:
        """Insert text into a document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error inserting text: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_text(self, path: str, position: int, length: int) -> Dict[str, Any]:
        """Delete text from a document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error deleting text: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_document_history(self, path: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get a document's version history."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
            file_type = self._get_file_type(path)
            room = await self.ydoc_extension.get_room(path, file_type)
            if not room:
                raise ValueError(f"Document not found: {path}")
            
            # Get the document history
            history = await room.get_history(limit)
            
            return history
        except Exception as e:
            logger.error(f"Error getting document history: {e}")
            return []
    
    async def restore_document_version(self, path: str, version_id: str) -> Dict[str, Any]:
        """Restore a document to a previous version."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error restoring document version: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def fork_document(self, path: str, title: Optional[str] = None, 
                          description: Optional[str] = None, synchronize: bool = False) -> Dict[str, Any]:
        """Create a fork of a document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "created_at": asyncio.get_event_loop().time()
            }
            
            return {
                "success": True,
                "fork_id": fork_id,
                "fork_path": fork_path,
                "title": title or f"Fork of {path}",
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error forking document: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def merge_document_fork(self, path: str, fork_id: str) -> Dict[str, Any]:
        """Merge a fork back into the original document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        try:
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
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"Error merging document fork: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # Awareness operations
    
    async def get_online_users(self, document_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get a list of users currently online."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would query the presence system
        users = [
            {
                "id": "user1",
                "name": "User 1",
                "status": "online",
                "last_activity": asyncio.get_event_loop().time(),
                "current_document": "/example.ipynb"
            },
            {
                "id": "user2",
                "name": "User 2",
                "status": "away",
                "last_activity": asyncio.get_event_loop().time() - 300,
                "current_document": "/example.md"
            }
        ]
        
        if document_path:
            users = [u for u in users if u.get("current_document") == document_path]
        
        return users
    
    async def get_user_presence(self, user_id: str, document_path: Optional[str] = None) -> Dict[str, Any]:
        """Get presence information for a specific user."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # Check cached presence
        if user_id in self._user_presence:
            presence = self._user_presence[user_id]
            if document_path and presence.get("current_document") != document_path:
                return {"error": "User not present in specified document"}
            return presence
        
        # Return default presence
        return {
            "user_id": user_id,
            "status": "offline",
            "last_activity": 0,
            "current_document": None
        }
    
    async def set_user_presence(self, status: str = "online", message: Optional[str] = None) -> Dict[str, Any]:
        """Set the current user's presence status."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would update the presence system
        user_id = "current_user"  # Would get from authenticated context
        
        self._user_presence[user_id] = {
            "user_id": user_id,
            "status": status,
            "message": message,
            "last_activity": asyncio.get_event_loop().time()
        }
        
        return {
            "success": True,
            "user_id": user_id,
            "status": status,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    async def get_user_cursors(self, document_path: str) -> List[Dict[str, Any]]:
        """Get cursor positions of users in a document."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would query the awareness system
        return [
            {
                "user_id": "user1",
                "position": {"line": 5, "column": 10},
                "selection": {
                    "start": {"line": 5, "column": 5},
                    "end": {"line": 5, "column": 15}
                }
            }
        ]
    
    async def update_cursor_position(self, document_path: str, position: Dict[str, int], 
                                   selection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update the current user's cursor position."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would update the awareness system
        user_id = "current_user"  # Would get from authenticated context
        
        return {
            "success": True,
            "user_id": user_id,
            "document_path": document_path,
            "position": position,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    async def get_user_activity(self, document_path: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent activity for users."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would query the activity system
        activities = [
            {
                "user_id": "user1",
                "activity_type": "edit",
                "description": "Edited notebook cell",
                "document_path": "/example.ipynb",
                "timestamp": asyncio.get_event_loop().time() - 60
            },
            {
                "user_id": "user2",
                "activity_type": "view",
                "description": "Opened document",
                "document_path": "/example.md",
                "timestamp": asyncio.get_event_loop().time() - 120
            }
        ]
        
        if document_path:
            activities = [a for a in activities if a.get("document_path") == document_path]
        
        return activities[:limit]
    
    async def broadcast_user_activity(self, activity_type: str, description: str, 
                                    document_path: Optional[str] = None, 
                                    metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Broadcast a user activity to other collaborators."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        # In a real implementation, this would broadcast to the activity system
        user_id = "current_user"  # Would get from authenticated context
        
        activity = {
            "user_id": user_id,
            "activity_type": activity_type,
            "description": description,
            "document_path": document_path,
            "metadata": metadata or {},
            "timestamp": asyncio.get_event_loop().time()
        }
        
        return {
            "success": True,
            "activity": activity
        }
    
    async def get_active_sessions(self, document_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get active collaboration sessions."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        sessions = list(self._sessions.values())
        
        if document_path:
            sessions = [s for s in sessions if s.get("path") == document_path]
        
        return sessions
    
    async def join_session(self, session_id: str) -> Dict[str, Any]:
        """Join an existing collaboration session."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        
        session = self._sessions[session_id]
        session["joined_at"] = asyncio.get_event_loop().time()
        
        return {
            "success": True,
            "session_id": session_id,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    async def leave_session(self, session_id: str) -> Dict[str, Any]:
        """Leave a collaboration session."""
        if not self._initialized:
            raise RuntimeError("RTCAdapter not initialized")
        
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        
        session = self._sessions[session_id]
        session["left_at"] = asyncio.get_event_loop().time()
        
        return {
            "success": True,
            "session_id": session_id,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    # Helper methods
    
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
            "last_activity": asyncio.get_event_loop().time()
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


class MockYDocExtension:
    """Mock YDocExtension for development/testing."""
    
    def __init__(self):
        self.rooms = {}
    
    async def get_room(self, path: str, file_type: str):
        """Get or create a room for a document."""
        key = f"{path}:{file_type}"
        if key not in self.rooms:
            self.rooms[key] = MockDocumentRoom(path, file_type)
        return self.rooms[key]


class MockDocumentRoom:
    """Mock DocumentRoom for development/testing."""
    
    def __init__(self, path: str, file_type: str):
        self.path = path
        self.file_type = file_type
        self.content = self._get_default_content()
        self.version = 1
    
    def _get_default_content(self) -> Union[str, Dict]:
        """Get default content based on file type."""
        if self.file_type == "notebook":
            return {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": ["print('Hello, World!')"]
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 4
            }
        else:
            return "# Default Document\n\nThis is a default document."
    
    async def get_content(self) -> Union[str, Dict]:
        """Get the document content."""
        return self.content
    
    async def update_cell(self, cell_id: str, content: str, cell_type: Optional[str] = None):
        """Update a notebook cell."""
        if isinstance(self.content, dict) and "cells" in self.content:
            for cell in self.content["cells"]:
                # In a real implementation, cells would have IDs
                if cell.get("source") and content in cell["source"][0]:
                    cell["source"] = [content]
                    if cell_type:
                        cell["cell_type"] = cell_type
                    break
        self.version += 1
    
    async def insert_cell(self, content: str, position: int, cell_type: str = "code") -> str:
        """Insert a new cell into a notebook."""
        if isinstance(self.content, dict) and "cells" in self.content:
            cell_id = f"cell_{len(self.content['cells'])}"
            new_cell = {
                "cell_type": cell_type,
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [content]
            }
            self.content["cells"].insert(position, new_cell)
            self.version += 1
            return cell_id
        return ""
    
    async def delete_cell(self, cell_id: str):
        """Delete a cell from a notebook."""
        if isinstance(self.content, dict) and "cells" in self.content:
            # In a real implementation, cells would have IDs
            self.version += 1
    
    async def execute_cell(self, cell_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute a notebook cell."""
        return {
            "execution_count": 1,
            "outputs": [
                {
                    "name": "stdout",
                    "output_type": "stream",
                    "text": ["Hello, World!\n"]
                }
            ]
        }
    
    async def update_content(self, content: str, position: int = -1, length: int = 0):
        """Update document content."""
        if position == -1:
            # Replace entire content
            self.content = content
        else:
            # Replace partial content
            if isinstance(self.content, str):
                self.content = self.content[:position] + content + self.content[position + length:]
        self.version += 1
    
    async def insert_text(self, text: str, position: int) -> int:
        """Insert text into a document."""
        if isinstance(self.content, str):
            self.content = self.content[:position] + text + self.content[position:]
            self.version += 1
            return len(self.content)
        return 0
    
    async def delete_text(self, position: int, length: int) -> int:
        """Delete text from a document."""
        if isinstance(self.content, str):
            self.content = self.content[:position] + self.content[position + length:]
            self.version += 1
            return len(self.content)
        return 0
    
    async def get_version(self) -> int:
        """Get the document version."""
        return self.version
    
    async def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get document history."""
        return [
            {
                "version": self.version - 1,
                "timestamp": asyncio.get_event_loop().time() - 3600,
                "changes": "Initial content"
            }
        ]
    
    async def restore_version(self, version_id: str):
        """Restore a document version."""
        # In a real implementation, this would restore from history
        self.version += 1