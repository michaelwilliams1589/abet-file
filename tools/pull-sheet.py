#!/usr/bin/env python3
"""Validate grade-entry CSVs and write tools/assessment-scores.csv.

Reads one or more CSV exports of the Entry tab and any Form Responses tab.
Rejects rows with identifier-like text or out-of-range scores. Never writes
student names, student IDs, or entered_by into the published CSV.

Usage (from the repo root):

    python3 tools/pull-sheet.py --dir tools/sheet-exports
    python3 tools/pull-sheet.py tools/sheet-exports/entry.csv

See tools/SYNC.md for the full scheduled procedure (MCP read, then this script,
then generate-data.py, then push only if files changed).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = HERE / "assessment-scores.csv"
REPORT_PATH = HERE / "pull-sheet-report.json"
PUBLISHED = ["course", "term", "assessment", "outcome", "score", "max"]

REQUIRED = ["course", "term", "assessment", "score"]

HEADER_ALIASES = {
    "course": "course",
    "term": "term",
    "assessment": "assessment",
    "assignment": "assessment",
    "outcome": "outcome",
    "student_outcome": "outcome",
    "so": "outcome",
    "score": "score",
    "earned": "score",
    "points_earned": "score",
    "max": "max",
    "maximum": "max",
    "points_possible": "max",
    "entered_by": "entered_by",
    "date": "date",
    "timestamp": "timestamp",
}

FORBIDDEN_HEADERS = {
    "name", "student", "student_name", "studentname", "first", "last",
    "first_name", "last_name", "firstname", "lastname", "full_name",
    "fullname", "sid", "student_id", "studentid", "banner", "banner_id",
    "bannerid", "email", "netid", "cwid", "n_number", "nnumber", "ssn",
    "anonymous_id", "anon_id", "student_code", "roster",
}

# Applied to course, term, assessment, outcome, score, max — not entered_by.
ID_LIKE = re.compile(
    r"""
    (?:^|[\s,;])(?:
        a\d{3,}
        | n\d{7,}
        | [a-z]?\d{8,9}
        | banner\s*id
        | student\s*id
        | sid\s*[:#]
    )
    | [A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}
    | \b(?:ssn|cwid|netid)\b
    | \b(?:last\s*,\s*first|first\s+last)\b
    | \b(?:student\s+name|full\s+name)\b
    """,
    re.I | re.X,
)

NAME_FIRST_LAST = re.compile(r"^[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$")


def norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (key or "").strip().lower()).strip("_")


def find_header(rows: list[list[str]]) -> tuple[int, list[str]] | None:
    for i, row in enumerate(rows):
        keys = [norm_key(c) for c in row]
        if "course" in keys:
            return i, [HEADER_ALIASES.get(k, k) for k in keys]
    return None


def parse_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def looks_like_identifier(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if ID_LIKE.search(v):
        return True
    # "Jane Doe" in a score field is almost certainly a name, not an assessment title.
    if NAME_FIRST_LAST.match(v) and " " in v and not re.search(r"ETDE|SO\s*\d|Fall|Spring|Summer|Lab|Exam|Project|Quiz|Rubric|Test|Presentation", v, re.I):
        return True
    return False


def to_number(value: str):
    s = (value or "").strip().replace("%", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def validate_row(rec: dict, source: str, line_no: int) -> tuple[dict | None, str | None]:
    # Forbidden header values (a name or ID column was present)
    for k, v in rec.items():
        nk = norm_key(k)
        if (nk in FORBIDDEN_HEADERS or nk.endswith("_id") or (nk.endswith("_name") and nk != "assessment")) and str(v or "").strip():
            return None, "identifier_column"

    for field in ("course", "term", "assessment", "outcome", "score", "max"):
        if looks_like_identifier(str(rec.get(field) or "")):
            return None, "identifier_like_text"

    course = str(rec.get("course") or "").strip()
    term = str(rec.get("term") or "").strip()
    assessment = str(rec.get("assessment") or "").strip()
    outcome = str(rec.get("outcome") or "").strip()
    # Skip banner / instruction leftovers
    if course.lower().startswith("do not enter"):
        return None, "skipped_banner"
    if "these headers match" in course.lower() or "these headers match" in assessment.lower():
        return None, "skipped_banner"
    if not course or not term or not assessment:
        if not any(str(rec.get(k) or "").strip() for k in rec):
            return None, "empty"
        return None, "missing_required"

    score = to_number(str(rec.get("score") or ""))
    if score is None:
        return None, "missing_or_invalid_score"
    maximum = to_number(str(rec.get("max") or rec.get("maximum") or "100"))
    if maximum is None or maximum <= 0:
        return None, "invalid_max"
    if score < 0 or score > maximum:
        return None, "score_out_of_range"

    out = {
        "course": course,
        "term": term,
        "assessment": assessment,
        "outcome": outcome,
        "score": str(int(score) if score == int(score) else score),
        "max": str(int(maximum) if maximum == int(maximum) else maximum),
        "_source": source,
        "_line": line_no,
        "_assessment_upper": assessment.upper(),
    }
    return out, None


def load_file(path: Path) -> tuple[list[dict], list[dict]]:
    text = path.read_text(encoding="utf-8-sig")
    rows = parse_csv(text)
    found = find_header(rows)
    accepted, rejected = [], []
    if not found:
        rejected.append({"source": path.name, "line": 0, "reason": "no_course_header"})
        return accepted, rejected
    header_i, headers = found
    for offset, raw in enumerate(rows[header_i + 1 :], start=header_i + 2):
        rec = {}
        for i, h in enumerate(headers):
            if not h:
                continue
            rec[h] = raw[i] if i < len(raw) else ""
        row, reason = validate_row(rec, path.name, offset)
        if reason == "empty" or reason == "skipped_banner":
            continue
        if row is None:
            rejected.append({"source": path.name, "line": offset, "reason": reason})
        else:
            accepted.append(row)
    return accepted, rejected


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("files", nargs="*", type=Path, help="CSV files to merge")
    p.add_argument("--dir", type=Path, help="Directory of CSV exports")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--drop-test", action="store_true", help="Drop rows whose assessment starts with TEST")
    args = p.parse_args(argv)

    paths: list[Path] = list(args.files)
    if args.dir:
        if not args.dir.is_dir():
            print(f"Export directory not found: {args.dir}", file=sys.stderr)
            return 2
        paths.extend(sorted(args.dir.glob("*.csv")))
    # unique, keep order
    seen = set()
    uniq = []
    for path in paths:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            uniq.append(path)
    paths = uniq
    if not paths:
        print("No CSV files given. Export the Entry / Form Responses tabs first (see tools/SYNC.md).", file=sys.stderr)
        return 2

    accepted, rejected = [], []
    for path in paths:
        a, r = load_file(path)
        accepted.extend(a)
        rejected.extend(r)

    if args.drop_test:
        kept = []
        for row in accepted:
            if row["_assessment_upper"].startswith("TEST"):
                rejected.append({"source": row["_source"], "line": row["_line"], "reason": "dropped_test"})
            else:
                kept.append(row)
        accepted = kept

    published = [{k: row[k] for k in PUBLISHED} for row in accepted]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PUBLISHED)
        w.writeheader()
        w.writerows(published)

    report = {
        "files": [str(p) for p in paths],
        "accepted": len(published),
        "rejected": len(rejected),
        "reasons": rejected,
        "output": str(args.out),
        "note": "Rejected reasons only; cell values are not stored in this report.",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.out} ({len(published)} row(s); {len(rejected)} rejected)")
    if rejected:
        counts: dict[str, int] = {}
        for r in rejected:
            counts[r["reason"]] = counts.get(r["reason"], 0) + 1
        for reason, n in sorted(counts.items()):
            print(f"  rejected {n} × {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
