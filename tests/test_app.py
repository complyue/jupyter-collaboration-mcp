"""
Tests for the main MCP server application.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    # session_manager is no longer an instance variable
    assert not hasattr(mcp_server, 'session_manager') or mcp_server.session_manager is None


@pytest.mark.asyncio
async def test_create_app(mcp_server):
    """Test that the Starlette application is created correctly."""
    app = mcp_server.create_app()

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
            (b"content-type", b"application/json"),
        ],
    }

    # Mock the authentication
    with patch("jupyter_collaboration_mcp.app.authenticate_mcp_request") as mock_auth, \
         patch("jupyter_collaboration_mcp.app.StreamableHTTPSessionManager") as mock_session_manager_class:
        
        mock_auth.return_value = {"sub": "test-user"}
        
        # Create a mock session manager instance
        mock_session_manager = MagicMock()
        mock_session_manager.run.return_value.__aenter__ = AsyncMock()
        mock_session_manager.run.return_value.__aexit__ = AsyncMock()
        mock_session_manager.handle_request = AsyncMock()
        mock_session_manager_class.return_value = mock_session_manager

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

        # Check that a new session manager was created for this request
        mock_session_manager_class.assert_called_once_with(
            app=mcp_server.server,
            event_store=mcp_server.event_store,
        )

        # Check that the session manager was used correctly
        mock_session_manager.run.assert_called_once()
        mock_session_manager.handle_request.assert_called_once_with(scope, receive, send)


@pytest.mark.asyncio
async def test_broadcast_event(mcp_server):
    """Test that events are broadcast correctly."""
    app = mcp_server.create_app()

    # Mock the event store
    mcp_server.event_store.store_event = AsyncMock(return_value="test-event-id")

    # Broadcast an event
    await mcp_server.broadcast_event("test-event", {"data": "test"})

    # Check that the event was stored
    mcp_server.event_store.store_event.assert_called_once()

    # Note: With per-request session managers, direct broadcasting is no longer supported
    # The event is stored in the event store for later retrieval


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
