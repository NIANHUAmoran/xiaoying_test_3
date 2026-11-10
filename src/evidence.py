import re


def canonical(value):
    return re.sub(r"\s+", "", value).casefold()


def topic_passages(state, topic):
    return [(doc_id, document, passage) for doc_id, document in state["documents"].items()
            for passage in document["passages"] if passage["topic"] == topic]


def citation(doc_id, document, passage):
    return {"doc_id": doc_id, "passage_id": passage["id"],
            "version_date": document["document"]["version_date"], "quote": passage["text"],
            "scope": document["document"].get("scope")}


def respond(arguments, state, kb, intent):
    kind, supplied = arguments["kind"], arguments["evidence"]
    topic = intent["topic"]
    validated = []
    seen = set()
    for item in supplied:
        if not isinstance(item, dict) or set(item) != {"doc_id", "passage_id", "quote"}:
            return {"ok": False, "error": "invalid_citation_fields"}
        if any(not isinstance(item[key], str) or not item[key].strip() for key in ["doc_id", "passage_id", "quote"]):
            return {"ok": False, "error": "invalid_citation_fields"}
        doc = state["documents"].get(item["doc_id"])
        if not doc:
            return {"ok": False, "error": "citation_not_read"}
        passage = next((p for p in doc["passages"] if p["id"] == item["passage_id"]), None)
        if not passage or passage["text"] != item["quote"]:
            return {"ok": False, "error": "citation_quote_mismatch"}
        if passage["topic"] != topic:
            return {"ok": False, "error": "citation_topic_mismatch"}
        pair = (item["doc_id"], item["passage_id"])
        if pair not in seen:
            validated.append(citation(item["doc_id"], doc, passage))
            seen.add(pair)
    related = set(kb.related_ids(topic)) if topic else set()
    missing = sorted(related - set(state["documents"]))
    passages = topic_passages(state, topic)
    values = {canonical(passage["value"]) for _, _, passage in passages}
    conflicts = [{**citation(doc_id, doc, passage), "value": passage["value"]} for doc_id, doc, passage in passages] if len(values) > 1 else []
    if kind in {"answer", "clarify"} and topic and missing:
        return {"ok": False, "error": "unread_related_documents", "missing_documents": missing}
    base = {"ok": True, "answer": "", "citations": validated, "conflicts": [], "gaps": [], "clarification_question": None}
    if kind == "answer":
        if not topic or not related or not passages or not validated:
            return {"ok": False, "error": "insufficient_evidence"}
        if conflicts:
            return {"ok": False, "error": "unresolved_conflict", "conflicting_documents": sorted({c["doc_id"] for c in conflicts})}
        source = validated[0]
        return {**base, "status": "answered",
                "answer": f"文档 {source['doc_id']}（版本 {source['version_date']}）原文：{source['quote']}"}
    if kind == "clarify":
        if intent["needs_clarification"] and not topic:
            return {**base, "status": "needs_clarification", "answer": "问题指向不明确，暂时无法可靠作答。",
                    "gaps": ["缺少明确制度、产品或问题主题"], "clarification_question": "请补充制度或产品名称，以及想了解的具体问题。"}
        if not conflicts:
            return {"ok": False, "error": "clarification_not_supported"}
        expected_pairs = {(c["doc_id"], c["passage_id"]) for c in conflicts}
        if not expected_pairs.issubset(seen):
            return {"ok": False, "error": "conflict_citations_incomplete"}
        description = "；".join(f"{c['doc_id']}（版本 {c['version_date']}）原文：{c['quote']}" for c in conflicts)
        return {**base, "status": "needs_clarification", "conflicts": conflicts,
                "answer": "资料存在差异，尚不能确定适用结论：" + description + "。版本日期不能单独决定优先级。",
                "gaps": ["适用范围或制度优先级尚未明确"], "clarification_question": "请确认适用的制度、部门或规则优先级。"}
    if kind == "not_found":
        if not state["searches"] or not any(search["ok"] for search in state["searches"]):
            return {"ok": False, "error": "successful_search_required"}
        if related:
            return {"ok": False, "error": "relevant_documents_exist", "required_query": intent.get("canonical_query")}
        if any(not error.get("resolved", False) for error in state["errors"]):
            return {"ok": False, "error": "search_or_read_failed_not_absent"}
        return {**base, "status": "out_of_scope", "answer": "当前资料库未找到支持该问题的可靠资料，无法给出确定答案。",
                "gaps": ["资料库缺少相关主题或问题所需信息"]}
    if kind == "tool_failure":
        if not any(not error.get("resolved", False) for error in state["errors"]):
            return {"ok": False, "error": "no_tool_failure_observed"}
        # Include already read relevant passages as partial evidence, without a definitive answer.
        partial = [citation(doc_id, doc, passage) for doc_id, doc, passage in passages]
        return {**base, "status": "tool_failure", "answer": "文档检索或片段读取未成功完成，暂时无法可靠作答。",
                "citations": partial, "conflicts": conflicts,
                "gaps": ["工具失败，资料查证未完成"] + ["未读取文档：" + doc_id for doc_id in missing]}
    if kind == "stop":
        return {**base, "status": "incomplete", "answer": "任务已停止，尚未形成可核查的答案。", "gaps": ["模型主动停止且未完成证据核对"]}
    return {"ok": False, "error": "unknown_response_kind"}
