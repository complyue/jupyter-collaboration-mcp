__all__ = [
    "define_awareness_tools",
]

from typing import Any, Dict, List, Optional, Tuple

from mcp.server import FastMCP
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData

from ..exceptions import MCPError
from ..rtc_adapter import RTCAdapter


def define_awareness_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all user awareness and presence tools using fastmcp."""

    @fastmcp.tool(
        description="""Get a list of users currently online in the collaboration space.

Returns information about users who are currently active in the collaboration space,
with optional filtering by document. Use document_path to see users collaborating on a specific document.

Examples:
• get_online_users() - Get all online users
• get_online_users(document_path="/projects/README.md") - Get users for a specific document
"""
    )
    async def get_online_users(
        document_path: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        users = await rtc_adapter.get_online_users(document_path)

        description = f"Found {len(users)} users currently online"
        if document_path:
            description += f" for document {document_path}"
        description += (
            ". Consider joining relevant collaboration sessions to interact with these users."
        )

        return description, users

    @fastmcp.tool(
        description="""Get presence information for a specific user.

Retrieves detailed presence information for a user, including their status,
last activity, and current document context. Use document_path to check presence
in a specific document context.

Examples:
• get_user_presence(user_id="user-123") - Get presence for a user
• get_user_presence(user_id="user-123", document_path="/projects/README.md") - Check presence in a specific document
"""
    )
    async def get_user_presence(
        user_id: str, document_path: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        if not user_id:
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="User ID is required",
                )
            )

        presence = await rtc_adapter.get_user_presence(user_id, document_path)

        description = f"Retrieved presence information for user {user_id}"
        if document_path:
            description += f" in document {document_path}"
        description += (
            ". Consider joining relevant collaboration sessions to interact with this user."
        )

        return description, presence

    @fastmcp.tool(
        description="""Set the current user's presence status and optional message.

Updates your presence status, making it visible to other collaborators in the workspace.
Your status helps others understand your availability and current activity.

Examples:
• set_user_presence(status="away", message="In a meeting, back soon") - Set away status with message
• set_user_presence(status="busy") - Set busy status
• set_user_presence(status="online") - Set online status
"""
    )
    async def set_user_presence(
        status: str = "online", message: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        result = await rtc_adapter.set_user_presence(status, message)

        description = f"Updated presence status to '{status}'"
        if message:
            description += f" with message: '{message}'"
        description += ". Your status is now visible to all collaborators in active sessions."

        return description, result

    @fastmcp.tool(
        description="""Get cursor positions of users in a document.

Retrieves the current cursor positions and selections of all users collaborating
on a specific document. This helps understand where collaborators are focusing
their attention in the document.

Examples:
• get_user_cursors(document_path="/projects/README.md") - Get cursor positions for a document
"""
    )
    async def get_user_cursors(document_path: str) -> Tuple[str, List[Dict[str, Any]]]:
        if not document_path:
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Document path is required",
                )
            )

        cursors = await rtc_adapter.get_user_cursors(document_path)

        description = (
            f"Retrieved cursor positions for {len(cursors)} users in document {document_path}"
        )
        description += ". Consider joining the collaboration session for this document to interact with these users."

        return description, cursors

    @fastmcp.tool(
        description="""Update the current user's cursor position and selection in a document.

Updates your cursor position and optional selection in a document, making it
visible to other collaborators. This helps others see where you're working
and what you're focusing on.

Examples:
• update_cursor_position(document_path="/projects/README.md", position={"line": 10, "column": 5}) - Update cursor position
• update_cursor_position(document_path="/projects/README.md", position={"line": 10, "column": 5}, selection={"start": {"line": 10, "column": 5}, "end": {"line": 15, "column": 0}}) - Update cursor with selection
"""
    )
    async def update_cursor_position(
        document_path: str, position: Dict[str, Any], selection: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        if not all([document_path, position]):
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Document path and position are required",
                )
            )

        result = await rtc_adapter.update_cursor_position(document_path, position, selection)

        description = f"Updated cursor position in document {document_path}"
        if selection:
            description += " with selection"
        description += ". Your position is now visible to all collaborators in the session."

        return description, result

    @fastmcp.tool(
        description="""Get recent activity for users in the collaboration space.

