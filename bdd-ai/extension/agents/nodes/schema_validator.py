"""
Schema Validator for Test-Genie

Validates API responses against OpenAPI schema definitions.
This enables Contract Testing - ensuring the API implementation
matches the documented contract (OpenAPI spec).

Features:
- Validates response body structure against OpenAPI schemas
- Checks required fields, data types, and formats
- Provides detailed error messages for violations
- Supports nested objects and arrays
"""

import re
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse

__all__ = ["SchemaValidator", "SchemaViolation", "ValidationResult", "format_violations_for_report"]

try:
    from jsonschema import Draft7Validator, ValidationError, FormatChecker
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    print("[SCHEMA] Warning: jsonschema not installed. Schema validation disabled.", file=sys.stderr)


@dataclass
class SchemaViolation:
    """Represents a single schema validation error."""
    path: str  # JSON path to the violation (e.g., "user.email")
    message: str  # Human-readable error message
    expected: str  # What was expected
    actual: str  # What was received
    severity: str = "error"  # "error" or "warning"
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "path": self.path,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity
        }


@dataclass
class ValidationResult:
    """Result of schema validation for a single response."""
    is_valid: bool
    violations: List[SchemaViolation] = field(default_factory=list)
    schema_found: bool = True  
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "schema_found": self.schema_found,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations]
        }


