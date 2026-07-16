from __future__ import annotations

import csv
import io
import json
import math
import random
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Assignment, ClinicalProtocol, ProtocolChunk, ReferenceGraph, User
from app.schemas import GraphSchema
from app.services.demo_cardiology_importer import import_cardiology_demo_workflow
from app.services.expert_evaluation import analyze_expert_ratings, baseline_comparison_rows
from app.services.graph_generation_judge import judge_reference_graph
from scripts.build_graph_eval_seed import build_seed as build_graph_seed
from scripts.build_rag_eval_seed import DEFAULT_BASE_SEED as DEFAULT_RAG_BASE_SEED
from scripts.build_rag_eval_seed import build_seed as build_rag_seed
from scripts.cardiology_synthetic_benchmark import (
    DEFAULT_PROTOCOL_SOURCE_IDS,
    run_cardiology_synthetic_benchmark,
)
from scripts.export_graph_expert_ratings import (
    _build_review_items,
    _write_csv_template,
    _write_items_jsonl,
    _write_key,
)
from scripts.run_benchmark import run_graph_benchmark, run_rag_ablation, run_rag_benchmark

BACKEND_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = BACKEND_ROOT / "benchmarks"

RAG_SEED = BENCHMARKS_DIR / "rag_queries.research.seed.json"
RAG_LATEST = BENCHMARKS_DIR / "rag_research_latest.json"
RAG_ABLATION_LATEST = BENCHMARKS_DIR / "rag_research_ablation_latest.json"

GRAPH_SEED = BENCHMARKS_DIR / "graph_cases.research.seed.json"
GRAPH_LATEST = BENCHMARKS_DIR / "graph_research_latest.json"

CARDIOLOGY_SEED = BENCHMARKS_DIR / "cardiology_synthetic_seed.json"
CARDIOLOGY_LATEST = BENCHMARKS_DIR / "cardiology_synthetic_latest.json"
CARDIOLOGY_REAL_VALIDATION_PILOT = BENCHMARKS_DIR / "cardiology_real_expert_validation_latest.json"
CARDIOLOGY_REAL_VALIDATION = BENCHMARKS_DIR / "cardiology_real_expert_validation_v2_latest.json"
CARDIOLOGY_REAL_RATINGS_CSV = BENCHMARKS_DIR / "cardiology_real_expert_ratings_latest.csv"
CARDIOLOGY_REAL_BASELINE_COMPARISON_PILOT_CSV = (
    BENCHMARKS_DIR / "cardiology_real_baseline_comparison_latest.csv"
)
CARDIOLOGY_REAL_BASELINE_COMPARISON_CSV = (
    BENCHMARKS_DIR / "cardiology_real_baseline_comparison_v2_latest.csv"
)
CARDIOLOGY_REAL_BOOTSTRAP = BENCHMARKS_DIR / "cardiology_real_case_cluster_bootstrap_v2_latest.json"
CARDIOLOGY_REAL_REFERENCE_AUDIT_CSV = (
    BENCHMARKS_DIR / "cardiology_real_reference_audit_v2_latest.csv"
)
CARDIOLOGY_PROTOCOL_GROUNDING_CSV = BENCHMARKS_DIR / "cardiology_protocol_grounding.csv"

EXPERT_RATINGS_TEMPLATE = BENCHMARKS_DIR / "graph_expert_ratings.template.csv"
EXPERT_REVIEW_ITEMS = BENCHMARKS_DIR / "graph_expert_review_items.jsonl"
EXPERT_REVIEW_KEY = BENCHMARKS_DIR / "graph_expert_review_key.json"
EXPERT_RATINGS_UPLOAD = BENCHMARKS_DIR / "graph_expert_ratings.uploaded.csv"
EXPERT_CORRELATION_LATEST = BENCHMARKS_DIR / "graph_expert_correlation_latest.json"

SUMMARY_CSV = BENCHMARKS_DIR / "benchmark_summary_latest.csv"
RAG_SEED_CSV = BENCHMARKS_DIR / "rag_queries_research_seed.csv"
RAG_RESULTS_CSV = BENCHMARKS_DIR / "rag_research_results_latest.csv"
RAG_MISSES_CSV = BENCHMARKS_DIR / "rag_research_misses_latest.csv"
RAG_ABLATION_CSV = BENCHMARKS_DIR / "rag_research_ablation_results_latest.csv"
GRAPH_SEED_CSV = BENCHMARKS_DIR / "graph_cases_research_seed.csv"
GRAPH_RESULTS_CSV = BENCHMARKS_DIR / "graph_research_results_latest.csv"
GRAPH_REFERENCE_QUALITY_CSV = BENCHMARKS_DIR / "graph_reference_quality_latest.csv"
CARDIOLOGY_TASKS_CSV = BENCHMARKS_DIR / "cardiology_synthetic_tasks_latest.csv"
CARDIOLOGY_RESULTS_CSV = BENCHMARKS_DIR / "cardiology_synthetic_results_latest.csv"
CARDIOLOGY_REFERENCE_QUALITY_CSV = BENCHMARKS_DIR / "cardiology_synthetic_reference_quality_latest.csv"
CARDIOLOGY_EXPERT_RATINGS_CSV = BENCHMARKS_DIR / "cardiology_synthetic_expert_ratings_latest.csv"
CARDIOLOGY_EXPERT_ITEMS_CSV = BENCHMARKS_DIR / "cardiology_synthetic_expert_items_latest.csv"
CARDIOLOGY_EXPERT_BY_EXPERT_CSV = BENCHMARKS_DIR / "cardiology_synthetic_expert_by_expert_latest.csv"
CARDIOLOGY_EXPERT_BY_PATTERN_CSV = BENCHMARKS_DIR / "cardiology_synthetic_expert_by_pattern_latest.csv"
CARDIOLOGY_PATTERN_SUMMARY_CSV = BENCHMARKS_DIR / "cardiology_synthetic_pattern_summary_latest.csv"
CARDIOLOGY_RECOMMENDATIONS_CSV = BENCHMARKS_DIR / "cardiology_synthetic_recommendations_latest.csv"
CARDIOLOGY_BASELINE_COMPARISON_CSV = BENCHMARKS_DIR / "cardiology_synthetic_baseline_comparison_latest.csv"
EXPERT_ITEMS_CSV = BENCHMARKS_DIR / "graph_expert_items_latest.csv"
EXPERT_BY_EXPERT_CSV = BENCHMARKS_DIR / "graph_expert_by_expert_latest.csv"
EXPERT_BY_PATTERN_CSV = BENCHMARKS_DIR / "graph_expert_by_pattern_latest.csv"
EXPERT_BASELINE_COMPARISON_CSV = BENCHMARKS_DIR / "graph_expert_baseline_comparison_latest.csv"
EXPERT_SKIPPED_ROWS_CSV = BENCHMARKS_DIR / "graph_expert_skipped_rows_latest.csv"
PROBLEMS_CSV = BENCHMARKS_DIR / "benchmark_problems_latest.csv"
GENERATION_AUDIT_JSON = BENCHMARKS_DIR / "generation_quality_audit_latest.json"
GENERATION_AUDIT_CSV = BENCHMARKS_DIR / "generation_quality_audit_latest.csv"
HISTORY_JSON = BENCHMARKS_DIR / "benchmark_runs.history.json"
HISTORY_CSV = BENCHMARKS_DIR / "benchmark_runs.history.csv"
XLSX_REPORT = BENCHMARKS_DIR / "benchmark_report_latest.xlsx"

ALLOWED_ARTIFACTS = {
    RAG_SEED.name,
    RAG_LATEST.name,
    RAG_ABLATION_LATEST.name,
    GRAPH_SEED.name,
    GRAPH_LATEST.name,
    CARDIOLOGY_SEED.name,
    CARDIOLOGY_LATEST.name,
    CARDIOLOGY_REAL_VALIDATION_PILOT.name,
    CARDIOLOGY_REAL_VALIDATION.name,
    CARDIOLOGY_REAL_RATINGS_CSV.name,
    CARDIOLOGY_REAL_BOOTSTRAP.name,
    CARDIOLOGY_REAL_REFERENCE_AUDIT_CSV.name,
    CARDIOLOGY_PROTOCOL_GROUNDING_CSV.name,
    EXPERT_RATINGS_TEMPLATE.name,
    EXPERT_REVIEW_ITEMS.name,
    EXPERT_REVIEW_KEY.name,
    EXPERT_RATINGS_UPLOAD.name,
    EXPERT_CORRELATION_LATEST.name,
    SUMMARY_CSV.name,
    RAG_SEED_CSV.name,
    RAG_RESULTS_CSV.name,
    RAG_MISSES_CSV.name,
    RAG_ABLATION_CSV.name,
    GRAPH_SEED_CSV.name,
    GRAPH_RESULTS_CSV.name,
    GRAPH_REFERENCE_QUALITY_CSV.name,
    CARDIOLOGY_TASKS_CSV.name,
    CARDIOLOGY_RESULTS_CSV.name,
    CARDIOLOGY_REFERENCE_QUALITY_CSV.name,
    CARDIOLOGY_EXPERT_RATINGS_CSV.name,
    CARDIOLOGY_EXPERT_ITEMS_CSV.name,
    CARDIOLOGY_EXPERT_BY_EXPERT_CSV.name,
    CARDIOLOGY_EXPERT_BY_PATTERN_CSV.name,
    CARDIOLOGY_PATTERN_SUMMARY_CSV.name,
    CARDIOLOGY_RECOMMENDATIONS_CSV.name,
    CARDIOLOGY_BASELINE_COMPARISON_CSV.name,
    CARDIOLOGY_REAL_BASELINE_COMPARISON_PILOT_CSV.name,
    CARDIOLOGY_REAL_BASELINE_COMPARISON_CSV.name,
    EXPERT_ITEMS_CSV.name,
    EXPERT_BY_EXPERT_CSV.name,
    EXPERT_BY_PATTERN_CSV.name,
    EXPERT_BASELINE_COMPARISON_CSV.name,
    EXPERT_SKIPPED_ROWS_CSV.name,
    PROBLEMS_CSV.name,
    GENERATION_AUDIT_JSON.name,
    GENERATION_AUDIT_CSV.name,
    HISTORY_JSON.name,
    HISTORY_CSV.name,
    XLSX_REPORT.name,
}


class RagSeedRequest(BaseModel):
    target: int = Field(default=50, ge=1, le=200)


class GraphSeedRequest(BaseModel):
    target: int = Field(default=20, ge=1, le=20)


class RagRunRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=500)
    ablation: bool = False


class GraphRunRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=200)
    use_embeddings: bool = False


class CardiologySyntheticRunRequest(BaseModel):
    case_count: int = Field(default=12, ge=1, le=12)
    expert_count: int = Field(default=30, ge=1, le=100)
    seed: int = Field(default=20260617, ge=1)
    use_embeddings: bool = False


class CardiologyDemoImportRequest(BaseModel):
    refresh_timestamps: bool = True


