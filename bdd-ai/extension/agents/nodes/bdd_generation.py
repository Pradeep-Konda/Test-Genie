import os
import sys
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.messages import SystemMessage, HumanMessage



class BDDGenerationNode:
    """
    Robust BDD generator and feature splitter.

    Responsibilities
    ----------------
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

    def __init__(self, output_dir: str = "bdd_tests/features"):
        load_dotenv()
        self.output_dir = output_dir

        try:
            self.llm = ChatOpenAI(model="gpt-4.1", temperature=0) if ChatOpenAI else None
            self.tools = []

            # Optional tool – currently we mostly call the LLM directly
            self.system_prompt = (
                        "You are a Senior QA Engineer specializing in Behavior-Driven Development (BDD) "
                        "and AI-assisted API testing. Your job is to convert the given OpenAPI 3.0 YAML "
                        "into comprehensive Gherkin test scenarios.\n\n"
                        "Follow these rules strictly:\n"
                        "1 Output must be in **pure Gherkin syntax** — no markdown, no explanations.\n"
                        "2 Each `Feature:` corresponds to an API resource or module.\n"
                        "3 Each endpoint must include:\n"
                        "   - **Happy Path**: Valid request and successful response.\n"
                        "   - **Edge Cases**: Boundary values, nulls, optional params, etc.\n"
                        "   - **Negative/Error**: Invalid input, missing fields, auth failure, etc.\n"
                        "   - **Security**: OWASP API Security Top 10 vulnerabilities (e.g., Injection, Broken Auth).\n"
                        "   - **Performance**: Assertions on latency or response time.\n"
                        "4 Tag scenarios using @security, @performance, @smoke, @edge, @negative where appropriate. "
                        "5 Generate schema-compliant **mock data** for each request body.\n"
                        "6 Use clear, readable step wording: Given / When / Then.\n"
                        "7 Do not omit any endpoint.\n"
                        "8 Start the response directly with `Feature:` — no text before that."
                    )
        #  self.system_prompt = (
        #         "Convert the given OpenAPI spec into pure Gherkin features. "
                
        #         "Return ONLY valid Gherkin text without explanations."
        #     )

            try:
                self.agent = (
                        create_agent(
                            model=self.llm,
                            tools=self.tools,
                            system_prompt=self.system_prompt,
                        )
                        if create_agent and self.llm
                        else None
                        )
            except Exception as e:
                       
                        self.agent = None
        except Exception as e:
        
            self.llm = None
            self.agent = None

    # ------------------------------------------------------------------
    # Fallback mock generator (used when LLM / OpenAPI is not available)
    # ------------------------------------------------------------------
    def _mock_bdd_generator(self, openapi_spec: str) -> str:
        return """Feature: Default API Endpoint

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
            safe_file = re.sub(r"\s+", "_", feat_title.lower()) + ".feature"
            # print(f"[DEBUG] Processing Feature: {feat_title}", file=sys.stderr)

            # We want human-readable headers:
            #   Feature: XYZ
            #     # Functional scenarios
            #   or
            #     # Non-functional scenarios
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
                path = os.path.join(func_dir, safe_file)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(func_buffer).rstrip() + "\n")
                written.append(path)
                print(f"[DEBUG]     SAVED functional/{safe_file}", file=sys.stderr)

            if has_nonf:
                path = os.path.join(nonf_dir, safe_file)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(nonf_buffer).rstrip() + "\n")
                written.append(path)
                print(f"[DEBUG]     SAVED non_functional/{safe_file}", file=sys.stderr)

        print(f"[DEBUG] Total files written: {len(written)}", file=sys.stderr)
        return written

    # ------------------------------------------------------------------
    # Main entrypoint used by the graph (main.py)
    # ------------------------------------------------------------------
    def __call__(self, state):
        """
        state.analysis   = OpenAPI YAML (string)   ← from CodeAnalysisNode
        state.feature_text = combined Gherkin text ← we set here
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
            feature_text = self._mock_bdd_generator("")
            state.feature_text = feature_text
            self._write_tagged_features(state.project_path, feature_text)
            return state

        feature_text = None

        # ------------------ Call LLM agent ------------------
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=f"Generate advanced BDD test cases (in Gherkin) for this OpenAPI 3.0 spec:\n\n{openapi_spec}"
                )
            ]
 
            result = self.agent.invoke({"messages": messages})
 
            # 🧠 Normalize outputs like CodeAnalysisNode
            if isinstance(result, dict) and "messages" in result:
                ai_messages = [
                    msg for msg in result["messages"]
                    if getattr(msg, "type", None) == "ai" or msg.__class__.__name__ == "AIMessage"
                ]
                feature_text = ai_messages[-1].content.strip() if ai_messages else ""
            elif hasattr(result, "content"):
                feature_text = result.content.strip()
            elif isinstance(result, str):
                feature_text = result.strip()
            else:
                feature_text = str(result or "").strip()
 
        except Exception as e:
            print(f"⚠️ LLM Error in BDDGenerationNode: {e}")
            feature_text = self._mock_bdd_generator(openapi_spec)


        # Save on state and write categorized .feature files
        state.feature_text = feature_text
        self._write_tagged_features(state.project_path, feature_text)
        return state
