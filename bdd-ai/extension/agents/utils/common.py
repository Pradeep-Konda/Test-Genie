from typing import List, Optional, Any, Dict
import re
import json


async def _calculate_openapi_coverage(feature_text: str, spec):
    """
    Computes OpenAPI test coverage based on the feature file content.
    Matches endpoints + methods defined in the spec.
    """
    try:
        defined, normalized_candidates = await path_matching(feature_text, spec)
        covered_set = set()

        for (method, openapi_path_only, pattern) in defined:
            # Check if HTTP method appears in feature text
            if method.lower() not in feature_text.lower():
                continue

            # Check if any URL in feature matches this OpenAPI path
            for cand in normalized_candidates:
                if pattern.match(cand):
                    covered_set.add((method, openapi_path_only))
                    break

        defined_set = {(m, p) for (m, p, _) in defined}

        # Compute coverage
        uncovered = sorted([f"{m} {p}" for (m, p) in (defined_set - covered_set)])
        total = len(defined_set)
        covered = len(covered_set)
        coverage = (covered / total * 100) if total else 0.0

        return coverage, uncovered

    except Exception as e:
        return 0.0, [f"Coverage calculation failed: {str(e)}"]


async def path_matching(feature_text: str, spec):
    try:
        defined = []

        for path, methods in spec.get("paths", {}).items():
            for method in methods.keys():
                method = method.upper()

                # PATH ONLY (NO SERVER HOST)
                openapi_path_only = path.rstrip("/")

                # Replace {param} -> regex for match
                regex_path = re.sub(r"\{[^/]+\}", r"[^/]+", openapi_path_only)

                # Exact match (allow trailing slash & ignore query params)
                pattern = re.compile(regex_path)

                defined.append((method, openapi_path_only, pattern))

        # Normalize feature file
        feature_lines = feature_text.splitlines()

        # Extract all potential URLs from feature file
        url_candidates = []
        for line in feature_lines:
            found = re.findall(r"/[^\s\"]+", line)
            url_candidates.extend(found)

        normalized_candidates = []
        for u in url_candidates:
            clean = u.split("?")[0].rstrip("/")
            normalized_candidates.append(clean)

        return defined, normalized_candidates

    except Exception:
        raise


async def _get_base_url_from_spec(spec: Dict[str, Any]) -> str:
    servers = spec.get("servers", [])
    if not servers:
        raise ValueError("No servers defined in OpenAPI spec")
    return servers[0]["url"].rstrip("/")


async def _get_content_from_spec(
    spec: Dict[str, Any],
    url: str,
    method: str,
    feature_text: str
):
    try:
        method = method.lower()
        defined, normalized_candidates = await path_matching(feature_text, spec)

        for (m, openapi_path_only, pattern) in defined:
            if m.lower() != method:
                continue

            for cand in normalized_candidates:
                if pattern.match(cand):
                    url = openapi_path_only
                    break

        method_obj = spec.get("paths").get(url).get(method)

        if method_obj and method_obj.get("requestBody"):
            return method_obj.get("requestBody").get("content")
        else:
            return None

    except Exception as e:
        raise RuntimeError("Unexpected error from _get_content_from_spec", e)


async def _extract_http_call(scenario_text: str):
    method = None
    url = None
    body = None

    lines = scenario_text.splitlines()

    for line in lines:
        line = line.strip()

        m_method = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\b", line, re.IGNORECASE)
        m_url = re.search(r"['\"]?(/[^\"'\s]+)['\"]?", line)

        if m_method:
            method = m_method.group(1).upper()

        if m_url:
            url = m_url.group(1)

    if not method or not url:
        raise ValueError(
            f"HTTP method or URL not found.\nScenario:\n{scenario_text}"
        )

    # Extra safety
    url = url.strip("'\"")

    body_match = re.search(r"\"\"\"(.*?)\"\"\"", scenario_text, re.DOTALL)
    if body_match:
        raw_body = body_match.group(1).strip()
        try:
            body = json.dumps(json.loads(raw_body))
        except Exception as e:
            print(f"Invalid JSON body:\n{raw_body}\nError:{e}")

    return method, url, body


async def _get_rule_from_search(l):
    try:
        m = re.search(r"status(?: code)? should be (\d+)", l)
        if m:
            return ("exact", int(m.group(1)))

        elif "should succeed" in l:
            return ("range", 200, 299)

        elif "should fail" in l:
            return ("range", 400, 599)

        return None
    except Exception:
        pass


async def _extract_expected_status(scenario_text: str):
    rules = []
    patterns = [
        r"status(?: code)? should be (\d+)",
        r"status code should be (\d+)"
    ]

    try:
        for line in scenario_text.splitlines():
            l = line.lower().strip()
            nums = list(map(int, re.findall(r"\d+", l)))
            m = next((re.search(p, l) for p in patterns), None)

            if "status code should be in range" in l and len(nums) >= 2:
                rules.append(("range", nums[0], nums[1]))

            elif "status code should be" in l and "or" in l and nums:
                rules.append(("or", nums))

            elif m:
                rules.append(("exact", int(m.group(1))))

            elif "should succeed" in l:
                rules.append(("range", 200, 299))

            elif "should fail" in l:
                rules.append(("range", 400, 599))

        return rules

    except Exception as e:
        raise TypeError("Error in extract expected status", e)


async def _validate_status(
    actual_status: int,
    expectations: list,
    is_negative: bool
) -> bool:
    status = True

    if expectations:
        for rule in expectations:
            if rule[0] in ["exact", "or"] and actual_status != rule[1]:
                status = False
            elif rule[0] == "range" and not (rule[1] <= actual_status <= rule[2]):
                status = False

        return status

    if is_negative:
        return 400 <= actual_status <= 599
    else:
        return 200 <= actual_status <= 299
