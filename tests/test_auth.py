"""
Tests for authentication and authorization functionality.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jupyter_collaboration_mcp.auth import (
    AuthConfig,
    AuthManager,
    ResourceAuthorizer,
    authenticate_mcp_request,
    configure_auth,
    configure_auth_with_token,
    get_auth_manager,
    get_authorizer,
)


@pytest.fixture
def auth_config():
    """Create an authentication configuration."""
    return AuthConfig()


@pytest.fixture
def auth_manager(auth_config):
    """Create an authentication manager."""
    return AuthManager(auth_config)


@pytest.fixture
def resource_authorizer(auth_manager):
    """Create a resource authorizer."""
    return ResourceAuthorizer(auth_manager)


def test_auth_config_initialization(auth_config):
    """Test that the authentication configuration initializes correctly."""
    assert auth_config.token_expiry == timedelta(hours=1)
    assert auth_config.allowed_origins == ["*"]
    assert auth_config.rate_limit_requests == 100
    assert auth_config.rate_limit_window == 60
    assert auth_config.valid_token is None


def test_auth_manager_initialization(auth_manager):
    """Test that the authentication manager initializes correctly."""
    assert auth_manager.config is not None
    assert auth_manager._rate_limits == {}


def test_set_and_verify_token(auth_manager):
    """Test setting and verifying a token."""
    token = "test-token"
    auth_manager.set_valid_token(token)
    
    assert auth_manager.verify_token(token) is True
    assert auth_manager.verify_token("wrong-token") is False


def test_verify_token_no_config(auth_manager):
    """Test token verification when no token is configured."""
    assert auth_manager.verify_token("any-token") is False


def test_check_rate_limit_within_limit(auth_manager):
    """Test rate limiting when within the limit."""
    client_id = "test-client"

    # Make requests up to the limit
    for i in range(auth_manager.config.rate_limit_requests):
        assert auth_manager.check_rate_limit(client_id) is True


def test_check_rate_limit_exceeded(auth_manager):
    """Test rate limiting when the limit is exceeded."""
    client_id = "test-client"

    # Make requests up to the limit
    for i in range(auth_manager.config.rate_limit_requests):
        auth_manager.check_rate_limit(client_id)

    # The next request should be rate limited
    assert auth_manager.check_rate_limit(client_id) is False


def test_check_rate_limit_after_window(auth_manager):
    """Test rate limiting after the rate limit window has passed."""
    client_id = "test-client"

    # Make requests up to the limit
    for i in range(auth_manager.config.rate_limit_requests):
        auth_manager.check_rate_limit(client_id)

    # The next request should be rate limited
    assert auth_manager.check_rate_limit(client_id) is False

    # Mock the time to be after the rate limit window
    with patch("time.time", return_value=time.time() + auth_manager.config.rate_limit_window + 1):
        # Now the request should be allowed
        assert auth_manager.check_rate_limit(client_id) is True


def test_check_cors_origin_allowed(auth_manager):
    """Test CORS origin checking with an allowed origin."""
    auth_manager.config.allowed_origins = ["https://example.com"]

    assert auth_manager.check_cors_origin("https://example.com") is True


def test_check_cors_origin_wildcard(auth_manager):
    """Test CORS origin checking with a wildcard."""
    auth_manager.config.allowed_origins = ["*"]

    assert auth_manager.check_cors_origin("https://example.com") is True


def test_check_cors_origin_not_allowed(auth_manager):
    """Test CORS origin checking with a disallowed origin."""
    auth_manager.config.allowed_origins = ["https://example.com"]

    assert auth_manager.check_cors_origin("https://malicious.com") is False


@pytest.mark.asyncio
async def test_check_document_access_allowed(resource_authorizer):
    """Test document access when access is allowed."""
    user_claims = {"sub": "test-user", "document_permissions": {"/test.md": ["read", "write"]}}

    result = await resource_authorizer.check_document_access(user_claims, "/test.md", "read")

    assert result is True


@pytest.mark.asyncio
async def test_check_document_access_denied(resource_authorizer):
    """Test document access when access is denied."""
    user_claims = {"sub": "test-user", "document_permissions": {"/test.md": ["read"]}}

    result = await resource_authorizer.check_document_access(user_claims, "/test.md", "write")

    assert result is False


@pytest.mark.asyncio
async def test_check_document_access_admin(resource_authorizer):
    """Test document access when user is an admin."""
    user_claims = {"sub": "test-user", "admin": True}

    result = await resource_authorizer.check_document_access(user_claims, "/test.md", "write")

    assert result is True


@pytest.mark.asyncio
async def test_check_document_access_default_read(resource_authorizer):
    """Test document access with default read access."""
    user_claims = {"sub": "test-user"}

    result = await resource_authorizer.check_document_access(user_claims, "/test.md", "read")

    assert result is True


@pytest.mark.asyncio
async def test_check_session_access_allowed(resource_authorizer):
    """Test session access when access is allowed."""
    user_claims = {"sub": "test-user", "session_permissions": {"test-session": ["join", "leave"]}}

    result = await resource_authorizer.check_session_access(user_claims, "test-session", "join")

    assert result is True


@pytest.mark.asyncio
async def test_check_session_access_denied(resource_authorizer):
    """Test session access when access is denied."""
    user_claims = {"sub": "test-user", "session_permissions": {"test-session": ["join"]}}

    result = await resource_authorizer.check_session_access(user_claims, "test-session", "manage")

    assert result is False


@pytest.mark.asyncio
async def test_check_session_access_admin(resource_authorizer):
    """Test session access when user is an admin."""
    user_claims = {"sub": "test-user", "admin": True}

    result = await resource_authorizer.check_session_access(user_claims, "test-session", "manage")

    assert result is True


@pytest.mark.asyncio
async def test_check_session_access_default_join(resource_authorizer):
    """Test session access with default join access."""
    user_claims = {"sub": "test-user"}

    result = await resource_authorizer.check_session_access(user_claims, "test-session", "join")

    assert result is True


def test_get_auth_manager():
    """Test getting the global auth manager."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    auth_manager = get_auth_manager()

    assert auth_manager is not None
    assert isinstance(auth_manager, AuthManager)


