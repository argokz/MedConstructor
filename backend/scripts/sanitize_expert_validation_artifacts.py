"""Replace expert login identifiers with stable public research codes.

The script edits only identifier fields in CSV/JSON validation artifacts. Clinical
scores, comments, case identifiers, and timestamps are preserved unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (
    BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_ratings_latest.csv",
    BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_validation_latest.json",
    BACKEND_ROOT / "benchmarks" / "cardiology_real_expert_validation_v2_latest.json",
)
IDENTIFIER_KEYS = {"expert_id", "expert_a", "expert_b"}


def _collect_identifiers(value: Any, identifiers: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in IDENTIFIER_KEYS and isinstance(item, str) and "@" in item:
                identifiers.add(item)
            _collect_identifiers(item, identifiers)
    elif isinstance(value, list):
        for item in value:
            _collect_identifiers(item, identifiers)


def _replace_identifiers(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: mapping.get(item, item)
            if key in IDENTIFIER_KEYS and isinstance(item, str)
            else _replace_identifiers(item, mapping)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_identifiers(item, mapping) for item in value]
    return value


def _sanitize_json(path: Path, mapping: dict[str, str], dry_run: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sanitized = _replace_identifiers(payload, mapping)
    changed = int(sanitized != payload)
    if changed and not dry_run:
        path.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def _sanitize_csv(path: Path, mapping: dict[str, str], dry_run: bool) -> int:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    changed = 0
    for row in rows:
        for key in IDENTIFIER_KEYS.intersection(row):
            original = row.get(key) or ""
            replacement = mapping.get(original, original)
            changed += int(replacement != original)
            row[key] = replacement
    if changed and not dry_run:
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pseudonymize expert identifiers in validation artifacts."
    )
    parser.add_argument("paths", nargs="*", type=Path, default=list(DEFAULT_PATHS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = [path.resolve() for path in args.paths if path.exists()]
    identifiers: set[str] = set()
    for path in paths:
        if path.suffix.lower() == ".json":
            _collect_identifiers(json.loads(path.read_text(encoding="utf-8")), identifiers)
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    for key in IDENTIFIER_KEYS.intersection(row):
                        value = row.get(key) or ""
                        if "@" in value:
                            identifiers.add(value)

    mapping = {
        identifier: f"expert_{index:02d}"
        for index, identifier in enumerate(sorted(identifiers), start=1)
    }
    changed = 0
    for path in paths:
        if path.suffix.lower() == ".json":
            changed += _sanitize_json(path, mapping, args.dry_run)
        elif path.suffix.lower() == ".csv":
            changed += _sanitize_csv(path, mapping, args.dry_run)
    print(
        json.dumps(
            {
                "files": len(paths),
                "identifiers": len(mapping),
                "changed": changed,
                "dry_run": args.dry_run,
            }
        )
    )


if __name__ == "__main__":
    main()
