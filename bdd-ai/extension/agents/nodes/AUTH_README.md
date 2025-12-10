# Authentication Handler for Test-Genie

## Overview

This document describes the authentication handling feature added to Test-Genie's API test execution pipeline. The feature enables automatic authentication header injection for testing protected API endpoints.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [Supported Authentication Types](#supported-authentication-types)
- [Configuration Guide](#configuration-guide)
- [Code Structure](#code-structure)
- [How It Works](#how-it-works)
- [Testing the Feature](#testing-the-feature)
- [Future Enhancements](#future-enhancements)

---

## Problem Statement

Previously, Test-Genie could only test unauthenticated API endpoints. When running tests against protected endpoints (requiring API keys, JWT tokens, or basic auth), all requests would fail with `401 Unauthorized` or `403 Forbidden`.

**Goal:** Enable users to configure authentication credentials that get automatically injected into all HTTP requests during test execution.

---

## Solution Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER'S PROJECT                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   .env file (in project root)                                   │
│   ┌─────────────────────────────────────────┐                   │
│   │ AUTH_BEARER_TOKEN=eyJhbGciOiJIUzI1...   │                   │
│   │ # or                                     │                   │
│   │ AUTH_API_KEY=sk-abc123                  │                   │
│   │ AUTH_API_KEY_HEADER=X-API-Key           │                   │
│   │ # or                                     │                   │
│   │ AUTH_BASIC_USERNAME=admin               │                   │
│   │ AUTH_BASIC_PASSWORD=secret              │                   │
│   └─────────────────────────────────────────┘                   │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AUTH HANDLER                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. Load .env from project root                                │
│   2. Auto-detect auth type based on which vars are set          │
│   3. Provide headers/params for HTTP requests                   │
│                                                                  │
│   Priority: Bearer > API Key > Basic Auth > None                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   TEST EXECUTION NODE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   _run_curl_command():                                          │
│                                                                  │
│   headers = {"Content-Type": "application/json"}                │
│                                                                  │
│   # 🔐 Auth injection happens here                              │
│   if self.auth_handler:                                         │
│       auth_headers = self.auth_handler.get_auth_headers()       │
│       headers.update(auth_headers)                              │
│                                                                  │
│   requests.request(method, url, headers=headers, ...)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Supported Authentication Types

### 1. Bearer Token (JWT)

**Use Case:** OAuth 2.0, JWT-based APIs

**Headers Generated:**
```
Authorization: Bearer <token>
```

**Environment Variables:**
| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_BEARER_TOKEN` | Yes | The JWT or access token |

**Alternatives:** `BEARER_TOKEN`, `JWT_TOKEN`, `ACCESS_TOKEN`

---

### 2. API Key

**Use Case:** Simple API key authentication (header or query param)

**Headers Generated (header mode):**
```
X-API-Key: <key>
```

**Or Query Param (query mode):**
```
?api_key=<key>
```

**Environment Variables:**
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH_API_KEY` | Yes | - | The API key value |
| `AUTH_API_KEY_HEADER` | No | `X-API-Key` | Header name or query param name |
| `AUTH_API_KEY_IN` | No | `header` | Where to send: `header` or `query` |

**Alternatives:** `API_KEY`, `API_KEY_HEADER`, `API_KEY_IN`

---

### 3. Basic Authentication

**Use Case:** Username/password authentication

**Headers Generated:**
```
Authorization: Basic <base64(username:password)>
```

**Environment Variables:**
| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_BASIC_USERNAME` | Yes | Username |
| `AUTH_BASIC_PASSWORD` | Yes | Password |

**Alternatives:** `BASIC_USERNAME`/`BASIC_PASSWORD`, `AUTH_USERNAME`/`AUTH_PASSWORD`

---

## Configuration Guide

### Step 1: Create `.env` File

Create a `.env` file in the **root of the project being tested** (not the Test-Genie extension folder):

```bash
# /path/to/your/project/.env

# Option A: Bearer Token
AUTH_BEARER_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U

# Option B: API Key (in header)
# AUTH_API_KEY=sk-proj-abc123xyz
# AUTH_API_KEY_HEADER=Authorization
# Note: For "Authorization: Bearer <key>" style, use Bearer token instead

# Option C: API Key (in query string)
# AUTH_API_KEY=abc123
# AUTH_API_KEY_HEADER=api_key
# AUTH_API_KEY_IN=query

# Option D: Basic Auth
# AUTH_BASIC_USERNAME=admin
# AUTH_BASIC_PASSWORD=supersecret123
```

### Step 2: Add `.env` to `.gitignore`

**IMPORTANT:** Never commit credentials to version control!

```bash
# .gitignore
.env
.env.local
.env.*.local
```

### Step 3: Run Tests

The authentication will be automatically detected and applied when you run BDD tests.

---

## Code Structure

### Files Modified/Added

```
bdd-ai/extension/agents/nodes/
├── auth_handler.py      # NEW: Authentication detection & header generation
├── test_execution.py    # MODIFIED: Integrates AuthHandler
├── requirements.txt     # MODIFIED: Added dependencies
└── AUTH_README.md       # NEW: This documentation
```

### `auth_handler.py` - Key Components

```python
class AuthHandler:
    """
    Handles authentication configuration auto-detection and header injection.
    
    Priority order for detection:
    1. Bearer Token (if AUTH_BEARER_TOKEN or BEARER_TOKEN is set)
    2. API Key (if AUTH_API_KEY or API_KEY is set)
    3. Basic Auth (if both AUTH_BASIC_USERNAME and AUTH_BASIC_PASSWORD are set)
    4. No Auth (fallback)
    """
    
    def __init__(self, project_path: str):
        """Load .env and detect auth type."""
        
    def get_auth_headers(self) -> Dict[str, str]:
        """Returns headers to inject into requests."""
        
    def get_auth_query_params(self) -> Dict[str, str]:
        """Returns query params (for API key in URL)."""
        
    def get_auth_summary(self) -> str:
        """Returns masked summary for logging/display."""
        
    def is_authenticated(self) -> bool:
        """Check if any auth is configured."""
```

### `test_execution.py` - Integration Points

```python
class TestExecutionNode:
    def __init__(self):
        # Auth handler initialized as None
        self.auth_handler: Optional[AuthHandler] = None
    
    def __call__(self, state):
        # Initialize auth handler with project path
        self.auth_handler = AuthHandler(state.project_path)
        
    def _run_curl_command(self, method, url, base_url, body=None):
        headers = {"Content-Type": "application/json"}
        
        # 🔐 Inject auth headers
        if self.auth_handler:
            auth_headers = self.auth_handler.get_auth_headers()
            headers.update(auth_headers)
            
            # Handle query param auth
            auth_params = self.auth_handler.get_auth_query_params()
            if auth_params:
                # URL encode and append
                ...
```

---

## How It Works

### Detection Flow

```
1. TestExecutionNode.__call__(state) is invoked
                    │
                    ▼
2. AuthHandler(state.project_path) is created
                    │
                    ▼
3. AuthHandler._load_env() loads .env file
                    │
                    ▼
4. AuthHandler._detect_auth_type() checks env vars:
   │
   ├─► AUTH_BEARER_TOKEN set? → auth_type = "bearer"
   │
   ├─► AUTH_API_KEY set? → auth_type = "apikey"
   │
   ├─► AUTH_BASIC_USERNAME + PASSWORD set? → auth_type = "basic"
   │
   └─► None set? → auth_type = None (no auth)
                    │
                    ▼
5. For each HTTP request in _run_curl_command():
   │
   └─► get_auth_headers() returns appropriate headers
       get_auth_query_params() returns URL params (if needed)
```

### Security Considerations

1. **Credentials never logged in full** - `get_auth_summary()` masks tokens:
   ```
   Bearer Token: eyJhbGciOi...xyz9
   API Key (header): X-API-Key=sk-p...xyz3
   Basic Auth: admin:****
   ```

2. **Logs go to stderr** - All `print()` statements use `file=sys.stderr` to avoid corrupting JSON output on stdout.

3. **URL encoding** - API keys in query params are URL-encoded using `urllib.parse.quote()`.

---

## Testing the Feature

### Manual Testing

1. **Create a test API** (e.g., Flask app with auth):

```python
# test_api.py
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/protected')
def protected():
    auth = request.headers.get('Authorization')
    if auth != 'Bearer test-token-123':
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"message": "Success!", "user": "authenticated"})

if __name__ == '__main__':
    app.run(port=5000)
```

2. **Create `.env` in your project:**

```bash
AUTH_BEARER_TOKEN=test-token-123
```

3. **Run Test-Genie** and verify:
   - Console shows: `[AUTH] Detected: Bearer Token authentication`
   - HTML report shows: `🔐 Authentication: Bearer Token: test-token...123`
   - Tests pass with 200 status (not 401)

### Unit Test Suggestions

```python
# test_auth_handler.py
import os
import pytest
from auth_handler import AuthHandler

def test_bearer_token_detection(tmp_path):
    # Create .env file
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_BEARER_TOKEN=my-secret-token")
    
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_type() == "bearer"
    assert handler.get_auth_headers() == {"Authorization": "Bearer my-secret-token"}
    assert handler.is_authenticated() == True

def test_api_key_in_header(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_API_KEY=abc123\nAUTH_API_KEY_HEADER=X-Custom-Key")
    
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_type() == "apikey"
    assert handler.get_auth_headers() == {"X-Custom-Key": "abc123"}

def test_api_key_in_query(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_API_KEY=abc123\nAUTH_API_KEY_IN=query")
    
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_headers() == {}  # Not in headers
    assert handler.get_auth_query_params() == {"X-API-Key": "abc123"}

def test_basic_auth(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_BASIC_USERNAME=admin\nAUTH_BASIC_PASSWORD=secret")
    
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_type() == "basic"
    headers = handler.get_auth_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")

def test_no_auth(tmp_path):
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_type() == None
    assert handler.get_auth_headers() == {}
    assert handler.is_authenticated() == False

def test_priority_bearer_over_apikey(tmp_path):
    """Bearer should take priority if both are set"""
    env_file = tmp_path / ".env"
    env_file.write_text("AUTH_BEARER_TOKEN=token\nAUTH_API_KEY=key")
    
    handler = AuthHandler(str(tmp_path))
    
    assert handler.get_auth_type() == "bearer"  # Bearer wins
```

---

## Future Enhancements

| Feature | Description | Priority |
|---------|-------------|----------|
| **OAuth 2.0 Token Refresh** | Auto-refresh expired tokens using client credentials flow | Medium |
| **OpenAPI Security Scheme Detection** | Parse `securitySchemes` from OpenAPI spec and prompt user for missing credentials | Medium |
| **VS Code Secure Storage** | Store credentials in VS Code's secret storage instead of `.env` | Low |
| **Per-Scenario Auth** | Support different auth for different scenarios via Gherkin Background steps | Low |
| **401/403 Detection** | Show helpful message when tests fail with auth errors | Low |
| **Custom Headers** | Support arbitrary custom headers beyond auth (e.g., `X-Request-ID`) | Low |

---

## Troubleshooting

### Issue: Tests still failing with 401

**Possible Causes:**
1. `.env` file not in project root
2. Wrong environment variable name
3. Token expired or invalid

**Debug Steps:**
1. Check stderr output for `[AUTH] Detected: ...` message
2. Verify `.env` path matches `state.project_path`
3. Test token manually with curl:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:5000/api/protected
   ```

### Issue: JSON parse error in VS Code

**Cause:** Print statements going to stdout instead of stderr

**Solution:** All logging uses `print(..., file=sys.stderr)` - this was fixed in the implementation.

### Issue: Special characters in API key not working

**Cause:** URL encoding issues for query param auth

**Solution:** The implementation uses `urllib.parse.quote()` with `safe=''` to encode all special characters.

---

## Contact

For questions about this implementation, contact the developer who worked on this feature or open an issue in the repository.