class ExpertExportRequest(BaseModel):
    shuffle: bool = True
    shuffle_seed: int = 20260617
    delimiter: Literal[",", ";"] = ","


class ExpertAnalyzeRequest(BaseModel):
    csv_text: str = Field(min_length=1)
    delimiter: Literal["auto", ",", ";"] = "auto"


class GenerationAuditRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


def require_teacher_or_admin(current_user: CurrentUser) -> User:
    if current_user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and admins can run research benchmarks.",
        )
    return current_user


router = APIRouter(
    prefix="/benchmarks",
    tags=["benchmarks"],
    dependencies=[Depends(require_teacher_or_admin)],
)


def _generated_at() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cell(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return "; ".join(str(item) for item in value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _cell(row.get(field)) for field in fieldnames})


def _read_csv_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


async def _load_cardiology_protocol_sources(db: DbSession) -> dict[str, dict[str, Any]]:
    protocol_ids = {
        int(source["protocol_id"])
        for source in DEFAULT_PROTOCOL_SOURCE_IDS.values()
        if source.get("protocol_id") is not None
    }
    if not protocol_ids:
        return {}

    rows = await db.execute(
        select(ClinicalProtocol, func.count(ProtocolChunk.id).label("chunk_count"))
        .outerjoin(ProtocolChunk, ProtocolChunk.protocol_id == ClinicalProtocol.id)
        .where(ClinicalProtocol.id.in_(protocol_ids))
        .group_by(ClinicalProtocol.id)
    )
    by_id = {protocol.id: (protocol, int(chunk_count or 0)) for protocol, chunk_count in rows.all()}

    sources: dict[str, dict[str, Any]] = {}
    for case_id, defaults in DEFAULT_PROTOCOL_SOURCE_IDS.items():
        source = dict(defaults)
        protocol_id = source.get("protocol_id")
        protocol, chunk_count = by_id.get(int(protocol_id or 0), (None, None))
        if protocol is not None:
            source.update(
                {
                    "protocol_id": protocol.id,
                    "protocol_title": protocol.title,
                    "protocol_year": protocol.year,
                    "protocol_sections": protocol.medical_sections or [],
                    "protocol_mkb_categories": protocol.mkb_categories or [],
                    "protocol_version": protocol.version,
                    "protocol_url": protocol.url,
                    "protocol_chunk_count": chunk_count,
                }
            )
        sources[case_id] = source
    return sources


def _xlsx_safe_text(value: Any) -> str:
    text = str(_cell(value))
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32)


def _xlsx_col(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result or "A"


def _xlsx_cell(ref: str, value: Any, style: int | None = None) -> str:
    style_attr = f' s="{style}"' if style is not None else ""
    if value is None or value == "":
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = escape(_xlsx_safe_text(value))
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(rows: list[list[Any]]) -> str:
    row_count = max(1, len(rows))
    col_count = max([len(row) for row in rows] or [1])
    dimension = f"A1:{_xlsx_col(col_count)}{row_count}"
    rendered_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cells.append(_xlsx_cell(f"{_xlsx_col(col_index)}{row_index}", value, 1 if row_index == 1 else None))
        rendered_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    widths = "".join(
        f'<col min="{index}" max="{index}" width="{min(48, max(12, len(str(rows[0][index - 1])) + 4))}" customWidth="1"/>'
        for index in range(1, col_count + 1)
        if rows and index <= len(rows[0])
    )
    auto_filter = f'<autoFilter ref="{dimension}"/>' if len(rows) > 1 else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{widths}</cols>"
        f'<sheetData>{"".join(rendered_rows)}</sheetData>'
        f"{auto_filter}"
        "</worksheet>"
    )


def _write_xlsx(path: Path, sheets: list[tuple[str, list[dict[str, Any]], list[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = []
    used_names = set()
    for index, (name, rows, fieldnames) in enumerate(sheets, start=1):
        safe_name = "".join(ch for ch in name if ch not in r'[]:*?/\\')[:31] or f"Sheet{index}"
        original = safe_name
        suffix = 2
        while safe_name in used_names:
            safe_name = f"{original[:28]}_{suffix}"[:31]
            suffix += 1
        used_names.add(safe_name)
        matrix = [fieldnames]
        matrix.extend([[row.get(field) for field in fieldnames] for row in rows])
        prepared.append((safe_name, matrix))

    workbook_sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _matrix) in enumerate(prepared, start=1)
    )
    workbook_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index, _sheet in enumerate(prepared, start=1)
    )
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index, _sheet in enumerate(prepared, start=1)
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{overrides}</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{workbook_rels}<Relationship Id="rId{len(prepared) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
            "</styleSheet>",
        )
        for index, (_name, matrix) in enumerate(prepared, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(matrix))


def _artifact_path(filename: str) -> Path:
    if filename not in ALLOWED_ARTIFACTS or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    path = (BENCHMARKS_DIR / filename).resolve()
    if BENCHMARKS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return path


def _artifact_info(filename: str) -> dict[str, Any]:
    path = (BENCHMARKS_DIR / filename).resolve()
    if not path.exists():
        return {
            "name": filename,
            "exists": False,
            "size_bytes": 0,
            "updated_at": None,
            "download_url": None,
        }
    stat = path.stat()
    return {
        "name": filename,
        "exists": True,
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        "download_url": f"/benchmarks/files/{filename}",
    }


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _read_json(path)


def _count_seed_cases(path: Path) -> int | None:
    payload = _read_json_if_exists(path)
    if isinstance(payload, list):
        return len(payload)
    return None


def _summary_payload() -> dict[str, Any]:
    rag_payload = _read_json_if_exists(RAG_LATEST) or {}
    rag_ablation_payload = _read_json_if_exists(RAG_ABLATION_LATEST) or {}
    graph_payload = _read_json_if_exists(GRAPH_LATEST) or {}
    cardiology_payload = _read_json_if_exists(CARDIOLOGY_LATEST) or {}
    human_validation_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {}
    human_validation_pilot_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION_PILOT) or {}
    expert_payload = _read_json_if_exists(EXPERT_CORRELATION_LATEST)

    rag = rag_payload.get("rag", {}) if isinstance(rag_payload, dict) else {}
    rag_ablation = (
        rag_ablation_payload.get("rag_ablation", {})
        if isinstance(rag_ablation_payload, dict)
        else {}
    )
    graph = graph_payload.get("graph", {}) if isinstance(graph_payload, dict) else {}
    cardiology = (
        cardiology_payload.get("cardiology", cardiology_payload)
        if isinstance(cardiology_payload, dict)
        else {}
    )

    return {
        "rag": {
            "seed_cases": _count_seed_cases(RAG_SEED),
            "generated_at": rag_payload.get("generated_at") if isinstance(rag_payload, dict) else None,
            "summary": rag.get("summary"),
        },
        "rag_ablation": {
            "generated_at": (
                rag_ablation_payload.get("generated_at")
                if isinstance(rag_ablation_payload, dict)
                else None
            ),
            "summary_by_mode": rag_ablation.get("summary_by_mode"),
        },
        "graph": {
            "seed_cases": _count_seed_cases(GRAPH_SEED),
            "generated_at": graph_payload.get("generated_at") if isinstance(graph_payload, dict) else None,
            "summary": graph.get("summary"),
            "reference_quality": graph.get("reference_quality", {}).get("summary"),
        },
        "cardiology": {
            "seed_cases": _count_seed_cases(CARDIOLOGY_SEED),
            "generated_at": cardiology_payload.get("generated_at") if isinstance(cardiology_payload, dict) else None,
            "summary": cardiology.get("summary"),
            "parameters": cardiology.get("parameters"),
            "reference_audit": {
                "stage": "primary_human_validation",
                "case_count": (human_validation_payload.get("summary") or {}).get(
                    "reference_correct_count"
                ),
                "audit_required_count": (human_validation_payload.get("summary") or {}).get(
                    "reference_correct_audit_required_count"
                ),
                "audit_required_rate": (human_validation_payload.get("summary") or {}).get(
                    "reference_correct_audit_required_rate"
                ),
                "mean_reference_expert_score": (
                    human_validation_payload.get("summary") or {}
                ).get("reference_correct_mean_expert"),
            },
        },
        "human_validation": {
            "primary": {
                "cohort": human_validation_payload.get("cohort"),
                "algorithm_version": human_validation_payload.get("algorithm_version"),
                "summary": human_validation_payload.get("summary"),
            },
            "pilot": {
                "cohort": human_validation_pilot_payload.get("cohort"),
                "algorithm_version": human_validation_pilot_payload.get("algorithm_version"),
                "summary": human_validation_pilot_payload.get("summary"),
            },
        },
        "expert": expert_payload,
        "artifacts": [_artifact_info(filename) for filename in sorted(ALLOWED_ARTIFACTS)],
    }


def _csv_rows(csv_text: str, delimiter: Literal["auto", ",", ";"]) -> list[dict[str, Any]]:
    text = csv_text.lstrip("\ufeff")
    if delimiter == "auto":
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
            delimiter = dialect.delimiter if dialect.delimiter in {",", ";"} else ","
        except csv.Error:
            delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV header is missing.")
    return [dict(row) for row in reader]


def _review_key_index() -> dict[str, dict[str, Any]]:
    payload = _read_json(EXPERT_REVIEW_KEY)
    return {
        str(item.get("review_item_id")): item
        for item in payload.get("items", [])
        if item.get("review_item_id")
    }


def _rag_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rag = payload.get("rag", payload)
    rows = []
    for item in rag.get("results", []) or []:
        sources = item.get("sources") or []
        top_source = sources[0] if sources else {}
        hit_rank = item.get("hit_rank")
        rows.append(
            {
                "id": item.get("id"),
                "mode": item.get("mode"),
                "query": item.get("query"),
                "hit_rank": hit_rank,
                "hit_at_1": hit_rank == 1,
                "hit_at_3": isinstance(hit_rank, int) and hit_rank <= 3,
                "hit_at_5": isinstance(hit_rank, int) and hit_rank <= 5,
                "miss": hit_rank is None,
                "section_hit_score": item.get("section_hit_score"),
                "key_phrase_hit_score": item.get("key_phrase_hit_score"),
                "latency_ms": item.get("latency_ms"),
                "expected_protocol_ids": item.get("expected_protocol_ids") or [],
                "retrieved_protocol_ids": item.get("retrieved_protocol_ids") or [],
                "retrieved_sections": item.get("retrieved_sections") or [],
                "expected_key_phrases": item.get("expected_key_phrases") or [],
                "top_protocol_id": top_source.get("protocol_id"),
                "top_protocol_title": top_source.get("protocol_title"),
                "top_section": top_source.get("section"),
                "top_chunk_index": top_source.get("chunk_index"),
                "top_preview": top_source.get("preview"),
                "sources": sources,
            }
        )
    return rows


def _rag_ablation_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ablation = payload.get("rag_ablation", payload)
    rows: list[dict[str, Any]] = []
    for mode, result in (ablation.get("by_mode") or {}).items():
        for row in _rag_result_rows(result):
            row["mode"] = mode
            rows.append(row)
    return rows


