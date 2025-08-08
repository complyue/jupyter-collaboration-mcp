__all__ = [
    "define_document_tools",
]

from typing import Any, Tuple, Dict, List, Optional

from mcp.server import FastMCP
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData

from ..rtc_adapter import RTCAdapter


def define_document_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all document collaboration tools using fastmcp."""

    @fastmcp.tool(
        description="""List available documents for collaboration with optional filtering.

Returns a description string and a list of document info objects with paths and collaboration status.
Use path_filter to filter by directory, file_type to filter by document type, and max_results to control response size.

Examples:
• list_documents() - List all available documents
• list_documents(path_filter="/projects/docs/") - List documents in a specific directory
• list_documents(file_type="markdown") - List only markdown documents
• list_documents(max_results=10) - Limit to 10 documents to manage response size
"""
    )
    async def list_documents(
        path_filter: Optional[str] = None,
        file_type: Optional[str] = None,
        max_results: int = 50,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        documents = await rtc_adapter.list_documents(path_filter, file_type)

        # Apply max_results limit if specified
        if max_results is not None and len(documents) > max_results:
            description = f"Found {len(documents)} documents (showing first {max_results} results)"
            documents = documents[:max_results]
        else:
            description = f"Found {len(documents)} documents available for collaboration"

        return description, documents

    @fastmcp.tool(
        description="""Get a document's content with optional collaboration metadata.

Use max_content_length to control response size and avoid context overflow. Returns a description
with content size information and the document data. Consider creating a session for real-time collaboration.

Examples:
• get_document(path="/projects/README.md") - Get full document with collaboration state
• get_document(path="/projects/README.md", max_content_length=50000) - Limit content size
• get_document(path="/projects/README.md", include_collaboration_state=False) - Get only document content
"""
    )
    async def get_document(
        path: str,
        include_collaboration_state: bool = True,
        max_content_length: int = 100000,
    ) -> Tuple[str, Dict[str, Any]]:
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

        # Apply content length limit if specified
        content_size = len(str(document))
        if max_content_length is not None and content_size > max_content_length:
            description = f"Document content is {content_size} characters (exceeds limit of {max_content_length}). Content has been truncated."
            # Simple truncation for now - in a real implementation, you'd want smarter truncation
            document_str = str(document)
            document = {"content": document_str[:max_content_length], "truncated": True}
        else:
            description = f"Retrieved document with {content_size} characters of content"

        # Add session information reminder
        if include_collaboration_state:
            description += ". Consider creating a collaboration session for real-time editing."

        return description, document

    @fastmcp.tool(
        description="""Create or retrieve a collaboration session for a document.

Enables real-time collaboration with multiple users. If a session already exists,
returns the existing session information. The session ID can be used to join
collaborative editing sessions.

Examples:
• create_document_session(path="/projects/README.md") - Create session for a document
• create_document_session(path="/projects/README.md", file_type="markdown") - Create session with explicit file type
"""
    )
    async def create_document_session(path: str, file_type: Optional[str] = None) -> Dict[str, Any]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        session = await rtc_adapter.create_document_session(path, file_type)
        return session

    @fastmcp.tool(
        description="""Batch update a document's content with multiple precise operations.

Performs multiple update operations on a document with precise position control.
Each operation can insert, replace, or append content. Changes are immediately
synchronized with all collaborators.

Examples:
• batch_update_document(path="/projects/README.md", operations=[{"content": "\n## New Section\nContent here", "position": -1}]) - Append content
• batch_update_document(path="/projects/README.md", operations=[{"content": "Updated title", "position": 0, "length": 10}]) - Replace content at position 0
• batch_update_document(path="/projects/README.md", operations=[{"content": "Text", "position": 5, "length": 0}]) - Insert text at position 5
"""
    )
    async def batch_update_document(
        path: str, operations: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Batch update document content with multiple operations.

        Args:
            path: Path to the document (required)
            operations: List of update operations, each containing:
                - content: New content (required)
                - position: Position to start update (-1 for append, default: -1)
                - length: Length of content to replace (0 for insert, default: 0)

        Returns:
            Description of operation results and list of update confirmations
        """
        if not path or not operations:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and operations are required",
            )

        results = []

        for op in operations:
            content = op.get("content", "")
            position = op.get("position", -1)
            length = op.get("length", 0)

            result = await rtc_adapter.update_document(path, content, position, length)
            results.append(result)

        description = f"Performed {len(results)} update operations on document. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Batch insert multiple text segments at specific positions in a document.

Inserts multiple text segments at specified positions in a document, shifting
existing content to the right. All insertions are synchronized with all collaborators.

