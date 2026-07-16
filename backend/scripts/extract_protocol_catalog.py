"""LLM extraction: clinical protocols -> categorized catalog blocks.

Why an LLM (not just lemmatization): a protocol describes everything in prose,
so turning it into discrete *categorized* blocks (symptom / exam / lab_test /
instrumental_test / disease / medication / surgery / monitoring) is a semantic
task. Lemmatization only *matches/dedups* afterwards — it cannot extract.

This script:
  1. splits each protocol into markdown sections and keeps the clinically
     relevant ones (diagnostics / treatment / monitoring / diagnosis);
  2. asks the LLM to extract blocks, copying terminology from the text (no
     invention) in Russian nominative case;
  3. dedups by LEMMA-KEY + category (morphology) against the existing catalog
     and within the run — so морфологические/словопорядковые дубли схлопываются;
  4. inserts new blocks as source="protocol_extracted", external_id="protocol:<id>".

patient_profile is intentionally NOT extracted — it is scenario-specific
(comes from the task), not a protocol concept.

Resumable: processed protocol ids are checkpointed to a JSON file; rerun to
continue. Idempotent against the catalog via the lemma-key dedup.

Usage:
  python scripts/extract_protocol_catalog.py --limit 15            # pilot
  python scripts/extract_protocol_catalog.py --limit 15 --dry-run  # no writes
  python scripts/extract_protocol_catalog.py                       # full run
"""
import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from openai import AsyncOpenAI  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import engine  # noqa: E402
from app.models import ClinicalProtocol, MedicalNode  # noqa: E402
from app.services import morphology  # noqa: E402

_SOURCE = "protocol_extracted"
_CATALOG_SOURCES = (
    "protocols", "clinical_protocols", "medelement_terms", "medelement",
    "protocol_graph", _SOURCE,
)
_ALLOWED = {
    "symptom", "exam", "lab_test", "instrumental_test",
    "disease", "medication", "surgery", "monitoring",
}

# Section titles worth feeding to the LLM (lowercased substring match).
_RELEVANT_SECTION_KEYWORDS = (
    "диагноз", "диагност", "клиническая картина", "клинические проявления",
    "симптом", "жалоб", "анамнез", "осмотр", "обследован", "физикальн",
    "лечени", "терапи", "препарат", "медикамент", "хирург", "оператив",
    "наблюдени", "мониторинг", "диспансер", "контрол", "дальнейшее ведение",
)
_MAX_SECTION_CHARS = 12_000

_CHECKPOINT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "_protocol_catalog_checkpoint.json",
)

_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string", "enum": sorted(_ALLOWED)},
                },
                "required": ["name", "category"],
            },
        }
    },
    "required": ["blocks"],
}

_SYSTEM_PROMPT = (
    "Ты медицинский эксперт по извлечению клинических данных из протоколов. "
    "Возвращай только валидный JSON по схеме."
)


