from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal, engine
from app.models import Assignment, ClinicalProtocol, ProtocolChunk, ReferenceGraph
from scripts.cardiology_synthetic_benchmark import DEFAULT_PROTOCOL_SOURCE_IDS


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if str(value) else []


def _case_id_from_text(text: str) -> str | None:
    for case_id in DEFAULT_PROTOCOL_SOURCE_IDS:
        if case_id in text:
            return case_id
    return None


def _protocol_ids_from_context(context: Any) -> list[int]:
    ids: list[int] = []
    if isinstance(context, list):
        for entry in context:
            if not isinstance(entry, dict):
                continue
            protocol_id = _int_or_none(entry.get("protocol_id") or entry.get("source_protocol_id"))
            if protocol_id is not None and protocol_id not in ids:
                ids.append(protocol_id)
    return ids


def _protocol_ids_from_text(text: str) -> list[int]:
    ids: list[int] = []
    for match in re.findall(r"protocols=\[([^\]]+)\]", text or ""):
        for raw_id in re.findall(r"\d+", match):
            protocol_id = int(raw_id)
            if protocol_id not in ids:
                ids.append(protocol_id)
    return ids


def _source_from_protocol(
    protocol: ClinicalProtocol | None,
    chunk_count: int | None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = defaults or {}
    protocol_id = protocol.id if protocol else _int_or_none(defaults.get("protocol_id"))
    protocol_url = protocol.url if protocol else defaults.get("protocol_url")
    external_id = defaults.get("protocol_external_id") or defaults.get("external_protocol_id") or defaults.get("medelement_id")
    if not external_id and isinstance(protocol_url, str):
        match = re.search(r"/(\d+)(?:$|[/?#])", protocol_url)
        if match:
            external_id = match.group(1)
    sections = _safe_list(protocol.medical_sections if protocol else defaults.get("protocol_sections"))
    category = (
        defaults.get("protocol_category")
        or (sections[0] if sections else None)
        or (protocol.category if protocol else None)
    )
    return {
        "protocol_id": protocol_id,
        "protocol_external_id": str(external_id) if external_id not in (None, "") else None,
        "protocol_title": protocol.title if protocol else defaults.get("protocol_title"),
        "protocol_year": protocol.year if protocol else defaults.get("protocol_year"),
        "protocol_version": protocol.version if protocol else defaults.get("protocol_version"),
        "protocol_url": protocol_url,
        "protocol_category": category,
        "protocol_sections": sections,
        "protocol_mkb_categories": _safe_list(protocol.mkb_categories if protocol else defaults.get("protocol_mkb_categories")),
        "protocol_chunk_count": int(chunk_count or defaults.get("protocol_chunk_count") or 0) or None,
        "source_fit": defaults.get("source_fit"),
        "source_note": defaults.get("source_note"),
        "source": "clinical_protocols",
    }


def _merge_context_entry(entry: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    merged = dict(entry)
    for key, value in source.items():
        if value not in (None, "", []):
            merged[key] = value
    section = merged.get("section")
    if section not in (None, ""):
        sections = _safe_list(merged.get("protocol_sections"))
        if str(section) not in sections:
            sections.append(str(section))
        merged["protocol_sections"] = sections
    return merged


def _dedup_sources(context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[int | None, str | None]] = set()
    for entry in context:
        protocol_id = _int_or_none(entry.get("protocol_id") or entry.get("source_protocol_id"))
        protocol_title = entry.get("protocol_title") or entry.get("source_protocol_title")
        if protocol_id is None and not protocol_title:
            continue
        key = (protocol_id, str(protocol_title) if protocol_title else None)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "protocol_id": protocol_id,
                "protocol_external_id": entry.get("protocol_external_id")
                or entry.get("external_protocol_id")
                or entry.get("medelement_id"),
                "protocol_title": protocol_title,
                "protocol_year": _int_or_none(entry.get("protocol_year") or entry.get("year")),
                "protocol_version": entry.get("protocol_version") or entry.get("version"),
                "protocol_url": entry.get("protocol_url") or entry.get("source_protocol_url") or entry.get("url"),
                "protocol_category": entry.get("protocol_category") or entry.get("category"),
                "protocol_sections": _safe_list(entry.get("protocol_sections") or entry.get("medical_sections")),
                "protocol_mkb_categories": _safe_list(entry.get("protocol_mkb_categories") or entry.get("mkb_categories")),
                "protocol_chunk_count": _int_or_none(entry.get("protocol_chunk_count") or entry.get("chunk_count")),
                "source_fit": entry.get("source_fit"),
                "source_note": entry.get("source_note"),
                "source": entry.get("source") or "clinical_protocols",
            }
        )
    return sources


def _context_hash(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_line(source: dict[str, Any]) -> str:
    protocol_id = source.get("protocol_id")
    title = source.get("protocol_title") or "название протокола не найдено"
    details = [
        str(source.get("protocol_year")) if source.get("protocol_year") else None,
        source.get("protocol_category"),
    ]
    suffix = "; ".join(item for item in details if item)
    return f"Источник: протокол #{protocol_id} — {title}" + (f" ({suffix})" if suffix else "")


def _update_assignment_description(description: str | None, source: dict[str, Any]) -> str | None:
    if not description or not source.get("protocol_id"):
        return description
    protocol_id = source["protocol_id"]
    target = _source_line(source)
    lines = description.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if "Источник:" in line and f"протокол #{protocol_id}" in line:
            lines[index] = target
            replaced = True
            break
    if replaced:
        return "\n".join(lines)
    return description.rstrip() + "\n\n" + target


async def _load_protocols(protocol_ids: set[int]) -> dict[int, tuple[ClinicalProtocol, int]]:
    if not protocol_ids:
        return {}
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ClinicalProtocol, func.count(ProtocolChunk.id).label("chunk_count"))
            .outerjoin(ProtocolChunk, ProtocolChunk.protocol_id == ClinicalProtocol.id)
            .where(ClinicalProtocol.id.in_(sorted(protocol_ids)))
            .group_by(ClinicalProtocol.id)
        )
        return {protocol.id: (protocol, int(chunk_count or 0)) for protocol, chunk_count in rows.all()}


