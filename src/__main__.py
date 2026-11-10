import argparse
import json
import sys
from pathlib import Path

from .agent import run, validate_request
from .config import DEFAULT_ENV, load_env
from .models import HTTPModel, MockModel


def main():
    parser = argparse.ArgumentParser(description="企业知识问答 Agent：文档检索、原文引用、冲突查证")
    parser.add_argument("--input", required=True)
    parser.add_argument("--data", default="data/world.json")
    parser.add_argument("--output")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--max-steps", type=int, default=16)
    args = parser.parse_args()
    try:
        request = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        world = json.loads(Path(args.data).read_text(encoding="utf-8-sig"))
        valid = validate_request(request)
        if valid and not args.mock:
            load_env(args.env_file)
        model = MockModel() if args.mock or not valid else HTTPModel()
        result = run(request, world, model, args.max_steps)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 1 if result["status"] in {"tool_failure", "incomplete"} else 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
