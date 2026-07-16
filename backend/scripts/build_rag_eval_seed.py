from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

from sqlalchemy import text

from app.database import AsyncSessionLocal

DEFAULT_BASE_SEED = BACKEND_ROOT / "benchmarks" / "rag_queries.extended.seed.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "benchmarks" / "rag_queries.research.seed.json"

TITLE_STOPWORDS = {
    "при",
    "для",
    "или",
    "как",
    "что",
    "это",
    "его",
    "под",
    "над",
    "без",
    "детей",
    "взрослых",
    "беременных",
    "беременности",
    "диагностика",
    "лечение",
    "клинический",
    "клинические",
    "протокол",
    "протоколы",
}

SECTION_INTENTS = [
    ("Диагностика", ("диагност", "диагноз", "обслед", "лаборатор", "инструмент", "узи", "анализ")),
    ("Лечение", ("лечение", "терап", "препарат", "фармаколог", "операц", "хирург")),
    ("Госпитализация", ("госпитал", "стационар", "экстренн")),
    ("Профилактика", ("профилакти", "предотвращ")),
    ("Классификация", ("классифика", "степен", "форма")),
    ("Мониторинг", ("монитор", "наблюден", "контрол", "ктг")),
]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_title(title: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", " ", title or "")
    cleaned = re.sub(r"[^0-9a-zа-яё]+", " ", cleaned.lower())
    return " ".join(cleaned.split())


def _content_tokens(text_value: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-zа-яё0-9]{4,}", text_value.lower()):
        if token not in TITLE_STOPWORDS:
            tokens.append(token)
    return tokens


def _title_key_phrases(title: str) -> list[str]:
    tokens = _content_tokens(title)
    phrases: list[str] = []
    if len(tokens) >= 2:
        phrases.append(" ".join(tokens[:2]))
    if len(tokens) >= 3:
        phrases.append(" ".join(tokens[:3]))
    if tokens:
        phrases.append(tokens[0])
    return list(dict.fromkeys(phrases))[:3]


def _extract_section_prefix(text_content: str) -> str:
    match = re.match(r"\[Секция:\s*([^\]]+)\]", text_content or "")
    return match.group(1).strip() if match else ""


def _section_intent(section: str) -> str | None:
    lowered = section.lower()
    for label, markers in SECTION_INTENTS:
        if any(marker in lowered for marker in markers):
            return label
    return None


def _expected_sections(chunks: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for chunk in chunks:
        section = _extract_section_prefix(str(chunk.get("text_content") or ""))
        intent = _section_intent(section)
        if intent and intent not in found:
            found.append(intent)
    if not found:
        found = ["Диагностика", "Лечение"]
    if "Диагностика" not in found:
        found.insert(0, "Диагностика")
    if "Лечение" not in found:
        found.append("Лечение")
    return found[:4]


def _query_for_case(title: str, expected_sections: list[str]) -> str:
    additions = []
    for section in expected_sections:
        lowered = section.lower()
        if lowered not in title.lower():
            additions.append(lowered)
    return " ".join([title.strip(), *additions, "клинический протокол"]).strip()


def _case_id(protocol_id: int) -> str:
    return f"auto_protocol_{protocol_id}"


def _enrich_base_case(case: dict[str, Any], title_by_id: dict[int, str]) -> dict[str, Any]:
    enriched = dict(case)
    if enriched.get("expected_key_phrases"):
        return enriched
    expected_ids = [int(item) for item in enriched.get("expected_protocol_ids", [])]
    title = title_by_id.get(expected_ids[0], "") if expected_ids else ""
    phrases = _title_key_phrases(title)
    if phrases:
        enriched["expected_key_phrases"] = phrases
    enriched.setdefault("metadata", {})
    enriched["metadata"].setdefault("source", "curated_extended_seed")
    return enriched


async def _load_protocol_rows() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT p.id, p.title, p.medical_sections, p.year, count(c.id) AS chunk_count
                FROM clinical_protocols p
                JOIN protocol_chunks c ON c.protocol_id = p.id
                GROUP BY p.id
                ORDER BY p.id
                """
            )
        )
        return [dict(row._mapping) for row in result.all()]


async def _load_chunks(protocol_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not protocol_ids:
        return {}
    ids_sql = ",".join(str(int(protocol_id)) for protocol_id in protocol_ids)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                f"""
                SELECT protocol_id, chunk_index, substring(text_content from 1 for 2500) AS text_content
                FROM protocol_chunks
                WHERE protocol_id IN ({ids_sql})
                ORDER BY protocol_id, chunk_index
                """
            )
        )
        chunks_by_protocol: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in result.all():
            payload = dict(row._mapping)
            chunks_by_protocol[int(payload["protocol_id"])].append(payload)
        return chunks_by_protocol


def _choose_protocol_groups(
    rows: list[dict[str, Any]],
    *,
    excluded_ids: set[int],
    target_extra: int,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        title = str(row.get("title") or "").strip()
        protocol_id = int(row["id"])
        if not title or protocol_id in excluded_ids:
            continue
        if int(row.get("chunk_count") or 0) < 4:
            continue
        groups[_normalize_title(title)].append(row)

    representatives = []
    for normalized_title, members in groups.items():
        if not normalized_title:
            continue
        members = sorted(members, key=lambda row: int(row["id"]))
        representative = members[0]
        representative["expected_protocol_ids"] = [int(member["id"]) for member in members]
        representatives.append(representative)

    representatives.sort(
        key=lambda row: (
            str((row.get("medical_sections") or [""])[0] if row.get("medical_sections") else ""),
            -int(row.get("chunk_count") or 0),
            int(row["id"]),
        )
    )

    selected: list[dict[str, Any]] = []
    section_counts: dict[str, int] = defaultdict(int)
    for row in representatives:
        sections = row.get("medical_sections") or ["unknown"]
        primary_section = str(sections[0] or "unknown")
        if section_counts[primary_section] >= 4:
            continue
        selected.append(row)
        section_counts[primary_section] += 1
        if len(selected) >= target_extra:
            break

    if len(selected) < target_extra:
        selected_ids = {int(row["id"]) for row in selected}
        for row in representatives:
            if int(row["id"]) in selected_ids:
                continue
            selected.append(row)
            if len(selected) >= target_extra:
                break
    return selected[:target_extra]


async def build_seed(base_path: Path, target: int) -> list[dict[str, Any]]:
    base_cases = _read_json(base_path)
    rows = await _load_protocol_rows()
    title_by_id = {int(row["id"]): str(row.get("title") or "") for row in rows}
    enriched_base = [_enrich_base_case(case, title_by_id) for case in base_cases]

    excluded_ids = {
        int(protocol_id)
        for case in enriched_base
        for protocol_id in case.get("expected_protocol_ids", [])
    }
    target_extra = max(0, target - len(enriched_base))
    selected_rows = _choose_protocol_groups(rows, excluded_ids=excluded_ids, target_extra=target_extra)
    chunks_by_protocol = await _load_chunks([int(row["id"]) for row in selected_rows])

    generated_cases = []
    for row in selected_rows:
        protocol_id = int(row["id"])
        title = str(row.get("title") or "").strip()
        chunks = chunks_by_protocol.get(protocol_id, [])
        expected_sections = _expected_sections(chunks)
        key_phrases = _title_key_phrases(title)
        key_phrases.extend(section.lower() for section in expected_sections[:2])

        generated_cases.append(
            {
                "id": _case_id(protocol_id),
                "query": _query_for_case(title, expected_sections),
                "expected_protocol_ids": row["expected_protocol_ids"],
                "expected_sections": expected_sections,
                "expected_key_phrases": list(dict.fromkeys(key_phrases))[:5],
                "limit": 10,
                "metadata": {
                    "source": "auto_generated_from_db",
                    "requires_expert_review": True,
                    "protocol_title": title,
                    "medical_sections": row.get("medical_sections") or [],
                    "year": row.get("year"),
                    "chunk_count": int(row.get("chunk_count") or 0),
                },
            }
        )

    return (enriched_base + generated_cases)[:target]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a draft research RAG eval seed from the protocol DB.")
    parser.add_argument("--base", default=str(DEFAULT_BASE_SEED), help="Base curated seed JSON.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output seed JSON.")
    parser.add_argument("--target", type=int, default=50, help="Target number of cases.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    base_path = Path(args.base)
    if not base_path.is_absolute():
        base_path = (BACKEND_ROOT / base_path).resolve()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (BACKEND_ROOT / out_path).resolve()

    seed = asyncio.run(build_seed(base_path, args.target))
    _write_json(out_path, seed)
    auto_count = sum(1 for case in seed if case.get("metadata", {}).get("source") == "auto_generated_from_db")
    print(
        json.dumps(
            {
                "out": str(out_path),
                "target": args.target,
                "cases": len(seed),
                "auto_generated": auto_count,
                "curated": len(seed) - auto_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
