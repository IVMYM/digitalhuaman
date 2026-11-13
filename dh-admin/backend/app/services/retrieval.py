"""知识库检索。

TODO: 接入 RAGFlow 或独立的 embedding 服务。
当前 KeywordRetriever 只做字符二元组重叠，适合少量 txt/md/pdf 的联调，
不是向量检索，也不要在本服务里加入 torch / sentence-transformers。

替换约定：
    retrieve(db, knowledge_base_id, query, top_k=3) -> list[{"document", "snippet"}]

建议以后用环境变量 RAGFLOW_BASE_URL 调用 RAGFlow 的 HTTP API，
把本地知识库 id 映射到 RAGFlow dataset，而不是把模型权重装进这个 CPU 容器。
"""

from sqlalchemy.orm import Session

from app.models import KnowledgeDocument

MAX_CONTEXT_CHARS = 4000


class KeywordRetriever:
    def retrieve(self, db: Session, knowledge_base_id: int, query: str, top_k: int = 3) -> list[dict]:
        compact = "".join((query or "").split())
        if not compact:
            return []
        grams = {compact[i : i + 2] for i in range(max(len(compact) - 1, 0))}
        if not grams:
            grams = {compact}
        grams = list(grams)[:40]
        docs = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
            .all()
        )
        scored: list[tuple[int, KnowledgeDocument, str]] = []
        for doc in docs:
            text = doc.text_content or ""
            if not text:
                continue
            score = sum(text.count(gram) for gram in grams)
            if score > 0:
                scored.append((score, doc, text))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _score, doc, text in scored[:top_k]:
            results.append({"document": doc.original_name, "snippet": _snippet(text, compact)})
        return results


def _snippet(text: str, query: str, window: int = 240) -> str:
    index = text.find(query[:12]) if query else -1
    if index < 0 and len(query) >= 2:
        index = text.find(query[:2])
    if index < 0:
        return text[:window]
    start = max(0, index - 40)
    return text[start : start + window]


def build_context(db: Session, knowledge_base_id: int | None, query: str) -> str:
    if not knowledge_base_id:
        return ""
    hits = KeywordRetriever().retrieve(db, knowledge_base_id, query)
    if not hits:
        return ""
    parts = [f"[{item['document']}] {item['snippet']}" for item in hits]
    return "\n\n".join(parts)[:MAX_CONTEXT_CHARS]


def extract_text(path, suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:200_000]
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)[:200_000]
    return ""
