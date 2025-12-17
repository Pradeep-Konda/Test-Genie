"""
Unit tests for SchemaValidator

Run with: python -m pytest test_schema_validator.py -v
"""

import pytest
from schema_validator import SchemaValidator, SchemaViolation, ValidationResult


# Sample OpenAPI spec for testing
SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/api/users": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "email": {"type": "string", "format": "email"}
                                        },
                                        "required": ["id", "name"]
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "responses": {
                    "201": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "name": {"type": "string"}
                                    },
                                    "required": ["id", "name"]
                                }
                            }
                        }
                    }
                }
            }
        },
        "/api/users/{id}": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "name": {"type": "string"}
                                    },
                                    "required": ["id", "name"]
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


class TestSchemaValidator:
    """Test suite for SchemaValidator"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.validator = SchemaValidator(SAMPLE_OPENAPI_SPEC)
    
    def test_valid_response(self):
        """Test validation passes for correct response"""
        response = [{"id": 1, "name": "John", "email": "john@example.com"}]
        
        result = self.validator.validate_response(
            endpoint="/api/users",
            method="GET",
            status_code=200,
            response_body=response
        )
        
        assert result.is_valid is True
        assert result.schema_found is True
        assert len(result.violations) == 0
    
    def test_invalid_type(self):
        """Test validation fails for wrong type"""
        response = [{"id": "not-an-integer", "name": "John"}]  # id should be integer
        
        result = self.validator.validate_response(
            endpoint="/api/users",
            method="GET",
            status_code=200,
            response_body=response
        )
        
        assert result.is_valid is False
        assert result.schema_found is True
        assert len(result.violations) > 0
        assert any("id" in v.path or "type" in v.message.lower() for v in result.violations)
    
    def test_missing_required_field(self):
        """Test validation fails for missing required field"""
        response = {"id": 1}  # missing 'name' which is required
        
        result = self.validator.validate_response(
            endpoint="/api/users",
            method="POST",
            status_code=201,
            response_body=response
        )
        
        assert result.is_valid is False
        assert any("name" in v.message for v in result.violations)
    
    def test_path_parameter_matching(self):
        """Test that /api/users/123 matches /api/users/{id}"""
        response = {"id": 123, "name": "John"}
        
        result = self.validator.validate_response(
            endpoint="/api/users/123",
            method="GET",
            status_code=200,
            response_body=response
        )
        
        assert result.schema_found is True
        assert result.is_valid is True
    
    def test_no_schema_found(self):
        """Test behavior when endpoint has no schema defined"""
        result = self.validator.validate_response(
            endpoint="/api/unknown",
            method="GET",
            status_code=200,
            response_body={"foo": "bar"}
        )
        
        assert result.schema_found is False
        assert result.is_valid is True  # No schema = can't fail validation
    
    def test_query_params_stripped(self):
        """Test that query params are stripped from path"""
        response = [{"id": 1, "name": "John"}]
        
        result = self.validator.validate_response(
            endpoint="/api/users?page=1&limit=10",
            method="GET",
            status_code=200,
            response_body=response
        )
        
        assert result.schema_found is True


class TestSchemaViolation:
    """Test SchemaViolation dataclass"""
    
    def test_to_dict(self):
        """Test serialization to dict"""
        violation = SchemaViolation(
            path="user.id",
            message="Expected integer",
            expected="type 'integer'",
            actual="'abc' (type: str)",
            severity="error"
        )
        
        d = violation.to_dict()
        
        assert d["path"] == "user.id"
        assert d["message"] == "Expected integer"
        assert d["expected"] == "type 'integer'"
        assert d["actual"] == "'abc' (type: str)"
        assert d["severity"] == "error"


class TestValidationResult:
    """Test ValidationResult dataclass"""
    
    def test_to_dict_empty(self):
        """Test serialization with no violations"""
        result = ValidationResult(is_valid=True, violations=[])
        
        d = result.to_dict()
        
        assert d["is_valid"] is True
        assert d["violation_count"] == 0
        assert d["violations"] == []
    
    def test_to_dict_with_violations(self):
        """Test serialization with violations"""
        violations = [
            SchemaViolation("path1", "msg1", "exp1", "act1"),
            SchemaViolation("path2", "msg2", "exp2", "act2"),
        ]
        result = ValidationResult(is_valid=False, violations=violations)
        
        d = result.to_dict()
        
        assert d["is_valid"] is False
        assert d["violation_count"] == 2
        assert len(d["violations"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