class SchemaValidator:
    """
    Validates API responses against OpenAPI 3.0 schema definitions.
    
    Usage:
        validator = SchemaValidator(openapi_spec)
        result = validator.validate_response(
            endpoint="/api/users",
            method="POST",
            status_code=200,
            response_body={"id": 1, "name": "John"}
        )
        
        if not result.is_valid:
            for violation in result.violations:
                print(f"Error at {violation.path}: {violation.message}")
    """
    
    def __init__(self, openapi_spec: Dict[str, Any]):
        """
        Initialize the validator with an OpenAPI spec.
        
        Args:
            openapi_spec: Parsed OpenAPI 3.0 specification (dict)
        """
        self.spec = openapi_spec
        self.paths = openapi_spec.get("paths", {})
        self.components = openapi_spec.get("components", {})
        self.schemas = self.components.get("schemas", {})
        self.server_url = ""
        servers = self.spec.get("servers", [])
        if servers:
            self.server_url = servers[0].get("url", "")
        try:
            parsed = urlparse(self.server_url or "")
            # base_path will be like "/api/v1" or "/" if none
            self.base_path = parsed.path.rstrip("/") or ""
        except Exception:
            self.base_path = ""

        
    def _resolve_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a $ref pointer to the actual schema.
        
        Args:
            ref: Reference string like "#/components/schemas/User"
            
        Returns:
            Resolved schema dict or None if not found
        """
        if not ref.startswith("#/"):
            return None
            
        parts = ref[2:].split("/")
        current = self.spec
        
        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return None
    
    def _expand_schema(self, schema: Dict[str, Any], _seen_refs: Optional[set] = None) -> Dict[str, Any]:
        """
        Recursively expand $ref references in a schema.
        
        Args:
            schema: Schema that may contain $ref
            _seen_refs: Internal set to track visited refs and prevent infinite recursion
            
        Returns:
            Expanded schema with refs resolved
        """
        if _seen_refs is None:
            _seen_refs = set()
            
        if not isinstance(schema, dict):
            return schema
            
        
        if "$ref" in schema:
            ref = schema["$ref"]
            
            if ref in _seen_refs:
                return schema  # Return unresolved to break cycle
            _seen_refs.add(ref)
            
            resolved = self._resolve_ref(ref)
            if resolved:
                return self._expand_schema(resolved, _seen_refs)
            return schema
            
        # Recursively expand nested schemas
        expanded = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                expanded[key] = {
                    k: self._expand_schema(v, _seen_refs.copy()) 
                    for k, v in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                expanded[key] = self._expand_schema(value, _seen_refs.copy())
            elif key in ("allOf", "oneOf", "anyOf") and isinstance(value, list):
                expanded[key] = [self._expand_schema(item, _seen_refs.copy()) for item in value]
            else:
                expanded[key] = value
                
        return expanded
    
    # def _normalize_path(self, endpoint: str) -> str:
    #     """
    #     Normalize endpoint path for matching.
    #     Converts /api/users/123 to /api/users/{id}
    #     """
    #     # Remove query params
    #     endpoint = endpoint.split("?")[0].rstrip("/")
    #     print("endpoint\n", endpoint)
    #     return endpoint

    def _normalize_path(self, endpoint: str) -> str:

        # 1) Extract the path from the URL
        parsed = urlparse(endpoint)
        path = parsed.path or endpoint      # e.g. "/api/v1/users/u1/addresses"

        # 2) Remove OpenAPI base_path (e.g., "/api/v1")
        if hasattr(self, "base_path") and self.base_path not in (None, "", "/"):
            if path.startswith(self.base_path):
                path = path[len(self.base_path):]   # → "/users/u1/addresses"

        # 3) Ensure leading slash
        if not path.startswith("/"):
            path = "/" + path

        # 4) Remove trailing slash
        path = path.rstrip("/") or "/"

        return path
    
    def _match_path(self, request_path: str) -> Optional[str]:
        """
        Find the OpenAPI path that matches the request path.
        Handles path parameters like /users/{id}.
        
        Args:
            request_path: Actual request path like /api/users/123
            
        Returns:
            Matching OpenAPI path or None
        """
        request_path = self._normalize_path(request_path)
        
        if request_path in self.paths:
            return request_path
            
        for openapi_path in self.paths.keys():
            # Convert /users/{id} to regex /users/[^/]+
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", openapi_path)
            pattern = f"^{pattern}$"
            
            if re.match(pattern, request_path):
                return openapi_path
                
        return None
    
    def _get_response_schema(
        self, 
        endpoint: str, 
        method: str, 
        status_code: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the expected response schema from OpenAPI spec.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            status_code: Response status code
            
        Returns:
            Response schema dict or None if not defined
        """
        matched_path = self._match_path(endpoint)
        if not matched_path:
            return None
            
        path_item = self.paths.get(matched_path, {})
        operation = path_item.get(method.lower(), {})
        
        if not operation:
            return None
            
        responses = operation.get("responses", {})
        
        response_def = responses.get(str(status_code))
        
        if not response_def:
            range_code = f"{str(status_code)[0]}XX"
            response_def = responses.get(range_code)
            
        if not response_def:
            schema = self.components.get("schemas").get("Error")
            return self._expand_schema(schema)

            
        if not response_def:
            return None
            
        content = response_def.get("content", {})

        if not content:
            if method.lower() == "delete" and status_code == 204:
                return None
            schema = self.components.get("schemas").get("Error")
            return self._expand_schema(schema)

        
        json_content = content.get("application/json", {})
        if not json_content:
            for content_type, content_def in content.items():
                if "json" in content_type.lower():
                    json_content = content_def
                    break
                    
        schema = json_content.get("schema", {})
        
        if schema:
            return self._expand_schema(schema)
            
        return None
    
    def validate_response(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_body: Any
    ) -> ValidationResult:
        """
        Validate an API response against the OpenAPI schema.
        
        Args:
            endpoint: API endpoint that was called
            method: HTTP method used
            status_code: Response status code
            response_body: Parsed JSON response body
            
        Returns:
            ValidationResult with is_valid flag and any violations
        """
        if not JSONSCHEMA_AVAILABLE:
            return ValidationResult(
                is_valid=True,
                schema_found=False,
                violations=[SchemaViolation(
                    path="",
                    message="jsonschema library not installed",
                    expected="N/A",
                    actual="N/A",
                    severity="warning"
                )]
            )
        
        schema = self._get_response_schema(endpoint, method, status_code)
        
        if not schema:
            return ValidationResult(
                is_valid=True,
                schema_found=False,
                violations=[]
            )
        
        violations: List[SchemaViolation] = []
        
        try:
            validator = Draft7Validator(schema, format_checker=FormatChecker())
            
            for error in validator.iter_errors(response_body):
                path = ".".join(str(p) for p in error.absolute_path) or "(root)"
                
                if "type" in error.schema:
                    if error.schema["nullable"] and error.instance is None:
                        continue
                    expected = f"type '{error.schema['type']}'"
                elif "enum" in error.schema:
                    expected = f"one of {error.schema['enum']}"
                elif "required" in str(error.message):
                    expected = "required field present"
                else:
                    expected = str(error.schema)[:50]
                
                if error.instance is None:
                    actual = "null"
                elif isinstance(error.instance, (dict, list)):
                    actual = f"type '{type(error.instance).__name__}'"
                else:
                    actual = f"'{error.instance}' (type: {type(error.instance).__name__})"
                
                violations.append(SchemaViolation(
                    path=path[2:],
                    message=error.message,
                    expected=expected,
                    actual=actual,
                    severity="error"
                ))
                
        except Exception as e:
            violations.append(SchemaViolation(
                path="",
                message=f"Validation error: {str(e)}",
                expected="valid schema",
                actual="validation failed",
                severity="error"
            ))
        
        return ValidationResult(
            is_valid=len(violations) == 0,
            schema_found=True,
            violations=violations
        )
    
    def validate_request(
        self,
        endpoint: str,
        method: str,
        request_body: Any
    ) -> ValidationResult:
        """
        Validate a request body against the OpenAPI schema.
        
        Args:
            endpoint: API endpoint being called
            method: HTTP method
            request_body: Request body to validate
            
        Returns:
            ValidationResult with is_valid flag and any violations
        """
        if not JSONSCHEMA_AVAILABLE:
            return ValidationResult(is_valid=True, schema_found=False)
        
        matched_path = self._match_path(endpoint)
        if not matched_path:
            return ValidationResult(is_valid=True, schema_found=False)
            
        path_item = self.paths.get(matched_path, {})
        operation = path_item.get(method.lower(), {})
        
        if not operation:
            return ValidationResult(is_valid=True, schema_found=False)
            
        request_body_def = operation.get("requestBody", {})
        content = request_body_def.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        
        if not schema:
            return ValidationResult(is_valid=True, schema_found=False)
            
        schema = self._expand_schema(schema)
        violations: List[SchemaViolation] = []
        
        try:
            validator = Draft7Validator(schema, format_checker=FormatChecker())
            
            for error in validator.iter_errors(request_body):
                path = ".".join(str(p) for p in error.absolute_path) or "(root)"
                
                violations.append(SchemaViolation(
                    path=path,
                    message=error.message,
                    expected=str(error.schema.get("type", "unknown")),
                    actual=str(type(error.instance).__name__),
                    severity="error"
                ))
                
        except Exception as e:
            violations.append(SchemaViolation(
                path="",
                message=f"Request validation error: {str(e)}",
                expected="valid request",
                actual="validation failed",
                severity="error"
            ))
        
        return ValidationResult(
            is_valid=len(violations) == 0,
            schema_found=True,
            violations=violations
        )


def format_violations_for_report(violations: List[SchemaViolation]) -> str:
    """
    Format schema violations as HTML for the test report.
    
    Args:
        violations: List of SchemaViolation objects
        
    Returns:
        HTML string showing violations
    """
    if not violations:
        return "<span style='color:green'>Schema Valid</span>"
    
    html_parts = [
        "<div class='schema-violations'>",
        f"<span style='color:red'>{len(violations)} Schema Violation(s)</span>",
        "<ul style='margin:5px 0; padding-left:20px; font-size:12px;'>"
    ]
    
    for v in violations[:5]:
        html_parts.append(
            f"<li><code>{v.path}</code>: {v.message}<br>"
            f"<small>Expected: {v.expected}, Got: {v.actual}</small></li>"
        )
    
    if len(violations) > 5:
        html_parts.append(f"<li><em>...and {len(violations) - 5} more</em></li>")
    
    html_parts.append("</ul></div>")
    
    return "".join(html_parts)
