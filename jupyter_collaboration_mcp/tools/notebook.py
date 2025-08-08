__all__ = [
    "define_notebook_tools",
]

from typing import Any, Tuple, Dict, List, Optional

from mcp.server import FastMCP
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData

from ..rtc_adapter import RTCAdapter


def define_notebook_tools(fastmcp: FastMCP, rtc_adapter: RTCAdapter):
    """Define all notebook collaboration tools using fastmcp."""

    @fastmcp.tool(
        description="""List available notebooks for collaboration.

Returns a description string and a list of notebook info objects with paths and collaboration status.
Use path_prefix to filter by directory and max_results to control response size.

Examples:
• list_notebooks() - List all available notebooks
• list_notebooks(path_prefix="/projects/data-science/") - List notebooks in a specific directory
• list_notebooks(max_results=5) - Limit to 5 notebooks to manage response size
"""
    )
    async def list_notebooks(
        path_prefix: Optional[str] = None,
        max_results: int = 50,
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
        description="""Get a notebook's content with cells and optional collaboration metadata.

Use max_content_length to control response size and avoid context overflow. Returns a description
with content size information and the notebook data. Consider creating a session for real-time collaboration.

Examples:
• get_notebook(path="/projects/analysis.ipynb") - Get full notebook with collaboration state
• get_notebook(path="/projects/analysis.ipynb", max_content_length=50000) - Limit content size
• get_notebook(path="/projects/analysis.ipynb", include_collaboration_state=False) - Get only notebook content
"""
    )
    async def get_notebook(
        path: str,
        include_collaboration_state: bool = True,
        max_content_length: int = 100000,
    ) -> Tuple[str, Dict[str, Any]]:
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

        # Apply content length limit if specified
        content_size = len(str(notebook))
        if max_content_length is not None and content_size > max_content_length:
            description = f"Notebook content is {content_size} characters (exceeds limit of {max_content_length}). Content has been truncated."
            # Simple truncation for now - in a real implementation, you'd want smarter truncation
            notebook_str = str(notebook)
            notebook = {"content": notebook_str[:max_content_length], "truncated": True}
        else:
            description = f"Retrieved notebook with {content_size} characters of content"

        # Add session information reminder
        if include_collaboration_state:
            description += ". Consider creating a collaboration session for real-time editing."

        return description, notebook

    @fastmcp.tool(
        description="""Create or retrieve a collaboration session for a notebook.

Enables real-time collaboration with multiple users. If a session already exists,
returns the existing session information. The session ID can be used to join
collaborative editing sessions.

Examples:
• create_notebook_session(path="/projects/analysis.ipynb") - Create session for a notebook
"""
    )
    async def create_notebook_session(path: str) -> Dict[str, Any]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        session = await rtc_adapter.create_notebook_session(path)
        return session

    @fastmcp.tool(
        description="""Batch update multiple cells in a notebook with range-based operations.

Updates cells within the specified range (start_index to end_index). Can update all cells
in the range or specific cells by ID. Changes are synchronized with all collaborators in real-time.

Args:
  path: Path to the notebook (required)
  updates: List of update operations, each containing content and optional cell_type
  start_index: Starting index for range-based updates (optional)
  end_index: Ending index for range-based updates (optional)
  cell_ids: Specific cell IDs to update (optional)

Returns:
  Description of operation results and list of update confirmations

Examples:
• batch_update_notebook_cells(path="/projects/analysis.ipynb", start_index=0, end_index=5, updates=[{"content": "print('Updated')"}]) - Update first 5 cells
• batch_update_notebook_cells(path="/projects/analysis.ipynb", cell_ids=["cell-1", "cell-3"], updates=[{"content": "print('Cell 1')"}, {"content": "print('Cell 3')"}]) - Update specific cells
• batch_update_notebook_cells(path="/projects/analysis.ipynb", start_index=2, end_index=2, updates=[{"content": "print('Single cell')"}]) - Update single cell at index 2
"""
    )
    async def batch_update_notebook_cells(
        path: str,
        updates: List[Dict[str, Any]],
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
        cell_ids: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not path or not updates:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and updates are required",
            )

        if (start_index is None or end_index is None) and not cell_ids:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Either start_index/end_index or cell_ids must be specified",
            )

        results = []

        # Handle range-based updates
        if start_index is not None and end_index is not None:
            for i in range(start_index, min(end_index + 1, len(updates))):
                if i < len(updates):
                    update = updates[i]
                    # For range-based updates, we need to get the cell ID first
                    # This is a simplified implementation - in reality you'd get the cell IDs from the notebook
                    cell_id = f"cell-{i}"  # Placeholder
                    result = await rtc_adapter.update_notebook_cell(
                        path, cell_id, update.get("content", ""), update.get("cell_type")
                    )
                    results.append(result)

        # Handle specific cell ID updates
        if cell_ids:
            for i, cell_id in enumerate(cell_ids):
                if i < len(updates):
                    update = updates[i]
                    result = await rtc_adapter.update_notebook_cell(
                        path, cell_id, update.get("content", ""), update.get("cell_type")
                    )
                    results.append(result)

        description = f"Updated {len(results)} cells in notebook. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Batch insert multiple cells into a notebook at specified positions.

Inserts multiple cells at the specified positions. Can insert a range of cells or specific cells
at different positions. Changes are synchronized with all collaborators in real-time.

Args:
  path: Path to the notebook (required)
  cells: List of cell data, each containing content and optional cell_type
  start_position: Starting position for range-based inserts (optional)
  positions: Specific positions for each cell (optional)

