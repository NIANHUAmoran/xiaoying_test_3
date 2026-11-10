"""Check submission structure, paired records and source-grounded citations.

This script reads local artifacts only. It does not call any model or tool service.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = {"README.md", "requirements.txt", ".env.example", ".gitignore", "src", "tests", "examples", "data", "docs"}
DOCS = {"01-requirements.md", "02-solution.md", "03-evaluation.md", "04-ai-usage.md", "05-retrospective.md"}
LOCAL_ONLY = {".env", ".runtime", ".git", ".venv", "__pycache__"}
CASE_DATA = {
    "normal": "world.json",
    "conflict": "conflict.world.json",
    "outside": "world.json",
    "paraphrase": "world.json",
    "context": "world.json",
    "tool-failure": "tool-failure.world.json",
    "partial-failure": "partial-failure.world.json",
    "transient-failure": "transient-failure.world.json",
    "changed-document": "changed-document.world.json",
    "resolved-conflict": "resolved-conflict.world.json",
    "ambiguous": "world.json",
    "missing-question": "world.json",
    "unsupported-product": "world.json",
    "multi-topic": "world.json",
    "step-limit": "world.json",
    "live-normal": "world.json",
    "live-conflict": "conflict.world.json",
    "live-paraphrase": "world.json",
}
EXPECTED_STATUS = {
    "normal": "answered", "conflict": "needs_clarification", "outside": "out_of_scope",
    "paraphrase": "answered", "context": "answered", "tool-failure": "tool_failure",
    "partial-failure": "tool_failure", "transient-failure": "answered", "changed-document": "answered",
    "resolved-conflict": "answered", "ambiguous": "needs_clarification", "missing-question": "needs_information",
    "unsupported-product": "out_of_scope", "multi-topic": "needs_clarification", "step-limit": "incomplete",
    "live-normal": "answered", "live-conflict": "needs_clarification", "live-paraphrase": "answered",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalize(value):
    return re.sub(r"\s+", "", value).casefold()


def successful_reads(trace):
    observed = {}
    for step in trace:
        result = step.get("observation", {})
        if step.get("action") == "read_document" and result.get("ok"):
            doc_id = result["document"]["doc_id"]
            require(step["arguments"]["doc_id"] == doc_id, "Read result does not match the requested document")
            observed.setdefault(doc_id, []).append(result)
    return observed


def check_citation(citation, sources, observed, case):
    require(isinstance(citation, dict), f"{case}: citation must be an object")
    require(all(isinstance(citation.get(key), str) and citation[key] for key in ["doc_id", "passage_id", "version_date", "quote"]),
            f"{case}: citation fields are missing or invalid")
    doc_id = citation["doc_id"]
    require(doc_id in sources and doc_id in observed, f"{case}: citation was not successfully read")
    source = sources[doc_id]
    passage = next((p for p in source["passages"] if p["id"] == citation["passage_id"]), None)
    require(passage is not None, f"{case}: cited passage does not exist")
    require(citation["quote"] == passage["text"], f"{case}: quote differs from source text")
    require(citation["version_date"] == source["version_date"], f"{case}: incorrect citation version")
    if "scope" in citation:
        require(citation["scope"] == source.get("scope"), f"{case}: incorrect citation scope")
    if "value" in citation:
        require(citation["value"] == passage["value"], f"{case}: conflict value differs from source")
    matches_read = any(result["document"]["version_date"] == citation["version_date"] and
                       any(p["id"] == citation["passage_id"] and p["text"] == citation["quote"] for p in result["passages"])
                       for result in observed[doc_id])
    require(matches_read, f"{case}: citation does not match an actual successful read result")
    return passage


def main():
    root_entries = {p.name for p in ROOT.iterdir()} - LOCAL_ONLY
    require(root_entries == ENTRIES, "Unexpected or missing submission root entries")
    require({p.name for p in (ROOT / "docs").iterdir()} == DOCS, "The five specified documents must be present")
    require((ROOT / "src/__main__.py").is_file(), "Executable CLI entry is missing")
    require(bool(list((ROOT / "tests").glob("test_*.py"))), "Executable tests are missing")
    require(not list((ROOT / "examples").glob("*.py")), "Verification scripts belong in tests")
    outputs = {}
    citation_count = 0
    for case, data_name in CASE_DATA.items():
        request, output, extracted = [read(ROOT / f"examples/{case}.{kind}.json") for kind in ["input", "output", "trace"]]
        require(request["request_id"] == output["request_id"] == extracted["request_id"], f"{case}: inconsistent request IDs")
        require(request["question"] == output["question"] == extracted["question"], f"{case}: inconsistent questions")
        require(extracted["source_output"] == case + ".output.json", f"{case}: incorrect trace source")
        require(extracted["trace"] == output["trace"], f"{case}: extracted Trace differs from actual output")
        require(output["status"] == EXPECTED_STATUS[case], f"{case}: unexpected actual status")
        expected_mode = "validation" if case == "missing-question" else "live" if case.startswith("live-") else "mock"
        require(output["mode"] == expected_mode == extracted["mode"], f"{case}: incorrect real model/Mock provenance")
        world = read(ROOT / "data" / data_name)
        sources = {document["id"]: document for document in world["documents"]}
        observed = successful_reads(output["trace"])
        citation_passages = []
        for reference in output["citations"]:
            citation_passages.append(check_citation(reference, sources, observed, case))
            citation_count += 1
        for reference in output["conflicts"]:
            check_citation(reference, sources, observed, case)
            citation_count += 1
        if output["status"] == "answered":
            require(bool(output["citations"]) and not output["conflicts"], f"{case}: unsupported or conflicting answer")
            topic = output.get("resolved_topic")
            require(bool(topic) and all(p["topic"] == topic for p in citation_passages), f"{case}: irrelevant citation")
            relevant = {doc_id for doc_id, document in sources.items() if any(p["topic"] == topic for p in document["passages"])}
            require(relevant.issubset(observed), f"{case}: not all related documents were read")
            values = {normalize(p["value"]) for doc_id in relevant for p in sources[doc_id]["passages"] if p["topic"] == topic}
            require(len(values) == 1, f"{case}: conflicting corpus values cannot yield a definite answer")
            require(any(c["quote"] in output["answer"] for c in output["citations"]), f"{case}: answer omits cited source content")
        outputs[case] = output
    for case in ["conflict", "live-conflict"]:
        output = outputs[case]
        require(len(output["conflicts"]) >= 2 and output["gaps"] and output["clarification_question"], f"{case}: conflict must be explained and clarified")
        require({c["doc_id"] for c in output["conflicts"]}.issubset({c["doc_id"] for c in output["citations"]}), f"{case}: missing conflict citation")
    require(outputs["outside"]["gaps"] and not outputs["outside"]["citations"], "Out-of-scope case needs an explicit source gap")
    require(outputs["tool-failure"]["tool_errors"] and outputs["tool-failure"]["gaps"], "Tool failure evidence is missing")
    require(outputs["partial-failure"]["citations"] and outputs["partial-failure"]["gaps"], "Partial failure must preserve read evidence and explain the gap")
    require(outputs["changed-document"]["answer"] != outputs["normal"]["answer"], "Changing the document did not change the answer")
    require(outputs["resolved-conflict"]["status"] == "answered", "Resolved conflicting values must permit a supported answer")
    queries = [step for step in outputs["paraphrase"]["trace"] if step.get("action") == "search_documents"]
    require(len({step["arguments"]["query"] for step in queries}) >= 2 and not queries[0]["observation"].get("matches"),
            "Paraphrase evidence must demonstrate query improvement after an empty result")
    require(outputs["context"]["resolved_topic"] == "expense_platform", "Context follow-up did not change to the requested attribute")
    offline = read(ROOT / "examples/offline-validation.json")
    require(offline["all_passed"] and offline["tests_run"] == 35 and offline["scenarios"] == 15, "Expected offline verification is incomplete")
    test_report = (ROOT / "examples/test-results.txt").read_text(encoding="utf-8")
    require(bool(re.search(r"Ran 35 tests", test_report)) and test_report.rstrip().endswith("OK"), "Actual passing test report is missing")
    live = read(ROOT / "examples/live-validation-summary.json")
    require(live["all_passed"] and len(live["checks"]) == 3, "Expected real model verification is incomplete")
    pending_report = (ROOT / "examples/submission-check.json").resolve()
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")), ROOT / "examples/README.md"]:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if target.startswith(("http:", "https:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            require(resolved.is_relative_to(ROOT), f"Document link depends on an external workspace file: {path.name}")
            require(resolved.exists() or resolved == pending_report, f"Broken document link: {path.name} -> {target}")
    result = {"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "all_passed": True,
              "root_entries": sorted(root_entries), "documents": sorted(DOCS), "evidence_groups": len(CASE_DATA),
              "offline_runs": 15, "live_paths": 3, "unit_tests": 35, "trace_matches_actual_output": True,
              "source_citation_records_checked": citation_count, "citation_text_and_versions_valid": True,
              "citations_observed_in_successful_reads": True, "answered_cases_have_full_topic_coverage": True,
              "six_required_scenarios_covered": True, "document_replacement_changes_answer": True,
              "query_rewrite_observed": True, "context_followup_resolved": True, "document_links_valid": True}
    pending_report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"submission": "passed", "evidence_groups": len(CASE_DATA), "tests": 35, "source_citations_checked": citation_count}))


if __name__ == "__main__":
    main()