async def backfill_protocol_provenance(*, dry_run: bool = False) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        reference_rows = (await session.execute(select(ReferenceGraph))).scalars().all()
        assignment_rows = (await session.execute(select(Assignment))).scalars().all()
        assignments_by_ref: dict[int, list[Assignment]] = {}
        for assignment in assignment_rows:
            assignments_by_ref.setdefault(assignment.reference_graph_id, []).append(assignment)

        protocol_ids: set[int] = {
            int(source["protocol_id"])
            for source in DEFAULT_PROTOCOL_SOURCE_IDS.values()
            if source.get("protocol_id") is not None
        }
        for graph in reference_rows:
            protocol_ids.update(_protocol_ids_from_context(graph.generation_context))
            protocol_ids.update(_protocol_ids_from_text(graph.review_notes or ""))

        protocols = await _load_protocols(protocol_ids)
        defaults_by_protocol_id = {
            int(source["protocol_id"]): dict(source)
            for source in DEFAULT_PROTOCOL_SOURCE_IDS.values()
            if source.get("protocol_id") is not None
        }

        updated_graphs = 0
        updated_assignments = 0
        tagged_graphs = 0
        manual_or_unknown: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat()

        for graph in reference_rows:
            assignment_text = " ".join(
                f"{assignment.title} {assignment.description or ''}"
                for assignment in assignments_by_ref.get(graph.id, [])
            )
            search_text = " ".join([graph.title or "", graph.description or "", graph.review_notes or "", assignment_text])
            case_id = _case_id_from_text(search_text)

            inferred_protocol_ids = _protocol_ids_from_context(graph.generation_context)
            inferred_protocol_ids.extend(_protocol_ids_from_text(graph.review_notes or ""))
            if case_id and not inferred_protocol_ids:
                protocol_id = _int_or_none(DEFAULT_PROTOCOL_SOURCE_IDS[case_id].get("protocol_id"))
                if protocol_id is not None:
                    inferred_protocol_ids.append(protocol_id)

            unique_protocol_ids: list[int] = []
            for protocol_id in inferred_protocol_ids:
                if protocol_id not in unique_protocol_ids:
                    unique_protocol_ids.append(protocol_id)

            if not unique_protocol_ids:
                manual_or_unknown.append({"reference_graph_id": graph.id, "title": graph.title})
                continue

            old_context_hash = _context_hash(graph.generation_context)
            context: list[dict[str, Any]] = []
            seen_context_protocol_ids: set[int] = set()
            if isinstance(graph.generation_context, list):
                for entry in graph.generation_context:
                    if not isinstance(entry, dict):
                        continue
                    protocol_id = _int_or_none(entry.get("protocol_id") or entry.get("source_protocol_id"))
                    if protocol_id is None:
                        context.append(dict(entry))
                        continue
                    protocol, chunk_count = protocols.get(protocol_id, (None, None))
                    defaults = defaults_by_protocol_id.get(protocol_id, {})
                    context.append(_merge_context_entry(entry, _source_from_protocol(protocol, chunk_count, defaults)))
                    seen_context_protocol_ids.add(protocol_id)

            for protocol_id in unique_protocol_ids:
                if protocol_id in seen_context_protocol_ids:
                    continue
                protocol, chunk_count = protocols.get(protocol_id, (None, None))
                defaults = defaults_by_protocol_id.get(protocol_id, {})
                source = _source_from_protocol(protocol, chunk_count, defaults)
                if case_id:
                    source["case_id"] = case_id
                context.append(source)

            sources = _dedup_sources(context)
            if not sources:
                manual_or_unknown.append({"reference_graph_id": graph.id, "title": graph.title})
                continue

            graph_data = deepcopy(graph.graph_data) if isinstance(graph.graph_data, dict) else graph.graph_data
            if isinstance(graph_data, dict):
                metadata = graph_data.setdefault("metadata", {})
                metadata["source_protocols"] = deepcopy(sources)
                metadata["primary_protocol"] = deepcopy(sources[0])
                metadata["protocol_provenance_backfilled_at"] = now

            if old_context_hash != _context_hash(context) or graph.graph_data != graph_data:
                graph.generation_context = context
                graph.graph_data = graph_data
                graph.source_type = graph.source_type or "protocol_grounded"
                graph.updated_at = datetime.now(timezone.utc)
                updated_graphs += 1

            tagged_graphs += 1
            primary_source = sources[0]
            for assignment in assignments_by_ref.get(graph.id, []):
                updated_description = _update_assignment_description(assignment.description, primary_source)
                if updated_description != assignment.description:
                    assignment.description = updated_description
                    updated_assignments += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    await engine.dispose()
    return {
        "dry_run": dry_run,
        "updated_graphs": updated_graphs,
        "updated_assignments": updated_assignments,
        "tagged_graphs": tagged_graphs,
        "manual_or_unknown_count": len(manual_or_unknown),
        "manual_or_unknown": manual_or_unknown[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill protocol provenance into reference graphs and assignments.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect changes without committing.")
    args = parser.parse_args()
    result = asyncio.run(backfill_protocol_provenance(dry_run=args.dry_run))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