Examples:
• batch_insert_text(path="/projects/README.md", operations=[{"text": "## New Section\n", "position": 100}]) - Insert single text segment
• batch_insert_text(path="/projects/README.md", operations=[{"text": "Intro: ", "position": 0}, {"text": "\n## Summary", "position": 200}]) - Insert multiple segments
• batch_insert_text(path="/projects/README.md", operations=[{"text": "Note: ", "position": 50}]) - Insert single note at position 50
"""
    )
    async def batch_insert_text(
        path: str, operations: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Batch insert multiple text segments into a document.

        Args:
            path: Path to the document (required)
            operations: List of insert operations, each containing:
                - text: Text to insert (required)
                - position: Position to insert at (0-based index, required)

        Returns:
            Description of operation results and list of insertion confirmations
        """
        if not path or not operations:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and operations are required",
            )

        results = []

        for op in operations:
            text = op.get("text", "")
            position = op.get("position")

            if position is None:
                raise ErrorData(
                    code=INVALID_PARAMS,
                    message="Position is required for each insert operation",
                )

            result = await rtc_adapter.insert_text(path, text, position)
            results.append(result)

        description = f"Inserted {len(results)} text segments into document. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Batch delete multiple text segments from specific positions in a document.

Removes multiple text segments from specified positions in a document, shifting
remaining content to the left. All deletions are synchronized with all collaborators.

Examples:
• batch_delete_text(path="/projects/README.md", operations=[{"position": 100, "length": 20}]) - Delete single text segment
• batch_delete_text(path="/projects/README.md", operations=[{"position": 0, "length": 5}, {"position": 50, "length": 10}]) - Delete multiple segments
• batch_delete_text(path="/projects/README.md", operations=[{"position": 200, "length": 1}]) - Delete single character at position 200
"""
    )
    async def batch_delete_text(
        path: str, operations: List[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Batch delete multiple text segments from a document.

        Args:
            path: Path to the document (required)
            operations: List of delete operations, each containing:
                - position: Position to start deletion (0-based index, required)
                - length: Length of text to delete (required)

        Returns:
            Description of operation results and list of deletion confirmations
        """
        if not path or not operations:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and operations are required",
            )

        results = []

        for op in operations:
            position = op.get("position")
            length = op.get("length")

            if position is None or length is None:
                raise ErrorData(
                    code=INVALID_PARAMS,
                    message="Position and length are required for each delete operation",
                )

            result = await rtc_adapter.delete_text(path, position, length)
            results.append(result)

        description = f"Deleted {len(results)} text segments from document. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Get a document's version history and change log.

Returns a list of document versions with timestamps, change summaries, and author information.
Use limit to control the number of history entries returned.

Examples:
• get_document_history(path="/projects/README.md") - Get last 10 versions
• get_document_history(path="/projects/README.md", limit=20) - Get last 20 versions
• get_document_history(path="/projects/README.md", limit=5) - Get only 5 most recent versions
"""
    )
    async def get_document_history(path: str, limit: int = 10) -> Tuple[str, List[Dict[str, Any]]]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        history = await rtc_adapter.get_document_history(path, limit)

        description = f"Retrieved {len(history)} version history entries for document."
        if len(history) == limit:
            description += f" Results limited to {limit} entries. More history may be available."

        return description, history

    @fastmcp.tool(
        description="""Restore a document to a previous version from history.

Reverts a document to a specific version from its history. This operation creates
a new version in the history and is synchronized with all collaborators.

Examples:
• restore_document_version(path="/projects/README.md", version_id="version-123") - Restore to specific version
"""
    )
    async def restore_document_version(path: str, version_id: str) -> Tuple[str, Dict[str, Any]]:
        if not all([path, version_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and version_id are required",
            )

        result = await rtc_adapter.restore_document_version(path, version_id)

        description = f"Document restored to version {version_id}. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, result

    @fastmcp.tool(
        description="""Create a fork of a document for parallel editing.

Creates a copy of a document that can be edited independently. Forks can be
merged back into the original document later. Use synchronize to keep the
fork updated with changes from the original.

Examples:
• fork_document(path="/projects/README.md") - Create basic fork
• fork_document(path="/projects/README.md", title="README - Experimental Changes", description="Testing new structure") - Create fork with metadata
• fork_document(path="/projects/README.md", synchronize=True) - Create synchronized fork
"""
    )
    async def fork_document(
        path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        synchronize: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        result = await rtc_adapter.fork_document(path, title, description, synchronize)

        description = f"Created fork of document. "
        if synchronize:
            description += "Fork will synchronize with original document. "
        description += "Consider creating collaboration sessions for both original and fork if editing simultaneously."

        return description, result

    @fastmcp.tool(
        description="""Merge a fork back into the original document.

Merges changes from a fork back into the original document. The merge operation
handles conflicts and creates a new version. All collaborators will see the merged changes.

Examples:
• merge_document_fork(path="/projects/README.md", fork_id="fork-123") - Merge fork back to original
"""
    )
    async def merge_document_fork(path: str, fork_id: str) -> Tuple[str, Dict[str, Any]]:
        if not all([path, fork_id]):
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and fork_id are required",
            )

        result = await rtc_adapter.merge_document_fork(path, fork_id)

        description = f"Merged fork {fork_id} back into original document. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, result