def _build_prompt(title: str, sections_text: str) -> str:
    return f"""Из выдержек клинического протокола «{title}» извлеки отдельные клинические блоки.

Категории (используй ТОЛЬКО их):
- symptom — симптом/жалоба/синдром (например: «одышка», «боль в грудной клетке»)
- exam — приём объективного осмотра (например: «аускультация сердца», «пальпация живота», «физикальное обследование»)
- lab_test — лабораторный анализ (например: «тропонин I», «общий анализ крови»)
- instrumental_test — инструментальное исследование (например: «ЭКГ», «КТ грудной клетки», «ЭхоКГ»)
- disease — диагноз/нозология (например: «острый инфаркт миокарда»)
- medication — препарат/действующее вещество (например: «клопидогрель»)
- surgery — хирургическое/инвазивное вмешательство (например: «чрескожное коронарное вмешательство»)
- monitoring — шаг наблюдения/контроля после лечения (например: «мониторинг ЭКГ 24 часа», «контроль АД»)

Правила:
- Бери термины ИЗ ТЕКСТА, НИЧЕГО НЕ ВЫДУМЫВАЙ. Если в выдержках чего-то нет — не добавляй.
- Название — на русском, в именительном падеже, единственном числе, краткая каноническая форма
  (специфику вроде «с подъёмом сегмента ST» сохраняй только если это отдельная нозология).
- Без дозировок, чисел, единиц измерения, ссылок [1], списков-заголовков («Диагностика», «Лечение»).
- lab_test / instrumental_test — это НАЗВАНИЕ исследования («общий анализ крови»), а НЕ его результат.
  Отклонение показателя («снижение гемоглобина») — это symptom, если это клинический признак, иначе пропусти.
- exam — только приёмы объективного осмотра врача (аускультация, пальпация, перкуссия, осмотр).
  Консультации других специалистов («консультация хирурга») и сбор анамнеза/жалоб НЕ включай.
- symptom — только клинический симптом/жалоба/синдром пациента. НЕ включай социальные и
  эпидемиологические исходы (смертность, самоубийство, статистика) и организационные понятия.
- medication — конкретное лекарство или действующее вещество («ампициллин»), а НЕ стратегия лечения
  («терапия инфекции», «антибактериальная терапия») — такие пропусти.
- Не дублируй один и тот же блок.

Выдержки протокола:
{sections_text}
"""


def _extract_relevant_sections(text: str) -> str:
    headings = [
        {"pos": m.start(), "title": m.group(2).strip()}
        for m in re.finditer(r"(?m)^(#{1,6})\s+(.*)$", text)
    ]
    if not headings:
        return text[:_MAX_SECTION_CHARS]

    parts: list[str] = []
    total = 0
    for i, heading in enumerate(headings):
        title_lower = heading["title"].lower()
        if not any(kw in title_lower for kw in _RELEVANT_SECTION_KEYWORDS):
            continue
        start = heading["pos"]
        end = headings[i + 1]["pos"] if i + 1 < len(headings) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        parts.append(chunk)
        total += len(chunk)
        if total >= _MAX_SECTION_CHARS:
            break

    return "\n\n".join(parts)[:_MAX_SECTION_CHARS]


def _clean_name(name: str) -> str:
    name = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", name)
    name = name.replace("**", "").replace("*", "").replace("`", "")
    name = re.sub(r"\s+", " ", name).strip(" ;,.:()-")
    return name


def _lemma_key(name: str, category: str) -> tuple:
    lemmas = morphology.lemmas(name)
    return (lemmas if lemmas else frozenset({name.lower()}), category)


def _load_checkpoint() -> set[int]:
    if os.path.exists(_CHECKPOINT):
        try:
            with open(_CHECKPOINT, encoding="utf-8") as fh:
                return set(json.load(fh).get("done", []))
        except Exception:
            return set()
    return set()


def _save_checkpoint(done: set[int]) -> None:
    with open(_CHECKPOINT, "w", encoding="utf-8") as fh:
        json.dump({"done": sorted(done)}, fh)


def _supports_reasoning_effort(model: str) -> bool:
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4")


async def _extract_blocks(
    client: AsyncOpenAI, model: str, title: str, sections_text: str, reasoning_effort: str
) -> list[dict]:
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(title, sections_text)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "protocol_catalog_extraction",
                "strict": True,
                "schema": _EXTRACTION_SCHEMA,
            },
        },
    }
    # gpt-5/o-series default to heavy reasoning (>100s on a 12k input); pin it
    # low for this simple extraction task. Plain models reject the param.
    if reasoning_effort and _supports_reasoning_effort(model):
        kwargs["reasoning_effort"] = reasoning_effort
    response = await client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content or ""
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group()
    try:
        return json.loads(raw).get("blocks", [])
    except Exception:
        return []


