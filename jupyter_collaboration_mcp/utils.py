"""
Utility functions for Jupyter Collaboration MCP Server.

This module provides various utility functions used throughout the MCP server
implementation.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def sanitize_path(path: str) -> str:
    """Sanitize a file path to prevent directory traversal attacks.

    Args:
        path: The path to sanitize

    Returns:
        Sanitized path
    """
    # Remove any URL encoding
    path = unquote(path)

    # Normalize path separators
    path = path.replace("/", os.sep).replace("\\", os.sep)

    # Remove any relative path components that could lead to directory traversal
    parts = []
    for part in path.split(os.sep):
        if part == "..":
            if parts:
                parts.pop()
        elif part and part != ".":
            parts.append(part)

    # Reconstruct the path
    sanitized = os.sep.join(parts)

    # Ensure path starts with a separator if it was absolute
    if path.startswith(os.sep) and not sanitized.startswith(os.sep):
        sanitized = os.sep + sanitized

    return sanitized


def is_valid_notebook_path(path: str) -> bool:
    """Check if a path is a valid notebook path.

    Args:
        path: The path to check

    Returns:
        True if the path is a valid notebook path
    """
    sanitized = sanitize_path(path)

    # Check if the path ends with .ipynb
    if not sanitized.endswith(".ipynb"):
        return False

    # Check for invalid characters
    invalid_chars = ["<", ">", ":", '"', "|", "?", "*"]
    if any(char in sanitized for char in invalid_chars):
        return False

    return True


def is_valid_document_path(path: str) -> bool:
    """Check if a path is a valid document path.

    Args:
        path: The path to check

    Returns:
        True if the path is a valid document path
    """
    sanitized = sanitize_path(path)

    # Check for invalid characters
    invalid_chars = ["<", ">", ":", '"', "|", "?", "*"]
    if any(char in sanitized for char in invalid_chars):
        return False

    return True


def get_file_type(path: str) -> str:
    """Get the file type from a path.

    Args:
        path: The file path

    Returns:
        The file type (notebook, markdown, text, etc.)
    """
    if path.endswith(".ipynb"):
        return "notebook"
    elif path.endswith(".md"):
        return "markdown"
    elif path.endswith(".txt"):
        return "text"
    else:
        return "unknown"


def format_timestamp(timestamp: float) -> str:
    """Format a timestamp as an ISO string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted timestamp string
    """
    return datetime.fromtimestamp(timestamp).isoformat()


def parse_timestamp(timestamp_str: str) -> float:
    """Parse an ISO timestamp string to a Unix timestamp.

    Args:
        timestamp_str: ISO timestamp string

    Returns:
        Unix timestamp
    """
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.timestamp()
    except ValueError:
        logger.warning(f"Invalid timestamp format: {timestamp_str}")
        return time.time()


def create_response(
    success: bool = True, data: Optional[Dict[str, Any]] = None, error: Optional[str] = None
) -> Dict[str, Any]:
    """Create a standardized response dictionary.

    Args:
        success: Whether the operation was successful
        data: Optional data to include in the response
        error: Optional error message

    Returns:
        Response dictionary
    """
    response = {"success": success, "timestamp": time.time()}

    if data is not None:
        response["data"] = data

    if error is not None:
        response["error"] = error

    return response


def safe_json_loads(json_str: str) -> Optional[Dict[str, Any]]:
    """Safely load a JSON string.

    Args:
        json_str: JSON string to load

    Returns:
        Parsed dictionary or None if parsing failed
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return None


def safe_json_dumps(obj: Any, indent: Optional[int] = None) -> str:
    """Safely dump an object to JSON.

    Args:
        obj: Object to dump
        indent: Optional indentation level

    Returns:
        JSON string
    """
    try:
        return json.dumps(obj, indent=indent, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        logger.error(f"Failed to serialize to JSON: {e}")
        return "{}"


def generate_id() -> str:
    """Generate a unique ID.

    Returns:
        Unique ID string
    """
    import uuid

    return str(uuid.uuid4())


def validate_cell_id(cell_id: str) -> bool:
    """Validate a cell ID.

    Args:
        cell_id: The cell ID to validate

    Returns:
        True if the cell ID is valid
    """
    # Cell IDs should be non-empty strings without special characters
    if not cell_id or not isinstance(cell_id, str):
        return False

    # Check for invalid characters
    invalid_chars = ["<", ">", ":", '"', "|", "?", "*", "/"]
    if any(char in cell_id for char in invalid_chars):
        return False

    return True


def validate_position(position: int, max_position: int) -> bool:
    """Validate a position index.

    Args:
        position: The position to validate
        max_position: Maximum valid position

    Returns:
        True if the position is valid
    """
    return isinstance(position, int) and 0 <= position <= max_position


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to a maximum length.

    Args:
        text: The text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - 3] + "..."