def _graph_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    graph = payload.get("graph", payload)
    rows = []
    for item in graph.get("results", []) or []:
        metrics = item.get("metrics") or {}
        rows.append(
            {
                "case_id": item.get("case_id"),
                "variant_id": item.get("variant_id"),
                "expected_pattern": item.get("expected_pattern"),
                "pattern_passed": item.get("pattern_passed"),
                "pattern_reason": item.get("pattern_reason"),
                "latency_ms": item.get("latency_ms"),
                "edge_f1": metrics.get("edge_f1"),
                "weighted_edge_f1": metrics.get("weighted_edge_f1"),
                "node_coverage": metrics.get("node_coverage"),
                "category_accuracy": metrics.get("category_accuracy"),
                "directed_path_completeness": metrics.get("directed_path_completeness"),
                "safety_penalty": metrics.get("safety_penalty"),
                "unsafe_extra_action": metrics.get("unsafe_extra_action"),
                "missing_critical_action": metrics.get("missing_critical_action"),
                "diagnostic_evidence_gap": metrics.get("diagnostic_evidence_gap"),
                "clinical_connectivity_gap": metrics.get("clinical_connectivity_gap"),
                "composite_score": metrics.get("composite_score"),
                "missing_edges_count": item.get("missing_edges_count"),
                "incorrect_edges_count": item.get("incorrect_edges_count"),
                "missing_nodes_count": item.get("missing_nodes_count"),
                "safety_findings": item.get("safety_findings") or [],
                "algorithm_version": item.get("algorithm_version"),
            }
        )
    return rows


def _graph_quality_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    graph = payload.get("graph", payload)
    rows = []
    for item in graph.get("reference_quality", {}).get("results", []) or []:
        quality = item.get("quality") or {}
        rows.append(
            {
                "case_id": item.get("case_id"),
                "title": item.get("title"),
                "schema_valid": quality.get("schema_valid"),
                "accepted": quality.get("accepted"),
                "quality_score": quality.get("quality_score"),
                "warning_count": quality.get("warning_count"),
                "critical_count": quality.get("critical_count"),
                "has_diagnosis": quality.get("has_diagnosis"),
                "has_diagnostic_step": quality.get("has_diagnostic_step"),
                "has_start_to_diagnosis_path": quality.get("has_start_to_diagnosis_path"),
                "has_diagnosis_to_action_path": quality.get("has_diagnosis_to_action_path"),
                "warnings": quality.get("warnings") or [],
            }
        )
    return rows


def _expert_item_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("items", []) or []:
        rows.append(
            {
                "case_id": item.get("case_id"),
                "variant_id": item.get("variant_id"),
                "expected_pattern": item.get("expected_pattern"),
                "model_score": item.get("model_score"),
                "expert_mean_score": item.get("expert_mean_score"),
                "expert_score_std": item.get("expert_score_std"),
                "expert_rating_count": item.get("expert_rating_count"),
                "score_gap_model_minus_expert": (
                    round(float(item.get("model_score") or 0.0) - float(item.get("expert_mean_score") or 0.0), 4)
                    if item.get("expert_mean_score") is not None
                    else None
                ),
            }
        )
    return rows


def _rag_seed_rows(seed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "query": item.get("query"),
            "expected_protocol_ids": item.get("expected_protocol_ids") or [],
            "expected_sections": item.get("expected_sections") or [],
            "expected_key_phrases": item.get("expected_key_phrases") or [],
            "limit": item.get("limit"),
            "source": item.get("metadata", {}).get("source"),
            "requires_expert_review": item.get("metadata", {}).get("requires_expert_review"),
            "protocol_title": item.get("metadata", {}).get("protocol_title"),
            "chunk_count": item.get("metadata", {}).get("chunk_count"),
        }
        for item in seed
    ]


