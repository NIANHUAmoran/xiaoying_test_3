import hashlib
import json
from datetime import datetime, timezone

from .evidence import citation, respond, topic_passages
from .knowledge import KnowledgeBase
from .models import ModelServiceError


def validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("输入必须为 JSON 对象")
    question = request.get("question")
    if question is None or question == "":
        return False
    if not isinstance(question, str):
        raise ValueError("question 必须为字符串")
    history = request.get("history", [])
    if not isinstance(history, list):
        raise ValueError("history 必须为数组")
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"} or not isinstance(item.get("content"), str):
            raise ValueError("history 只接受含 role=user/assistant 和 content 字符串的对象")
    return bool(question.strip())


def validate_decision(decision):
    if not isinstance(decision, dict) or set(decision) != {"action", "arguments", "basis"}:
        raise ValueError("invalid_decision_fields")
    schemas = {"search_documents": {"query"}, "read_document": {"doc_id"}, "respond": {"kind", "evidence"}}
    action = decision["action"]
    if action not in schemas or not isinstance(decision["arguments"], dict) or set(decision["arguments"]) != schemas[action]:
        raise ValueError("invalid_tool_or_arguments")
    args = decision["arguments"]
    if not isinstance(decision["basis"], str) or not 1 <= len(decision["basis"]) <= 500:
        raise ValueError("invalid_basis")
    if action in {"search_documents", "read_document"}:
        value = args["query" if action == "search_documents" else "doc_id"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_string_argument")
    elif args["kind"] not in {"answer", "clarify", "not_found", "tool_failure", "stop"} or not isinstance(args["evidence"], list):
        raise ValueError("invalid_response_arguments")


def run(request, world, model, max_steps=16):
    valid = validate_request(request)
    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise ValueError("max_steps 必须为 1..100 的整数")
    identity = request.get("request_id") or "qa-" + hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    if not valid:
        return {"request_id": identity, "question": request.get("question"), "status": "needs_information",
                "answer": "请提供需要查询的问题。", "citations": [], "conflicts": [], "gaps": ["缺少问题"],
                "clarification_question": "请提供具体问题。", "mode": "validation", "model": None, "model_calls": 0,
                "termination": "input_incomplete", "trace": [{"step": 1, "actor": "runtime", "action": "validate_input",
                "arguments": {}, "basis": "问题为空", "observation": {"missing": ["question"]}, "next_action": None}],
                "generated_at": datetime.now(timezone.utc).isoformat()}
    kb = KnowledgeBase(world)
    intent = kb.resolve(request["question"], request.get("history", []))
    state = {"searches": [], "documents": {}, "errors": [], "attempts": {}, "last_observation": None}
    trace = []
    terminal = None
    termination = "step_limit"
    for step in range(1, max_steps + 1):
        context = {"question": request["question"], "history": request.get("history", []), "intent": intent,
                   "state": state, "remaining_steps": max_steps - step + 1}
        decision = None
        try:
            # Protect observation snapshots from in-process test doubles as well as model mutation.
            decision = model.decide(json.loads(json.dumps(context, ensure_ascii=False)))
            validate_decision(decision)
        except Exception as exc:
            error = {"step": step, "actor": "model", "error": "model_error", "detail": type(exc).__name__}
            if isinstance(exc, ModelServiceError):
                error["service_error"] = str(exc)
            if isinstance(decision, dict):
                error["response_fields"] = list(decision)
                error["returned_action"] = str(decision.get("action", ""))[:64]
            trace.append(error)
            termination = "model_error"
            break
        action, args = decision["action"], decision["arguments"]
        entry = {"step": step, "actor": "model", **decision}
        if action == "respond":
            result = respond(args, state, kb, intent)
        else:
            key = action + ":" + args.get("doc_id", "*")
            count = state["attempts"].get(key, 0)
            state["attempts"][key] = count + 1
            failure = next((rule for rule in world.get("failures", []) if rule["tool"] == action and
                            (not rule.get("doc_id") or rule["doc_id"] == args.get("doc_id"))), None)
            if failure and (failure["mode"] == "always" or count == 0):
                result = {"ok": False, "error": "injected_tool_failure", "retryable": failure["mode"] == "once"}
            elif action == "search_documents":
                result = kb.search(args["query"])
            else:
                retrieved_ids = {match["doc_id"] for search in state["searches"] for match in search.get("matches", [])}
                result = kb.read(args["doc_id"]) if args["doc_id"] in retrieved_ids else {"ok": False, "error": "document_not_retrieved", "retryable": False}
            if action == "search_documents":
                state["searches"].append({"query": args["query"], **result})
            elif result.get("ok"):
                state["documents"][args["doc_id"]] = result
            if result.get("ok"):
                for error in state["errors"]:
                    if error["action"] == action and error["arguments"] == args:
                        error["resolved"] = True
            if not result.get("ok"):
                state["errors"].append({"action": action, "arguments": args, **result})
        entry["observation"] = result
        trace.append(entry)
        state["last_observation"] = {"action": action, "arguments": args, **result}
        if action == "respond" and result["ok"]:
            terminal = {key: value for key, value in result.items() if key != "ok"}
            termination = "responded"
            break
    for index, entry in enumerate(trace):
        entry["next_action"] = trace[index + 1].get("action", "model_error") if index + 1 < len(trace) else None
    if terminal is None:
        partial = [citation(doc_id, document, passage) for doc_id, document, passage in topic_passages(state, intent["topic"])]
        terminal = {"status": "incomplete", "answer": "查证尚未完成，暂时不能给出可靠答案。", "citations": partial,
                    "conflicts": [], "gaps": ["模型调用失败" if termination == "model_error" else "达到执行步数上限"],
                    "clarification_question": None}
    return {"request_id": identity, "question": request["question"], "resolved_topic": intent["topic"],
            "mode": model.mode, "model": model.name, "generated_at": datetime.now(timezone.utc).isoformat(),
            "max_steps": max_steps, "model_calls": len(trace), "termination": termination,
            "read_document_ids": sorted(state["documents"]), "tool_errors": state["errors"], **terminal, "trace": trace}