def extract_error_message(e: Exception) -> str:
    """Extract a user-friendly error message from an exception.

    Args:
        e: The exception

    Returns:
        Error message string
    """
    if hasattr(e, "message"):
        return str(e.message)
    elif hasattr(e, "args") and e.args:
        return str(e.args[0])
    else:
        return str(e)


def get_notebook_name_from_path(path: str) -> str:
    """Extract the notebook name from a path.

    Args:
        path: The notebook path

    Returns:
        Notebook name
    """
    sanitized = sanitize_path(path)
    basename = os.path.basename(sanitized)

    # Remove .ipynb extension if present
    if basename.endswith(".ipynb"):
        basename = basename[:-6]

    return basename


def get_document_name_from_path(path: str) -> str:
    """Extract the document name from a path.

    Args:
        path: The document path

    Returns:
        Document name
    """
    sanitized = sanitize_path(path)
    basename = os.path.basename(sanitized)

    # Remove file extension if present
    if "." in basename:
        basename = basename[: basename.rfind(".")]

    return basename


def normalize_line_endings(text: str) -> str:
    """Normalize line endings in text to LF.

    Args:
        text: The text to normalize

    Returns:
        Text with normalized line endings
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def count_lines(text: str) -> int:
    """Count the number of lines in text.

    Args:
        text: The text to count lines in

    Returns:
        Number of lines
    """
    if not text:
        return 0

    return text.count("\n") + (1 if not text.endswith("\n") else 0)


def get_line_and_column(text: str, position: int) -> Tuple[int, int]:
    """Get the line and column for a position in text.

    Args:
        text: The text
        position: The character position

    Returns:
        Tuple of (line, column) (0-based)
    """
    if position < 0 or position > len(text):
        return (0, 0)

    text_before = text[:position]
    lines = text_before.split("\n")

    line = len(lines) - 1
    column = len(lines[-1]) if lines else 0

    return (line, column)


def get_position_from_line_column(text: str, line: int, column: int) -> int:
    """Get the character position from line and column.

    Args:
        text: The text
        line: The line number (0-based)
        column: The column number (0-based)

    Returns:
        Character position
    """
    lines = text.split("\n")

    if line < 0 or line >= len(lines):
        return 0

    # Calculate position up to the start of the line
    position = sum(len(lines[i]) + 1 for i in range(line))  # +1 for newline

    # Add column within the line
    position += min(column, len(lines[line]))

    return min(position, len(text))


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL.

    Args:
        url: The URL to check

    Returns:
        True if the URL is valid
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def debounce(func, delay=0.3):
    """Decorator to debounce a function.

    Args:
        func: The function to debounce
        delay: Debounce delay in seconds

    Returns:
        Debounced function
    """
    last_called = [0]
    timer = [None]

    async def debounced(*args, **kwargs):
        async def call_func():
            func(*args, **kwargs)
            last_called[0] = time.time()
            timer[0] = None

        # Cancel any pending call
        if timer[0] is not None:
            timer[0].cancel()

        # Schedule new call
        loop = asyncio.get_event_loop()
        timer[0] = loop.call_later(delay, lambda: asyncio.create_task(call_func()))

    return debounced


def throttle(func, limit=0.3):
    """Decorator to throttle a function.

    Args:
        func: The function to throttle
        limit: Throttle limit in seconds

    Returns:
        Throttled function
    """
    last_called = [0]

    async def throttled(*args, **kwargs):
        current_time = time.time()
        if current_time - last_called[0] >= limit:
            await func(*args, **kwargs)
            last_called[0] = current_time

    return throttled


def create_error_response(error_message: str, status_code: int = 400) -> Dict[str, Any]:
    """Create an error response for HTTP endpoints.

    Args:
        error_message: The error message
        status_code: HTTP status code

    Returns:
        Error response dictionary
    """
    return {
        "success": False,
        "error": error_message,
        "status_code": status_code,
        "timestamp": time.time(),
    }


def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two dictionaries recursively.

    Args:
        dict1: First dictionary
        dict2: Second dictionary

    Returns:
        Merged dictionary
    """
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten a nested dictionary.

    Args:
        d: The dictionary to flatten
        parent_key: The parent key for nested items
        sep: Separator for nested keys

    Returns:
        Flattened dictionary
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def get_file_size(path: str) -> int:
    """Get the size of a file in bytes.

    Args:
        path: The file path

    Returns:
        File size in bytes, or 0 if file doesn't exist
    """
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def format_file_size(size_bytes: int) -> str:
    """Format a file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted file size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.1f} {size_names[i]}"
