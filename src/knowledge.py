"""Small, inspectable keyword retrieval over an explicitly annotated synthetic corpus.

Version dates are metadata, never document precedence. Facts are only exposed by
read(); each annotated value must occur verbatim in its supporting passage.
"""
import copy
import re
from datetime import date


CANONICAL = {
    "expense_deadline": "报销期限",
    "expense_platform": "报销提交平台",
    "product_offline": "产品离线使用",
}


def _normalize(value):
    return re.sub(r"\s+", "", value.casefold())


def _domain(text):
    if "产品" in text:
        return "product"
    if any(word in text for word in ["报销", "报账", "差旅", "单据", "费用", "发票"]):
        return "expense"
    if any(word in text for word in ["离线", "断网", "没网", "没有网络"]):
        return "product"
    return None


class KnowledgeBase:
    def __init__(self, world):
        if not isinstance(world, dict) or not isinstance(world.get("documents"), list):
            raise ValueError("documents 必须为文档数组")
        documents = copy.deepcopy(world["documents"])
        self._documents = {}
        topic_labels = {}
        for document in documents:
            if not isinstance(document, dict):
                raise ValueError("文档必须是对象")
            doc_id = document.get("id")
            if not isinstance(doc_id, str) or not doc_id.strip() or doc_id in self._documents:
                raise ValueError("文档 ID 必须非空且唯一")
            if not isinstance(document.get("title"), str) or not document["title"].strip():
                raise ValueError("文档标题不能为空")
            version = document.get("version_date")
            if not isinstance(version, str) or len(version) != 10:
                raise ValueError("文档版本必须是 YYYY-MM-DD 日期")
            try:
                date.fromisoformat(version)
            except ValueError:
                raise ValueError("文档版本必须是合法日期") from None
            if document.get("scope") is not None and (not isinstance(document["scope"], str) or not document["scope"].strip()):
                raise ValueError("scope 必须为空或非空字符串")
            if document.get("priority") is not None and type(document["priority"]) is not int:
                raise ValueError("priority 必须为空或整数；日期不会自动赋予优先级")
            keywords = document.get("keywords")
            if not isinstance(keywords, list) or not keywords or any(not isinstance(k, str) or not k.strip() for k in keywords):
                raise ValueError("检索关键词必须为非空字符串数组")
            passages = document.get("passages")
            if not isinstance(passages, list) or not passages:
                raise ValueError("文档至少需要一个原文片段")
            passage_ids = set()
            for passage in passages:
                if not isinstance(passage, dict):
                    raise ValueError("原文片段必须是对象")
                for field in ["id", "topic", "label", "value", "text"]:
                    if not isinstance(passage.get(field), str) or not passage[field].strip():
                        raise ValueError("片段字段必须为非空字符串")
                if passage["id"] in passage_ids:
                    raise ValueError("同一文档中的片段 ID 必须唯一")
                passage_ids.add(passage["id"])
                if passage["value"] not in passage["text"]:
                    raise ValueError("标注值必须是支撑原文的精确子串，不能仅修改隐藏答案")
                if passage["topic"] not in CANONICAL:
                    raise ValueError("本合成知识库仅支持明确列出的问答主题")
                known_label = topic_labels.setdefault(passage["topic"], passage["label"])
                if known_label != passage["label"]:
                    raise ValueError("相同主题应使用一致的答案标签")
            self._documents[doc_id] = document

    def resolve(self, question, history=None):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 必须为非空字符串")
        if history is None:
            history = []
        if not isinstance(history, list):
            raise ValueError("history 必须为对话数组")
        for item in history:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"} or not isinstance(item.get("content"), str):
                raise ValueError("history 需要 user/assistant 角色与字符串 content")
        question = question.strip()
        normalized = _normalize(question)
        explicit_domain = _domain(normalized)
        domain = explicit_domain
        if domain is None:
            for message in reversed(history):
                if message["role"] == "user":
                    domain = _domain(_normalize(message["content"]))
                    if domain:
                        break
        platform = any(term in normalized for term in ["平台", "渠道", "哪里", "哪儿", "系统", "在哪", "提交到"])
        deadline = any(term in normalized for term in ["期限", "多久", "几天", "多少天", "最晚", "什么时候", "何时", "时限", "时效"])
        offline = any(term in normalized for term in ["离线", "断网", "没网", "没有网络"])
        unsupported_attribute = any(term in normalized for term in [
            "价格", "定价", "支付", "付款", "收费", "多少钱", "费用多少", "股价", "市值", "限额", "额度", "上限",
            "比例", "税率", "到账", "审批", "审核", "工资", "薪资", "薪酬", "收益", "退款", "折扣", "优惠券",
            "发票抬头", "联系人", "电话", "视频格式", "文件格式",
        ]) or (domain == "expense" and offline)
        # A single-topic extractive answer must not silently omit another requested attribute.
        multiple_topics = (domain == "expense" and platform and deadline) or (
            offline and "产品" in normalized and any(term in normalized for term in ["报销", "报账", "差旅"]) and (deadline or platform))
        topic = None
        if not unsupported_attribute and not multiple_topics and domain == "expense":
            topic = "expense_platform" if platform else "expense_deadline" if deadline else None
        elif not unsupported_attribute and not multiple_topics and domain == "product" and offline:
            topic = "product_offline"
        vague = normalized.rstrip("？?。.!！") in {"那这个呢", "那它呢", "那呢", "这个呢", "那怎么说", "那具体呢", "它呢", "这个", "那这个", "那它", "这个可以吗", "那怎么办"}
        needs_clarification = topic is None and not unsupported_attribute and (vague or multiple_topics or explicit_domain is not None or platform or deadline)
        query = ("报销 " + question) if topic and domain == "expense" and explicit_domain is None else question
        return {"topic": topic, "query": query, "canonical_query": CANONICAL.get(topic),
                "needs_clarification": needs_clarification}

    def search(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("检索 query 必须为非空字符串")
        normalized = _normalize(query)
        matches = []
        for document in self._documents.values():
            score = sum(len(_normalize(keyword)) for keyword in document["keywords"] if _normalize(keyword) in normalized)
            if _normalize(document["title"]) in normalized:
                score += len(_normalize(document["title"]))
            if score:
                matches.append((score, {"doc_id": document["id"], "title": document["title"],
                    "version_date": document["version_date"], "passage_ids": [p["id"] for p in document["passages"]],
                    "topics": sorted({p["topic"] for p in document["passages"]})}))
        matches.sort(key=lambda item: (-item[0], item[1]["doc_id"]))
        return {"ok": True, "matches": [item[1] for item in matches], "exhaustive": True}

    def read(self, doc_id):
        document = self._documents.get(doc_id)
        if document is None:
            return {"ok": False, "error": "document_not_found", "doc_id": doc_id}
        return {"ok": True, "document": {"doc_id": doc_id, "title": document["title"],
                    "version_date": document["version_date"], "scope": document.get("scope"), "priority": document.get("priority")},
                "passages": copy.deepcopy(document["passages"])}

    def related_ids(self, topic):
        return sorted(document["id"] for document in self._documents.values()
                      if any(passage["topic"] == topic for passage in document["passages"]))