Returns:
  Description of operation results and list of inserted cell information

Examples:
• batch_insert_notebook_cells(path="/projects/analysis.ipynb", start_position=2, cells=[{"content": "print('Cell 1')"}, {"content": "print('Cell 2')"}]) - Insert 2 cells starting at position 2
• batch_insert_notebook_cells(path="/projects/analysis.ipynb", positions=[0, 5], cells=[{"content": "print('First')"}, {"content": "print('Middle')}]) - Insert at specific positions
• batch_insert_notebook_cells(path="/projects/analysis.ipynb", start_position=3, cells=[{"content": "print('Single cell')"}]) - Insert single cell at position 3
"""
    )
    async def batch_insert_notebook_cells(
        path: str,
        cells: List[Dict[str, Any]],
        start_position: Optional[int] = None,
        positions: Optional[List[int]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not path or not cells:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path and cells are required",
            )

        if start_position is None and not positions:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Either start_position or positions must be specified",
            )

        results = []

        # Handle range-based inserts
        if start_position is not None:
            for i, cell in enumerate(cells):
                position = start_position + i
                result = await rtc_adapter.insert_notebook_cell(
                    path, cell.get("content", ""), position, cell.get("cell_type", "code")
                )
                results.append(result)

        # Handle specific position inserts
        if positions:
            for i, position in enumerate(positions):
                if i < len(cells):
                    cell = cells[i]
                    result = await rtc_adapter.insert_notebook_cell(
                        path, cell.get("content", ""), position, cell.get("cell_type", "code")
                    )
                    results.append(result)

        description = f"Inserted {len(results)} cells into notebook. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Batch delete multiple cells from a notebook by range or specific IDs.

Deletes cells within the specified range or specific cells by ID. The deletions are
synchronized with all collaborators in real-time.

Args:
  path: Path to the notebook (required)
  start_index: Starting index for range-based deletion (optional)
  end_index: Ending index for range-based deletion (optional)
  cell_ids: Specific cell IDs to delete (optional)

Returns:
  Description of operation results and list of deletion confirmations

Examples:
• batch_delete_notebook_cells(path="/projects/analysis.ipynb", start_index=3, end_index=5) - Delete cells from index 3 to 5
• batch_delete_notebook_cells(path="/projects/analysis.ipynb", cell_ids=["cell-2", "cell-4"]) - Delete specific cells by ID
• batch_delete_notebook_cells(path="/projects/analysis.ipynb", start_index=7, end_index=7) - Delete single cell at index 7
"""
    )
    async def batch_delete_notebook_cells(
        path: str,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
        cell_ids: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        if (start_index is None or end_index is None) and not cell_ids:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Either start_index/end_index or cell_ids must be specified",
            )

        results = []

        # Handle range-based deletions
        if start_index is not None and end_index is not None:
            for i in range(start_index, end_index + 1):
                # For range-based deletions, we need to get the cell ID first
                # This is a simplified implementation - in reality you'd get the cell IDs from the notebook
                cell_id = f"cell-{i}"  # Placeholder
                result = await rtc_adapter.delete_notebook_cell(path, cell_id)
                results.append(result)

        # Handle specific cell ID deletions
        if cell_ids:
            for cell_id in cell_ids:
                result = await rtc_adapter.delete_notebook_cell(path, cell_id)
                results.append(result)

        description = f"Deleted {len(results)} cells from notebook. Changes are synchronized with all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results

    @fastmcp.tool(
        description="""Batch execute multiple cells in a notebook and return results.

Executes cells within the specified range or specific cells by ID. The execution is
visible to all collaborators in real-time. Use timeout to control execution time.

Args:
  path: Path to the notebook (required)
  start_index: Starting index for range-based execution (optional)
  end_index: Ending index for range-based execution (optional)
  cell_ids: Specific cell IDs to execute (optional)
  timeout: Execution timeout in seconds (default: 30)

Returns:
  Description of operation results and list of execution results

Examples:
• batch_execute_notebook_cells(path="/projects/analysis.ipynb", start_index=0, end_index=3) - Execute first 4 cells
• batch_execute_notebook_cells(path="/projects/analysis.ipynb", cell_ids=["cell-1", "cell-5"], timeout=60) - Execute specific cells with custom timeout
• batch_execute_notebook_cells(path="/projects/analysis.ipynb", start_index=2, end_index=2) - Execute single cell at index 2
"""
    )
    async def batch_execute_notebook_cells(
        path: str,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
        cell_ids: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not path:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Path is required",
            )

        if (start_index is None or end_index is None) and not cell_ids:
            raise ErrorData(
                code=INVALID_PARAMS,
                message="Either start_index/end_index or cell_ids must be specified",
            )

        results = []

        # Handle range-based executions
        if start_index is not None and end_index is not None:
            for i in range(start_index, end_index + 1):
                # For range-based executions, we need to get the cell ID first
                # This is a simplified implementation - in reality you'd get the cell IDs from the notebook
                cell_id = f"cell-{i}"  # Placeholder
                result = await rtc_adapter.execute_notebook_cell(path, cell_id, timeout)
                results.append(result)

        # Handle specific cell ID executions
        if cell_ids:
            for cell_id in cell_ids:
                result = await rtc_adapter.execute_notebook_cell(path, cell_id, timeout)
                results.append(result)

        description = f"Executed {len(results)} cells in notebook. Execution results are visible to all collaborators."
        description += " Consider creating a collaboration session for real-time editing if not already active."

        return description, results
