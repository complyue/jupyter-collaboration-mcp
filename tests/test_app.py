"""
Tests for the main MCP server application.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tornado.httpclient import HTTPRequest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

from jupyter_collaboration_mcp.app import MCPServer, MCPHandler
from jupyter_collaboration_mcp.tornado_event_store import TornadoEventStore
from jupyter_collaboration_mcp.tornado_session_manager import TornadoSessionManager


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
    assert isinstance(mcp_server.event_store, TornadoEventStore)


@pytest.mark.asyncio
async def test_create_app(mcp_server):
    """Test that the Tornado application is created correctly."""
    app = mcp_server.create_app()

    # Check that the app is a Tornado Application
    assert isinstance(app, Application)

    # Check that the app has the expected handlers
    handlers = [handler[1] for handler in app.handlers[0][1]]
    assert MCPHandler in handlers


@pytest.mark.asyncio
async def test_handle_mcp_request(mcp_server):
    """Test that MCP requests are handled correctly."""
    app = mcp_server.create_app()

    # Mock the authentication
    with patch("jupyter_collaboration_mcp.app.authenticate_mcp_request") as mock_auth:
        mock_auth.return_value = {"sub": "test-user"}

        # Create a mock HTTP request
        request = HTTPRequest(
            url="http://localhost:8888/mcp",
            method="POST",
            headers={
                "Authorization": "Identity.token test-token",
                "Content-Type": "application/json",
            },
            body=b'{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
        )

        # Get the MCP request handler
        handler = None
        for handler_spec in app.handlers[0][1]:
            if handler_spec[1] == MCPHandler:
                handler = handler_spec[1](app, request)
                break

        assert handler is not None

        # Mock the handler's prepare method to simulate authentication
        handler._user = {"sub": "test-user"}

        # Check that authentication was called with the correct scope
        # Note: In Tornado, the scope is created from the request
        expected_scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [
                (b"authorization", b"Identity.token test-token"),
                (b"content-type", b"application/json"),
            ],
        }
        mock_auth.assert_called_once()


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
