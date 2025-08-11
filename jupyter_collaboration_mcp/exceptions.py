"""
Custom exceptions for Jupyter Collaboration MCP Server.
"""

from typing import Any, Optional

from mcp.types import ErrorData


class MCPError(Exception):
    """
    Base exception class for MCP-related errors.

    This exception can hold ErrorData information for proper MCP error handling.
    """

    def __init__(self, error_data: ErrorData):
        """
        Initialize MCPError with ErrorData.

        Args:
            error_data: The ErrorData object containing error information
        """
        self.error_data = error_data
        super().__init__(error_data.message)

    @property
    def code(self) -> int:
        """Get the error code."""
        return self.error_data.code

    @property
    def message(self) -> str:
        """Get the error message."""
        return self.error_data.message

    @property
    def data(self) -> Optional[Any]:
        """Get additional error data."""
        return getattr(self.error_data, "data", None)
