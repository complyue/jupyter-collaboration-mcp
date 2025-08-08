__all__ = [
    "define_notebook_tools",
    "define_document_tools",
    "define_awareness_tools",
]

from typing import Any, Tuple, Dict, List, Optional

from mcp.server import FastMCP
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData

from .rtc_adapter import RTCAdapter


def define_notebook_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all notebook collaboration tools using fastmcp."""

    @fastmcp.tool(
        description="""List available notebooks for collaboration.

This tool allows AI agents to discover notebooks that are available for 
real-time collaboration. Returns a tuple containing:
- A description string summarizing the results
- A list of notebook info objects with paths and collaboration status

Parameters:
- path_prefix (Optional[str]): Limit results to paths starting with this prefix
- max_results (Optional[int]): Maximum number of notebooks to return

Examples:
• list_notebooks() - List all notebooks
• list_notebooks(path_prefix='/projects/data-science/') - List notebooks in a specific directory
• list_notebooks(max_results=5) - List at most 5 notebooks
"""
    )
    async def list_notebooks(
        path_prefix: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        notebooks = await rtc_adapter.list_notebooks(path_prefix)

        # Apply max_results limit if specified
        if max_results is not None and len(notebooks) > max_results:
            description = f"Found {len(notebooks)} notebooks (showing first {max_results} results)"
            notebooks = notebooks[:max_results]
        else:
            description = f"Found {len(notebooks)} notebooks available for collaboration"

        return description, notebooks

    @fastmcp.tool(
        description="Get a notebook's content including cells and collaboration metadata.",
    )
    async def get_notebook(path: str, include_collaboration_state: bool = True) -> Dict[str, Any]:
        """
        Get a notebook's content with optional collaboration state.

        This tool retrieves the full content of a notebook, including all cells,
        their contents, and optionally collaboration metadata like active users
        and change history.

        Args:
            path: Path to the notebook (required)
            include_collaboration_state: Whether to include collaboration metadata (default: True)

        Returns:
            Notebook content as JSON with cells and metadata

        Example:
            # Get notebook with collaboration state
            notebook = await get_notebook(path="/projects/analysis.ipynb")

            # Get just the notebook content
            notebook = await get_notebook(path="/projects/analysis.ipynb", include_collaboration_state=False)
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        notebook = await rtc_adapter.get_notebook(path, include_collaboration_state)

        if not notebook:
            raise ErrorData(
                code=INTERNAL_ERROR,
                message=f"Notebook not found: {path}",
            )

        return notebook

    @fastmcp.tool(
        description="Create or retrieve a collaboration session for a notebook.",
    )
    async def create_notebook_session(path: str) -> Dict[str, Any]:
        """
        Create or retrieve a collaboration session for a notebook.

        This tool establishes a real-time collaboration session for a notebook,
        enabling multiple users to collaborate simultaneously. If a session
        already exists, it returns the existing session information.

        Args:
            path: Path to the notebook (required)

        Returns:
            Session information including room ID and session ID

        Example:
            session = await create_notebook_session(path="/projects/analysis.ipynb")
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        session = await rtc_adapter.create_notebook_session(path)
        return session

    @fastmcp.tool(
        description="Update the content of a specific cell in a notebook.",
    )
    async def update_notebook_cell(
        path: str, cell_id: str, content: str, cell_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update a notebook cell's content.

        This tool allows modification of an existing cell's content in a notebook.
        The change is immediately synchronized with all collaborators in real-time.

        Args:
            path: Path to the notebook (required)
            cell_id: ID of the cell to update (required)
            content: New content for the cell (required)
            cell_type: Type of cell (code, markdown, etc.) - optional, keeps existing type if not specified

        Returns:
            Confirmation of the update with timestamp

        Example:
            result = await update_notebook_cell(
                path="/projects/analysis.ipynb",
                cell_id="cell-123",
                content="print('Hello, World!')",
                cell_type="code"
            )
        """
        if not all([path, cell_id, content]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path, cell_id, and content are required",
            )

        result = await rtc_adapter.update_notebook_cell(path, cell_id, content, cell_type)
        return result

    @fastmcp.tool(
        description="Insert a new cell into a notebook at a specific position.",
    )
    async def insert_notebook_cell(
        path: str, content: str, position: int, cell_type: str = "code"
    ) -> Dict[str, Any]:
        """
        Insert a new cell into a notebook.

        This tool creates a new cell at the specified position in a notebook.
        The insertion is immediately synchronized with all collaborators.

        Args:
            path: Path to the notebook (required)
            content: Content for the new cell (required)
            position: Position to insert the cell (0-based index, required)
            cell_type: Type of cell (code, markdown, etc.) - defaults to "code"

        Returns:
            ID of the newly created cell and confirmation

        Example:
            result = await insert_notebook_cell(
                path="/projects/analysis.ipynb",
                content="# Analysis Results\nprint('Analysis complete')",
                position=2,
                cell_type="markdown"
            )
        """
        if not all([path, content, position is not None]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path, content, and position are required",
            )

        result = await rtc_adapter.insert_notebook_cell(path, content, position, cell_type)
        return result

    @fastmcp.tool(description="Delete a cell from a notebook.")
    async def delete_notebook_cell(path: str, cell_id: str) -> Dict[str, Any]:
        """
        Delete a cell from a notebook.

        This tool removes a specified cell from a notebook. The deletion is
        immediately synchronized with all collaborators in real-time.

        Args:
            path: Path to the notebook (required)
            cell_id: ID of the cell to delete (required)

        Returns:
            Confirmation of the deletion

        Example:
            result = await delete_notebook_cell(
                path="/projects/analysis.ipynb",
                cell_id="cell-123"
            )
        """
        if not all([path, cell_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and cell_id are required",
            )

        result = await rtc_adapter.delete_notebook_cell(path, cell_id)
        return result

    @fastmcp.tool(
        description="Execute a specific cell in a notebook and return the results.",
    )
    async def execute_notebook_cell(path: str, cell_id: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute a notebook cell.

        This tool runs the code in a specified notebook cell and returns the
        execution results, including output, execution count, and any errors.
        The execution is visible to all collaborators in real-time.

        Args:
            path: Path to the notebook (required)
            cell_id: ID of the cell to execute (required)
            timeout: Execution timeout in seconds (default: 30)

        Returns:
            Execution result including output, execution count, and any errors

        Example:
            result = await execute_notebook_cell(
                path="/projects/analysis.ipynb",
                cell_id="cell-123",
                timeout=60
            )
        """
        if not all([path, cell_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and cell_id are required",
            )

        result = await rtc_adapter.execute_notebook_cell(path, cell_id, timeout)
        return result


def define_document_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all document collaboration tools using fastmcp."""

    @fastmcp.tool(
        description="List available documents for collaboration with optional filtering.",
    )
    async def list_documents(
        path_filter: Optional[str] = None, file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List available documents for collaboration.

        This tool allows AI agents to discover documents that are available for
        real-time collaboration. It supports filtering by path and file type.

        Args:
            path_filter: Optional path filter to limit results to a specific directory
            file_type: Optional file type filter (e.g., 'file', 'text', 'markdown')

        Returns:
            List of documents with their paths, types, and collaboration status

        Example:
            # List all documents
            documents = await list_documents()

            # List markdown documents in a specific directory
            documents = await list_documents(
                path_filter="/projects/docs/",
                file_type="markdown"
            )
        """
        documents = await rtc_adapter.list_documents(path_filter, file_type)
        return documents

    @fastmcp.tool(
        description="Get a document's content including collaboration metadata.",
    )
    async def get_document(path: str, include_collaboration_state: bool = True) -> Dict[str, Any]:
        """
        Get a document's content with optional collaboration state.

        This tool retrieves the full content of a document, optionally including
        collaboration metadata like active users, cursors, and change history.

        Args:
            path: Path to the document (required)
            include_collaboration_state: Whether to include collaboration metadata (default: True)

        Returns:
            Document content as JSON with optional collaboration metadata

        Example:
            # Get document with collaboration state
            document = await get_document(path="/projects/README.md")

            # Get just the document content
            document = await get_document(
                path="/projects/README.md",
                include_collaboration_state=False
            )
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        document = await rtc_adapter.get_document(path, include_collaboration_state)

        if not document:
            raise ErrorData(
                code=INTERNAL_ERROR,
                message=f"Document not found: {path}",
            )

        return document

    @fastmcp.tool(
        description="Create or retrieve a collaboration session for a document.",
    )
    async def create_document_session(path: str, file_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Create or retrieve a collaboration session for a document.

        This tool establishes a real-time collaboration session for a document,
        enabling multiple users to collaborate simultaneously. If a session
        already exists, it returns the existing session information.

        Args:
            path: Path to the document (required)
            file_type: Type of the document (auto-detected if not provided)

        Returns:
            Session information including room ID and session ID

        Example:
            session = await create_document_session(
                path="/projects/README.md",
                file_type="markdown"
            )
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        session = await rtc_adapter.create_document_session(path, file_type)
        return session

    @fastmcp.tool(
        description="Update a document's content with precise position control.",
    )
    async def update_document(
        path: str, content: str, position: int = -1, length: int = 0
    ) -> Dict[str, Any]:
        """
        Update a document's content.

        This tool allows precise updates to document content with control over
        the position and length of the update. The change is immediately
        synchronized with all collaborators.

        Args:
            path: Path to the document (required)
            content: New content (required)
            position: Position to start update (-1 for append, default: -1)
            length: Length of content to replace (0 for insert, default: 0)

        Returns:
            Confirmation of the update with version information

        Example:
            # Append content to document
            result = await update_document(
                path="/projects/README.md",
                content="\n## New Section\nContent here"
            )

            # Replace content at specific position
            result = await update_document(
                path="/projects/README.md",
                content="Updated title",
                position=0,
                length=10
            )
        """
        if not all([path, content]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and content are required",
            )

        result = await rtc_adapter.update_document(path, content, position, length)
        return result

    @fastmcp.tool(description="Insert text at a specific position in a document.")
    async def insert_text(path: str, text: str, position: int) -> Dict[str, Any]:
        """
        Insert text into a document.

        This tool inserts text at a specific position in a document, shifting
        existing content to the right. The insertion is immediately synchronized
        with all collaborators.

        Args:
            path: Path to the document (required)
            text: Text to insert (required)
            position: Position to insert at (0-based index, required)

        Returns:
            Confirmation of the insertion with new document length

        Example:
            result = await insert_text(
                path="/projects/README.md",
                text="## New Section\n",
                position=100
            )
        """
        if not all([path, text, position is not None]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path, text, and position are required",
            )

        result = await rtc_adapter.insert_text(path, text, position)
        return result

    @fastmcp.tool(description="Delete text from a specific position in a document.")
    async def delete_text(path: str, position: int, length: int) -> Dict[str, Any]:
        """
        Delete text from a document.

        This tool removes text from a specific position in a document, shifting
        remaining content to the left. The deletion is immediately synchronized
        with all collaborators.

        Args:
            path: Path to the document (required)
            position: Position to start deletion (0-based index, required)
            length: Length of text to delete (required)

        Returns:
            Confirmation of the deletion with new document length

        Example:
            result = await delete_text(
                path="/projects/README.md",
                position=100,
                length=20
            )
        """
        if not all([path, position is not None, length is not None]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path, position, and length are required",
            )

        result = await rtc_adapter.delete_text(path, position, length)
        return result

    @fastmcp.tool(description="Get a document's version history and change log.")
    async def get_document_history(path: str, limit: int = 10) -> Dict[str, Any]:
        """
        Get a document's version history.

        This tool retrieves the version history of a document, including
        timestamps, change summaries, and author information for each version.

        Args:
            path: Path to the document (required)
            limit: Maximum number of history entries to return (default: 10)

        Returns:
            List of document versions with timestamps and change summaries

        Example:
            history = await get_document_history(
                path="/projects/README.md",
                limit=20
            )
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        history = await rtc_adapter.get_document_history(path, limit)
        return history

    @fastmcp.tool(
        description="Restore a document to a previous version from history.",
    )
    async def restore_document_version(path: str, version_id: str) -> Dict[str, Any]:
        """
        Restore a document to a previous version.

        This tool reverts a document to a specific version from its history.
        This operation creates a new version in the history and is synchronized
        with all collaborators.

        Args:
            path: Path to the document (required)
            version_id: ID of the version to restore (required)

        Returns:
            Confirmation of the restoration

        Example:
            result = await restore_document_version(
                path="/projects/README.md",
                version_id="version-123"
            )
        """
        if not all([path, version_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and version_id are required",
            )

        result = await rtc_adapter.restore_document_version(path, version_id)
        return result

    @fastmcp.tool(description="Create a fork of a document for parallel editing.")
    async def fork_document(
        path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        synchronize: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a fork of a document.

        This tool creates a copy of a document that can be edited independently.
        Forks can be merged back into the original document later.

        Args:
            path: Path to the document to fork (required)
            title: Title for the forked document (optional)
            description: Description for the forked document (optional)
            synchronize: Whether to keep the fork synchronized with the original (default: False)

        Returns:
            Fork information including fork ID

        Example:
            fork = await fork_document(
                path="/projects/README.md",
                title="README - Experimental Changes",
                description="Testing new documentation structure",
                synchronize=False
            )
        """
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        result = await rtc_adapter.fork_document(path, title, description, synchronize)
        return result

    @fastmcp.tool(description="Merge a fork back into the original document.")
    async def merge_document_fork(path: str, fork_id: str) -> Dict[str, Any]:
        """
        Merge a fork back into the original document.

        This tool merges changes from a fork back into the original document.
        The merge operation handles conflicts and creates a new version.

        Args:
            path: Path to the original document (required)
            fork_id: ID of the fork to merge (required)

        Returns:
            Confirmation of the merge with conflict resolution information

        Example:
            result = await merge_document_fork(
                path="/projects/README.md",
                fork_id="fork-123"
            )
        """
        if not all([path, fork_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and fork_id are required",
            )

        result = await rtc_adapter.merge_document_fork(path, fork_id)
        return result


def define_awareness_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all user awareness and presence tools using fastmcp."""

    @fastmcp.tool(
        description="Get a list of users currently online in the collaboration space.",
    )
    async def get_online_users(document_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a list of users currently online.

        This tool retrieves information about users who are currently active
        in the collaboration space, with optional filtering by document.

        Args:
            document_path: Optional document path to filter users for a specific document

        Returns:
            List of online users with their identity information and status

        Example:
            # Get all online users
            users = await get_online_users()

            # Get users for a specific document
            users = await get_online_users(document_path="/projects/README.md")
        """
        users = await rtc_adapter.get_online_users(document_path)
        return users

    @fastmcp.tool(description="Get presence information for a specific user.")
    async def get_user_presence(
        user_id: str, document_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get presence information for a specific user.

        This tool retrieves detailed presence information for a user, including
        their status, last activity, and current document context.

        Args:
            user_id: ID of the user (required)
            document_path: Optional document path to check presence in a specific document

        Returns:
            User presence information including status, last activity, and current document

        Example:
            presence = await get_user_presence(user_id="user-123")

            # Check presence in a specific document
            presence = await get_user_presence(
                user_id="user-123",
                document_path="/projects/README.md"
            )
        """
        if not user_id:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="User ID is required",
            )

        presence = await rtc_adapter.get_user_presence(user_id, document_path)
        return presence

    @fastmcp.tool(
        description="Set the current user's presence status and optional message.",
    )
    async def set_user_presence(
        status: str = "online", message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Set the current user's presence status.

        This tool allows the current user to update their presence status,
        making it visible to other collaborators in the workspace.

        Args:
            status: Presence status (online, away, busy, offline) - default: "online"
            message: Optional status message to provide additional context

        Returns:
            Confirmation of the presence update

        Example:
            # Set status to away with a message
            result = await set_user_presence(
                status="away",
                message="In a meeting, back soon"
            )

            # Set status to busy
            result = await set_user_presence(status="busy")
        """
        result = await rtc_adapter.set_user_presence(status, message)
        return result

    @fastmcp.tool(description="Get cursor positions of users in a document.")
    async def get_user_cursors(document_path: str) -> Dict[str, Any]:
        """
        Get cursor positions of users in a document.

        This tool retrieves the current cursor positions and selections of all
        users collaborating on a specific document.

        Args:
            document_path: Path to the document (required)

        Returns:
            List of user cursor positions with line, column, and selection information

        Example:
            cursors = await get_user_cursors(document_path="/projects/README.md")
        """
        if not document_path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Document path is required",
            )

        cursors = await rtc_adapter.get_user_cursors(document_path)
        return cursors

    @fastmcp.tool(
        description="Update the current user's cursor position and selection in a document.",
    )
    async def update_cursor_position(
        document_path: str, position: Dict[str, Any], selection: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update the current user's cursor position.

        This tool updates the current user's cursor position and optional selection
        in a document, making it visible to other collaborators.

        Args:
            document_path: Path to the document (required)
            position: Cursor position with line and column (required)
            selection: Optional selection range with start and end positions

        Returns:
            Confirmation of the cursor update

        Example:
            # Update cursor position
            result = await update_cursor_position(
                document_path="/projects/README.md",
                position={"line": 10, "column": 5}
            )

            # Update cursor with selection
            result = await update_cursor_position(
                document_path="/projects/README.md",
                position={"line": 10, "column": 5},
                selection={
                    "start": {"line": 10, "column": 5},
                    "end": {"line": 15, "column": 0}
                }
            )
        """
        if not all([document_path, position]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Document path and position are required",
            )

        result = await rtc_adapter.update_cursor_position(document_path, position, selection)
        return result

    @fastmcp.tool(
        description="Get recent activity for users in the collaboration space.",
    )
    async def get_user_activity(
        document_path: Optional[str] = None, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get recent activity for users.

        This tool retrieves a log of recent user activities in the collaboration
        space, with optional filtering by document and activity limit.

        Args:
            document_path: Optional document path to filter activities for a specific document
            limit: Maximum number of activities to return (default: 20)

        Returns:
            List of recent user activities with timestamps and descriptions

        Example:
            # Get recent activities
            activities = await get_user_activity()

            # Get activities for a specific document
            activities = await get_user_activity(
                document_path="/projects/README.md",
                limit=50
            )
        """
        activity = await rtc_adapter.get_user_activity(document_path, limit)
        return activity

    @fastmcp.tool(
        description="Broadcast a user activity to other collaborators.",
    )
    async def broadcast_user_activity(
        activity_type: str,
        description: str,
        document_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Broadcast a user activity to other collaborators.

        This tool allows broadcasting of user activities to make them visible
        to other collaborators in the workspace.

        Args:
            activity_type: Type of activity (edit, view, execute, etc.) (required)
            description: Human-readable description of the activity (required)
            document_path: Optional document path related to the activity
            metadata: Optional additional metadata about the activity

        Returns:
            Confirmation of the activity broadcast

        Example:
            # Broadcast editing activity
            result = await broadcast_user_activity(
                activity_type="edit",
                description="Updated documentation",
                document_path="/projects/README.md",
                metadata={"section": "introduction"}
            )

            # Broadcast viewing activity
            result = await broadcast_user_activity(
                activity_type="view",
                description="Viewed analysis results"
            )
        """
        if not all([activity_type, description]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Activity type and description are required",
            )

        if metadata is None:
            metadata = {}

        result = await rtc_adapter.broadcast_user_activity(
            activity_type, description, document_path, metadata
        )
        return result

    @fastmcp.tool(
        description="Get active collaboration sessions in the workspace.",
    )
    async def get_active_sessions(document_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get active collaboration sessions.

        This tool retrieves information about currently active collaboration
        sessions, with optional filtering by document.

        Args:
            document_path: Optional document path to filter sessions for a specific document

        Returns:
            List of active sessions with participant information

        Example:
            # Get all active sessions
            sessions = await get_active_sessions()

            # Get sessions for a specific document
            sessions = await get_active_sessions(
                document_path="/projects/README.md"
            )
        """
        sessions = await rtc_adapter.get_active_sessions(document_path)
        return sessions

    @fastmcp.tool(description="Join an existing collaboration session.")
    async def join_session(session_id: str) -> Dict[str, Any]:
        """
        Join an existing collaboration session.

        This tool allows the current user to join an existing collaboration
        session, enabling real-time interaction with other participants.

        Args:
            session_id: ID of the session to join (required)

        Returns:
            Confirmation of joining the session with session information

        Example:
            result = await join_session(session_id="session-123")
        """
        if not session_id:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Session ID is required",
            )

        result = await rtc_adapter.join_session(session_id)
        return result

    @fastmcp.tool(description="Leave a collaboration session.")
    async def leave_session(session_id: str) -> Dict[str, Any]:
        """
        Leave a collaboration session.

        This tool allows the current user to leave a collaboration session,
        ending their participation in that specific collaborative context.

        Args:
            session_id: ID of the session to leave (required)

        Returns:
            Confirmation of leaving the session

        Example:
            result = await leave_session(session_id="session-123")
        """
        if not session_id:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Session ID is required",
            )

        result = await rtc_adapter.leave_session(session_id)
        return result