def _graph_seed_rows(seed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in seed:
        graph = item.get("reference_graph") or {}
        rows.append(
            {
                "case_id": item.get("case_id"),
                "title": item.get("title"),
                "source": item.get("metadata", {}).get("source"),
                "requires_expert_review": item.get("metadata", {}).get("requires_expert_review"),
                "node_count": len(graph.get("nodes") or []),
                "edge_count": len(graph.get("edges") or []),
                "variant_count": len(item.get("variants") or []),
                "error_taxonomy": item.get("metadata", {}).get("error_taxonomy") or [],
                "variants": [variant.get("variant_id") for variant in item.get("variants") or []],
            }
        )
    return rows


def _cardiology_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload if payload is not None else (_read_json_if_exists(CARDIOLOGY_LATEST) or {})
    if not isinstance(payload, dict):
        return {}
    return payload.get("cardiology", payload)


def _cardiology_task_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cardiology = _cardiology_payload(payload)
    rows = cardiology.get("tasks") or []
    if rows:
        return list(rows)

    seed = _read_json_if_exists(CARDIOLOGY_SEED) or []
    rows = []
    if not isinstance(seed, list):
        return rows
    for case in seed:
        task = case.get("task") or {}
        graph = case.get("reference_graph") or {}
        source = case.get("source_protocol") or task.get("source_protocol") or {}
        rows.append(
            {
                "case_id": case.get("case_id"),
                "title": case.get("title"),
                "protocol_area": case.get("protocol_area"),
                "source_protocol_id": source.get("protocol_id"),
                "source_protocol_title": source.get("protocol_title"),
                "source_protocol_year": source.get("protocol_year"),
                "source_protocol_sections": source.get("protocol_sections") or [],
                "source_protocol_chunk_count": source.get("protocol_chunk_count"),
                "source_protocol_url": source.get("protocol_url"),
                "source_fit": source.get("source_fit"),
                "source_note": source.get("source_note"),
                "protocol_focus": task.get("protocol_focus"),
                "difficulty": task.get("difficulty"),
                "target_competency": task.get("target_competency"),
                "task_quality_score": task.get("task_quality_score"),
                "task_quality_accepted": task.get("task_quality_accepted"),
                "expected_sections": task.get("expected_sections") or [],
                "red_flags": task.get("red_flags") or [],
                "checklist_count": len(task.get("checklist") or []),
                "description_chars": len(str(task.get("description") or "")),
                "reference_node_count": len(graph.get("nodes") or []),
                "reference_edge_count": len(graph.get("edges") or []),
                "variant_count": len(case.get("variants") or []),
            }
        )
    return rows


def _cardiology_graph_result_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _graph_result_rows(_cardiology_payload(payload).get("graph") or {})


def _cardiology_reference_quality_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _graph_quality_rows(_cardiology_payload(payload).get("graph") or {})


def _cardiology_expert_item_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _expert_item_rows(_cardiology_payload(payload).get("expert") or {})


def _cardiology_expert_by_expert_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _cardiology_payload(payload).get("expert", {}).get("by_expert") or []


def _cardiology_expert_by_pattern_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _cardiology_payload(payload).get("expert", {}).get("by_expected_pattern") or []


def _cardiology_expert_rating_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _cardiology_payload(payload).get("expert_ratings") or []


def _cardiology_recommendation_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _cardiology_payload(payload).get("recommendations") or []


def _cardiology_pattern_summary_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _cardiology_payload(payload).get("pattern_summary") or []


def _cardiology_reference_audit_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if payload is None:
        validation_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {}
        payload = validation_payload.get("reference_audit") or {}
    if not isinstance(payload, dict):
        return []

    source_items = payload.get("items") or []
    recommended_actions: dict[str, str] = {}
    if not source_items and payload.get("reference_quality_items"):
        source_items = payload.get("reference_quality_items") or []
        recommended_actions = {
            str(item.get("case_id")): str(item.get("recommended_action") or "")
            for item in payload.get("cases") or []
        }

    rows: list[dict[str, Any]] = []
    for item in source_items:
        comments = item.get("expert_comments") or []
        comment_excerpt = ""
        if comments and isinstance(comments[0], dict):
            comment_excerpt = str(comments[0].get("comment") or "")[:600]
        rows.append(
            {
                "priority": item.get("priority") or ("high" if item.get("audit_required") else "low"),
                "audit_required": item.get("audit_required"),
                "case_id": item.get("case_id"),
                "case_title": item.get("case_title"),
                "expert_mean_score": item.get("expert_mean_score"),
                "expert_min_score": item.get("expert_min_score"),
                "expert_max_score": item.get("expert_max_score"),
                "expert_accept_rate": item.get("expert_accept_rate"),
                "rating_count": item.get("rating_count"),
                "model_score": item.get("model_score"),
                "model_minus_expert": (
                    item.get("model_minus_expert")
                    if item.get("model_minus_expert") is not None
                    else (
                        round(float(item.get("model_score")) - float(item.get("expert_mean_score")), 4)
                        if item.get("model_score") is not None
                        and item.get("expert_mean_score") is not None
                        else None
                    )
                ),
                "judge_quality_score": item.get("judge_quality_score"),
                "judge_accepted": item.get("judge_accepted"),
                "judge_critical_count": item.get("judge_critical_count"),
                "judge_warning_count": item.get("judge_warning_count"),
                "clinical_connectivity_gap": item.get("clinical_connectivity_gap"),
                "diagnostic_evidence_gap": item.get("diagnostic_evidence_gap"),
                "safety_penalty": item.get("safety_penalty"),
                "issue_tags": item.get("issue_tags") or [],
                "recommendation": item.get("recommendation")
                or recommended_actions.get(str(item.get("case_id"))),
                "comment_excerpt": comment_excerpt,
            }
        )
    return rows


def _normalize_flat_graph_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    metric_keys = [
        "edge_f1",
        "weighted_edge_f1",
        "node_coverage",
        "category_accuracy",
        "directed_path_completeness",
        "safety_penalty",
        "unsafe_extra_action",
        "missing_critical_action",
        "diagnostic_evidence_gap",
        "clinical_connectivity_gap",
        "composite_score",
    ]
    for row in results:
        if row.get("metrics"):
            normalized.append(row)
            continue
        metrics = {key: row.get(key) for key in metric_keys if key in row}
        normalized.append({**row, "metrics": metrics})
    return normalized


def _derive_baseline_comparison(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    existing = payload.get("baseline_comparison")
    if isinstance(existing, list) and existing:
        return existing

    expert_payload = payload.get("expert") if isinstance(payload.get("expert"), dict) else payload
    existing = expert_payload.get("baseline_comparison") if isinstance(expert_payload, dict) else None
    if isinstance(existing, list) and existing:
        return existing

    item_rows = (
        expert_payload.get("items")
        if isinstance(expert_payload, dict) and expert_payload.get("items")
        else payload.get("expert_items")
    )
    if not isinstance(item_rows, list) or not item_rows:
        return []

    graph_payload = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    results = graph_payload.get("results") or payload.get("results") or []
    if not isinstance(results, list) or not results:
        return []
    return baseline_comparison_rows({"graph": {"results": _normalize_flat_graph_results(results)}}, item_rows)


def _cardiology_baseline_comparison_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _derive_baseline_comparison(_cardiology_payload(payload))


def _expert_baseline_comparison_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("baseline_comparison")
    return rows if isinstance(rows, list) else []


def _cardiology_real_baseline_comparison_rows(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    payload = payload if payload is not None else (_read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {})
    return _derive_baseline_comparison(payload)


def _summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rag = summary.get("rag", {})
    rag_summary = rag.get("summary") or {}
    for key, value in (rag_summary.get("recall") or {}).items():
        rows.append({"system": "rag", "section": "recall", "metric": key, "value": value})
    for key in ("mrr", "section_hit_rate", "key_phrase_hit_rate"):
        rows.append({"system": "rag", "section": "quality", "metric": key, "value": rag_summary.get(key)})
    for key, value in (rag_summary.get("latency_ms") or {}).items():
        rows.append({"system": "rag", "section": "latency_ms", "metric": key, "value": value})

    graph = summary.get("graph", {})
    graph_summary = graph.get("summary") or {}
    rows.append(
        {
            "system": "graph",
            "section": "pattern",
            "metric": "pattern_pass_rate",
            "value": graph_summary.get("pattern_pass_rate"),
        }
    )
    for key, value in (graph_summary.get("averages") or {}).items():
        rows.append({"system": "graph", "section": "averages", "metric": key, "value": value})
    for key, value in (graph.get("reference_quality") or {}).items():
        rows.append({"system": "reference_graph", "section": "quality", "metric": key, "value": value})

    expert = summary.get("expert") or {}
    for key in ("item_count", "rating_count", "expert_count", "skipped_row_count"):
        rows.append({"system": "expert", "section": "coverage", "metric": key, "value": expert.get(key)})
    for key, value in (expert.get("correlation_with_mean_expert") or {}).items():
        rows.append({"system": "expert", "section": "correlation", "metric": key, "value": value})
    for key, value in (expert.get("inter_rater") or {}).items():
        if key != "pairs":
            rows.append({"system": "expert", "section": "inter_rater", "metric": key, "value": value})

    cardiology = summary.get("cardiology") or {}
    cardiology_summary = cardiology.get("summary") or {}
    for key, value in cardiology_summary.items():
        if isinstance(value, (dict, list)):
            continue
        rows.append({"system": "cardiology_synthetic", "section": "summary", "metric": key, "value": value})
    cardiology_reference_audit = cardiology.get("reference_audit") or {}
    for key, value in cardiology_reference_audit.items():
        if isinstance(value, (dict, list)):
            continue
        rows.append({"system": "cardiology_reference_audit", "section": "summary", "metric": key, "value": value})

    human_validation = summary.get("human_validation") or {}
    for stage in ("primary", "pilot"):
        stage_payload = human_validation.get(stage) or {}
        for key, value in (stage_payload.get("summary") or {}).items():
            if isinstance(value, (dict, list)):
                continue
            rows.append(
                {
                    "system": "human_expert_validation",
                    "section": stage,
                    "metric": key,
                    "value": value,
                }
            )

    return rows


RAG_RESULT_FIELDS = [
    "id",
    "mode",
    "query",
    "hit_rank",
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "miss",
    "section_hit_score",
    "key_phrase_hit_score",
    "latency_ms",
    "expected_protocol_ids",
    "retrieved_protocol_ids",
    "retrieved_sections",
    "expected_key_phrases",
    "top_protocol_id",
    "top_protocol_title",
    "top_section",
    "top_chunk_index",
    "top_preview",
    "sources",
]
RAG_ABLATION_FIELDS = [field for field in RAG_RESULT_FIELDS if field != "sources"]
GRAPH_RESULT_FIELDS = [
    "case_id",
    "variant_id",
    "expected_pattern",
    "pattern_passed",
    "pattern_reason",
    "latency_ms",
    "edge_f1",
    "weighted_edge_f1",
    "node_coverage",
    "category_accuracy",
    "directed_path_completeness",
    "safety_penalty",
    "unsafe_extra_action",
    "missing_critical_action",
    "diagnostic_evidence_gap",
    "clinical_connectivity_gap",
    "composite_score",
    "missing_edges_count",
    "incorrect_edges_count",
    "missing_nodes_count",
    "safety_findings",
    "algorithm_version",
]
GRAPH_QUALITY_FIELDS = [
    "case_id",
    "title",
    "schema_valid",
    "accepted",
    "quality_score",
    "warning_count",
    "critical_count",
    "has_diagnosis",
    "has_diagnostic_step",
    "has_start_to_diagnosis_path",
    "has_diagnosis_to_action_path",
    "warnings",
]
EXPERT_ITEM_FIELDS = [
    "case_id",
    "variant_id",
    "expected_pattern",
    "model_score",
    "expert_mean_score",
    "expert_score_std",
    "expert_rating_count",
    "score_gap_model_minus_expert",
]
CI_FIELDS = [
    "pearson_ci_low",
    "pearson_ci_high",
    "spearman_ci_low",
    "spearman_ci_high",
    "kendall_tau_a_ci_low",
    "kendall_tau_a_ci_high",
    "mae_ci_low",
    "mae_ci_high",
    "rmse_ci_low",
    "rmse_ci_high",
    "bias_ci_low",
    "bias_ci_high",
]
EXPERT_CORRELATION_FIELDS = [
    "expert_id",
    "expected_pattern",
    "n",
    "pearson",
    "spearman",
    "kendall_tau_a",
    "mean_model_score",
    "mean_expert_score",
    "mae",
    "rmse",
    "bias",
    *CI_FIELDS,
]
BASELINE_COMPARISON_FIELDS = [
    "model",
    "metric_source",
    "description",
    "n",
    "pearson",
    "pearson_ci_low",
    "pearson_ci_high",
    "spearman",
    "spearman_ci_low",
    "spearman_ci_high",
    "kendall_tau_a",
    "kendall_tau_a_ci_low",
    "kendall_tau_a_ci_high",
    "mean_model_score",
    "mean_expert_score",
    "mae",
    "mae_ci_low",
    "mae_ci_high",
    "rmse",
    "rmse_ci_low",
    "rmse_ci_high",
    "bias",
    "bias_ci_low",
    "bias_ci_high",
    "delta_spearman_vs_composite",
    "delta_mae_vs_composite",
]
PROBLEM_FIELDS = [
    "system",
    "severity",
    "item_id",
    "metric",
    "value",
    "threshold",
    "reason",
    "recommendation",
]
GENERATION_AUDIT_FIELDS = [
    "reference_graph_id",
    "title",
    "assignment_count",
    "assignment_titles",
    "assignment_quality_score",
    "assignment_warning_count",
    "assignment_warnings",
    "has_assignment_description",
    "min_assignment_description_chars",
    "avg_assignment_description_chars",
    "schema_valid",
    "accepted",
    "quality_score",
    "warning_count",
    "critical_count",
    "node_count",
    "edge_count",
    "has_diagnosis",
    "has_diagnostic_step",
    "has_start_to_diagnosis_path",
    "has_diagnosis_to_action_path",
    "warnings",
]
CARDIOLOGY_TASK_FIELDS = [
    "case_id",
    "title",
    "protocol_area",
    "source_protocol_id",
    "source_protocol_title",
    "source_protocol_year",
    "source_protocol_sections",
    "source_protocol_chunk_count",
    "source_protocol_url",
    "source_fit",
    "source_note",
    "protocol_focus",
    "difficulty",
    "target_competency",
    "task_quality_score",
    "task_quality_accepted",
    "expected_sections",
    "red_flags",
    "checklist_count",
    "description_chars",
    "reference_node_count",
    "reference_edge_count",
    "variant_count",
]
CARDIOLOGY_EXPERT_RATING_FIELDS = [
    "expert_id",
    "panel_mode",
    "specialty",
    "expert_status",
    "experience_years",
    "country_region",
    "organization_type",
    "evaluation_scale",
    "case_id",
    "variant_id",
    "expected_pattern",
    "model_score",
    "expert_score",
    "expert_score_0_100",
    "confidence",
    "expert_comment",
]
CARDIOLOGY_PATTERN_SUMMARY_FIELDS = [
    "expected_pattern",
    "n",
    "mean_model_score",
    "mean_expert_score",
    "mean_gap_model_minus_expert",
    "pattern_pass_rate",
]
CARDIOLOGY_RECOMMENDATION_FIELDS = [
    "case_id",
    "variant_id",
    "expected_pattern",
    "model_score",
    "expert_mean_score",
    "score_gap_model_minus_expert",
    "system_recommendation",
    "missing_edges_count",
    "incorrect_edges_count",
    "missing_nodes_count",
    "safety_findings",
]
CARDIOLOGY_REFERENCE_AUDIT_FIELDS = [
    "priority",
    "audit_required",
    "case_id",
    "case_title",
    "expert_mean_score",
    "expert_min_score",
    "expert_max_score",
    "expert_accept_rate",
    "rating_count",
    "model_score",
    "model_minus_expert",
    "judge_quality_score",
    "judge_accepted",
    "judge_critical_count",
    "judge_warning_count",
    "clinical_connectivity_gap",
    "diagnostic_evidence_gap",
    "safety_penalty",
    "issue_tags",
    "recommendation",
    "comment_excerpt",
]
HISTORY_FIELDS = [
    "run_id",
    "generated_at",
    "run_type",
    "status",
    "rag_recall_at_1",
    "rag_recall_at_5",
    "rag_mrr",
    "rag_p95_latency_ms",
    "graph_pattern_pass_rate",
    "graph_composite_score",
    "graph_safety_penalty",
    "reference_accepted_rate",
    "expert_pearson",
    "expert_spearman",
    "cardiology_pattern_pass_rate",
    "cardiology_expert_spearman",
    "cardiology_expert_mae",
    "cardiology_reference_audit_required",
    "cardiology_reference_audit_high_priority",
    "metadata",
]


def _problem(
    system: str,
    severity: str,
    item_id: str,
    metric: str,
    value: Any,
    threshold: Any,
    reason: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "system": system,
        "severity": severity,
        "item_id": item_id,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "reason": reason,
        "recommendation": recommendation,
    }


def _judge_assignments(assignments: list[Assignment], reference_title: str | None) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    descriptions = [(assignment.description or "").strip() for assignment in assignments]
    titles = [(assignment.title or "").strip() for assignment in assignments]
    description_lengths = [len(description) for description in descriptions if description]
    has_description = bool(description_lengths)

    if not assignments:
        warnings.append(
            {
                "code": "assignment_missing",
                "severity": "critical",
                "message": "Reference graph is not linked to any assignment.",
            }
        )
    if assignments and not has_description:
        warnings.append(
            {
                "code": "assignment_description_missing",
                "severity": "warning",
                "message": "Linked assignments have no student-facing description.",
            }
        )
    if description_lengths and min(description_lengths) < 80:
        warnings.append(
            {
                "code": "assignment_description_too_short",
                "severity": "warning",
                "message": "At least one assignment description is too short for a clinical scenario.",
            }
        )
    if reference_title:
        ref_title = reference_title.strip().casefold()
        mismatched = [title for title in titles if title and ref_title and title.casefold() != ref_title]
        if mismatched:
            warnings.append(
                {
                    "code": "assignment_reference_title_mismatch",
                    "severity": "info",
                    "message": "Assignment title differs from linked reference graph title.",
                }
            )

    critical_count = sum(1 for warning in warnings if warning.get("severity") == "critical")
    warning_count = len(warnings)
    penalty = 0.35 * critical_count + 0.12 * (warning_count - critical_count)
    quality_score = max(0.0, round(1.0 - penalty, 4))
    return {
        "assignment_quality_score": quality_score,
        "assignment_warning_count": warning_count,
        "assignment_warnings": warnings,
        "has_assignment_description": has_description,
        "min_assignment_description_chars": min(description_lengths) if description_lengths else 0,
        "avg_assignment_description_chars": (
            round(sum(description_lengths) / len(description_lengths), 2)
            if description_lengths
            else 0
        ),
    }


def _problem_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rag_payload = _read_json_if_exists(RAG_LATEST) or {}
    rag_summary = rag_payload.get("rag", {}).get("summary", {}) if isinstance(rag_payload, dict) else {}
    rag_p95 = rag_summary.get("latency_ms", {}).get("p95")
    for item in _rag_result_rows(rag_payload):
        item_id = str(item.get("id") or "")
        if item.get("miss"):
            rows.append(
                _problem(
                    "rag",
                    "critical",
                    item_id,
                    "hit_rank",
                    "miss",
                    "hit_rank is not null",
                    "RAG did not retrieve an expected protocol.",
                    "Add lexical synonyms/key phrases or inspect protocol chunk quality for this query.",
                )
            )
        if float(item.get("section_hit_score") or 0.0) < 0.8:
            rows.append(
                _problem(
                    "rag",
                    "warning",
                    item_id,
                    "section_hit_score",
                    item.get("section_hit_score"),
                    ">=0.8",
                    "Retrieved chunks miss expected clinical sections.",
                    "Improve section-aware reranking and chunk section metadata.",
                )
            )
        if float(item.get("key_phrase_hit_score") or 0.0) < 0.8:
            rows.append(
                _problem(
                    "rag",
                    "warning",
                    item_id,
                    "key_phrase_hit_score",
                    item.get("key_phrase_hit_score"),
                    ">=0.8",
                    "Retrieved context misses expected key phrases.",
                    "Review query seed phrases and protocol chunk normalization.",
                )
            )
        if rag_p95 is not None and float(item.get("latency_ms") or 0.0) > float(rag_p95):
            rows.append(
                _problem(
                    "rag",
                    "info",
                    item_id,
                    "latency_ms",
                    item.get("latency_ms"),
                    f"<=p95({rag_p95})",
                    "Query is in the slow tail of RAG retrieval.",
                    "Inspect candidate count, reranking cost, and DB/vector indexes for this query pattern.",
                )
            )

    for item in _graph_result_rows(_read_json_if_exists(GRAPH_LATEST) or {}):
        item_id = f"{item.get('case_id')}::{item.get('variant_id')}"
        if item.get("pattern_passed") is False:
            rows.append(
                _problem(
                    "graph",
                    "critical",
                    item_id,
                    "pattern_passed",
                    item.get("pattern_passed"),
                    "true",
                    "Expected benchmark assertion did not pass.",
                    "Inspect evaluator logic for this error pattern and compare with expert judgement.",
                )
            )
        if float(item.get("composite_score") or 0.0) < 0.55:
            rows.append(
                _problem(
                    "graph",
                    "warning",
                    item_id,
                    "composite_score",
                    item.get("composite_score"),
                    ">=0.55",
                    "Very low graph score; this case may dominate aggregate averages.",
                    "Check whether the penalty is clinically justified and explain it in reporting.",
                )
            )
        if float(item.get("safety_penalty") or 0.0) > 0.0:
            rows.append(
                _problem(
                    "graph",
                    "warning",
                    item_id,
                    "safety_penalty",
                    item.get("safety_penalty"),
                    "0",
                    "Unsafe or missing critical action was detected.",
                    "Use this case in the article as safety-sensitive grading evidence.",
                )
            )
        if float(item.get("directed_path_completeness") or 0.0) < 0.25:
            rows.append(
                _problem(
                    "graph",
                    "warning",
                    item_id,
                    "directed_path_completeness",
                    item.get("directed_path_completeness"),
                    ">=0.25",
                    "Clinical reasoning chain is broken.",
                    "Inspect missing edges from patient data to diagnosis/action.",
                )
            )

    for item in _graph_quality_rows(_read_json_if_exists(GRAPH_LATEST) or {}):
        item_id = str(item.get("case_id") or "")
        if not item.get("accepted"):
            rows.append(
                _problem(
                    "reference_graph",
                    "critical",
                    item_id,
                    "accepted",
                    item.get("accepted"),
                    "true",
                    "Reference graph judge rejected this graph.",
                    "Revise graph before using it as a defensible expert benchmark.",
                )
            )
        elif int(item.get("warning_count") or 0) > 0:
            rows.append(
                _problem(
                    "reference_graph",
                    "warning",
                    item_id,
                    "warning_count",
                    item.get("warning_count"),
                    "0",
                    "Reference graph has pedagogical/clinical warnings.",
                    "Review warnings and decide whether to keep, revise, or document the limitation.",
                )
            )

    expert_payload = _read_json_if_exists(EXPERT_CORRELATION_LATEST) or {}
    for item in _expert_item_rows(expert_payload):
        gap = item.get("score_gap_model_minus_expert")
        if gap is not None and abs(float(gap)) >= 0.15:
            rows.append(
                _problem(
                    "expert",
                    "warning",
                    f"{item.get('case_id')}::{item.get('variant_id')}",
                    "score_gap_model_minus_expert",
                    gap,
                    "<0.15 absolute",
                    "Algorithm and expert score diverge.",
                    "Use this item for metric calibration or qualitative error analysis.",
                )
            )
    for item in expert_payload.get("skipped_rows") or []:
        rows.append(
            _problem(
                "expert",
                "info",
                f"csv_row_{item.get('row')}",
                "skipped_row",
                item.get("reason"),
                "valid rating row",
                "Expert CSV row was skipped.",
                "Check filled CSV format and review_item_id mapping.",
            )
        )

    generation_payload = _read_json_if_exists(GENERATION_AUDIT_JSON) or {}
    for item in generation_payload.get("items", []) or []:
        item_id = str(item.get("reference_graph_id") or "")
        if not item.get("accepted"):
            rows.append(
                _problem(
                    "generation",
                    "critical",
                    item_id,
                    "accepted",
                    item.get("accepted"),
                    "true",
                    "Stored generated/reference graph is not accepted by judge.",
                    "Regenerate or manually revise this task before using it in teaching/evaluation.",
                )
            )
        elif int(item.get("warning_count") or 0) > 0:
            rows.append(
                _problem(
                    "generation",
                    "warning",
                    item_id,
                    "warning_count",
                    item.get("warning_count"),
                    "0",
                    "Stored graph has judge warnings.",
                    "Review task quality and warning reasons with a teacher.",
                )
            )
        if int(item.get("assignment_warning_count") or 0) > 0:
            severity = "critical" if any(
                warning.get("severity") == "critical"
                for warning in item.get("assignment_warnings", []) or []
                if isinstance(warning, dict)
            ) else "warning"
            rows.append(
                _problem(
                    "generation",
                    severity,
                    item_id,
                    "assignment_warning_count",
                    item.get("assignment_warning_count"),
                    "0",
                    "Linked assignment has quality warnings.",
                    "Revise the student-facing clinical scenario before using this task in a benchmark.",
                )
            )

    cardiology_payload = _read_json_if_exists(CARDIOLOGY_LATEST) or {}
    cardiology = _cardiology_payload(cardiology_payload)
    cardiology_summary = cardiology.get("summary") or {}
    if cardiology_summary:
        if float(cardiology_summary.get("pattern_pass_rate") or 0.0) < 0.9:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "warning",
                    "summary",
                    "pattern_pass_rate",
                    cardiology_summary.get("pattern_pass_rate"),
                    ">=0.9",
                    "At least one cardiology error pattern is not captured strongly enough by the evaluator.",
                    "Use failed patterns for metric calibration and report them as controlled weak points.",
                )
            )
        if float(cardiology_summary.get("expert_spearman") or 0.0) < 0.8:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "warning",
                    "summary",
                    "expert_spearman",
                    cardiology_summary.get("expert_spearman"),
                    ">=0.8",
                    "Synthetic proxy-rater agreement is lower than the target threshold.",
                    "Inspect by-pattern gaps and adjust safety/path weights before real expert validation.",
                )
            )

    for item in _cardiology_task_rows(cardiology_payload):
        if float(item.get("task_quality_score") or 0.0) < 0.85:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "critical",
                    str(item.get("case_id") or ""),
                    "task_quality_score",
                    item.get("task_quality_score"),
                    ">=0.85",
                    "Synthetic cardiology task lacks required pedagogical fields.",
                    "Revise the task description, expected sections, checklist, and red flags.",
                )
            )
    for item in _cardiology_reference_quality_rows(cardiology_payload):
        if not item.get("accepted"):
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "critical",
                    str(item.get("case_id") or ""),
                    "reference_accepted",
                    item.get("accepted"),
                    "true",
                    "Synthetic cardiology reference graph was rejected by graph judge.",
                    "Fix the reference before using this case in the article benchmark.",
                )
            )
    for item in _cardiology_graph_result_rows(cardiology_payload):
        item_id = f"{item.get('case_id')}::{item.get('variant_id')}"
        if item.get("pattern_passed") is False:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "warning",
                    item_id,
                    "pattern_passed",
                    item.get("pattern_passed"),
                    "true",
                    "Cardiology synthetic assertion did not pass.",
                    "Inspect this variant as evidence for evaluator calibration.",
                )
            )
        if float(item.get("safety_penalty") or 0.0) > 0.0:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "info",
                    item_id,
                    "safety_penalty",
                    item.get("safety_penalty"),
                    "0",
                    "Safety-sensitive finding was triggered in cardiology control set.",
                    "Use this row to illustrate patient-safety behavior of the metric.",
                )
            )
    for item in _cardiology_recommendation_rows(cardiology_payload):
        gap = item.get("score_gap_model_minus_expert")
        if gap is not None and abs(float(gap)) >= 0.2:
            rows.append(
                _problem(
                    "cardiology_synthetic",
                    "warning",
                    f"{item.get('case_id')}::{item.get('variant_id')}",
                    "score_gap_model_minus_expert",
                    gap,
                    "<0.2 absolute",
                    "Synthetic proxy raters and the automatic score diverge substantially.",
                    "Use this case for calibration of path and safety weights.",
                )
            )

    human_validation_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {}
    for item in _cardiology_reference_audit_rows(
        human_validation_payload.get("reference_audit") or {}
    ):
        if not item.get("audit_required"):
            continue
        priority = str(item.get("priority") or "medium")
        severity = "critical" if priority == "high" else ("warning" if priority == "medium" else "info")
        rows.append(
            _problem(
                "cardiology_reference_audit",
                severity,
                str(item.get("case_id") or ""),
                "reference_expert_score",
                item.get("expert_mean_score"),
                ">=0.85",
                "Expert cardiologist ratings indicate that this reference graph is not ready as a final teaching standard.",
                item.get("recommendation") or "Revise the reference graph before the next expert-validation round.",
            )
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(rows, key=lambda row: (severity_rank.get(str(row["severity"]), 9), row["system"], row["item_id"]))


def _current_history_metrics() -> dict[str, Any]:
    summary = _summary_payload()
    rag_summary = summary.get("rag", {}).get("summary") or {}
    graph_summary = summary.get("graph", {}).get("summary") or {}
    graph_avg = graph_summary.get("averages") or {}
    ref_quality = summary.get("graph", {}).get("reference_quality") or {}
    expert = summary.get("expert") or {}
    corr = expert.get("correlation_with_mean_expert") or {}
    cardiology = summary.get("cardiology", {}).get("summary") or {}
    reference_audit = summary.get("cardiology", {}).get("reference_audit") or {}
    return {
        "rag_recall_at_1": rag_summary.get("recall", {}).get("recall_at_1"),
        "rag_recall_at_5": rag_summary.get("recall", {}).get("recall_at_5"),
        "rag_mrr": rag_summary.get("mrr"),
        "rag_p95_latency_ms": rag_summary.get("latency_ms", {}).get("p95"),
        "graph_pattern_pass_rate": graph_summary.get("pattern_pass_rate"),
        "graph_composite_score": graph_avg.get("composite_score"),
        "graph_safety_penalty": graph_avg.get("safety_penalty"),
        "reference_accepted_rate": ref_quality.get("accepted_rate"),
        "expert_pearson": corr.get("pearson"),
        "expert_spearman": corr.get("spearman"),
        "cardiology_pattern_pass_rate": cardiology.get("pattern_pass_rate"),
        "cardiology_expert_spearman": cardiology.get("expert_spearman"),
        "cardiology_expert_mae": cardiology.get("expert_mae"),
        "cardiology_reference_audit_required": reference_audit.get("audit_required_count"),
        "cardiology_reference_audit_high_priority": reference_audit.get("high_priority_count"),
    }


def _history_rows() -> list[dict[str, Any]]:
    history = _read_json_if_exists(HISTORY_JSON)
    return history if isinstance(history, list) else []


def _append_history(run_type: str, *, status: str = "completed", metadata: dict[str, Any] | None = None) -> None:
    history = _history_rows()
    generated_at = _generated_at()
    row = {
        "run_id": f"{generated_at}_{run_type}",
        "generated_at": generated_at,
        "run_type": run_type,
        "status": status,
        **_current_history_metrics(),
        "metadata": metadata or {},
    }
    history.append(row)
    _write_json(HISTORY_JSON, history[-200:])


def _report_tables() -> list[tuple[str, list[dict[str, Any]], list[str]]]:
    expert_payload = _read_json_if_exists(EXPERT_CORRELATION_LATEST) or {}
    generation_payload = _read_json_if_exists(GENERATION_AUDIT_JSON) or {}
    cardiology_payload = _read_json_if_exists(CARDIOLOGY_LATEST) or {}
    cardiology_real_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {}
    cardiology_real_pilot_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION_PILOT) or {}
    human_rating_rows = _read_csv_if_exists(CARDIOLOGY_REAL_RATINGS_CSV)
    protocol_grounding_rows = _read_csv_if_exists(CARDIOLOGY_PROTOCOL_GROUNDING_CSV)
    human_rating_fields = [
        "expert_id",
        "case_id",
        "variant_id",
        "expected_pattern",
        "model_score",
        "expert_score_0_100",
        "expert_accept",
        "expert_comment",
    ]
    protocol_grounding_fields = list(protocol_grounding_rows[0]) if protocol_grounding_rows else []
    return [
        ("Summary", _summary_rows(_summary_payload()), ["system", "section", "metric", "value"]),
        ("Problems", _problem_rows(), PROBLEM_FIELDS),
        ("RAG Results", _rag_result_rows(_read_json_if_exists(RAG_LATEST) or {}), RAG_RESULT_FIELDS),
        ("RAG Ablation", _rag_ablation_rows(_read_json_if_exists(RAG_ABLATION_LATEST) or {}), RAG_ABLATION_FIELDS),
        ("Graph Results", _graph_result_rows(_read_json_if_exists(GRAPH_LATEST) or {}), GRAPH_RESULT_FIELDS),
        ("Reference Quality", _graph_quality_rows(_read_json_if_exists(GRAPH_LATEST) or {}), GRAPH_QUALITY_FIELDS),
        ("Protocol Grounding", protocol_grounding_rows, protocol_grounding_fields),
        ("Synthetic Cardiology Tasks", _cardiology_task_rows(cardiology_payload), CARDIOLOGY_TASK_FIELDS),
        ("Synthetic Cardiology Results", _cardiology_graph_result_rows(cardiology_payload), GRAPH_RESULT_FIELDS),
        ("Synthetic Ref Quality", _cardiology_reference_quality_rows(cardiology_payload), GRAPH_QUALITY_FIELDS),
        ("Synthetic Expert Items", _cardiology_expert_item_rows(cardiology_payload), EXPERT_ITEM_FIELDS),
        ("Synthetic By Expert", _cardiology_expert_by_expert_rows(cardiology_payload), [field for field in EXPERT_CORRELATION_FIELDS if field != "expected_pattern"]),
        ("Synthetic By Pattern", _cardiology_expert_by_pattern_rows(cardiology_payload), [field for field in EXPERT_CORRELATION_FIELDS if field != "expert_id"]),
        ("Synthetic Pattern Summary", _cardiology_pattern_summary_rows(cardiology_payload), CARDIOLOGY_PATTERN_SUMMARY_FIELDS),
        ("Synthetic Baselines", _cardiology_baseline_comparison_rows(cardiology_payload), BASELINE_COMPARISON_FIELDS),
        ("Synthetic Ratings", _cardiology_expert_rating_rows(cardiology_payload), CARDIOLOGY_EXPERT_RATING_FIELDS),
        ("Synthetic Recommendations", _cardiology_recommendation_rows(cardiology_payload), CARDIOLOGY_RECOMMENDATION_FIELDS),
        (
            "Human Primary Items",
            _expert_item_rows({"items": cardiology_real_payload.get("expert_items") or []}),
            EXPERT_ITEM_FIELDS,
        ),
        ("Human Primary Experts", cardiology_real_payload.get("by_expert") or [], [field for field in EXPERT_CORRELATION_FIELDS if field != "expected_pattern"]),
        ("Human Primary Patterns", cardiology_real_payload.get("by_expected_pattern") or [], [field for field in EXPERT_CORRELATION_FIELDS if field != "expert_id"]),
        ("Human Primary Baselines", _cardiology_real_baseline_comparison_rows(cardiology_real_payload), BASELINE_COMPARISON_FIELDS),
        ("Human Primary Ratings", human_rating_rows, human_rating_fields),
        ("Human Primary Ref Audit", _cardiology_reference_audit_rows(cardiology_real_payload.get("reference_audit") or {}), CARDIOLOGY_REFERENCE_AUDIT_FIELDS),
        ("Human Pilot Baselines", _cardiology_real_baseline_comparison_rows(cardiology_real_pilot_payload), BASELINE_COMPARISON_FIELDS),
        ("Expert Items", _expert_item_rows(expert_payload), EXPERT_ITEM_FIELDS),
        ("Expert By Expert", expert_payload.get("by_expert") or [], EXPERT_CORRELATION_FIELDS),
        ("Expert By Pattern", expert_payload.get("by_expected_pattern") or [], EXPERT_CORRELATION_FIELDS),
        ("Expert Baselines", _expert_baseline_comparison_rows(expert_payload), BASELINE_COMPARISON_FIELDS),
        ("Expert Skipped", expert_payload.get("skipped_rows") or [], ["row", "reason"]),
        ("Generation Audit", generation_payload.get("items") or [], GENERATION_AUDIT_FIELDS),
        ("History", _history_rows(), HISTORY_FIELDS),
    ]


