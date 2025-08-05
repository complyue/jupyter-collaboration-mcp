"""
Tests for the main MCP server application.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jupyter_collaboration_mcp.app import MCPServer


@pytest.fixture
def mcp_server():
    """Create an MCP server instance for testing."""
    return MCPServer()


@pytest.mark.asyncio
async def test_mcp_server_initialization(mcp_server):
    """Test that the MCP server initializes correctly."""
    assert mcp_server.server.name == "jupyter-collaboration-mcp"
    assert mcp_server.rtc_adapter is not None
    assert mcp_server.event_store is not None
    assert mcp_server.session_manager is None


@pytest.mark.asyncio
async def test_create_app(mcp_server):
    """Test that the Starlette application is created correctly."""
    app = mcp_server.create_app()
    
    # Check that the session manager was created
    assert mcp_server.session_manager is not None
    
    # Check that the app has the expected routes
    routes = [route.path for route in app.routes]
    assert "/mcp" in routes


@pytest.mark.asyncio
async def test_handle_mcp_request(mcp_server):
    """Test that MCP requests are handled correctly."""
    app = mcp_server.create_app()
    
    # Create a mock scope with authentication
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [
            (b"authorization", b"Bearer test-token"),
            (b"content-type", b"application/json")
        ]
    }
    
    # Mock the authentication
    with patch("jupyter_collaboration_mcp.app.authenticate_mcp_request") as mock_auth:
        mock_auth.return_value = {"sub": "test-user"}
        
        # Mock the session manager
        mcp_server.session_manager.handle_request = AsyncMock()
        
        # Create mock receive and send functions
        receive = AsyncMock()
        send = AsyncMock()
        
        # Get the MCP request handler
        mcp_handler = None
        for route in app.routes:
            if route.path == "/mcp":
                mcp_handler = route.app
                break
        
        assert mcp_handler is not None
        
        # Call the handler
        await mcp_handler(scope, receive, send)
        
        # Check that authentication was called
        mock_auth.assert_called_once_with(scope)
        
        # Check that the user was added to the scope
        assert scope["user"]["sub"] == "test-user"
        
        # Check that the session manager was called
        mcp_server.session_manager.handle_request.assert_called_once_with(
            scope, receive, send
        )


@pytest.mark.asyncio
async def test_broadcast_event(mcp_server):
    """Test that events are broadcast correctly."""
    app = mcp_server.create_app()
    
    # Mock the event store
    mcp_server.event_store.store_event = AsyncMock(return_value="test-event-id")
    
    # Mock the session manager
    mcp_server.session_manager.broadcast_event = AsyncMock()
    
    # Broadcast an event
    await mcp_server.broadcast_event("test-event", {"data": "test"})
    
    # Check that the event was stored
    mcp_server.event_store.store_event.assert_called_once()
    
    # Check that the event was broadcast
    mcp_server.session_manager.broadcast_event.assert_called_once()


@pytest.mark.asyncio
async def test_get_server_info(mcp_server):
    """Test that server information is returned correctly."""
    info = await mcp_server.get_server_info()
    
    assert info["name"] == "jupyter-collaboration-mcp"
    assert info["version"] == "0.1.0"
    assert "description" in info
    assert "capabilities" in info
    
    # Check capabilities
    capabilities = info["capabilities"]
    assert capabilities["notebooks"] is True
    assert capabilities["documents"] is True
    assert capabilities["awareness"] is True
    assert capabilities["realtime"] is True


@pytest.mark.asyncio
async def test_list_resources(mcp_server):
    """Test that resources are listed correctly."""
    app = mcp_server.create_app()
    
    # Get the list resources handler
    list_handler = None
    for route in app.routes:
        if route.path == "/mcp":
            # The handler is wrapped, so we need to access it through the server
            list_handler = mcp_server.server.list_resources
            break
    
    assert list_handler is not None
    
    # Call the handler
    resources = await list_handler()
    
    # Check that we got the expected resources
    assert len(resources) >= 3
    
    # Check for expected resource types
    resource_uris = [resource.uri for resource in resources]
    assert "collaboration://notebooks" in resource_uris
    assert "collaboration://documents" in resource_uris
    assert "collaboration://awareness" in resource_uris


@pytest.mark.asyncio
async def test_read_notebook_resource(mcp_server):
    """Test that notebook resources are read correctly."""
    app = mcp_server.create_app()
    
    # Mock the RTC adapter
    mcp_server.rtc_adapter.get_notebook_content = AsyncMock(
        return_value='{"cells": []}'
    )
    
    # Get the read resource handler
    read_handler = None
    for route in app.routes:
        if route.path == "/mcp":
            # The handler is wrapped, so we need to access it through the server
            read_handler = mcp_server.server.read_resource
            break
    
    assert read_handler is not None
    
    # Call the handler with a notebook URI
    result = await read_handler("collaboration://notebooks/test.ipynb")
    
    # Check the result
    assert len(result.contents) == 1
    assert result.contents[0].uri == "collaboration://notebooks/test.ipynb"
    assert result.contents[0].mimeType == "application/json"
    
    # Check that the RTC adapter was called
    mcp_server.rtc_adapter.get_notebook_content.assert_called_once_with("test.ipynb")


@pytest.mark.asyncio
async def test_read_document_resource(mcp_server):
    """Test that document resources are read correctly."""
    app = mcp_server.create_app()
    
    # Mock the RTC adapter
    mcp_server.rtc_adapter.get_document_content = AsyncMock(
        return_value="Test document content"
    )
    
    # Get the read resource handler
    read_handler = None
    for route in app.routes:
        if route.path == "/mcp":
            # The handler is wrapped, so we need to access it through the server
            read_handler = mcp_server.server.read_resource
            break
    
    assert read_handler is not None
    
    # Call the handler with a document URI
    result = await read_handler("collaboration://documents/test.md")
    
    # Check the result
    assert len(result.contents) == 1
    assert result.contents[0].uri == "collaboration://documents/test.md"
    assert result.contents[0].mimeType == "text/plain"
    
    # Check that the RTC adapter was called
    mcp_server.rtc_adapter.get_document_content.assert_called_once_with("test.md")


@pytest.mark.asyncio
async def test_read_unknown_resource(mcp_server):
    """Test that unknown resources raise an error."""
    app = mcp_server.create_app()
    
    # Get the read resource handler
    read_handler = None
    for route in app.routes:
        if route.path == "/mcp":
            # The handler is wrapped, so we need to access it through the server
            read_handler = mcp_server.server.read_resource
            break
    
    assert read_handler is not None
    
    # Call the handler with an unknown URI
    with pytest.raises(ValueError, match="Unknown resource URI"):
        await read_handler("collaboration://unknown/resource")


@pytest.mark.asyncio
async def test_subscribe_resource(mcp_server):
    """Test that resource subscriptions work correctly."""
    app = mcp_server.create_app()
    
    # Get the subscribe resource handler
    subscribe_handler = None
    for route in app.routes:
        if route.path == "/mcp":
            # The handler is wrapped, so we need to access it through the server
            subscribe_handler = mcp_server.server.subscribe_resource
            break
    
    assert subscribe_handler is not None
    
    # Call the handler with a resource URI
    result = await subscribe_handler("collaboration://notebooks/test.ipynb")
    
    # Check the result
    assert result.streamId.startswith("resource:")
    assert "notebooks/test.ipynb" in result.streamId