Retrieves a log of recent user activities in the collaboration space, with optional
filtering by document and activity limit. Use limit to control the amount of data returned.

Examples:
• get_user_activity() - Get recent activities
• get_user_activity(document_path="/projects/README.md", limit=50) - Get activities for a specific document
• get_user_activity(limit=10) - Get only 10 most recent activities
"""
    )
    async def get_user_activity(
        document_path: Optional[str] = None, limit: int = 20
    ) -> Tuple[str, List[Dict[str, Any]]]:
        activity = await rtc_adapter.get_user_activity(document_path, limit)

        description = f"Retrieved {len(activity)} recent user activities"
        if document_path:
            description += f" for document {document_path}"
        if len(activity) == limit:
            description += f" (limited to {limit} entries)"
        description += (
            ". Consider joining relevant collaboration sessions to participate in these activities."
        )

        return description, activity

    @fastmcp.tool(
        description="""Broadcast a user activity to other collaborators.

Broadcasts user activities to make them visible to other collaborators in the workspace.
This helps keep everyone informed about what others are working on.

Examples:
• broadcast_user_activity(activity_type="edit", description="Updated documentation", document_path="/projects/README.md", metadata={"section": "introduction"}) - Broadcast editing activity
• broadcast_user_activity(activity_type="view", description="Viewed analysis results") - Broadcast viewing activity
"""
    )
    async def broadcast_user_activity(
        activity_type: str,
        description: str,
        document_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if not all([activity_type, description]):
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Activity type and description are required",
                )
            )

        if metadata is None:
            metadata = {}

        result = await rtc_adapter.broadcast_user_activity(
            activity_type, description, document_path, metadata
        )

        activity_desc = f"Broadcasted {activity_type} activity: '{description}'"
        if document_path:
            activity_desc += f" for document {document_path}"
        activity_desc += ". Your activity is now visible to all collaborators in active sessions."

        return activity_desc, result

    @fastmcp.tool(
        description="""Get active collaboration sessions in the workspace.

Retrieves information about currently active collaboration sessions, with optional
filtering by document. Use document_path to see sessions for a specific document.

Examples:
• get_active_sessions() - Get all active sessions
• get_active_sessions(document_path="/projects/README.md") - Get sessions for a specific document
"""
    )
    async def get_active_sessions(
        document_path: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        sessions = await rtc_adapter.get_active_sessions(document_path)

        description = f"Retrieved {len(sessions)} active collaboration sessions"
        if document_path:
            description += f" for document {document_path}"
        description += ". Consider joining relevant sessions to collaborate with other users."

        return description, sessions

    @fastmcp.tool(
        description="""Join an existing collaboration session.

Joins an existing collaboration session, enabling real-time interaction with other
participants. The session ID can be obtained from get_active_sessions.

Examples:
• join_session(session_id="session-123") - Join a specific session
"""
    )
    async def join_session(session_id: str) -> Tuple[str, Dict[str, Any]]:
        if not session_id:
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Session ID is required",
                )
            )

        result = await rtc_adapter.join_session(session_id)

        description = f"Joined collaboration session {session_id}"
        description += ". You can now interact with other participants in real-time."

        return description, result

    @fastmcp.tool(
        description="""Leave a collaboration session.

Leaves a collaboration session, ending your participation in that specific
collaborative context. Your presence and cursor positions will no longer be
visible to other participants.

Examples:
• leave_session(session_id="session-123") - Leave a specific session
"""
    )
    async def leave_session(session_id: str) -> Tuple[str, Dict[str, Any]]:
        if not session_id:
            raise MCPError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message="Session ID is required",
                )
            )

        result = await rtc_adapter.leave_session(session_id)

        description = f"Left collaboration session {session_id}"
        description += ". Your presence is no longer visible to other participants."

        return description, result