def _refresh_csv_artifacts() -> list[Path]:
    generated: list[Path] = []

    if RAG_SEED.exists():
        _write_csv(
            RAG_SEED_CSV,
            _rag_seed_rows(_read_json(RAG_SEED)),
            [
                "id",
                "query",
                "expected_protocol_ids",
                "expected_sections",
                "expected_key_phrases",
                "limit",
                "source",
                "requires_expert_review",
                "protocol_title",
                "chunk_count",
            ],
        )
        generated.append(RAG_SEED_CSV)

    if RAG_LATEST.exists():
        rag_rows = _rag_result_rows(_read_json(RAG_LATEST))
        _write_csv(RAG_RESULTS_CSV, rag_rows, RAG_RESULT_FIELDS)
        _write_csv(RAG_MISSES_CSV, [row for row in rag_rows if row.get("miss")], RAG_RESULT_FIELDS)
        generated.extend([RAG_RESULTS_CSV, RAG_MISSES_CSV])

    if RAG_ABLATION_LATEST.exists():
        _write_csv(
            RAG_ABLATION_CSV,
            _rag_ablation_rows(_read_json(RAG_ABLATION_LATEST)),
            RAG_ABLATION_FIELDS,
        )
        generated.append(RAG_ABLATION_CSV)

    if GRAPH_SEED.exists():
        _write_csv(
            GRAPH_SEED_CSV,
            _graph_seed_rows(_read_json(GRAPH_SEED)),
            [
                "case_id",
                "title",
                "source",
                "requires_expert_review",
                "node_count",
                "edge_count",
                "variant_count",
                "error_taxonomy",
                "variants",
            ],
        )
        generated.append(GRAPH_SEED_CSV)

    if GRAPH_LATEST.exists():
        _write_csv(
            GRAPH_RESULTS_CSV,
            _graph_result_rows(_read_json(GRAPH_LATEST)),
            GRAPH_RESULT_FIELDS,
        )
        _write_csv(
            GRAPH_REFERENCE_QUALITY_CSV,
            _graph_quality_rows(_read_json(GRAPH_LATEST)),
            GRAPH_QUALITY_FIELDS,
        )
        generated.extend([GRAPH_RESULTS_CSV, GRAPH_REFERENCE_QUALITY_CSV])

    if CARDIOLOGY_LATEST.exists():
        cardiology_payload = _read_json(CARDIOLOGY_LATEST)
        _write_csv(CARDIOLOGY_TASKS_CSV, _cardiology_task_rows(cardiology_payload), CARDIOLOGY_TASK_FIELDS)
        _write_csv(CARDIOLOGY_RESULTS_CSV, _cardiology_graph_result_rows(cardiology_payload), GRAPH_RESULT_FIELDS)
        _write_csv(
            CARDIOLOGY_REFERENCE_QUALITY_CSV,
            _cardiology_reference_quality_rows(cardiology_payload),
            GRAPH_QUALITY_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_EXPERT_RATINGS_CSV,
            _cardiology_expert_rating_rows(cardiology_payload),
            CARDIOLOGY_EXPERT_RATING_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_EXPERT_ITEMS_CSV,
            _cardiology_expert_item_rows(cardiology_payload),
            EXPERT_ITEM_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_EXPERT_BY_EXPERT_CSV,
            _cardiology_expert_by_expert_rows(cardiology_payload),
            [field for field in EXPERT_CORRELATION_FIELDS if field != "expected_pattern"],
        )
        _write_csv(
            CARDIOLOGY_EXPERT_BY_PATTERN_CSV,
            _cardiology_expert_by_pattern_rows(cardiology_payload),
            [field for field in EXPERT_CORRELATION_FIELDS if field != "expert_id"],
        )
        _write_csv(
            CARDIOLOGY_PATTERN_SUMMARY_CSV,
            _cardiology_pattern_summary_rows(cardiology_payload),
            CARDIOLOGY_PATTERN_SUMMARY_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_BASELINE_COMPARISON_CSV,
            _cardiology_baseline_comparison_rows(cardiology_payload),
            BASELINE_COMPARISON_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_RECOMMENDATIONS_CSV,
            _cardiology_recommendation_rows(cardiology_payload),
            CARDIOLOGY_RECOMMENDATION_FIELDS,
        )
        generated.extend(
            [
                CARDIOLOGY_TASKS_CSV,
                CARDIOLOGY_RESULTS_CSV,
                CARDIOLOGY_REFERENCE_QUALITY_CSV,
                CARDIOLOGY_EXPERT_RATINGS_CSV,
                CARDIOLOGY_EXPERT_ITEMS_CSV,
                CARDIOLOGY_EXPERT_BY_EXPERT_CSV,
                CARDIOLOGY_EXPERT_BY_PATTERN_CSV,
                CARDIOLOGY_PATTERN_SUMMARY_CSV,
                CARDIOLOGY_BASELINE_COMPARISON_CSV,
                CARDIOLOGY_RECOMMENDATIONS_CSV,
            ]
        )

    if CARDIOLOGY_REAL_VALIDATION.exists():
        cardiology_real_payload = _read_json(CARDIOLOGY_REAL_VALIDATION)
        _write_csv(
            CARDIOLOGY_REAL_BASELINE_COMPARISON_CSV,
            _cardiology_real_baseline_comparison_rows(cardiology_real_payload),
            BASELINE_COMPARISON_FIELDS,
        )
        _write_csv(
            CARDIOLOGY_REAL_REFERENCE_AUDIT_CSV,
            _cardiology_reference_audit_rows(cardiology_real_payload.get("reference_audit") or {}),
            CARDIOLOGY_REFERENCE_AUDIT_FIELDS,
        )
        generated.extend(
            [CARDIOLOGY_REAL_BASELINE_COMPARISON_CSV, CARDIOLOGY_REAL_REFERENCE_AUDIT_CSV]
        )

    if EXPERT_CORRELATION_LATEST.exists():
        expert = _read_json(EXPERT_CORRELATION_LATEST)
        _write_csv(
            EXPERT_ITEMS_CSV,
            _expert_item_rows(expert),
            EXPERT_ITEM_FIELDS,
        )
        _write_csv(
            EXPERT_BY_EXPERT_CSV,
            expert.get("by_expert") or [],
            [field for field in EXPERT_CORRELATION_FIELDS if field != "expected_pattern"],
        )
        _write_csv(
            EXPERT_BY_PATTERN_CSV,
            expert.get("by_expected_pattern") or [],
            [field for field in EXPERT_CORRELATION_FIELDS if field != "expert_id"],
        )
        _write_csv(
            EXPERT_BASELINE_COMPARISON_CSV,
            _expert_baseline_comparison_rows(expert),
            BASELINE_COMPARISON_FIELDS,
        )
        _write_csv(EXPERT_SKIPPED_ROWS_CSV, expert.get("skipped_rows") or [], ["row", "reason"])
        generated.extend(
            [
                EXPERT_ITEMS_CSV,
                EXPERT_BY_EXPERT_CSV,
                EXPERT_BY_PATTERN_CSV,
                EXPERT_BASELINE_COMPARISON_CSV,
                EXPERT_SKIPPED_ROWS_CSV,
            ]
        )

    if GENERATION_AUDIT_JSON.exists():
        generation = _read_json(GENERATION_AUDIT_JSON)
        _write_csv(GENERATION_AUDIT_CSV, generation.get("items") or [], GENERATION_AUDIT_FIELDS)
        generated.append(GENERATION_AUDIT_CSV)

    _write_csv(PROBLEMS_CSV, _problem_rows(), PROBLEM_FIELDS)
    generated.append(PROBLEMS_CSV)

    _write_csv(HISTORY_CSV, _history_rows(), HISTORY_FIELDS)
    generated.append(HISTORY_CSV)

    _write_csv(SUMMARY_CSV, _summary_rows(_summary_payload()), ["system", "section", "metric", "value"])
    generated.append(SUMMARY_CSV)

    _write_xlsx(XLSX_REPORT, _report_tables())
    generated.append(XLSX_REPORT)
    return generated


