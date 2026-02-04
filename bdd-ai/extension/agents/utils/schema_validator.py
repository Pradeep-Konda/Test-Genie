import re
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse

try:
    from jsonschema import Draft7Validator, FormatChecker
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


# =========================
# Models
# =========================

@dataclass
class SchemaViolation:
    path: str
    message: str
    expected: str
    actual: str
    severity: str = "error"

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


# =========================
# Validator
# =========================

class SchemaValidator:
    """
    Validates API requests and responses against OpenAPI 3.0 schema definitions.
    """

    def __init__(self, openapi_spec: Dict[str, Any]):
        self.spec = openapi_spec
        self.paths = openapi_spec.get("paths", {})
        self.components = openapi_spec.get("components", {})
        self.schemas = self.components.get("schemas", {})

        self.server_url = ""
        servers = self.spec.get("servers", [])
        if servers:
            self.server_url = servers[0].get("url", "")
            try:
                parsed = urlparse(self.server_url)
                self.base_path = parsed.path.rstrip("/") or ""
            except Exception:
                self.base_path = ""
        else:
            self.base_path = ""


# =========================
# Helpers
# =========================

    async def _normalize_path(self, endpoint: str) -> str:
        parsed = urlparse(endpoint)
        path = parsed.path or endpoint

        if self.base_path and path.startswith(self.base_path):
            path = path[len(self.base_path):]

        if not path.startswith("/"):
            path = "/" + path

        return path.rstrip("/") or "/"

    async def _match_path(self, request_path: str) -> Optional[str]:
        request_path = await self._normalize_path(request_path)

        if request_path in self.paths:
            return request_path

        for openapi_path in self.paths.keys():
            pattern = re.sub(r"\{[^/]+\}", r"[^/]+", openapi_path)
            pattern = f"^{pattern}$"
            if re.match(pattern, request_path):
                return openapi_path

        return None

    async def _resolve_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        if not ref.startswith("#/"):
            return None

        parts = ref.lstrip("#/").split("/")
        current = self.spec

        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return None


# =========================
# Schema Expansion
# =========================

    async def _expanded_values(self, schema, _seen_refs):
        try:
            expanded = {}
            for key, value in schema.items():
                if key == "properties" and isinstance(value, dict):
                    expanded[key] = {
                        k: await self._expand_schema(v, _seen_refs.copy())
                        for k, v in value.items()
                    }
                elif key == "items" and isinstance(value, dict):
                    expanded[key] = await self._expand_schema(value, _seen_refs.copy())
                elif key in ("allOf", "oneOf", "anyOf") and isinstance(value, list):
                    expanded[key] = [
                        await self._expand_schema(v, _seen_refs.copy())
                        for v in value
                    ]
                else:
                    expanded[key] = value
            return expanded
        except Exception:
            pass

    async def _expand_schema(
        self,
        schema: Dict[str, Any],
        _seen_refs: Optional[set] = None
    ) -> Dict[str, Any]:

        if not isinstance(schema, dict):
            return schema

        _seen_refs = _seen_refs or set()
        ref = schema.get("$ref")

        if ref:
            if ref in _seen_refs:
                return schema
            _seen_refs.add(ref)
            resolved = await self._resolve_ref(ref)
            return await self._expand_schema(resolved, _seen_refs) if resolved else schema

        return await self._expanded_values(schema, _seen_refs)


# =========================
# Schema Navigation
# =========================

    async def _is_nullable(self, schema_node: Dict[str, Any]) -> bool:
        if not isinstance(schema_node, dict):
            return False

        if schema_node.get("nullable") is True:
            return True

        if "allOf" in schema_node:
            for sub in schema_node["allOf"]:
                if isinstance(sub, dict) and sub.get("nullable") is True:
                    return True

        return False

    async def _get_schema_for_path(
        self,
        root_schema: Dict[str, Any],
        path: List[Any]
    ) -> Optional[Dict[str, Any]]:

        current = root_schema
        try:
            for p in path:
                if "allOf" in current and isinstance(current["allOf"], list):
                    current = current["allOf"][0]

                if isinstance(p, int):
                    current = current.get("items")
                else:
                    current = current.get("properties", {}).get(p)

                if current is None:
                    return None

            return current
        except Exception:
            return None

    async def _get_error_schema(self):
        try:
            schema = self.components.get("schemas", {}).get("Error")
            return await self._expand_schema(schema) if schema else None
        except Exception:
            return None

    async def _extract_json_schema(self, content):
        try:
            json_content = content.get("application/json")
            if not json_content:
                for ct, val in content.items():
                    if "json" in ct.lower():
                        json_content = val
                        break
            return json_content.get("schema") if json_content else None
        except Exception:
            return None


