"""Run recorded offline scenarios through the actual CLI, then test the implementation."""
import copy
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def write(relative, value):
    (ROOT / relative).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_traces():
    for path in sorted((ROOT / "examples").glob("*.output.json")):
        output = json.loads(path.read_text(encoding="utf-8"))
        write("examples/" + path.name.replace(".output.json", ".trace.json"), {"source_output": path.name,
              **{key: output.get(key) for key in ["request_id", "question", "mode", "model", "generated_at", "trace"]}})


def main():
    started = time.monotonic()
    world = json.loads((ROOT / "data/world.json").read_text(encoding="utf-8"))
    conflict = json.loads((ROOT / "data/conflict.world.json").read_text(encoding="utf-8"))
    partial = copy.deepcopy(conflict)
    partial["failures"] = [{"tool": "read_document", "doc_id": "D02", "mode": "always"}]
    write("data/partial-failure.world.json", partial)
    cases = [
        ("normal", "报销期限多久？", [], "world", "answered", 16),
        ("conflict", "报销期限多久？", [], "conflict.world", "needs_clarification", 16),
        ("outside", "公司今年股价是多少？", [], "world", "out_of_scope", 16),
        ("paraphrase", "费用单据最晚什么时候交", [], "world", "answered", 16),
        ("context", "那在哪个平台提交？", [{"role": "user", "content": "报销期限多久？"},
                 {"role": "assistant", "content": "请以制度原文为准。"}], "world", "answered", 16),
        ("tool-failure", "报销期限多久？", [], "tool-failure.world", "tool_failure", 16),
        ("partial-failure", "报销期限多久？", [], "partial-failure.world", "tool_failure", 16),
        ("transient-failure", "报销期限多久？", [], "transient-failure.world", "answered", 16),
        ("changed-document", "报销期限多久？", [], "changed-document.world", "answered", 16),
        ("resolved-conflict", "报销期限多久？", [], "resolved-conflict.world", "answered", 16),
        ("ambiguous", "那这个呢", [], "world", "needs_clarification", 16),
        ("missing-question", "", [], "world", "needs_information", 16),
        ("unsupported-product", "这个产品支持哪些支付方式？", [], "world", "out_of_scope", 16),
        ("multi-topic", "报销期限多久、在哪个平台提交？", [], "world", "needs_clarification", 16),
        ("step-limit", "报销期限多久？", [], "world", "incomplete", 2),
    ]
    rows = []
    for name, question, history, data, expected, limit in cases:
        request = {"request_id": "test3-" + name, "question": question, "history": history}
        write(f"examples/{name}.input.json", request)
        process = subprocess.run([sys.executable, "-B", "-m", "src", "--mock", "--input", f"examples/{name}.input.json",
                                  "--data", f"data/{data}.json", "--output", f"examples/{name}.output.json",
                                  "--max-steps", str(limit)], cwd=ROOT, capture_output=True)
        expected_code = 1 if expected in {"tool_failure", "incomplete"} else 0
        if process.returncode != expected_code:
            raise RuntimeError(f"{name}: unexpected exit {process.returncode}")
        result = json.loads((ROOT / f"examples/{name}.output.json").read_text(encoding="utf-8"))
        assert result["status"] == expected, (name, result["status"])
        rows.append({"scenario": name, "status": result["status"], "mode": result["mode"], "exit_code": process.returncode,
                     "citations": len(result["citations"]), "steps": len(result["trace"]), "data": f"data/{data}.json"})
    for name in ["normal", "conflict", "paraphrase"]:
        request = json.loads((ROOT / f"examples/{name}.input.json").read_text(encoding="utf-8"))
        request["request_id"] = "test3-live-" + name
        write(f"examples/live-{name}.input.json", request)
    extract_traces()
    write("examples/run-summary.json", rows)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (ROOT / "examples/test-results.txt").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    write("examples/offline-validation.json", {"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
          "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "scenarios": len(rows),
          "elapsed_seconds": round(time.monotonic() - started, 2), "live_calls_performed": False, "all_passed": result.wasSuccessful()})
    print(json.dumps({"offline_scenarios": len(rows), "tests": result.testsRun, "passed": result.wasSuccessful()}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