@router.get("/summary")
async def get_benchmark_summary() -> dict[str, Any]:
    return _summary_payload()


@router.get("/details")
async def get_benchmark_details() -> dict[str, Any]:
    rag_rows = _rag_result_rows(_read_json_if_exists(RAG_LATEST) or {})
    graph_payload = _read_json_if_exists(GRAPH_LATEST) or {}
    cardiology_payload = _read_json_if_exists(CARDIOLOGY_LATEST) or {}
    cardiology_real_payload = _read_json_if_exists(CARDIOLOGY_REAL_VALIDATION) or {}
    expert_payload = _read_json_if_exists(EXPERT_CORRELATION_LATEST) or {}
    generation_payload = _read_json_if_exists(GENERATION_AUDIT_JSON) or {}
    return {
        "rag": {
            "results": rag_rows,
            "misses": [row for row in rag_rows if row.get("miss")],
            "ablation_results": _rag_ablation_rows(_read_json_if_exists(RAG_ABLATION_LATEST) or {}),
        },
        "graph": {
            "results": _graph_result_rows(graph_payload),
            "reference_quality": _graph_quality_rows(graph_payload),
        },
        "cardiology": {
            "tasks": _cardiology_task_rows(cardiology_payload),
            "results": _cardiology_graph_result_rows(cardiology_payload),
            "reference_quality": _cardiology_reference_quality_rows(cardiology_payload),
            "expert_ratings": _cardiology_expert_rating_rows(cardiology_payload),
            "expert_items": _cardiology_expert_item_rows(cardiology_payload),
            "expert_by_expert": _cardiology_expert_by_expert_rows(cardiology_payload),
            "expert_by_pattern": _cardiology_expert_by_pattern_rows(cardiology_payload),
            "pattern_summary": _cardiology_pattern_summary_rows(cardiology_payload),
            "baseline_comparison": _cardiology_baseline_comparison_rows(cardiology_payload),
            "real_baseline_comparison": _cardiology_real_baseline_comparison_rows(cardiology_real_payload),
            "real_validation_summary": cardiology_real_payload.get("summary") or {},
            "real_expert_items": cardiology_real_payload.get("expert_items") or [],
            "real_by_expert": cardiology_real_payload.get("by_expert") or [],
            "real_by_pattern": cardiology_real_payload.get("by_expected_pattern") or [],
            "recommendations": _cardiology_recommendation_rows(cardiology_payload),
            "reference_audit": _cardiology_reference_audit_rows(
                cardiology_real_payload.get("reference_audit") or {}
            ),
        },
        "expert": {
            "items": _expert_item_rows(expert_payload),
            "by_expert": expert_payload.get("by_expert") or [],
            "by_expected_pattern": expert_payload.get("by_expected_pattern") or [],
            "baseline_comparison": _expert_baseline_comparison_rows(expert_payload),
            "skipped_rows": expert_payload.get("skipped_rows") or [],
            "inter_rater_pairs": expert_payload.get("inter_rater", {}).get("pairs") or [],
        },
        "generation": generation_payload,
        "problems": _problem_rows(),
        "history": _history_rows(),
    }


