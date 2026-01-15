"""
BDD Evaluator - LLM-as-Judge for BDD Test Scenario Quality

This module implements an LLM-based evaluation system that scores generated
Gherkin scenarios against quality criteria and provides targeted feedback
for iterative refinement.

Features:
- Evaluates completeness, structure, data quality, coverage depth, and security
- Provides detailed feedback with specific issues and suggestions
- Generates targeted refinement prompts for improvement iterations
"""

import os
import re
import sys
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


@dataclass
class EvaluationResult:
    """
    Structured result from the BDD quality evaluation.
    
    Attributes:
        overall_score: Weighted average score (0.0-1.0)
        criteria_scores: Individual scores per evaluation criterion
        issues: List of identified issues with suggestions
        passed: Whether the evaluation meets the quality threshold
        iteration: Which iteration this evaluation was performed on
        summary: Brief text summary of the evaluation
    """
    overall_score: float
    criteria_scores: Dict[str, float]
    issues: List[Dict[str, Any]]
    passed: bool
    iteration: int = 0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResult":
        """Create EvaluationResult from dictionary."""
        return cls(
            overall_score=data.get("overall_score", 0.0),
            criteria_scores=data.get("criteria_scores", {}),
            issues=data.get("issues", []),
            passed=data.get("passed", False),
            iteration=data.get("iteration", 0),
            summary=data.get("summary", "")
        )
    
    @classmethod
    def default_failed(cls, iteration: int = 0, error: str = "") -> "EvaluationResult":
        """Create a default failed evaluation result."""
        return cls(
            overall_score=0.0,
            criteria_scores={
                "completeness": 0.0,
                "structure": 0.0,
                "data_quality": 0.0,
                "coverage_depth": 0.0,
                "security": 0.0
            },
            issues=[{"type": "evaluation_error", "message": error}] if error else [],
            passed=False,
            iteration=iteration,
            summary=f"Evaluation failed: {error}" if error else "Evaluation failed"
        )


class RefinementPromptBuilder:
    """
    Builds targeted refinement prompts based on evaluation feedback.
    
    Takes the original Gherkin scenarios and evaluation issues to generate
    a focused prompt that guides the LLM to fix specific problems.
    """
    
    # Issue type to refinement instruction mapping
    ISSUE_INSTRUCTIONS = {
        "missing_endpoint": "Add test scenarios for the missing endpoint: {endpoint} {method}",
        "weak_coverage": "Improve coverage for scenario: {scenario}. Suggestion: {suggestion}",
        "missing_edge_case": "Add edge case scenarios for: {context}",
        "missing_negative_case": "Add negative/error handling scenarios for: {context}",
        "missing_security": "Add security test scenarios covering: {vulnerability}",
        "poor_structure": "Fix Gherkin structure issues: {details}",
        "invalid_data": "Improve test data quality: {details}",
        "incomplete_scenario": "Complete the scenario: {scenario}",
        "missing_assertions": "Add proper Then assertions for: {scenario}",
    }
    
    def build_refinement_prompt(
        self, 
        openapi_spec: str,
        original_gherkin: str, 
        feedback: EvaluationResult
    ) -> str:
        """
        Build a targeted refinement prompt based on evaluation feedback.
        
        Args:
            openapi_spec: The OpenAPI specification (for context)
            original_gherkin: The original generated Gherkin scenarios
            feedback: The evaluation result with identified issues
            
        Returns:
            A prompt string for the refinement LLM call
        """
        # Build issue-specific instructions
        issue_instructions = []
        for issue in feedback.issues:
            issue_type = issue.get("type", "unknown")
            template = self.ISSUE_INSTRUCTIONS.get(issue_type, "Fix: {type} - {details}")
            
            try:
                instruction = template.format(**issue, type=issue_type, details=str(issue))
            except KeyError:
                instruction = f"Fix issue: {issue_type} - {json.dumps(issue)}"
            
            issue_instructions.append(f"  - {instruction}")
        
        issues_text = "\n".join(issue_instructions) if issue_instructions else "  - General quality improvements needed"
        
        # Build criteria feedback
        criteria_feedback = []
        for criterion, score in feedback.criteria_scores.items():
            if score < 0.7:
                criteria_feedback.append(f"  - {criterion}: {score:.0%} (needs improvement)")
        criteria_text = "\n".join(criteria_feedback) if criteria_feedback else "  - All criteria acceptable"
        
        return f"""You are a Senior QA Engineer improving BDD test scenarios.

EVALUATION FEEDBACK (Score: {feedback.overall_score:.0%})
=========================================================

ISSUES TO FIX:
{issues_text}

CRITERIA SCORES:
{criteria_text}

OPENAPI SPECIFICATION:
{openapi_spec}

ORIGINAL SCENARIOS TO IMPROVE:
{original_gherkin}

INSTRUCTIONS:
1. Address ALL issues listed above
2. Maintain proper Gherkin syntax (Feature/Scenario/Given/When/Then)
3. Keep existing good scenarios, only improve or add where needed
4. Use realistic, schema-compliant test data
5. Include @tags for categorization (@smoke, @security, @edge, @negative)

OUTPUT:
Generate the COMPLETE improved Gherkin scenarios.
Start directly with "Feature:" - no explanations or markdown.
"""