def test_get_authorizer():
    """Test getting the global resource authorizer."""
    # Reset the global authorizer
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._authorizer = None

    authorizer = get_authorizer()

    assert authorizer is not None
    assert isinstance(authorizer, ResourceAuthorizer)


def test_configure_auth():
    """Test configuring authentication."""
    # Reset the global instances
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None
    jupyter_collaboration_mcp.auth._authorizer = None

    # Create a custom config
    config = AuthConfig()
    config.rate_limit_requests = 200

    # Configure auth
    configure_auth(config)

    # Check that the instances were updated
    auth_manager = get_auth_manager()
    assert auth_manager.config.rate_limit_requests == 200

    authorizer = get_authorizer()
    assert authorizer.auth_manager.config.rate_limit_requests == 200


def test_configure_auth_with_token():
    """Test configuring authentication with a token."""
    # Reset the global instances
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None
    jupyter_collaboration_mcp.auth._authorizer = None

    # Configure auth with a token
    configure_auth_with_token("test-token")

    # Check that the instances were updated
    auth_manager = get_auth_manager()
    assert auth_manager.config.valid_token == "test-token"

    authorizer = get_authorizer()
    assert authorizer.auth_manager.config.valid_token == "test-token"


@pytest.mark.asyncio
async def test_authenticate_mcp_request():
    """Test authenticating an MCP request."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token
    configure_auth_with_token("test-token")

    # Create a mock scope
    scope = {
        "headers": [
            (b"authorization", b"Identity.token test-token"),
            (b"x-forwarded-for", b"test-client"),
        ]
    }

    # Authenticate the request
    user_claims = await authenticate_mcp_request(scope)

    assert user_claims["sub"] == "user"
    assert user_claims["admin"] is True


@pytest.mark.asyncio
async def test_authenticate_mcp_request_missing_header():
    """Test authenticating an MCP request with missing auth header."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token
    configure_auth_with_token("test-token")

    # Create a mock scope without auth header
    scope = {"headers": []}

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_invalid_header():
    """Test authenticating an MCP request with invalid auth header."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token
    configure_auth_with_token("test-token")

    # Create a mock scope with invalid auth header
    scope = {"headers": [(b"authorization", b"Bearer test-token")]}

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_invalid_token():
    """Test authenticating an MCP request with invalid token."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token
    configure_auth_with_token("test-token")

    # Create a mock scope with invalid token
    scope = {
        "headers": [
            (b"authorization", b"Identity.token invalid-token"),
            (b"x-forwarded-for", b"test-client"),
        ]
    }

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_rate_limited():
    """Test authenticating an MCP request when rate limited."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token
    configure_auth_with_token("test-token")

    # Create a mock scope
    scope = {
        "headers": [
            (b"authorization", b"Identity.token test-token"),
            (b"x-forwarded-for", b"test-client"),
        ]
    }

    # Use up the rate limit
    for _ in range(100):  # Default rate limit is 100
        await authenticate_mcp_request(scope)

    # The next request should be rate limited
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_cors_denied():
    """Test authenticating an MCP request with disallowed CORS origin."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Configure with a token and restricted origins
    configure_auth_with_token("test-token")
    config = AuthConfig()
    config.allowed_origins = ["https://example.com"]
    configure_auth(config)

    # Create a mock scope with disallowed origin
    scope = {
        "headers": [
            (b"authorization", b"Identity.token test-token"),
            (b"x-forwarded-for", b"test-client"),
            (b"origin", b"https://malicious.com"),
        ]
    }

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)