@router.get("/files/{filename}")
async def download_benchmark_artifact(filename: str) -> FileResponse:
    return FileResponse(path=_artifact_path(filename), filename=filename)


@router.get("/problems")
async def get_benchmark_problems() -> dict[str, Any]:
    rows = _problem_rows()
    return {
        "items": rows,
        "summary": {
            "total": len(rows),
            "critical": sum(1 for row in rows if row.get("severity") == "critical"),
            "warning": sum(1 for row in rows if row.get("severity") == "warning"),
            "info": sum(1 for row in rows if row.get("severity") == "info"),
        },
    }


@router.get("/history")
async def get_benchmark_history() -> dict[str, Any]:
    rows = _history_rows()
    return {"items": rows, "summary": {"total": len(rows)}}


@router.post("/tables/export")
async def export_benchmark_tables() -> dict[str, Any]:
    generated = _refresh_csv_artifacts()
    _append_history("tables_export", metadata={"artifacts": [path.name for path in generated]})
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/generation/audit")
async def audit_generated_reference_graphs(req: GenerationAuditRequest, db: DbSession) -> dict[str, Any]:
    result = await db.execute(
        select(ReferenceGraph)
        .order_by(ReferenceGraph.id.desc())
        .limit(req.limit)
    )
    refs = list(result.scalars().all())
    ref_ids = [int(ref.id) for ref in refs]
    assignments_by_ref: dict[int, list[Assignment]] = {ref_id: [] for ref_id in ref_ids}
    if ref_ids:
        assignment_result = await db.execute(
            select(Assignment).where(Assignment.reference_graph_id.in_(ref_ids))
        )
        for assignment in assignment_result.scalars().all():
            assignments_by_ref.setdefault(int(assignment.reference_graph_id), []).append(assignment)

    rows: list[dict[str, Any]] = []
    for ref in refs:
        graph_payload = ref.graph_data if isinstance(ref.graph_data, dict) else {}
        assignments = assignments_by_ref.get(int(ref.id), [])
        assignment_quality = _judge_assignments(assignments, ref.title)
        base = {
            "reference_graph_id": int(ref.id),
            "title": ref.title,
            "assignment_count": len(assignments),
            "assignment_titles": [assignment.title for assignment in assignments],
            **assignment_quality,
            "node_count": len(graph_payload.get("nodes") or []),
            "edge_count": len(graph_payload.get("edges") or []),
        }
        try:
            graph = GraphSchema.model_validate(graph_payload)
            quality = judge_reference_graph(graph)
            rows.append(
                {
                    **base,
                    "schema_valid": quality.get("schema_valid"),
                    "accepted": quality.get("accepted"),
                    "quality_score": quality.get("quality_score"),
                    "warning_count": quality.get("warning_count"),
                    "critical_count": quality.get("critical_count"),
                    "has_diagnosis": quality.get("has_diagnosis"),
                    "has_diagnostic_step": quality.get("has_diagnostic_step"),
                    "has_start_to_diagnosis_path": quality.get("has_start_to_diagnosis_path"),
                    "has_diagnosis_to_action_path": quality.get("has_diagnosis_to_action_path"),
                    "warnings": quality.get("warnings") or [],
                }
            )
        except Exception as exc:
            rows.append(
                {
                    **base,
                    "schema_valid": False,
                    "accepted": False,
                    "quality_score": 0.0,
                    "warning_count": 1,
                    "critical_count": 1,
                    "has_diagnosis": False,
                    "has_diagnostic_step": False,
                    "has_start_to_diagnosis_path": False,
                    "has_diagnosis_to_action_path": False,
                    "warnings": [{"code": "schema_invalid", "severity": "critical", "message": str(exc)}],
                }
            )

    summary = {
        "n": len(rows),
        "schema_valid_rate": round(sum(1 for row in rows if row.get("schema_valid")) / len(rows), 4) if rows else None,
        "accepted_rate": round(sum(1 for row in rows if row.get("accepted")) / len(rows), 4) if rows else None,
        "warning_rate": round(sum(1 for row in rows if int(row.get("warning_count") or 0) > 0) / len(rows), 4) if rows else None,
        "critical_rate": round(sum(1 for row in rows if int(row.get("critical_count") or 0) > 0) / len(rows), 4) if rows else None,
        "assignment_warning_rate": round(sum(1 for row in rows if int(row.get("assignment_warning_count") or 0) > 0) / len(rows), 4) if rows else None,
        "avg_quality_score": (
            round(sum(float(row.get("quality_score") or 0.0) for row in rows) / len(rows), 4)
            if rows
            else None
        ),
        "avg_assignment_quality_score": (
            round(sum(float(row.get("assignment_quality_score") or 0.0) for row in rows) / len(rows), 4)
            if rows
            else None
        ),
    }
    payload = {"generated_at": _generated_at(), "summary": summary, "items": rows}
    _write_json(GENERATION_AUDIT_JSON, payload)
    _write_csv(GENERATION_AUDIT_CSV, rows, GENERATION_AUDIT_FIELDS)
    _append_history("generation_audit", metadata={"limit": req.limit, "items": len(rows)})
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "summary": summary,
        "artifact": _artifact_info(GENERATION_AUDIT_JSON.name),
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/rag/seed")
async def create_rag_seed(req: RagSeedRequest) -> dict[str, Any]:
    seed = await build_rag_seed(DEFAULT_RAG_BASE_SEED, req.target)
    _write_json(RAG_SEED, seed)
    _append_history("rag_seed", metadata={"target": req.target, "cases": len(seed)})
    generated = _refresh_csv_artifacts()
    auto_count = sum(
        1
        for case in seed
        if case.get("metadata", {}).get("source") == "auto_generated_from_db"
    )
    return {
        "ok": True,
        "artifact": _artifact_info(RAG_SEED.name),
        "summary": {
            "target": req.target,
            "cases": len(seed),
            "auto_generated": auto_count,
            "curated": len(seed) - auto_count,
        },
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/rag/run")
async def run_rag_research_benchmark(req: RagRunRequest) -> dict[str, Any]:
    if not RAG_SEED.exists():
        raise HTTPException(status_code=404, detail="RAG seed is missing.")
    if req.ablation:
        result = await run_rag_ablation(RAG_SEED, limit=req.limit)
        payload = {"generated_at": _generated_at(), "rag_ablation": result}
        _write_json(RAG_ABLATION_LATEST, payload)
        _append_history("rag_ablation", metadata={"limit": req.limit})
        generated = _refresh_csv_artifacts()
        return {
            "ok": True,
            "artifact": _artifact_info(RAG_ABLATION_LATEST.name),
            "summary_by_mode": result.get("summary_by_mode"),
            "table_artifacts": [_artifact_info(path.name) for path in generated],
        }

    result = await run_rag_benchmark(RAG_SEED, limit=req.limit)
    payload = {"generated_at": _generated_at(), "rag": result}
    _write_json(RAG_LATEST, payload)
    _append_history("rag_full", metadata={"limit": req.limit})
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "artifact": _artifact_info(RAG_LATEST.name),
        "summary": result.get("summary"),
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/graph/seed")
async def create_graph_seed(req: GraphSeedRequest) -> dict[str, Any]:
    seed = build_graph_seed(req.target)
    _write_json(GRAPH_SEED, seed)
    _append_history("graph_seed", metadata={"target": req.target, "cases": len(seed)})
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "artifact": _artifact_info(GRAPH_SEED.name),
        "summary": {
            "reference_cases": len(seed),
            "student_variants": sum(len(case.get("variants", [])) for case in seed),
        },
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/graph/run")
async def run_graph_research_benchmark(req: GraphRunRequest) -> dict[str, Any]:
    if not GRAPH_SEED.exists():
        raise HTTPException(status_code=404, detail="Graph seed is missing.")
    result = run_graph_benchmark(
        GRAPH_SEED,
        limit=req.limit,
        use_embeddings=req.use_embeddings,
    )
    payload = {"generated_at": _generated_at(), "graph": result}
    _write_json(GRAPH_LATEST, payload)
    _append_history("graph_benchmark", metadata={"limit": req.limit, "use_embeddings": req.use_embeddings})
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "artifact": _artifact_info(GRAPH_LATEST.name),
        "summary": result.get("summary"),
        "reference_quality": result.get("reference_quality", {}).get("summary"),
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/cardiology/synthetic/run")
async def run_cardiology_synthetic_research_benchmark(
    req: CardiologySyntheticRunRequest,
    db: DbSession,
) -> dict[str, Any]:
    protocol_sources = await _load_cardiology_protocol_sources(db)
    result = run_cardiology_synthetic_benchmark(
        case_count=req.case_count,
        expert_count=req.expert_count,
        seed=req.seed,
        use_embeddings=req.use_embeddings,
        protocol_sources=protocol_sources,
    )
    _write_json(CARDIOLOGY_SEED, result.get("cases") or [])
    payload = {"generated_at": _generated_at(), "cardiology": result}
    _write_json(CARDIOLOGY_LATEST, payload)
    _append_history(
        "cardiology_synthetic",
        metadata={
            "case_count": req.case_count,
            "expert_count": req.expert_count,
            "seed": req.seed,
            "use_embeddings": req.use_embeddings,
            "variant_count": result.get("summary", {}).get("variant_count"),
            "rating_count": result.get("summary", {}).get("rating_count"),
            "source_protocol_count": result.get("summary", {}).get("source_protocol_count"),
            "direct_cardiology_protocol_rate": result.get("summary", {}).get("direct_cardiology_protocol_rate"),
            "expert_panel_mode": result.get("summary", {}).get("expert_panel_mode"),
            "expert_panel_items_per_expert": result.get("summary", {}).get("expert_panel_items_per_expert"),
        },
    )
    generated = _refresh_csv_artifacts()
    return {
        "ok": True,
        "artifact": _artifact_info(CARDIOLOGY_LATEST.name),
        "seed_artifact": _artifact_info(CARDIOLOGY_SEED.name),
        "summary": result.get("summary"),
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/cardiology/synthetic/import-demo")
async def import_cardiology_synthetic_demo_workflow(
    req: CardiologyDemoImportRequest,
    db: DbSession,
) -> dict[str, Any]:
    if not CARDIOLOGY_LATEST.exists():
        raise HTTPException(status_code=404, detail="Cardiology synthetic benchmark is missing. Run it first.")
    result = await import_cardiology_demo_workflow(
        db,
        benchmark_path=CARDIOLOGY_LATEST,
        refresh_timestamps=req.refresh_timestamps,
    )
    _append_history(
        "cardiology_demo_import",
        metadata={
            "assignments": result.get("assignments"),
            "attempts": result.get("attempts"),
            "student_id": result.get("student_id"),
            "teacher_id": result.get("teacher_id"),
        },
    )
    return {"ok": True, "summary": result}


@router.post("/expert/export")
async def export_expert_review_package(req: ExpertExportRequest) -> dict[str, Any]:
    if not GRAPH_LATEST.exists() or not GRAPH_SEED.exists():
        raise HTTPException(status_code=404, detail="Graph benchmark or seed is missing.")

    benchmark = _read_json(GRAPH_LATEST)
    seed_cases = _read_json(GRAPH_SEED)
    items = _build_review_items(benchmark, seed_cases)
    if req.shuffle:
        random.Random(req.shuffle_seed).shuffle(items)

    _write_csv_template(EXPERT_RATINGS_TEMPLATE, items, req.delimiter)
    _write_items_jsonl(EXPERT_REVIEW_ITEMS, items)
    _write_key(EXPERT_REVIEW_KEY, items)
    _append_history("expert_export", metadata={"items": len(items), "shuffle": req.shuffle})
    generated = _refresh_csv_artifacts()

    return {
        "ok": True,
        "summary": {
            "items": len(items),
            "shuffle_seed": req.shuffle_seed if req.shuffle else None,
        },
        "artifacts": [
            _artifact_info(EXPERT_RATINGS_TEMPLATE.name),
            _artifact_info(EXPERT_REVIEW_ITEMS.name),
            _artifact_info(EXPERT_REVIEW_KEY.name),
        ],
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }


@router.post("/expert/analyze")
async def analyze_expert_review_package(req: ExpertAnalyzeRequest) -> dict[str, Any]:
    if not GRAPH_LATEST.exists() or not EXPERT_REVIEW_KEY.exists():
        raise HTTPException(status_code=404, detail="Graph benchmark or expert review key is missing.")

    rating_rows = _csv_rows(req.csv_text, req.delimiter)
    EXPERT_RATINGS_UPLOAD.write_text(req.csv_text, encoding="utf-8")
    report = analyze_expert_ratings(
        benchmark=_read_json(GRAPH_LATEST),
        rating_rows=rating_rows,
        key_by_review_item=_review_key_index(),
    )
    _write_json(EXPERT_CORRELATION_LATEST, report)
    _append_history(
        "expert_analyze",
        metadata={
            "rating_count": report.get("rating_count"),
            "expert_count": report.get("expert_count"),
        },
    )
    generated = _refresh_csv_artifacts()

    return {
        "ok": True,
        "artifact": _artifact_info(EXPERT_CORRELATION_LATEST.name),
        "ratings_artifact": _artifact_info(EXPERT_RATINGS_UPLOAD.name),
        "summary": {
            "item_count": report.get("item_count"),
            "rating_count": report.get("rating_count"),
            "expert_count": report.get("expert_count"),
            "skipped_row_count": report.get("skipped_row_count"),
            "correlation_with_mean_expert": report.get("correlation_with_mean_expert"),
            "inter_rater": report.get("inter_rater"),
        },
        "report": report,
        "table_artifacts": [_artifact_info(path.name) for path in generated],
    }