async def main(
    limit: int | None,
    offset: int,
    dry_run: bool,
    reset: bool,
    model: str,
    concurrency: int,
    reasoning_effort: str,
) -> None:
    if reset and os.path.exists(_CHECKPOINT):
        os.remove(_CHECKPOINT)

    settings = get_settings()
    if not settings.openai_api_key:
        print("OPENAI_API_KEY is not set.")
        return
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    done = _load_checkpoint()
    inserted = Counter()
    seen_keys: set[tuple] = set()
    stats = {"processed": 0, "failed": 0, "pending_ckpt": 0}

    # Never hold a DB connection open across an LLM await (asyncpg pool pre-ping
    # cannot reconnect outside greenlet context) — use short-lived sessions only.
    async with AsyncSession(engine) as session:
        existing = await session.execute(
            select(MedicalNode.name, MedicalNode.category)
            .where(MedicalNode.source.in_(_CATALOG_SOURCES))
        )
        existing_pairs = existing.all()
        stmt = select(ClinicalProtocol.id, ClinicalProtocol.title).order_by(ClinicalProtocol.id).offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        protocol_refs = list((await session.execute(stmt)).all())

    for name, category in existing_pairs:
        seen_keys.add(_lemma_key(name, category))
    print(f"Loaded {len(seen_keys)} existing lemma-keys. Model={model}, concurrency={concurrency}.")

    todo = [(pid, title) for pid, title in protocol_refs if pid not in done]
    print(f"Protocols to process: {len(todo)} (already done: {len(done)}).")

    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async def worker(protocol_id: int, title: str) -> None:
        async with sem:
            async with AsyncSession(engine) as s:
                text = await s.scalar(
                    select(ClinicalProtocol.text_content).where(ClinicalProtocol.id == protocol_id)
                )
            sections = _extract_relevant_sections(text or "")
            if not sections.strip():
                async with lock:
                    done.add(protocol_id)
                return

            try:
                blocks = await _extract_blocks(client, model, title, sections, reasoning_effort)
            except Exception as exc:  # noqa: BLE001
                async with lock:
                    stats["failed"] += 1
                print(f"  [protocol {protocol_id}] LLM error: {exc}")
                return

            # Dedup check+add must be atomic across coroutines → hold the lock with
            # no await inside (lemmatization is sync + cached).
            new_nodes: list[MedicalNode] = []
            async with lock:
                for block in blocks:
                    category = str(block.get("category") or "").strip().lower()
                    name = _clean_name(str(block.get("name") or ""))
                    if category not in _ALLOWED or len(name) < 3 or re.search(r"\d", name):
                        continue
                    key = _lemma_key(name, category)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    inserted[category] += 1
                    new_nodes.append(MedicalNode(
                        name=name,
                        category=category,
                        external_id=f"protocol:{protocol_id}",
                        source=_SOURCE,
                    ))

            if new_nodes and not dry_run:
                async with AsyncSession(engine) as s:
                    s.add_all(new_nodes)
                    await s.commit()

            async with lock:
                stats["processed"] += 1
                done.add(protocol_id)
                stats["pending_ckpt"] += 1
                if not dry_run and stats["pending_ckpt"] >= 10:
                    _save_checkpoint(done)
                    stats["pending_ckpt"] = 0
                count_so_far = stats["processed"]
            if count_so_far % 25 == 0:
                print(f"  ...{count_so_far}/{len(todo)} processed")

    await asyncio.gather(*(worker(pid, title) for pid, title in todo))

    if not dry_run:
        _save_checkpoint(done)

    total = sum(inserted.values())
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processed {stats['processed']} protocols "
          f"({stats['failed']} failed). Inserted {total} new blocks (source={_SOURCE}):")
    for category, count in sorted(inserted.items()):
        print(f"  {category:20} +{count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="clear checkpoint and start over")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--reasoning-effort", default="minimal",
                        help="gpt-5/o-series only: minimal|low|medium|high")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.offset, args.dry_run, args.reset,
                     args.model, args.concurrency, args.reasoning_effort))