class BDDEvaluator:
    """
    LLM-as-Judge for evaluating BDD test scenario quality.
    
    Evaluates generated Gherkin scenarios against multiple criteria:
    - Completeness (25%): All OpenAPI endpoints have corresponding scenarios
    - Structure (25%): Proper Given/When/Then format, clear steps
    - Data Quality (20%): Realistic, schema-compliant test data
    - Coverage Depth (20%): Happy path + edge cases + negative scenarios
    - Security (10%): OWASP-aligned security scenarios present
    """
    
    # Criteria weights for overall score calculation
    CRITERIA_WEIGHTS = {
        "completeness": 0.25,
        "structure": 0.25,
        "data_quality": 0.20,
        "coverage_depth": 0.20,
        "security": 0.10
    }
    
    EVALUATOR_PROMPT = """You are a Senior QA Engineer and BDD expert evaluating API test scenarios.

Your task is to evaluate the quality of Gherkin test scenarios generated from an OpenAPI specification.

EVALUATION CRITERIA (score each 0.0 to 1.0):

1. **Completeness** (25% weight):
   - Are ALL endpoints from the OpenAPI spec covered?
   - Does each endpoint have at least one scenario?
   - Check: paths, methods (GET, POST, PUT, DELETE, PATCH)

2. **Structure** (25% weight):
   - Proper Gherkin syntax (Feature, Scenario, Given, When, Then)
   - Clear, readable step definitions
   - Appropriate use of Background, Scenario Outline where applicable
   - Proper indentation and formatting

3. **Data Quality** (20% weight):
   - Realistic test data values
   - Schema-compliant data (correct types, formats)
   - Meaningful example values (not just "test" or "123")
   - Proper handling of required vs optional fields

4. **Coverage Depth** (20% weight):
   - Happy path scenarios (valid requests → success responses)
   - Edge cases (boundary values, empty strings, nulls)
   - Negative scenarios (invalid data → error responses)
   - Error handling (4xx, 5xx responses)

5. **Security** (10% weight):
   - Authentication/authorization test scenarios
   - Input validation (SQL injection, XSS attempts)
   - OWASP API Security Top 10 coverage
   - Proper @security tags on security scenarios

RESPONSE FORMAT (strict JSON only):
{
  "overall_score": <float 0.0-1.0>,
  "criteria_scores": {
    "completeness": <float 0.0-1.0>,
    "structure": <float 0.0-1.0>,
    "data_quality": <float 0.0-1.0>,
    "coverage_depth": <float 0.0-1.0>,
    "security": <float 0.0-1.0>
  },
  "issues": [
    {
      "type": "<issue_type>",
      "endpoint": "<affected endpoint if applicable>",
      "method": "<HTTP method if applicable>",
      "scenario": "<scenario name if applicable>",
      "context": "<additional context>",
      "suggestion": "<specific improvement suggestion>"
    }
  ],
  "passed": <boolean>,
  "summary": "<brief 1-2 sentence summary>"
}

ISSUE TYPES to use:
- "missing_endpoint": An OpenAPI endpoint has no test scenarios
- "weak_coverage": Endpoint exists but lacks edge/negative cases
- "missing_edge_case": No boundary value or edge case testing
- "missing_negative_case": No error/invalid input scenarios
- "missing_security": No security-focused test scenarios
- "poor_structure": Gherkin syntax or format issues
- "invalid_data": Test data doesn't match schema or is unrealistic
- "incomplete_scenario": Scenario missing steps or assertions
- "missing_assertions": No proper Then steps to verify outcomes

IMPORTANT:
- Be thorough but fair in scoring
- Always provide actionable suggestions in issues
- Set passed=true only if overall_score >= 0.8
- Output ONLY valid JSON, no markdown or explanations
"""

    def __init__(self):
        """Initialize the BDD Evaluator with LLM."""
        load_dotenv()
        model = os.getenv("MODEL", "gpt-4.1")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=0  # Deterministic evaluation
        )
        
        self.refinement_builder = RefinementPromptBuilder()
    
    def _extract_endpoints_from_openapi(self, openapi_spec: str) -> List[Dict[str, str]]:
        """
        Extract endpoint information from OpenAPI spec for coverage checking.
        
        Args:
            openapi_spec: OpenAPI specification as string (YAML or JSON)
            
        Returns:
            List of endpoint dicts with path and methods
        """
        endpoints = []
        try:
            import yaml
            spec = yaml.safe_load(openapi_spec) if "openapi:" in openapi_spec else json.loads(openapi_spec)
            
            paths = spec.get("paths", {})
            for path, methods in paths.items():
                for method in methods.keys():
                    if method.lower() in ["get", "post", "put", "delete", "patch", "head", "options"]:
                        endpoints.append({
                            "path": path,
                            "method": method.upper()
                        })
        except Exception as e:
            print(f"[EVALUATOR] Warning: Could not parse OpenAPI spec: {e}", file=sys.stderr)
        
        return endpoints
    
    def _calculate_weighted_score(self, criteria_scores: Dict[str, float]) -> float:
        """
        Calculate the weighted overall score from criteria scores.
        
        Args:
            criteria_scores: Dictionary of criterion -> score
            
        Returns:
            Weighted average score
        """
        total = 0.0
        weight_sum = 0.0
        
        for criterion, weight in self.CRITERIA_WEIGHTS.items():
            score = criteria_scores.get(criterion, 0.0)
            total += score * weight
            weight_sum += weight
        
        return total / weight_sum if weight_sum > 0 else 0.0
    
    def evaluate(
        self, 
        openapi_spec: str, 
        gherkin_text: str,
        quality_threshold: float = 0.8,
        iteration: int = 1
    ) -> EvaluationResult:
        """
        Evaluate the quality of generated Gherkin scenarios.
        
        Args:
            openapi_spec: The OpenAPI specification used for generation
            gherkin_text: The generated Gherkin scenarios to evaluate
            quality_threshold: Score threshold for passing (default 0.8)
            iteration: Current iteration number for tracking
            
        Returns:
            EvaluationResult with scores, issues, and pass/fail status
        """
        # Quick sanity checks
        if not gherkin_text or not gherkin_text.strip():
            return EvaluationResult.default_failed(iteration, "Empty Gherkin text")
        
        if "Feature:" not in gherkin_text and "Scenario:" not in gherkin_text:
            return EvaluationResult.default_failed(iteration, "No valid Gherkin structure found")
        
        try:
            # Build evaluation prompt with both inputs
            messages = [
                SystemMessage(content=self.EVALUATOR_PROMPT),
                HumanMessage(content=f"""Evaluate the following BDD scenarios:

=== OPENAPI SPECIFICATION ===
{openapi_spec}

=== GENERATED GHERKIN SCENARIOS ===
{gherkin_text}

Respond with JSON only.""")
            ]
            
            # Call LLM for evaluation
            print(f"[JUDGE] Evaluating scenarios (iteration {iteration})...", file=sys.stderr)
            result = self.llm.invoke(messages)
            
            # Parse the response
            content = result.content.strip()
            
            # Try to extract JSON from response (handle potential markdown wrapping)
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group(0)
            
            parsed = json.loads(content)
            
            # Extract and validate fields
            criteria_scores = parsed.get("criteria_scores", {})
            
            # Ensure all criteria are present
            for criterion in self.CRITERIA_WEIGHTS.keys():
                if criterion not in criteria_scores:
                    criteria_scores[criterion] = 0.5  # Default middle score
            
            # Calculate overall score (use LLM's if provided, otherwise calculate)
            overall_score = parsed.get("overall_score")
            if overall_score is None:
                overall_score = self._calculate_weighted_score(criteria_scores)
            
            # Determine pass/fail
            passed = overall_score >= quality_threshold
            
            evaluation = EvaluationResult(
                overall_score=overall_score,
                criteria_scores=criteria_scores,
                issues=parsed.get("issues", []),
                passed=passed,
                iteration=iteration,
                summary=parsed.get("summary", f"Score: {overall_score:.0%}")
            )
            
            print(f"[JUDGE] Evaluation complete: {overall_score:.0%} ({'PASSED' if passed else 'NEEDS REFINEMENT'})", 
                  file=sys.stderr)
            
            return evaluation
            
        except json.JSONDecodeError as e:
            print(f"[JUDGE] Failed to parse evaluation response: {e}", file=sys.stderr)
            return EvaluationResult.default_failed(iteration, f"Invalid JSON response: {e}")
        except Exception as e:
            print(f"[JUDGE] Evaluation error: {e}", file=sys.stderr)
            return EvaluationResult.default_failed(iteration, str(e))
    
    def build_refinement_prompt(
        self,
        openapi_spec: str,
        original_gherkin: str,
        feedback: EvaluationResult
    ) -> str:
        """
        Build a refinement prompt based on evaluation feedback.
        
        Delegates to RefinementPromptBuilder.
        
        Args:
            openapi_spec: The OpenAPI specification
            original_gherkin: The original Gherkin scenarios
            feedback: The evaluation result with issues
            
        Returns:
            Refinement prompt string
        """
        return self.refinement_builder.build_refinement_prompt(
            openapi_spec, original_gherkin, feedback
        )
    
    def get_improvement_summary(self, evaluations: List[EvaluationResult]) -> Dict[str, Any]:
        """
        Generate a summary of improvement across iterations.
        
        Args:
            evaluations: List of evaluation results from each iteration
            
        Returns:
            Summary dict with improvement metrics
        """
        if not evaluations:
            return {"error": "No evaluations provided"}
        
        first = evaluations[0]
        last = evaluations[-1]
        
        improvement = last.overall_score - first.overall_score
        
        criteria_improvements = {}
        for criterion in self.CRITERIA_WEIGHTS.keys():
            first_score = first.criteria_scores.get(criterion, 0)
            last_score = last.criteria_scores.get(criterion, 0)
            criteria_improvements[criterion] = {
                "initial": first_score,
                "final": last_score,
                "improvement": last_score - first_score
            }
        
        return {
            "iterations": len(evaluations),
            "initial_score": first.overall_score,
            "final_score": last.overall_score,
            "overall_improvement": improvement,
            "improvement_percentage": (improvement / first.overall_score * 100) if first.overall_score > 0 else 0,
            "criteria_improvements": criteria_improvements,
            "final_passed": last.passed,
            "issues_resolved": len(first.issues) - len(last.issues)
        }
