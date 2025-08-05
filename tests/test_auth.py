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
    AuthorizedMCPHandler,
    ResourceAuthorizer,
    authenticate_mcp_request,
    configure_auth,
    create_auth_token,
    get_auth_manager,
    get_authorizer,
    get_secret_key,
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
    assert auth_config.secret_key == "default-secret-key"
    assert auth_config.algorithm == "HS256"
    assert auth_config.allowed_origins == ["*"]
    assert auth_config.rate_limit_requests == 100
    assert auth_config.rate_limit_window == 60


def test_auth_manager_initialization(auth_manager):
    """Test that the authentication manager initializes correctly."""
    assert auth_manager.config is not None
    assert auth_manager._rate_limits == {}


def test_create_token(auth_manager):
    """Test creating a JWT token."""
    user_id = "test-user"
    additional_claims = {"admin": True}

    token = auth_manager.create_token(user_id, additional_claims)

    assert isinstance(token, str)
    assert len(token) > 0


def test_verify_token(auth_manager):
    """Test verifying a JWT token."""
    user_id = "test-user"
    additional_claims = {"admin": True}

    # Create a token
    token = auth_manager.create_token(user_id, additional_claims)

    # Verify the token
    claims = auth_manager.verify_token(token)

    assert claims["sub"] == user_id
    assert claims["admin"] is True
    assert claims["type"] == "mcp-access"


def test_verify_invalid_token(auth_manager):
    """Test verifying an invalid JWT token."""
    with pytest.raises(Exception):  # Should raise jwt.PyJWTError
        auth_manager.verify_token("invalid-token")


def test_verify_expired_token(auth_manager):
    """Test verifying an expired JWT token."""
    # Create a token that's already expired
    user_id = "test-user"
    claims = {
        "sub": user_id,
        "iat": datetime.utcnow() - timedelta(hours=2),
        "exp": datetime.utcnow() - timedelta(hours=1),
        "type": "mcp-access",
    }

    import jwt

    token = jwt.encode(
        claims, auth_manager.config.secret_key, algorithm=auth_manager.config.algorithm
    )

    # Verify the token
    with pytest.raises(Exception):  # Should raise jwt.PyJWTError
        auth_manager.verify_token(token)


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
    config.secret_key = "custom-secret-key"

    # Configure auth
    configure_auth(config)

    # Check that the instances were updated
    auth_manager = get_auth_manager()
    assert auth_manager.config.secret_key == "custom-secret-key"

    authorizer = get_authorizer()
    assert authorizer.auth_manager.config.secret_key == "custom-secret-key"


@pytest.mark.asyncio
async def test_authenticate_mcp_request():
    """Test authenticating an MCP request."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Create a valid token
    auth_manager = get_auth_manager()
    token = auth_manager.create_token("test-user")

    # Create a mock scope
    scope = {
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"x-forwarded-for", b"test-client"),
        ]
    }

    # Authenticate the request
    user_claims = await authenticate_mcp_request(scope)

    assert user_claims["sub"] == "test-user"


@pytest.mark.asyncio
async def test_authenticate_mcp_request_missing_header():
    """Test authenticating an MCP request with missing auth header."""
    # Create a mock scope without auth header
    scope = {"headers": []}

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_invalid_header():
    """Test authenticating an MCP request with invalid auth header."""
    # Create a mock scope with invalid auth header
    scope = {"headers": [(b"authorization", b"InvalidHeader test-token")]}

    # Authenticate the request
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


@pytest.mark.asyncio
async def test_authenticate_mcp_request_rate_limited():
    """Test authenticating an MCP request when rate limited."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    # Create a valid token
    auth_manager = get_auth_manager()
    token = auth_manager.create_token("test-user")

    # Create a mock scope
    scope = {
        "headers": [
            (b"authorization", f"Bearer {token}".encode()),
            (b"x-forwarded-for", b"test-client"),
        ]
    }

    # Use up the rate limit
    for _ in range(auth_manager.config.rate_limit_requests):
        await authenticate_mcp_request(scope)

    # The next request should be rate limited
    with pytest.raises(Exception):  # Should raise HTTPError
        await authenticate_mcp_request(scope)


def test_authorized_mcp_handler_prepare():
    """Test the AuthorizedMCPHandler prepare method."""
    # Create a mock request
    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-token"}

    # Create a mock application
    application = MagicMock()

    # Create the handler
    handler = AuthorizedMCPHandler(application, request)

    # Mock the parent prepare method
    with patch.object(AuthorizedMCPHandler, "prepare"):
        # Mock the auth manager
        with patch("jupyter_collaboration_mcp.auth.get_auth_manager") as mock_get_auth:
            mock_auth_manager = MagicMock()
            mock_auth_manager.verify_token.return_value = {"sub": "test-user"}
            mock_get_auth.return_value = mock_auth_manager

            # Call prepare
            handler.prepare()

            # Check that the token was verified
            mock_auth_manager.verify_token.assert_called_once_with("test-token")

            # Check that the current user was set
            assert handler.current_user == {"sub": "test-user"}


@pytest.mark.asyncio
async def test_authorized_mcp_handler_check_document_access():
    """Test the AuthorizedMCPHandler check_document_access method."""
    # Create a mock request
    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-token"}

    # Create a mock application
    application = MagicMock()

    # Create the handler
    handler = AuthorizedMCPHandler(application, request)
    handler.current_user = {"sub": "test-user"}

    # Mock the authorizer
    with patch("jupyter_collaboration_mcp.auth.get_authorizer") as mock_get_authorizer:
        mock_authorizer = MagicMock()
        mock_authorizer.check_document_access = AsyncMock(return_value=True)
        mock_get_authorizer.return_value = mock_authorizer

        # Call check_document_access
        await handler.check_document_access("/test.md", "read")

        # Check that the authorizer was called correctly
        mock_authorizer.check_document_access.assert_called_once_with(
            {"sub": "test-user"}, "/test.md", "read"
        )


@pytest.mark.asyncio
async def test_authorized_mcp_handler_check_document_access_denied():
    """Test the AuthorizedMCPHandler check_document_access method when access is denied."""
    # Create a mock request
    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-token"}

    # Create a mock application
    application = MagicMock()

    # Create the handler
    handler = AuthorizedMCPHandler(application, request)
    handler.current_user = {"sub": "test-user"}

    # Mock the authorizer
    with patch("jupyter_collaboration_mcp.auth.get_authorizer") as mock_get_authorizer:
        mock_authorizer = MagicMock()
        mock_authorizer.check_document_access = AsyncMock(return_value=False)
        mock_get_authorizer.return_value = mock_authorizer

        # Call check_document_access and expect an exception
        with pytest.raises(Exception):  # Should raise HTTPError
            await handler.check_document_access("/test.md", "write")


def test_get_secret_key():
    """Test getting the secret key."""
    secret_key = get_secret_key()

    assert secret_key == "default-secret-key"


def test_create_auth_token():
    """Test creating an authentication token."""
    # Reset the global auth manager
    import jupyter_collaboration_mcp.auth

    jupyter_collaboration_mcp.auth._auth_manager = None

    token = create_auth_token("test-user", admin=True)

    assert isinstance(token, str)
    assert len(token) > 0

    # Verify the token
    auth_manager = get_auth_manager()
    claims = auth_manager.verify_token(token)

    assert claims["sub"] == "test-user"
    assert claims["admin"] is True