# =========================
# Schema Fetchers
# =========================

    async def _get_response_schema(
        self,
        endpoint: str,
        method: str,
        status_code: int
    ) -> Optional[Dict[str, Any]]:

        matched_path = await self._match_path(endpoint)
        if not matched_path:
            return None

        path_item = self.paths.get(matched_path, {})
        operation = path_item.get(method.lower(), {})

        if not operation:
            return None

        responses = operation.get("responses", {})
        response_def = (
            responses.get(str(status_code)) or
            responses.get(f"{str(status_code)[0]}XX")
        )

        if not response_def:
            return await self._get_error_schema()

        content = response_def.get("content", {})
        if not content:
            if method.lower() == "delete" and status_code == 204:
                return None
            return await self._get_error_schema()

        schema = await self._extract_json_schema(content)
        if not schema:
            return None
        return await self._expand_schema(schema)

    async def _get_request_schema(
        self,
        endpoint: str,
        method: str
    ) -> Optional[Dict[str, Any]]:

        matched_path = await self._match_path(endpoint)
        if not matched_path:
            return None

        path_item = self.paths.get(matched_path, {})
        operation = path_item.get(method.lower(), {})
        request_body = operation.get("requestBody", {})

        content = request_body.get("content", {})
        json_content = content.get("application/json")

        if not json_content:
            for ct, val in content.items():
                if "json" in ct.lower():
                    json_content = val
                    break

        if not json_content:
            return None

        schema = json_content.get("schema")
        if not schema:
            return None

        return await self._expand_schema(schema)


# =========================
# Violation Builder
# =========================

    async def _get_violation(self, error, path, schema_node, instance):
        try:
            if error.validator == "required":
                return SchemaViolation(
                    path=path,
                    message=error.message,
                    expected="required field present",
                    actual="missing",
                    severity="error"
                )

            elif error.validator == "enum":
                return SchemaViolation(
                    path=path,
                    message=error.message,
                    expected=f"one of {schema_node.get('enum')}",
                    actual=str(instance),
                    severity="error"
                )

            elif error.validator == "type":
                return SchemaViolation(
                    path=path,
                    message=error.message,
                    expected=schema_node.get("type"),
                    actual=f"{instance} (type: {type(instance).__name__})",
                    severity="error"
                )

            elif error.validator == "format":
                return SchemaViolation(
                    path=path,
                    message=error.message,
                    expected=schema_node.get("format", "valid format"),
                    actual=str(instance),
                    severity="warning"
                )

            else:
                return SchemaViolation(
                    path=path,
                    message=error.message,
                    expected=str(schema_node)[:50],
                    actual=str(instance),
                    severity="error"
                )
        except Exception:
            pass


# =========================
# Core Validation Logic
# =========================

    async def _run_validation(
        self,
        schema: Dict[str, Any],
        payload: Any
    ) -> List[SchemaViolation]:

        violations: List[SchemaViolation] = []

        if not JSONSCHEMA_AVAILABLE:
            return violations

        validator = Draft7Validator(schema, format_checker=FormatChecker())

        for error in validator.iter_errors(payload):
            path = ".".join(str(p) for p in error.absolute_path) or "(root)"
            schema_node = (
                await self._get_schema_for_path(schema, list(error.absolute_path))
                or error.schema
            )
            instance = error.instance

            if instance is None and not (await self._is_nullable(schema_node)):
                violations.append(
                    SchemaViolation(
                        path=path,
                        message="Null value is not allowed",
                        expected=schema_node.get("type", "non-null"),
                        actual="null",
                        severity="error"
                    )
                )
                continue

            violation = await self._get_violation(error, path, schema_node, instance)
            if violation:
                violations.append(violation)

        return violations


# =========================
# Public APIs
# =========================

    async def validate_request(
        self,
        endpoint: str,
        method: str,
        request_body: Any
    ) -> ValidationResult:

        schema = await self._get_request_schema(endpoint, method)
        if not schema:
            return ValidationResult(is_valid=True, schema_found=False, violations=[])

        violations = await self._run_validation(schema, request_body)

        return ValidationResult(
            is_valid=len(violations) == 0,
            schema_found=True,
            violations=violations
        )

    async def validate_response(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_body: Any
    ) -> ValidationResult:

        schema = await self._get_response_schema(endpoint, method, status_code)
        if not schema:
            return ValidationResult(is_valid=True, schema_found=False, violations=[])

        violations = await self._run_validation(schema, response_body)

        return ValidationResult(
            is_valid=len(violations) == 0,
            schema_found=True,
            violations=violations
        )


# =========================
# Report Formatter
# =========================

async def format_violations_for_report(
    violations: List[SchemaViolation]
) -> str:

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
        html_parts.append(
            f"<li><em>...and {len(violations) - 5} more</em></li>"
        )

    html_parts.append("</ul></div>")
    return "".join(html_parts)
