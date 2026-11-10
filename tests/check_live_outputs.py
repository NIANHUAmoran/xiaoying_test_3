"""Audit recorded real-model paths and their citations against read results and source data."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    rows = []
    for case, expected in [("normal", "answered"), ("conflict", "needs_clarification"), ("paraphrase", "answered")]:
        output = read(ROOT / f"examples/live-{case}.output.json")
        source = read(ROOT / ("data/conflict.world.json" if case == "conflict" else "data/world.json"))
        documents = {doc["id"]: doc for doc in source["documents"]}
        assert output["mode"] == "live" and output["status"] == expected
        readings = {step["arguments"]["doc_id"]: step["observation"] for step in output["trace"]
                    if step.get("action") == "read_document" and step["observation"].get("ok")}
        for cite in output["citations"]:
            original = documents[cite["doc_id"]]
            passage = next(p for p in original["passages"] if p["id"] == cite["passage_id"])
            assert cite["quote"] == passage["text"] and cite["version_date"] == original["version_date"]
            assert cite["doc_id"] in readings
            assert any(p["id"] == cite["passage_id"] and p["text"] == cite["quote"] for p in readings[cite["doc_id"]]["passages"])
        searches = [step for step in output["trace"] if step.get("action") == "search_documents"]
        queries = [step["arguments"]["query"] for step in searches]
        first_empty = bool(searches and not searches[0]["observation"].get("matches"))
        if case == "conflict":
            assert {"D01", "D02"}.issubset(readings)
            assert {x["value"] for x in output["conflicts"]} == {"30 天", "15 天"}
            assert len(searches) >= 2 and output["clarification_question"] and output["gaps"]
        else:
            assert output["citations"] and output["citations"][0]["quote"] in output["answer"]
        if case == "paraphrase":
            assert first_empty and len(set(queries)) >= 2
        rows.append({"scenario": case, "model": output["model"], "status": output["status"],
                     "steps": len(output["trace"]), "read_document_ids": sorted(readings),
                     "citations": len(output["citations"]), "all_citations_exact": True,
                     "queries": queries, "first_search_empty": first_empty, "query_rewritten": len(set(queries)) >= 2,
                     "conflict_values": sorted({x["value"] for x in output["conflicts"]})})
    report = {"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "all_passed": True,
              "checks": rows, "scope": "Three actual model runs; not a statistical reliability or open-domain entailment claim."}
    (ROOT / "examples/live-validation-summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"live_paths": len(rows), "citations_checked": "passed"}))


if __name__ == "__main__":
    main()
