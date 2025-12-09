"""
Authentication Handler for Test-Genie

Auto-detects authentication type from .env file and provides headers for API requests.

Supported Auth Types:
- Bearer Token (JWT)
- API Key (header or query param)
- Basic Auth (username:password)

Environment Variables:
-----------------------
# Bearer Token
AUTH_BEARER_TOKEN=eyJhbGciOiJIUzI1NiIs...

# API Key
AUTH_API_KEY=your-api-key
AUTH_API_KEY_HEADER=X-API-Key  # Optional, defaults to X-API-Key
AUTH_API_KEY_IN=header         # Optional: "header" or "query", defaults to "header"

# Basic Auth
AUTH_BASIC_USERNAME=admin
AUTH_BASIC_PASSWORD=secret123
"""

import os
import sys
import base64
from typing import Dict, Optional
from dotenv import load_dotenv


class AuthHandler:
    """
    Handles authentication configuration auto-detection and header injection.
    
    Priority order for detection:
    1. Bearer Token (if AUTH_BEARER_TOKEN or BEARER_TOKEN is set)
    2. API Key (if AUTH_API_KEY or API_KEY is set)
    3. Basic Auth (if both AUTH_BASIC_USERNAME and AUTH_BASIC_PASSWORD are set)
    4. No Auth (fallback)
    """
    
    
    BEARER_TOKEN_VARS = ["AUTH_BEARER_TOKEN", "BEARER_TOKEN", "JWT_TOKEN", "ACCESS_TOKEN"]
    API_KEY_VARS = ["AUTH_API_KEY", "API_KEY"]
    API_KEY_HEADER_VARS = ["AUTH_API_KEY_HEADER", "API_KEY_HEADER"]
    API_KEY_IN_VARS = ["AUTH_API_KEY_IN", "API_KEY_IN"]
    BASIC_USERNAME_VARS = ["AUTH_BASIC_USERNAME", "BASIC_USERNAME", "AUTH_USERNAME"]
    BASIC_PASSWORD_VARS = ["AUTH_BASIC_PASSWORD", "BASIC_PASSWORD", "AUTH_PASSWORD"]
    
    def __init__(self, project_path: str):
        """
        Initialize AuthHandler and load .env from project root.
        
        Args:
            project_path: Path to the project root directory
        """
        self.project_path = project_path
        self.auth_type: Optional[str] = None
        self.auth_config: Dict = {}
        
        self._load_env()
        self._detect_auth_type()
    
    def _load_env(self):
        """Load .env file from project root if it exists."""
        env_path = os.path.join(self.project_path, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            print(f"[AUTH] Loaded .env from: {env_path}", file=sys.stderr, flush=True)
        else:
            print(f"[AUTH] No .env file found at: {env_path}", file=sys.stderr, flush=True)
    
    def _get_env_value(self, var_names: list) -> Optional[str]:
        """
        Get environment variable value, checking multiple possible names.
        
        Args:
            var_names: List of possible environment variable names
            
        Returns:
            Value of the first found variable, or None
        """
        for var in var_names:
            value = os.getenv(var)
            if value:
                return value
        return None
    
    def _detect_auth_type(self):
        """
        Auto-detect authentication type based on which env variables are set.
        Sets self.auth_type and self.auth_config.
        """
    
        bearer_token = self._get_env_value(self.BEARER_TOKEN_VARS)
        if bearer_token:
            self.auth_type = "bearer"
            self.auth_config = {"token": bearer_token}
            print(f"[AUTH] Detected: Bearer Token authentication", file=sys.stderr, flush=True)
            return
        
      
        api_key = self._get_env_value(self.API_KEY_VARS)
        if api_key:
            self.auth_type = "apikey"
            header_name = self._get_env_value(self.API_KEY_HEADER_VARS) or "X-API-Key"
            key_location = self._get_env_value(self.API_KEY_IN_VARS) or "header"
            self.auth_config = {
                "key": api_key,
                "header": header_name,
                "in": key_location.lower()
            }
            print(f"[AUTH] Detected: API Key authentication (header: {header_name})", file=sys.stderr, flush=True)
            return
        
      
        username = self._get_env_value(self.BASIC_USERNAME_VARS)
        password = self._get_env_value(self.BASIC_PASSWORD_VARS)
        if username and password:
            self.auth_type = "basic"
            self.auth_config = {"username": username, "password": password}
            print(f"[AUTH] Detected: Basic authentication (user: {username})", file=sys.stderr, flush=True)
            return
        
        
        self.auth_type = None
        self.auth_config = {}
        print("[AUTH] No authentication configured", file=sys.stderr, flush=True)
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers to inject into HTTP requests.
        
        Returns:
            Dictionary of headers to add to requests
        """
        headers = {}
        
        if self.auth_type == "bearer":
            token = self.auth_config.get("token", "")
            headers["Authorization"] = f"Bearer {token}"
            
        elif self.auth_type == "apikey":
            key = self.auth_config.get("key", "")
            header_name = self.auth_config.get("header", "X-API-Key")
            key_location = self.auth_config.get("in", "header")
            
            if key_location == "header":
                headers[header_name] = key
            # Note: Query param auth is handled separately in get_auth_query_params()
            
        elif self.auth_type == "basic":
            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        
        return headers
    
    def get_auth_query_params(self) -> Dict[str, str]:
        """
        Get authentication query parameters (for API keys in query string).
        
        Returns:
            Dictionary of query params to add to requests
        """
        params = {}
        
        if self.auth_type == "apikey":
            key_location = self.auth_config.get("in", "header")
            if key_location == "query":
                param_name = self.auth_config.get("header", "api_key")
                params[param_name] = self.auth_config.get("key", "")
        
        return params
    
    def get_auth_summary(self) -> str:
        """
        Get a human-readable summary of the current auth configuration.
        
        Returns:
            Description string of the auth setup
        """
        if self.auth_type == "bearer":
            token = self.auth_config.get("token", "")
            masked = token[:10] + "..." + token[-4:] if len(token) > 20 else "***"
            return f"Bearer Token: {masked}"
        
        elif self.auth_type == "apikey":
            key = self.auth_config.get("key", "")
            header = self.auth_config.get("header", "X-API-Key")
            location = self.auth_config.get("in", "header")
            masked = key[:4] + "..." + key[-4:] if len(key) > 10 else "***"
            return f"API Key ({location}): {header}={masked}"
        
        elif self.auth_type == "basic":
            username = self.auth_config.get("username", "")
            return f"Basic Auth: {username}:****"
        
        return "No authentication configured"
    
    def is_authenticated(self) -> bool:
        """Check if any authentication is configured."""
        return self.auth_type is not None
    
    def get_auth_type(self) -> Optional[str]:
        """Get the detected authentication type."""
        return self.auth_type

