"""
Authentication Handler for Test-Genie

Auto-detects authentication type from .env file and provides headers
and query params for API requests.

Supported Auth Types:
- Bearer Token (JWT)
- API Key (header or query param)
- Basic Auth (username:password)
"""

import os
import sys
import json
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

    BEARER_TOKEN_VARS = [
        "AUTH_BEARER_TOKEN",
        "BEARER_TOKEN",
        "JWT_TOKEN",
        "ACCESS_TOKEN",
    ]

    API_KEY_VARS = [
        "AUTH_API_KEY",
        "API_KEY",
    ]

    API_KEY_HEADER_VARS = [
        "AUTH_API_KEY_HEADER",
        "API_KEY_HEADER",
    ]

    API_KEY_IN_VARS = [
        "AUTH_API_KEY_IN",
        "API_KEY_IN",
    ]

    BASIC_USERNAME_VARS = [
        "AUTH_BASIC_USERNAME",
        "BASIC_USERNAME",
        "AUTH_USERNAME",
    ]

    BASIC_PASSWORD_VARS = [
        "AUTH_BASIC_PASSWORD",
        "BASIC_PASSWORD",
        "AUTH_PASSWORD",
    ]

    def __init__(self, project_path: str):
        """
        Initialize AuthHandler and load auth config from env.
        """
        self.auth_type: Optional[str] = None
        self.auth_config: Dict = {}
        self.project_path = project_path

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

    def _get_env_value(self, var_names: list, env: Dict) -> Optional[str]:
        """
        Get environment variable value, checking multiple possible names.
        """
        for var in var_names:
            value = env.get(var)
            if value:
                return value
        return None

    def _detect_auth_type(self, env: Dict):
        """
        Auto-detect authentication type based on env variables.
        Sets self.auth_type and self.auth_config.
        """

        # Bearer Token
        bearer_token = self._get_env_value(self.BEARER_TOKEN_VARS, env)
        if bearer_token:
            self.auth_type = "bearer"
            self.auth_config = {"token": bearer_token}
            print("[AUTH] Detected: Bearer Token authentication", file=sys.stderr, flush=True)
            return

        # API Key
        api_key = self._get_env_value(self.API_KEY_VARS, env)
        if api_key:
            header_name = (
                self._get_env_value(self.API_KEY_HEADER_VARS, env)
                or "X-API-Key"
            )
            key_location = (
                self._get_env_value(self.API_KEY_IN_VARS, env)
                or "header"
            )

            self.auth_type = "apikey"
            self.auth_config = {
                "key": api_key,
                "header": header_name,
                "in": key_location.lower(),
            }

            print(
                f"[AUTH] Detected: API Key authentication (header: {header_name})",
                file=sys.stderr,
                flush=True,
            )
            return

        # Basic Auth
        username = self._get_env_value(self.BASIC_USERNAME_VARS, env)
        password = self._get_env_value(self.BASIC_PASSWORD_VARS, env)
        if username and password:
            self.auth_type = "basic"
            self.auth_config = {
                "username": username,
                "password": password,
            }
            print(
                f"[AUTH] Detected: Basic authentication (user: {username})",
                file=sys.stderr,
                flush=True,
            )
            return

        # No Auth
        self.auth_type = None
        self.auth_config = {}
        print("[AUTH] No authentication configured", file=sys.stderr, flush=True)

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers to inject into HTTP requests.
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
            # query handled separately

        elif self.auth_type == "basic":
            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            credentials = base64.b64encode(
                f"{username}:{password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    def get_auth_query_params(self) -> Dict[str, str]:
        """
        Get authentication query parameters (for API keys in query string).
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
        """
        if self.auth_type == "bearer":
            token = self.auth_config.get("token", "")
            masked = token[:10] + "..." + token[-4:] if len(token) > 20 else "****"
            return f"Bearer Token: {masked}"

        elif self.auth_type == "apikey":
            key = self.auth_config.get("key", "")
            header = self.auth_config.get("header", "X-API-Key")
            location = self.auth_config.get("in", "header")
            masked = key[:4] + "..." + key[-4:] if len(key) > 10 else "****"
            return f"API Key ({location}): {header}={masked}"

        elif self.auth_type == "basic":
            username = self.auth_config.get("username", "")
            return f"Basic Auth: {username}:****"

        return "No authentication configured"

    def is_authenticated(self) -> bool:
        """
        Check if any authentication is configured.
        """
        return self.auth_type is not None

    def get_auth_type(self) -> Optional[str]:
        """
        Get the detected authentication type.
        """
        return self.auth_type
