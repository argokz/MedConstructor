"""
Единая точка кодирования текстов в векторы для БД и ConceptMatcher.

- Модели OpenAI (`text-embedding-*`): через API, если задан `OPENAI_API_KEY`.
- Остальное: `sentence-transformers` по имени модели на Hugging Face.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import List, Optional

import numpy as np

from app.config import Settings

_ST_FALLBACK = "intfloat/multilingual-e5-small"

# Process-local LRU cache of label -> vector. Reference-graph labels are stable
# across all student submissions, so caching avoids re-embedding them on every
# /evaluate call (and collapses the matcher + evaluator double lookup into one).
_EMB_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_EMB_CACHE_MAX = 20000


def _cache_key(settings: Settings, text: str) -> str:
    return f"{settings.embedding_model_name}|{settings.embedding_vector_dim}|{text}"


def _strip_st_prefix(name: str) -> str:
    s = name.strip()
    if s.lower().startswith("sentence-transformers/"):
        return s.split("/", 1)[-1].strip()
    return s


def _is_openai_embedding_model(name: str) -> bool:
    n = _strip_st_prefix(name).lower()
    return "text-embedding" in n


def _openai_model_id(name: str) -> str:
    """Нормализует идентификатор для OpenAI (убирает ошибочный префикс sentence-transformers/)."""
    return _strip_st_prefix(name)


def encode_texts_sync(settings: Settings, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    keys = [_cache_key(settings, t) for t in texts]
    result: List[Optional[List[float]]] = [None] * len(texts)
    missing_idx: List[int] = []
    missing_texts: List[str] = []
    for i, key in enumerate(keys):
        cached = _EMB_CACHE.get(key)
        if cached is not None:
            _EMB_CACHE.move_to_end(key)
            result[i] = cached
        else:
            missing_idx.append(i)
            missing_texts.append(texts[i])

    if missing_texts:
        if settings.openai_api_key and _is_openai_embedding_model(settings.embedding_model_name):
            encoded = _encode_openai(settings, missing_texts)
        else:
            encoded = _encode_sentence_transformers(settings, missing_texts)
        for j, idx in enumerate(missing_idx):
            result[idx] = encoded[j]
            _EMB_CACHE[keys[idx]] = encoded[j]
            _EMB_CACHE.move_to_end(keys[idx])
        while len(_EMB_CACHE) > _EMB_CACHE_MAX:
            _EMB_CACHE.popitem(last=False)

    return [vec for vec in result if vec is not None]


def _encode_openai(settings: Settings, texts: List[str]) -> List[List[float]]:
    from openai import OpenAI

    model = _openai_model_id(settings.embedding_model_name)
    # Bound the call so a slow/unreachable OpenAI endpoint fails fast instead of
    # hanging past the reverse-proxy read timeout (Cloudflare 524). Worst case
    # ~= timeout * (max_retries + 1), well under 120 s.
    timeout = float(getattr(settings, "openai_embedding_timeout", 8.0))
    max_retries = int(getattr(settings, "openai_embedding_max_retries", 0))
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=max(1.0, timeout),
        max_retries=max(0, max_retries),
    )
    dim = settings.embedding_vector_dim or None
    batch = max(1, min(getattr(settings, "embedding_batch_size", 64) or 64, 256))
    out: List[List[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        kwargs: dict = {"model": model, "input": chunk}
        if dim and model.startswith("text-embedding-3"):
            kwargs["dimensions"] = dim
        resp = client.embeddings.create(**kwargs)
        for item in sorted(resp.data, key=lambda d: d.index):
            v = np.asarray(item.embedding, dtype=np.float64)
            n = np.linalg.norm(v)
            if n > 0:
                v = v / n
            out.append(v.tolist())
    return out


def _encode_sentence_transformers(settings: Settings, texts: List[str]) -> List[List[float]]:
    from sentence_transformers import SentenceTransformer

    name = settings.embedding_model_name.strip()
    if _is_openai_embedding_model(name) and not settings.openai_api_key:
        name = _ST_FALLBACK
    try:
        model = SentenceTransformer(name)
    except Exception:
        model = SentenceTransformer(_ST_FALLBACK)
    batch = max(1, min(getattr(settings, "embedding_batch_size", 64) or 64, 512))
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=batch,
    )
    return [v.astype("float64").tolist() for v in vectors]
