import os
import sys
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from prompts.prompt_loader_bdd import PromptLoader
import traceback
import json
from langchain_openai import ChatOpenAI


class BDDGenerationNode:
    """
    Robust BDD generator and feature splitter.

    Responsibilities
    -----------------
    1) Take OpenAPI (from state.analysis)
    2) Ask LLM to convert it into Gherkin features
    3) Classify scenarios into:
    - functional
    - non_functional (@performance / @security)
    4) Write .feature files into:
    bdd_tests/functional/
    bdd_tests/non_functional/
    5) Store the whole combined Gherkin in state.feature_text
    """
    # Map labels like "(Security)" in scenario titles to tags
    LABEL_TO_TAG = {
        "happy path": "@smoke",
        "happy": "@smoke",
        "smoke": "@smoke",
        "edge": "@edge",
        "negative": "@negative",
        "error": "@negative",
        "security": "@security",
        "performance": "@performance",
        "perf": "@performance",
    }

    # Tags that we treat as NON-functional
    NON_FUNCTIONAL_TAGS = {"@security", "@performance"}
    
    
    MAX_REFINEMENT_ROUNDS = 1

    def __init__(self, output_dir: str = "bdd_tests/features"):
        load_dotenv()
        self.output_dir = output_dir
        model = os.getenv("MODEL", "gpt-4.1")
        
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.judge_llm = ChatOpenAI(model=model, temperature=0)

    # ---------------------------------------------------------------------
    # Fallback mock generator (used when LLM / OpenAPI is not available)
    # ---------------------------------------------------------------------
    async def _mock_bdd_generator(self) -> str:
        return """[PLACE HOLDER]
Feature: Default API Endpoint

@smoke
Scenario: Happy Path
    Given an API endpoint "/example"
    When I send a valid POST request
    Then I should receive a 200 OK response

@performance
Scenario: Response time baseline
    Given an API endpoint "/example"
    When I measure a valid POST request
    Then response time should be under 500 milliseconds

@security
Scenario: SQL Injection attempt
    Given an API endpoint "/example"
    When I send a malicious payload "' OR 1=1 --"
    Then the API should respond with a 4xx or sanitized response
"""

    # ------------------------------------------------------------------
    # Normalize a single Scenario block, and collect tags
    # ------------------------------------------------------------------
    def _normalize_scenario(self, sc_text: str):
        """
        Input:
            sc_text = full text of one scenario including its @tags + steps

        Output:
            normalized_text (string)
            detected_tags (set of '@tag')
        """
        detected = set()

        # 1) Collect explicit @tags already present
        found = re.findall(r'@([a-zA-Z_]+)', sc_text)
        for t in found:
            detected.add("@" + t.lower())

        lines = sc_text.splitlines()
        if not lines:
            return sc_text, detected

        # 2) Look for labels in parentheses in the Scenario title
        #    Example: "Scenario: Login (Security)" → "@security"
        first_idx = 0
        while first_idx < len(lines) and not lines[first_idx].strip():
            first_idx += 1
        if first_idx >= len(lines):
            return sc_text, detected

        first_line = lines[first_idx]
        m = re.search(r'\(([^)]+)\)\s*$', first_line)
        if m:
            label = m.group(1).strip().lower()
            tag = self.LABEL_TO_TAG.get(label)
            if tag:
                detected.add(tag)
                # remove "(Security)" etc from the title
                lines[first_idx] = re.sub(r'\s*\([^)]+\)\s*$', '', first_line)

        normalized = "\n".join(lines)
        return normalized, detected

    # ------------------------------------------------------------------
    # Split Gherkin by Feature and write into functional / non_functional
    # ------------------------------------------------------------------
    def _write_tagged_features(self, project_path: str, gherkin_text: str) -> list:
        """
        - Creates:
            <project>/bdd_tests/functional/
            <project>/bdd_tests/non_functional/

        - For each Feature:
            * identifies scenarios + tags
            * writes:
                - functional/<feature>.feature
                - non_functional/<feature>.feature
              with only the relevant scenarios.

        Also prints debug lines like:
          [DEBUG] Processing Feature: User management
          [DEBUG]     → functional (tags={'@smoke'}) :   @smoke
        """
        base = os.path.join(project_path, "bdd_tests")
        func_dir = os.path.join(base, "functional")
        nonf_dir = os.path.join(base, "non_functional")
        os.makedirs(func_dir, exist_ok=True)
        os.makedirs(nonf_dir, exist_ok=True)

        # Clear old feature files so we always have a fresh snapshot
        for folder in (func_dir, nonf_dir):
            try:
                for f in os.listdir(folder):
                    if f.endswith(".feature"):
                        os.remove(os.path.join(folder, f))
            except FileNotFoundError:
                pass

        # Split on "Feature:" boundaries
        feature_blocks = re.split(r"(?=Feature:)", gherkin_text)
        written = []
        usedFuncFilenames = set()
        usedNonFuncFilenames = set()

        for block in feature_blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.splitlines()
            if not lines:
                continue

            # ------------------ Feature header ------------------
            name_line = lines[0]
            feat_title = name_line.replace("Feature:", "").strip()
            # safe_file = re.sub(r"\s+", "_", feat_title.lower()) + ".feature"
            base_name = re.sub(r'[^a-z0-9]+', '_', feat_title.lower())
            if len(base_name) > 50:
                base_name = base_name[:50]
            
            func_buffer = [
                f"Feature: {feat_title}",
                "",
                "  # Functional scenarios",
            ]
            nonf_buffer = [
                f"Feature: {feat_title}",
                "",
                "  # Non-functional scenarios",
            ]

            has_func = False
            has_nonf = False

            # ---- Improved grouping loop with lookahead for @tag lines ----
            scenarios = []
            cur_lines = []
            prev_nonempty = []

            total_lines = len(lines)
            i = 1  # start after Feature line
            while i < total_lines:
                raw_ln = lines[i]
                ln = raw_ln.rstrip("\n")

                if not ln.strip():
                    # blank line: keep inside current scenario if building one
                    if cur_lines:
                        cur_lines.append(ln)
                    i += 1
                    continue

                stripped = ln.lstrip()

                # If this line is an @tag line, decide whether it belongs to the next Scenario
                if stripped.startswith("@"):
                    # look ahead for the next non-empty line
                    j = i + 1
                    next_nonempty = None
                    while j < total_lines:
                        candidate = lines[j].strip()
                        if candidate:
                            next_nonempty = candidate
                            break
                        j += 1

                    if next_nonempty and next_nonempty.startswith("Scenario:"):
                        # this @tag should be attached to the next scenario -> store in prev_nonempty
                        prev_nonempty.append(ln)
                        i += 1
                        continue
                    else:
                        # no upcoming Scenario: treat as part of current scenario if that exists,
                        # otherwise keep it for the next scenario
                        if cur_lines:
                            cur_lines.append(ln)
                        else:
                            prev_nonempty.append(ln)
                        i += 1
                        continue

                # If this is a Scenario line
                if stripped.startswith("Scenario:"):
                    # flush previous scenario if exists
                    if cur_lines:
                        scenarios.append("\n".join(cur_lines).rstrip())
                        cur_lines = []

                    # attach any immediately preceding @ lines stored in prev_nonempty
                    tags_to_attach = []
                    for prev in reversed(prev_nonempty):
                        if prev.strip().startswith("@"):
                            tags_to_attach.insert(0, prev)
                        else:
                            break
                    prev_nonempty = []

                    for t in tags_to_attach:
                        cur_lines.append(t)
                    cur_lines.append(stripped)
                    i += 1
                    continue

                # otherwise it's a step or something else
                if cur_lines:
                    cur_lines.append(ln)
                else:
                    # no active scenario: hold this line for potential attachment
                    prev_nonempty.append(ln)
                i += 1

            # flush last scenario
            if cur_lines:
                scenarios.append("\n".join(cur_lines).rstrip())

            # ------------------ Classify scenarios ------------------
            for sc in scenarios:
                normalized, tags = self._normalize_scenario(sc)
                sc_to_write = normalized

                if any(t in tags for t in self.NON_FUNCTIONAL_TAGS):
                    has_nonf = True
                    nonf_buffer.append("")
                    nonf_buffer.append(sc_to_write)
                    print(
                        f"[DEBUG]     → non_functional (tags={tags}) : {sc_to_write.splitlines()[0]}",
                        file=sys.stderr,
                    )
                else:
                    has_func = True
                    func_buffer.append("")
                    func_buffer.append(sc_to_write)
                    print(
                        f"[DEBUG]     → functional (tags={tags}) : {sc_to_write.splitlines()[0]}",
                        file=sys.stderr,
                    )

            # ------------------ Write files per category ------------------
            if has_func:
                safe_file = f"{base_name}.feature"
                counter = 1
                while safe_file in usedFuncFilenames:
                    safe_file = f"{base_name}_{counter}.feature"
                    counter += 1
 
                usedFuncFilenames.add(safe_file)
                path = os.path.join(func_dir, safe_file)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(func_buffer).rstrip() + "\n")
                written.append(path)
                print(f"[DEBUG]     SAVED functional/{safe_file}", file=sys.stderr)

            if has_nonf:
                safe_file = f"{base_name}.feature"
                counter = 1
                while safe_file in usedNonFuncFilenames:
                    safe_file = f"{base_name}_{counter}.feature"
                    counter += 1
 
                usedNonFuncFilenames.add(safe_file)
                path = os.path.join(nonf_dir, safe_file)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(nonf_buffer).rstrip() + "\n")
                written.append(path)
                print(f"[DEBUG]     SAVED non_functional/{safe_file}", file=sys.stderr)

        print(f"[DEBUG] Total files written: {len(written)}", file=sys.stderr)
        return written
    
    
    # ---------------------------------------------------------------------
    # Main entrypoint used by the graph (main.py)
    # ---------------------------------------------------------------------
    async def __call__(self, state):
        """
        state.analysis = OpenAPI YAML (string)  <- from CodeAnalysisNode
        state.feature_text = combined Gherkin text <- we set here
        """

        openapi_spec = getattr(state, "analysis", None)

        # sanity: if not OpenAPI-like, fallback to mock
        if isinstance(openapi_spec, str):
            looks_like_openapi = bool(
                re.search(r"openapi\s*:\s*3", openapi_spec, re.I)
            ) or ("paths:" in openapi_spec)
        else:
            looks_like_openapi = False

        if not looks_like_openapi:
            feature_text = await self._mock_bdd_generator()
            state.feature_text = feature_text
            self._write_tagged_features(state.project_path, feature_text)
            return state

        try:
            feature_text = await self._generate_with_feedback_loop(openapi_spec)
        except Exception as e:
            print(
                f"LLM Error in BDDGenerationNode: {e}",
                file=sys.stderr,
                flush=True,
            )
            feature_text = self._mock_bdd_generator()

        state.feature_text = feature_text
        self._write_tagged_features(state.project_path, feature_text)
        return state

    # ---------------------------------------------------------------------
    # ORIGINAL GENERATION
    # ---------------------------------------------------------------------
    async def _generate_initial_bdd(self, openapi_spec: str) -> str:
        rendered_prompt = PromptLoader().prompt_loader(
            "bdd/bdd_generation.jinja"
        )

        if not isinstance(rendered_prompt, str):
            raise ValueError("bdd_generation.jinja returned invalid jinja")

        messages = [
            SystemMessage(content=rendered_prompt),
            HumanMessage(
                content=f"Your job is to convert the given OpenAPI 3.0 specification into comprehensive BDD Gherkin test scenarios.\n\n{openapi_spec}"
            ),
        ]

        result = await self.llm.ainvoke(messages)
        return result.content.replace("```gherkin", "").replace("```", "").strip()

    # ---------------------------------------------------------------------
    # NEW: FEEDBACK LOOP CONTROLLER
    # ---------------------------------------------------------------------
    async def _generate_with_feedback_loop(self, openapi_spec: str) -> str:
        feature_text = await self._generate_initial_bdd(openapi_spec)

        for _ in range(self.MAX_REFINEMENT_ROUNDS):
            judge_result = await self._judge_bdd(openapi_spec, feature_text)

            missing_endpoints = judge_result.get("missing_endpoints", [])

            if judge_result.get("verdict") == "PASS" and not missing_endpoints:
                return feature_text

            for endpoint in missing_endpoints:
                refinement_prompt = PromptLoader().prompt_loader(
                    "bdd/bdd_refinement_prompt.jinja",
                    context={
                        "openapi_spec": openapi_spec,
                        "missing_endpoint": endpoint.get("path"),
                        "missing_method": endpoint.get("method"),
                        "instructions": judge_result.get("refinement_instructions", ""),
                    },
                )

                if not isinstance(refinement_prompt, str):
                    raise ValueError("bdd_refinement.jinja returned invalid prompt")

                messages = [
                    HumanMessage(content=refinement_prompt)
                ]

                response = await self.llm.ainvoke(messages)
                feature_text = (
                    feature_text.rstrip()
                    + "\n\n"
                    + response.content.replace("```gherkin", "").replace("```", "").strip()
                )

        return feature_text

    # ---------------------------------------------------------------------
    # NEW: JUDGE LOGIC
    # ---------------------------------------------------------------------
    async def _judge_bdd(self, openapi_spec: str, feature_text: str) -> dict:
        judge_prompt = PromptLoader().prompt_loader(
            "bdd/bdd_judge.jinja",
            context={
                "openapi_spec": openapi_spec,
                "feature_text": feature_text,
            },
        )

        if not isinstance(judge_prompt, str):
            raise ValueError("judge_prompt.jinja returned invalid prompt")

        messages = [
            SystemMessage(content=judge_prompt),
            HumanMessage(content=feature_text),
        ]

        result = await self.judge_llm.ainvoke(messages)

        try:
            response = result.content
            start = response.find("{")
            end = response.rfind("}")
            if start == -1 or end == -1 or start > end:
                raise ValueError("No json found in response")
            return json.loads(response[start: end + 1])
        except json.JSONDecodeError as e:
            raise ValueError("no valid json has been passed", e)
