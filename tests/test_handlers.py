"""
Tests for MCP request handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from jupyter_collaboration_mcp.handlers import (
    NotebookHandlers, DocumentHandlers, AwarenessHandlers
)


@pytest.fixture
def mock_server():
    """Create a mock MCP server."""
    server = MagicMock()
    return server


@pytest.fixture
def mock_rtc_adapter():
    """Create a mock RTC adapter."""
    adapter = MagicMock()
    return adapter


@pytest.fixture
def notebook_handlers(mock_server, mock_rtc_adapter):
    """Create notebook handlers with mocked dependencies."""
    return NotebookHandlers(mock_server, mock_rtc_adapter)


@pytest.fixture
def document_handlers(mock_server, mock_rtc_adapter):
    """Create document handlers with mocked dependencies."""
    return DocumentHandlers(mock_server, mock_rtc_adapter)


@pytest.fixture
def awareness_handlers(mock_server, mock_rtc_adapter):
    """Create awareness handlers with mocked dependencies."""
    return AwarenessHandlers(mock_server, mock_rtc_adapter)


@pytest.mark.asyncio
async def test_list_notebooks(notebook_handlers, mock_rtc_adapter):
    """Test listing notebooks."""
    # Mock the RTC adapter response
    mock_rtc_adapter.list_notebooks = AsyncMock(return_value=[
        {
            "path": "/test.ipynb",
            "name": "Test Notebook",
            "collaborative": True,
            "last_modified": "2023-01-01T00:00:00Z",
            "collaborators": 2
        }
    ])
    
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="list_notebooks",
        arguments={"path": "/test"}
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "Test Notebook" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.list_notebooks.assert_called_once_with("/test")


@pytest.mark.asyncio
async def test_get_notebook(notebook_handlers, mock_rtc_adapter):
    """Test getting a notebook."""
    # Mock the RTC adapter response
    mock_rtc_adapter.get_notebook = AsyncMock(return_value={
        "path": "/test.ipynb",
        "content": {"cells": []},
        "format": "json",
        "type": "notebook"
    })
    
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_notebook':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="get_notebook",
        arguments={
            "path": "/test.ipynb",
            "include_collaboration_state": True
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "cells" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.get_notebook.assert_called_once_with(
        "/test.ipynb", True
    )


@pytest.mark.asyncio
async def test_get_notebook_missing_path(notebook_handlers):
    """Test getting a notebook without a path."""
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_notebook':
                break
    
    assert handler is not None
    
    # Call the handler without a path
    with pytest.raises(ValueError, match="Path is required"):
        await handler(
            name="get_notebook",
            arguments={}
        )


@pytest.mark.asyncio
async def test_create_notebook_session(notebook_handlers, mock_rtc_adapter):
    """Test creating a notebook session."""
    # Mock the RTC adapter response
    mock_rtc_adapter.create_notebook_session = AsyncMock(return_value={
        "session_id": "test-session-id",
        "room_id": "notebook:/test.ipynb",
        "path": "/test.ipynb",
        "status": "active"
    })
    
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'create_notebook_session':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="create_notebook_session",
        arguments={"path": "/test.ipynb"}
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "test-session-id" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.create_notebook_session.assert_called_once_with("/test.ipynb")


@pytest.mark.asyncio
async def test_update_notebook_cell(notebook_handlers, mock_rtc_adapter):
    """Test updating a notebook cell."""
    # Mock the RTC adapter response
    mock_rtc_adapter.update_notebook_cell = AsyncMock(return_value={
        "success": True,
        "cell_id": "test-cell-id",
        "timestamp": 1234567890
    })
    
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'update_notebook_cell':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="update_notebook_cell",
        arguments={
            "path": "/test.ipynb",
            "cell_id": "test-cell-id",
            "content": "print('hello')",
            "cell_type": "code"
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "test-cell-id" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.update_notebook_cell.assert_called_once_with(
        "/test.ipynb", "test-cell-id", "print('hello')", "code"
    )


@pytest.mark.asyncio
async def test_list_documents(document_handlers, mock_rtc_adapter):
    """Test listing documents."""
    # Mock the RTC adapter response
    mock_rtc_adapter.list_documents = AsyncMock(return_value=[
        {
            "path": "/test.md",
            "name": "Test Document",
            "file_type": "markdown",
            "collaborative": True,
            "last_modified": "2023-01-01T00:00:00Z",
            "collaborators": 1
        }
    ])
    
    # Get the handler function
    handler = None
    for decorator in document_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'list_documents':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="list_documents",
        arguments={
            "path": "/test",
            "file_type": "markdown"
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "Test Document" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.list_documents.assert_called_once_with("/test", "markdown")


@pytest.mark.asyncio
async def test_get_document(document_handlers, mock_rtc_adapter):
    """Test getting a document."""
    # Mock the RTC adapter response
    mock_rtc_adapter.get_document = AsyncMock(return_value={
        "path": "/test.md",
        "content": "# Test Document\n\nThis is a test.",
        "file_type": "markdown",
        "type": "document"
    })
    
    # Get the handler function
    handler = None
    for decorator in document_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_document':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="get_document",
        arguments={
            "path": "/test.md",
            "include_collaboration_state": True
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "Test Document" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.get_document.assert_called_once_with(
        "/test.md", True
    )


@pytest.mark.asyncio
async def test_update_document(document_handlers, mock_rtc_adapter):
    """Test updating a document."""
    # Mock the RTC adapter response
    mock_rtc_adapter.update_document = AsyncMock(return_value={
        "success": True,
        "path": "/test.md",
        "version": 2,
        "timestamp": 1234567890
    })
    
    # Get the handler function
    handler = None
    for decorator in document_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'update_document':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="update_document",
        arguments={
            "path": "/test.md",
            "content": "# Updated Document\n\nThis has been updated.",
            "position": 0,
            "length": 20
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "version" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.update_document.assert_called_once_with(
        "/test.md", "# Updated Document\n\nThis has been updated.", 0, 20
    )


@pytest.mark.asyncio
async def test_fork_document(document_handlers, mock_rtc_adapter):
    """Test forking a document."""
    # Mock the RTC adapter response
    mock_rtc_adapter.fork_document = AsyncMock(return_value={
        "success": True,
        "fork_id": "test-fork-id",
        "fork_path": "/test.md.fork-test-fork-id",
        "title": "Fork of Test Document",
        "timestamp": 1234567890
    })
    
    # Get the handler function
    handler = None
    for decorator in document_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'fork_document':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="fork_document",
        arguments={
            "path": "/test.md",
            "title": "Fork of Test Document",
            "description": "A test fork",
            "synchronize": False
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "test-fork-id" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.fork_document.assert_called_once_with(
        "/test.md", "Fork of Test Document", "A test fork", False
    )


@pytest.mark.asyncio
async def test_get_online_users(awareness_handlers, mock_rtc_adapter):
    """Test getting online users."""
    # Mock the RTC adapter response
    mock_rtc_adapter.get_online_users = AsyncMock(return_value=[
        {
            "id": "user1",
            "name": "User 1",
            "status": "online",
            "last_activity": 1234567890,
            "current_document": "/test.ipynb"
        }
    ])
    
    # Get the handler function
    handler = None
    for decorator in awareness_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_online_users':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="get_online_users",
        arguments={"document_path": "/test.ipynb"}
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "User 1" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.get_online_users.assert_called_once_with("/test.ipynb")


@pytest.mark.asyncio
async def test_get_user_presence(awareness_handlers, mock_rtc_adapter):
    """Test getting user presence."""
    # Mock the RTC adapter response
    mock_rtc_adapter.get_user_presence = AsyncMock(return_value={
        "user_id": "user1",
        "status": "online",
        "last_activity": 1234567890,
        "current_document": "/test.ipynb"
    })
    
    # Get the handler function
    handler = None
    for decorator in awareness_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_user_presence':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="get_user_presence",
        arguments={
            "user_id": "user1",
            "document_path": "/test.ipynb"
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "online" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.get_user_presence.assert_called_once_with(
        "user1", "/test.ipynb"
    )


@pytest.mark.asyncio
async def test_get_user_presence_missing_user_id(awareness_handlers):
    """Test getting user presence without a user ID."""
    # Get the handler function
    handler = None
    for decorator in awareness_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'get_user_presence':
                break
    
    assert handler is not None
    
    # Call the handler without a user ID
    with pytest.raises(ValueError, match="User ID is required"):
        await handler(
            name="get_user_presence",
            arguments={}
        )


@pytest.mark.asyncio
async def test_update_cursor_position(awareness_handlers, mock_rtc_adapter):
    """Test updating cursor position."""
    # Mock the RTC adapter response
    mock_rtc_adapter.update_cursor_position = AsyncMock(return_value={
        "success": True,
        "user_id": "user1",
        "document_path": "/test.md",
        "position": {"line": 5, "column": 10},
        "timestamp": 1234567890
    })
    
    # Get the handler function
    handler = None
    for decorator in awareness_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'update_cursor_position':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="update_cursor_position",
        arguments={
            "document_path": "/test.md",
            "position": {"line": 5, "column": 10},
            "selection": {
                "start": {"line": 5, "column": 5},
                "end": {"line": 5, "column": 15}
            }
        }
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "line" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.update_cursor_position.assert_called_once_with(
        "/test.md", {"line": 5, "column": 10}, {
            "start": {"line": 5, "column": 5},
            "end": {"line": 5, "column": 15}
        }
    )


@pytest.mark.asyncio
async def test_join_session(awareness_handlers, mock_rtc_adapter):
    """Test joining a session."""
    # Mock the RTC adapter response
    mock_rtc_adapter.join_session = AsyncMock(return_value={
        "success": True,
        "session_id": "test-session-id",
        "timestamp": 1234567890
    })
    
    # Get the handler function
    handler = None
    for decorator in awareness_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            if hasattr(handler, '__name__') and handler.__name__ == 'join_session':
                break
    
    assert handler is not None
    
    # Call the handler
    result = await handler(
        name="join_session",
        arguments={"session_id": "test-session-id"}
    )
    
    # Check the result
    assert len(result) == 1
    assert result[0].type == "text"
    assert "test-session-id" in result[0].text
    
    # Check that the RTC adapter was called correctly
    mock_rtc_adapter.join_session.assert_called_once_with("test-session-id")


@pytest.mark.asyncio
async def test_unknown_tool(notebook_handlers):
    """Test handling an unknown tool."""
    # Get the handler function
    handler = None
    for decorator in notebook_handlers.server.call_tool.mock_calls:
        if decorator:
            handler = decorator.args[0]
            break
    
    assert handler is not None
    
    # Call the handler with an unknown tool name
    with pytest.raises(ValueError, match="Unknown tool"):
        await handler(
            name="unknown_tool",
            arguments={}
        )