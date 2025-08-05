"""
Authentication and authorization for Jupyter Collaboration MCP Server.

This module implements token-based authentication and resource-based authorization
integrated with Jupyter's existing security infrastructure.
"""

import jwt
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from jupyter_server.auth import AuthorizedAsyncHandler
from tornado.web import HTTPError

logger = logging.getLogger(__name__)


class AuthConfig:
    """Configuration for authentication and authorization."""
    
    def __init__(self):
        """Initialize authentication configuration."""
        self.token_expiry = timedelta(hours=1)
        self.secret_key = "default-secret-key"  # Should be overridden in config
        self.algorithm = "HS256"
        self.allowed_origins = ["*"]  # Should be restricted in production
        self.rate_limit_requests = 100  # requests per minute
        self.rate_limit_window = 60  # seconds


class AuthManager:
    """Manager for authentication and authorization operations."""
    
    def __init__(self, config: AuthConfig):
        """Initialize the auth manager.
        
        Args:
            config: Authentication configuration
        """
        self.config = config
        self._rate_limits: Dict[str, List[float]] = {}
    
    def create_token(self, user_id: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
        """Create a JWT token for a user.
        
        Args:
            user_id: ID of the user
            additional_claims: Additional claims to include in the token
            
        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        expiry = now + self.config.token_expiry
        
        claims = {
            "sub": user_id,
            "iat": now,
            "exp": expiry,
            "type": "mcp-access"
        }
        
        if additional_claims:
            claims.update(additional_claims)
        
        token = jwt.encode(
            claims,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )
        
        return token
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token claims
            
        Raises:
            jwt.PyJWTError: If the token is invalid
        """
        try:
            claims = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm]
            )
            
            # Check token type
            if claims.get("type") != "mcp-access":
                raise jwt.PyJWTError("Invalid token type")
            
            return claims
        except jwt.ExpiredSignatureError:
            raise jwt.PyJWTError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise jwt.PyJWTError(f"Invalid token: {str(e)}")
    
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
                timestamp for timestamp in self._rate_limits[client_id]
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


class ResourceAuthorizer:
    """Authorizer for resource-based access control."""
    
    def __init__(self, auth_manager: AuthManager):
        """Initialize the resource authorizer.
        
        Args:
            auth_manager: Authentication manager
        """
        self.auth_manager = auth_manager
    
    async def check_document_access(self, user_claims: Dict[str, Any], 
                                   document_path: str, 
                                   permission: str = "read") -> bool:
        """Check if a user has access to a document.
        
        Args:
            user_claims: User claims from the JWT token
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
    
    async def check_session_access(self, user_claims: Dict[str, Any], 
                                 session_id: str, 
                                 permission: str = "join") -> bool:
        """Check if a user has access to a collaboration session.
        
        Args:
            user_claims: User claims from the JWT token
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
            "admin": ["read", "write", "execute", "admin"]
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


async def authenticate_mcp_request(scope) -> Dict[str, Any]:
    """Authenticate an MCP request using Jupyter's authentication system.
    
    Args:
        scope: ASGI scope dictionary
        
    Returns:
        User claims dictionary
        
    Raises:
        HTTPError: If authentication fails
    """
    auth_manager = get_auth_manager()
    
    # Extract token from headers
    headers = dict(scope.get("headers", []))
    auth_header = headers.get(b"authorization", b"").decode()
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPError(401, "Missing or invalid authentication header")
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    # Check rate limit
    client_id = headers.get(b"x-forwarded-for", b"").decode() or "unknown"
    if not auth_manager.check_rate_limit(client_id):
        raise HTTPError(429, "Rate limit exceeded")
    
    # Check CORS origin
    origin = headers.get(b"origin", b"").decode()
    if origin and not auth_manager.check_cors_origin(origin):
        raise HTTPError(403, "Origin not allowed")
    
    try:
        # Validate JWT token
        claims = auth_manager.verify_token(token)
        return claims
    except jwt.PyJWTError as e:
        raise HTTPError(401, f"Invalid token: {str(e)}")


class AuthorizedMCPHandler(AuthorizedAsyncHandler):
    """Base handler for MCP endpoints with authorization."""
    
    def prepare(self):
        """Prepare the handler with authentication and authorization."""
        super().prepare()
        
        # Get user from the request
        token = self.request.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            raise HTTPError(401, "Missing or invalid authentication header")
        
        token = token[7:]  # Remove "Bearer " prefix
        
        try:
            auth_manager = get_auth_manager()
            self.current_user = auth_manager.verify_token(token)
        except jwt.PyJWTError as e:
            raise HTTPError(401, f"Invalid token: {str(e)}")
    
    async def check_document_access(self, document_path: str, permission: str = "read"):
        """Check if the current user has access to a document.
        
        Args:
            document_path: Path to the document
            permission: Permission level to check
            
        Raises:
            HTTPError: If access is denied
        """
        authorizer = get_authorizer()
        if not await authorizer.check_document_access(
            self.current_user, document_path, permission
        ):
            raise HTTPError(403, f"Access denied for document: {document_path}")
    
    async def check_session_access(self, session_id: str, permission: str = "join"):
        """Check if the current user has access to a session.
        
        Args:
            session_id: ID of the session
            permission: Permission level to check
            
        Raises:
            HTTPError: If access is denied
        """
        authorizer = get_authorizer()
        if not await authorizer.check_session_access(
            self.current_user, session_id, permission
        ):
            raise HTTPError(403, f"Access denied for session: {session_id}")


def get_secret_key() -> str:
    """Get the secret key for JWT token validation.
    
    In a real implementation, this would get the key from Jupyter's configuration.
    For now, we'll use a default key.
    
    Returns:
        Secret key string
    """
    # This should be overridden in production to get the key from Jupyter's config
    return "default-secret-key"


def create_auth_token(user_id: str, **kwargs) -> str:
    """Create an authentication token for a user.
    
    Args:
        user_id: ID of the user
        **kwargs: Additional claims to include in the token
        
    Returns:
        JWT token string
    """
    auth_manager = get_auth_manager()
    return auth_manager.create_token(user_id, kwargs)