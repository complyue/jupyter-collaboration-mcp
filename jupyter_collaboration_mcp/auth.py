"""
Authentication and authorization for Jupyter Collaboration MCP Server.

This module implements simple token-based authentication and resource-based authorization
integrated with Jupyter's existing security infrastructure.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from tornado.web import HTTPError

logger = logging.getLogger(__name__)


class AuthConfig:
    """Configuration for authentication and authorization."""

    def __init__(self):
        """Initialize authentication configuration."""
        self.allowed_origins = ["*"]  # Should be restricted in production
        self.rate_limit_requests = 100  # requests per minute
        self.rate_limit_window = 60  # seconds
        self.valid_token = None  # Simple token for authentication


class AuthManager:
    """Manager for authentication and authorization operations."""

    def __init__(self, config: AuthConfig):
        """Initialize the auth manager.

        Args:
            config: Authentication configuration
        """
        self.config = config
        self._rate_limits: Dict[str, List[float]] = {}

    def check_rate_limit(self, client_id: str) -> bool:
        """Check if a client has exceeded the rate limit.

        Args:
            client_id: Identifier for the client (e.g., IP address or user ID)

        Returns:
            True if the client is within the rate limit, False if exceeded
        """
        now = datetime.utcnow().timestamp()

        # Clean up old entries
        if client_id in self._rate_limits:
            self._rate_limits[client_id] = [
                timestamp
                for timestamp in self._rate_limits[client_id]
                if now - timestamp < self.config.rate_limit_window
            ]
        else:
            self._rate_limits[client_id] = []

        # Check if limit exceeded
        if len(self._rate_limits[client_id]) >= self.config.rate_limit_requests:
            return False

        # Add current request
        self._rate_limits[client_id].append(now)
        return True

    def check_cors_origin(self, origin: str) -> bool:
        """Check if an origin is allowed for CORS.

        Args:
            origin: Origin URL to check

        Returns:
            True if the origin is allowed, False otherwise
        """
        if "*" in self.config.allowed_origins:
            return True

        return origin in self.config.allowed_origins

    def verify_token(self, token: str) -> bool:
        """Verify a token.

        Args:
            token: Token string to verify

        Returns:
            True if the token is valid, False otherwise
        """
        if not self.config.valid_token:
            return False  # No token configured

        return token == self.config.valid_token

    def set_valid_token(self, token: str):
        """Set the valid token for authentication.

        Args:
            token: Token string to use for authentication
        """
        self.config.valid_token = token


class ResourceAuthorizer:
    """Authorizer for resource-based access control."""

    def __init__(self, auth_manager: AuthManager):
        """Initialize the resource authorizer.

        Args:
            auth_manager: Authentication manager
        """
        self.auth_manager = auth_manager

    async def check_document_access(
        self, user_claims: Dict[str, Any], document_path: str, permission: str = "read"
    ) -> bool:
        """Check if a user has access to a document.

        Args:
            user_claims: User claims from the authentication
            document_path: Path to the document
            permission: Permission level to check (read, write, execute, admin)

        Returns:
            True if access is granted, False otherwise
        """
        user_id = user_claims.get("sub")

        # In a real implementation, this would check against Jupyter's
        # file permissions and collaboration access control
        # For now, we'll implement a simple check

        # Admin users have access to everything
        if user_claims.get("admin", False):
            return True

        # Check document-specific permissions
        document_permissions = user_claims.get("document_permissions", {})
        if document_path in document_permissions:
            user_permissions = document_permissions[document_path]
            return self._has_permission(user_permissions, permission)

        # Default allow for read access
        return permission == "read"

    async def check_session_access(
        self, user_claims: Dict[str, Any], session_id: str, permission: str = "join"
    ) -> bool:
        """Check if a user has access to a collaboration session.

        Args:
            user_claims: User claims from the authentication
            session_id: ID of the session
            permission: Permission level to check (join, leave, manage)

        Returns:
            True if access is granted, False otherwise
        """
        user_id = user_claims.get("sub")

        # In a real implementation, this would check against session
        # membership and permissions
        # For now, we'll implement a simple check

        # Admin users have access to everything
        if user_claims.get("admin", False):
            return True

        # Check session-specific permissions
        session_permissions = user_claims.get("session_permissions", {})
        if session_id in session_permissions:
            user_permissions = session_permissions[session_id]
            return self._has_permission(user_permissions, permission)

        # Default allow for join permission
        return permission == "join"

    def _has_permission(self, user_permissions: List[str], required_permission: str) -> bool:
        """Check if the user has the required permission.

        Args:
            user_permissions: List of permissions the user has
            required_permission: Permission that is required

        Returns:
            True if the user has the required permission
        """
        permission_hierarchy = {
            "read": ["read"],
            "write": ["read", "write"],
            "execute": ["read", "write", "execute"],
            "admin": ["read", "write", "execute", "admin"],
        }

        if required_permission not in permission_hierarchy:
            return False

        required_permissions = permission_hierarchy[required_permission]
        return any(perm in user_permissions for perm in required_permissions)


# Global auth manager instance
_auth_manager: Optional[AuthManager] = None
_authorizer: Optional[ResourceAuthorizer] = None


def get_auth_manager() -> AuthManager:
    """Get the global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager(AuthConfig())
    return _auth_manager


def get_authorizer() -> ResourceAuthorizer:
    """Get the global resource authorizer instance."""
    global _authorizer
    if _authorizer is None:
        _authorizer = ResourceAuthorizer(get_auth_manager())
    return _authorizer


def configure_auth(config: AuthConfig):
    """Configure authentication with a custom config.

    Args:
        config: Authentication configuration
    """
    global _auth_manager, _authorizer
    _auth_manager = AuthManager(config)
    _authorizer = ResourceAuthorizer(_auth_manager)


def configure_auth_with_token(token: str):
    """Configure authentication with a simple token.

    Args:
        token: Token to use for authentication
    """
    config = AuthConfig()
    config.valid_token = token
    configure_auth(config)


async def authenticate_mcp_request(scope) -> Dict[str, Any]:
    """Authenticate an MCP request using a simple token.

    Args:
        scope: ASGI scope dictionary

    Returns:
        User claims dictionary

    Raises:
        HTTPError: If authentication fails
    """
    auth_manager = get_auth_manager()

    if isinstance(auth_manager.config.valid_token, str):
        # Extract token from headers
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if not auth_header or not auth_header.startswith("Identity.token "):
            raise HTTPError(401, "Missing or invalid authentication header")

        token = auth_header[15:]  # Remove "Identity.token " prefix

        # Verify token
        if token != auth_manager.config.valid_token:
            raise HTTPError(401, "Invalid token")
    else:
        # TODO: impl other means of auth for security
        pass

    # Return basic user claims
    return {"sub": "user", "iat": datetime.utcnow(), "admin": True}
