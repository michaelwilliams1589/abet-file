#!/usr/bin/env python3
"""Generate data.js for the ABET File PWA from the local cycle folder and Drive map.

Documents are never copied into the site. data.js holds titles, short summaries,
running-log rows, Google Drive links, and anonymized assessment aggregates only.
Student names and IDs are never written to data.js.

Usage (from the repo root, /workspace/abet-app):

    python3 tools/generate-data.py

Optional flags:

    --cycle DIR      Local cycle folder
                     (default: /workspace/abet/OSUIT_ABET_Cycle_2026-2032)
    --previous DIR   Local previous-cycle folder
                     (default: /workspace/abet/previous-cycle-final/OSUIT_ABET)
    --out FILE       Output path (default: ./data.js)

After ABET BOT adds files:

    1. Sync the new files to Google Drive (do not change sharing).
    2. Add each new path and Drive file id to tools/drive-map.json.
    3. Update tools/meta.json if meetings, deadlines, or open items changed.
    4. Add de-identified score rows to tools/assessment-aggregates.json
       (or tools/assessment-scores.csv). Do not include names or IDs.
    5. Run this script, then commit data.js (and any map/meta/aggregate edits) and push.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

DEFAULT_CYCLE = Path("/workspace/abet/OSUIT_ABET_Cycle_2026-2032")
DEFAULT_PREVIOUS = Path("/workspace/abet/previous-cycle-final/OSUIT_ABET")

SKIP_NAMES = {".DS_Store", "Thumbs.db"}

YEAR_IDS = [
    "Y1_2026-27",
    "Y2_2027-28",
    "Y3_2028-29",
    "Y4_2029-30",
    "Y5_2030-31",
    "Y6_2031-32",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ext_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def is_notes_file(name: str) -> bool:
    lower = name.lower()
    return lower.startswith("osuit_etde_abet_meeting_notes") and ext_of(name) in {"pdf", "docx"}


def is_evidence_file(name: str) -> bool:
    return name.startswith("E") and name[1:2].isdigit()


def is_readme(name: str) -> bool:
    return name.lower() in {"readme.txt", "readme.md"}


def lookup(drive_index: dict, ns: str, path: str):
    return drive_index.get((ns, path))


def link_for(drive_index: dict, ns: str, path: str):
    item = lookup(drive_index, ns, path)
    return item["webViewLink"] if item else None


def file_item(drive_index: dict, ns: str, path: str, name: str | None = None, extra: dict | None = None):
    item = lookup(drive_index, ns, path)
    name = name or (item["name"] if item else Path(path).name)
    rec = {
        "name": name,
        "path": path,
        "type": ext_of(name) or ("folder" if item and item["kind"] == "folder" else ""),
        "kind": item["kind"] if item else "file",
        "url": item["webViewLink"] if item else None,
        "mapped": bool(item),
    }
    if extra:
        rec.update(extra)
    return rec


def parse_running_log_md(text: str) -> list[dict]:
    """Parse the markdown table in Running_Log.md."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0].lower() in {"date added", "---"} or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(
            {
                "date": cells[0],
                "file": cells[1],
                "section": cells[2],
                "year": cells[3],
                "status": cells[4],
                "notes": cells[5],
            }
        )
    return rows


def parse_running_log_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        # Be tolerant of header wording
        def get(*keys):
            for k in keys:
                for rk, rv in raw.items():
                    if rk and rk.strip().lower() == k.lower():
                        return (rv or "").strip()
            return ""

        rows.append(
            {
                "date": get("Date added", "date"),
                "file": get("File", "file"),
                "section": get("Section", "section"),
                "year": get("Cycle year", "year"),
                "status": get("Status", "status"),
                "notes": get("Notes", "notes"),
            }
        )
    return rows


def walk_local(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    paths = []
    for p in sorted(folder.rglob("*")):
        if p.name in SKIP_NAMES:
            continue
        rel = p.relative_to(folder).as_posix()
        if p.is_dir():
            paths.append(rel)
        elif p.is_file():
            paths.append(rel)
    return paths


def attach_log_urls(rows: list[dict], drive_index: dict) -> list[dict]:
    out = []
    for row in rows:
        path = row["file"].lstrip("./")
        rec = dict(row)
        rec["url"] = link_for(drive_index, "cycle", path)
        out.append(rec)
    return out



MIN_N_FOR_DISTRIBUTION = 5
FORBIDDEN_SCORE_FIELDS = {
    "name", "student", "student_name", "studentname", "first", "last",
    "first_name", "last_name", "firstname", "lastname", "full_name",
    "fullname", "sid", "id", "student_id", "studentid", "banner",
    "banner_id", "bannerid", "email", "netid", "cwid", "n_number",
    "nnumber", "ssn", "wid", "widid", "anonymous_id", "anon_id",
    "code", "student_code", "roster",
}

DEFAULT_OUTCOMES = [
    {"id": "SO 1", "short": "Technical problem-solving", "label": "SO 1 — Technical problem-solving"},
    {"id": "SO 2", "short": "Design", "label": "SO 2 — Design"},
    {"id": "SO 3", "short": "Communication", "label": "SO 3 — Communication"},
    {"id": "SO 4", "short": "Testing and measurement", "label": "SO 4 — Testing and measurement"},
    {"id": "SO 5", "short": "Teamwork", "label": "SO 5 — Teamwork"},
]


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (key or "").strip().lower()).strip("_")


def _pct(score, maximum) -> float | None:
    try:
        s = float(score)
        m = float(maximum) if maximum not in (None, "") else 100.0
    except (TypeError, ValueError):
        return None
    if m <= 0:
        return None
    return round(100.0 * s / m, 2)


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    xs = sorted(vals)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return round(xs[mid], 1)
    return round((xs[mid - 1] + xs[mid]) / 2, 1)


def _histogram(vals: list[float], bins: int = 10) -> list[dict]:
    edges = list(range(0, 101, 100 // bins))
    if edges[-1] != 100:
        edges.append(100)
    counts = [0] * (len(edges) - 1)
    for v in vals:
        x = min(100.0, max(0.0, v))
        # 100 belongs in the last bin
        i = min(len(counts) - 1, int(x // (100 / (len(edges) - 1))))
        if x >= 100:
            i = len(counts) - 1
        counts[i] += 1
    out = []
    for i, c in enumerate(counts):
        lo, hi = edges[i], edges[i + 1]
        label = f"{lo}–{hi}" if i < len(counts) - 1 else f"{lo}–{hi}"
        out.append({"from": lo, "to": hi, "label": label, "count": c})
    return out


def _summarize_scores(vals: list[float], threshold: float, min_n: int) -> dict:
    n = len(vals)
    meeting = sum(1 for v in vals if v >= threshold)
    rec = {
        "n": n,
        "mean": _mean(vals),
        "median": _median(vals),
        "min": round(min(vals), 1) if vals else None,
        "max": round(max(vals), 1) if vals else None,
        "meeting": meeting,
        "percentMeeting": round(100.0 * meeting / n, 1) if n else None,
        "distributionShown": n >= min_n,
    }
    if n >= min_n:
        rec["scores"] = [round(v, 1) for v in sorted(vals)]
        rec["histogram"] = _histogram(vals)
    return rec


def _load_score_rows(warnings: list[str]) -> tuple[dict, list[dict]]:
    src = HERE / "assessment-aggregates.json"
    raw = load_json(src) if src.is_file() else {}
    if not src.is_file():
        warnings.append("tools/assessment-aggregates.json not found; Data tab will be empty.")
        raw = {}

    forbidden_found = []
    rows: list[dict] = []

    def accept_row(item: dict, origin: str):
        cleaned = {}
        dropped = []
        for k, v in item.items():
            nk = _norm_key(k)
            if nk in FORBIDDEN_SCORE_FIELDS or nk.endswith("_id") or nk.endswith("_name"):
                dropped.append(k)
                continue
            cleaned[nk] = v
        if dropped:
            forbidden_found.append(f"{origin}: dropped {', '.join(dropped)}")
        course = str(cleaned.get("course") or "").strip()
        term = str(cleaned.get("term") or "").strip()
        assessment = str(cleaned.get("assessment") or cleaned.get("assignment") or "").strip()
        outcome = str(cleaned.get("outcome") or cleaned.get("so") or "").strip()
        pct = _pct(cleaned.get("score") or cleaned.get("earned") or cleaned.get("percent"),
                   cleaned.get("max") or cleaned.get("maximum") or cleaned.get("points_possible") or 100)
        if pct is None:
            warnings.append(f"{origin}: skipped a row with no usable score")
            return
        rows.append({
            "course": course or "Unspecified course",
            "term": term or "Unspecified term",
            "assessment": assessment or "Unspecified assessment",
            "outcome": outcome or "",
            "percent": pct,
        })

    for i, item in enumerate(raw.get("rows") or []):
        if isinstance(item, dict):
            accept_row(item, f"assessment-aggregates.json rows[{i}]")

    csv_path = HERE / "assessment-scores.csv"
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8", newline="") as f:
            # Skip comment lines
            lines = [ln for ln in f if not ln.lstrip().startswith("#")]
        reader = csv.DictReader(io.StringIO("".join(lines)))
        for i, item in enumerate(reader):
            accept_row(item, f"assessment-scores.csv row {i+2}")

    if forbidden_found:
        for msg in forbidden_found:
            warnings.append("Removed identifier column(s) from assessment input — " + msg)

    precomputed = []
    for i, item in enumerate(raw.get("aggregates") or []):
        if not isinstance(item, dict):
            continue
        # Never pass through names/ids
        safe = {k: v for k, v in item.items() if _norm_key(k) not in FORBIDDEN_SCORE_FIELDS and not _norm_key(k).endswith("_id") and not _norm_key(k).endswith("_name")}
        precomputed.append(safe)

    return raw, rows, precomputed


def build_assessment_data(drive_index: dict, warnings: list[str]) -> dict:
    raw, rows, precomputed = _load_score_rows(warnings)
    criteria = raw.get("criteria") or {}
    threshold = float(criteria.get("threshold") or 70)
    target = float(criteria.get("programTarget") or 75)
    min_n = int(raw.get("minNForDistribution") or MIN_N_FOR_DISTRIBUTION)
    outcomes = raw.get("outcomes") or DEFAULT_OUTCOMES

    # Group rows
    def key(r):
        return (r["course"], r["term"])

    sections = []
    by_section: dict[tuple, list] = {}
    for r in rows:
        by_section.setdefault(key(r), []).append(r)

    for (course, term), items in sorted(by_section.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        percents = [x["percent"] for x in items]
        summary = _summarize_scores(percents, threshold, min_n)
        # Per assessment
        by_as: dict[str, list] = {}
        for x in items:
            by_as.setdefault(x["assessment"], []).append(x["percent"])
        assessments = []
        for name, vals in sorted(by_as.items()):
            rec = {"name": name, **_summarize_scores(vals, threshold, min_n)}
            assessments.append(rec)
        # Per outcome within the section
        by_out: dict[str, list] = {}
        for x in items:
            if x["outcome"]:
                by_out.setdefault(x["outcome"], []).append(x["percent"])
        section_outcomes = [{"id": oid, **_summarize_scores(vals, threshold, min_n)} for oid, vals in sorted(by_out.items())]
        sections.append({
            "course": course,
            "term": term,
            "source": "anonymized score rows",
            **summary,
            "assessments": assessments,
            "outcomes": section_outcomes,
        })

    # Precomputed aggregates (used when no rows exist for that course/term)
    covered = {(s["course"], s["term"]) for s in sections}
    # Also allow precomputed even alongside? Only if that section has no rows.
    pre_groups: dict[tuple, list] = {}
    for a in precomputed:
        course = str(a.get("course") or "Unspecified course").strip()
        term = str(a.get("term") or "Unspecified term").strip()
        if (course, term) in covered:
            continue
        pre_groups.setdefault((course, term), []).append(a)
    for (course, term), items in sorted(pre_groups.items()):
        # If a single overall row exists, use it; otherwise compose from parts
        overall = next((x for x in items if not x.get("assessment") and not x.get("outcome")), None)
        n = int(overall.get("n") or 0) if overall else sum(int(x.get("n") or 0) for x in items)
        section = {
            "course": course,
            "term": term,
            "source": (overall or items[0]).get("source") or "precomputed aggregate (no score list provided)",
            "n": n,
            "mean": (overall or {}).get("mean"),
            "median": (overall or {}).get("median"),
            "min": (overall or {}).get("min"),
            "max": (overall or {}).get("max"),
            "meeting": (overall or {}).get("meeting"),
            "percentMeeting": (overall or {}).get("percentMeeting") or (overall or {}).get("percent_meeting"),
            "distributionShown": False,
            "assessments": [],
            "outcomes": [],
        }
        if n >= min_n and overall and overall.get("scores"):
            # Only if caller already provided an anonymized score list
            scores = [float(s) for s in overall["scores"]]
            section.update(_summarize_scores(scores, threshold, min_n))
            section["source"] = overall.get("source") or section["source"]
        for x in items:
            if x.get("assessment"):
                section["assessments"].append({
                    "name": x["assessment"],
                    "n": x.get("n"),
                    "mean": x.get("mean"),
                    "percentMeeting": x.get("percentMeeting") or x.get("percent_meeting"),
                    "distributionShown": False,
                })
            if x.get("outcome"):
                section["outcomes"].append({
                    "id": x["outcome"],
                    "n": x.get("n"),
                    "mean": x.get("mean"),
                    "percentMeeting": x.get("percentMeeting") or x.get("percent_meeting"),
                    "distributionShown": False,
                })
        sections.append(section)

    # Cycle-level outcome summary from score rows
    cycle_outcomes = []
    by_out: dict[str, list] = {}
    for r in rows:
        if r["outcome"]:
            by_out.setdefault(r["outcome"], []).append(r["percent"])
    # Include precomputed outcome totals only if no rows for that outcome
    for a in precomputed:
        oid = str(a.get("outcome") or "")
        if oid and oid not in by_out:
            cycle_outcomes.append({
                "id": oid,
                "n": a.get("n"),
                "mean": a.get("mean"),
                "percentMeeting": a.get("percentMeeting") or a.get("percent_meeting"),
                "distributionShown": False,
                "source": a.get("source") or "precomputed aggregate",
            })
    known_ids = {o["id"] for o in outcomes}
    for spec in outcomes:
        oid = spec["id"]
        vals = by_out.get(oid)
        rec = {"id": oid, "short": spec.get("short") or "", "label": spec.get("label") or oid}
        if vals:
            rec.update(_summarize_scores(vals, threshold, min_n))
            rec["source"] = "anonymized score rows"
        else:
            prior = next((x for x in cycle_outcomes if x["id"] == oid), None)
            if prior:
                rec.update(prior)
            else:
                rec.update({"n": 0, "mean": None, "percentMeeting": None, "distributionShown": False, "source": None})
        cycle_outcomes = [x for x in cycle_outcomes if x["id"] != oid]  # keep extras later
        cycle_outcomes.append(rec)
    # Any outcome ids in rows not in the standard 1-5 list
    for oid, vals in sorted(by_out.items()):
        if oid not in known_ids:
            rec = {"id": oid, "short": "", "label": oid, "source": "anonymized score rows"}
            rec.update(_summarize_scores(vals, threshold, min_n))
            cycle_outcomes.append(rec)

    has_results = bool(rows or precomputed)
    return {
        "folderUrl": link_for(drive_index, "cycle", "03_Assessment_Hub/Data"),
        "readmeUrl": link_for(drive_index, "cycle", "03_Assessment_Hub/Data/README.txt"),
        "empty": not has_results,
        "emptyMessage": "No data yet — send grades/assessment results to Chief BOT.",
        "criteria": {
            "threshold": threshold,
            "thresholdSource": criteria.get("thresholdSource") or "",
            "programTarget": target,
            "programTargetSource": criteria.get("programTargetSource") or "",
        },
        "outcomes": outcomes,
        "outcomeNote": raw.get("outcomeNote") or "",
        "minNForDistribution": min_n,
        "privacyNote": "Scores in this app are de-identified. Names and student IDs are not published. Course/term sections with fewer than 5 assessed students show only class averages and attainment rates, not score distributions.",
        "cycleOutcomes": cycle_outcomes,
        "sections": sections,
    }


def build(cycle_dir: Path, previous_dir: Path) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    drive_map = load_json(HERE / "drive-map.json")
    meta = load_json(HERE / "meta.json")

    drive_index = {(e["ns"], e["path"]): e for e in drive_map["entries"]}

    # Local inventory vs map
    if cycle_dir.is_dir():
        local_cycle = set(walk_local(cycle_dir))
        mapped_cycle = {e["path"] for e in drive_map["entries"] if e["ns"] == "cycle" and e["path"]}
        missing_from_map = sorted(local_cycle - mapped_cycle)
        missing_locally = sorted(p for p in mapped_cycle if p and p not in local_cycle)
        for p in missing_from_map:
            warnings.append(f"Local cycle path not in drive-map.json: {p}")
        for p in missing_locally:
            warnings.append(f"drive-map.json path not found locally (cycle): {p}")
    else:
        warnings.append(f"Cycle folder not found at {cycle_dir}; using drive-map.json and meta.json only.")

    if previous_dir.is_dir():
        local_prev = set(walk_local(previous_dir))
        mapped_prev = {e["path"] for e in drive_map["entries"] if e["ns"] == "previous" and e["path"]}
        for p in sorted(local_prev - mapped_prev):
            warnings.append(f"Local previous-cycle path not in drive-map.json: {p}")
        for p in sorted(p for p in mapped_prev if p and p not in local_prev):
            warnings.append(f"drive-map.json path not found locally (previous): {p}")
    else:
        warnings.append(f"Previous-cycle folder not found at {previous_dir}; using drive-map.json only.")

    # Running log
    log_rows: list[dict] = []
    log_md = cycle_dir / "00_Index_and_Log" / "Running_Log.md"
    log_csv = cycle_dir / "00_Index_and_Log" / "Running_Log.csv"
    snapshot = HERE / "log-snapshot.json"
    if log_md.is_file():
        log_rows = parse_running_log_md(log_md.read_text(encoding="utf-8"))
        snapshot.write_text(json.dumps(log_rows, indent=2) + "\n", encoding="utf-8")
    elif log_csv.is_file():
        log_rows = parse_running_log_csv(log_csv.read_text(encoding="utf-8"))
        snapshot.write_text(json.dumps(log_rows, indent=2) + "\n", encoding="utf-8")
    elif snapshot.is_file():
        log_rows = load_json(snapshot)
        warnings.append("Used tools/log-snapshot.json because the local running log was not found.")
    else:
        warnings.append("No running log found; Log tab will be empty.")

    log_rows = attach_log_urls(log_rows, drive_index)

    # Meetings by year
    meta_by_id = {m["id"]: m for m in meta["meetings"]}
    years = []
    for y in meta["years"]:
        year_path = f"04_Meeting_Notes/{y['id']}"
        meetings = []
        # Discover meeting folders from the drive map (and local dir if present)
        folder_ids = []
        for e in drive_map["entries"]:
            if e["ns"] != "cycle" or e["kind"] != "folder":
                continue
            prefix = year_path + "/"
            if e["path"].startswith(prefix) and e["path"].count("/") == 2:
                folder_ids.append(e["path"].split("/")[-1])
        if cycle_dir.is_dir() and (cycle_dir / year_path).is_dir():
            for p in sorted((cycle_dir / year_path).iterdir()):
                if p.is_dir() and p.name not in folder_ids:
                    folder_ids.append(p.name)
                    warnings.append(f"Meeting folder present locally but missing from drive-map.json: {year_path}/{p.name}")

        # Keep meta order, then any unlisted folders
        ordered = []
        seen = set()
        for m in sorted(meta["meetings"], key=lambda x: x.get("order", 99)):
            if m["yearId"] == y["id"] and m["id"] in folder_ids:
                ordered.append(m["id"])
                seen.add(m["id"])
        for fid in folder_ids:
            if fid not in seen:
                ordered.append(fid)

        for mid in ordered:
            mpath = f"{year_path}/{mid}"
            info = meta_by_id.get(mid, {
                "id": mid,
                "title": mid.replace("_", " "),
                "date": "",
                "dateLabel": "",
                "status": "",
                "summary": "",
            })
            notes = []
            evidence = []
            other = []
            children = [
                e for e in drive_map["entries"]
                if e["ns"] == "cycle" and e["path"].startswith(mpath + "/") and e["path"].count("/") == mpath.count("/") + 1
            ]
            # Also pick up unmapped local files
            if cycle_dir.is_dir() and (cycle_dir / mpath).is_dir():
                local_names = {c["name"] for c in children}
                for p in sorted((cycle_dir / mpath).iterdir()):
                    if p.is_file() and p.name not in SKIP_NAMES and p.name not in local_names:
                        children.append({"ns": "cycle", "path": f"{mpath}/{p.name}", "name": p.name, "kind": "file", "webViewLink": None})
                        warnings.append(f"Meeting file not in drive-map.json: {mpath}/{p.name}")

            for c in children:
                if c["kind"] == "folder":
                    continue
                rec = file_item(drive_index, "cycle", c["path"], c["name"])
                if is_notes_file(c["name"]):
                    notes.append(rec)
                elif is_evidence_file(c["name"]):
                    evidence.append(rec)
                elif not is_readme(c["name"]):
                    other.append(rec)

            def sort_key(r):
                # Prefer PDF notes first, then docx; evidence in E1, E2 order
                name = r["name"]
                if is_notes_file(name):
                    return (0, 0 if ext_of(name) == "pdf" else 1, name.lower())
                m = re.match(r"E(\d+)_", name)
                return (1, int(m.group(1)) if m else 99, name.lower())

            notes.sort(key=sort_key)
            evidence.sort(key=sort_key)
            meetings.append({
                "id": mid,
                "title": info.get("title") or mid,
                "date": info.get("date") or "",
                "dateLabel": info.get("dateLabel") or "",
                "status": info.get("status") or "",
                "summary": info.get("summary") or "",
                "folderUrl": link_for(drive_index, "cycle", mpath),
                "notes": notes,
                "evidence": evidence,
                "other": other,
            })

        years.append({
            "id": y["id"],
            "label": y["label"],
            "note": y.get("note") or "",
            "folderUrl": link_for(drive_index, "cycle", year_path),
            "meetings": meetings,
        })

    def files_in(ns: str, folder: str, include_readme=False):
        prefix = (folder + "/") if folder else ""
        depth = prefix.count("/")
        items = []
        for e in drive_map["entries"]:
            if e["ns"] != ns or e["kind"] != "file":
                continue
            if folder:
                if not e["path"].startswith(prefix) or e["path"].count("/") != depth:
                    continue
            if is_readme(e["name"]) and not include_readme:
                continue
            items.append(file_item(drive_index, ns, e["path"], e["name"]))
        items.sort(key=lambda r: (0 if r["name"].lower().startswith("readme") else 1, r["name"].lower()))
        return items

    index_files = files_in("cycle", "00_Index_and_Log")
    preview_files = files_in("cycle", "00_Index_and_Log/previews")

    quick_links = []
    for path, label in [
        ("00_Index_and_Log/OSUIT_ABET_Cycle_2026-2032_Binder.pdf", "Compiled binder (PDF)"),
        ("00_Index_and_Log/Cycle_Index.pdf", "Cycle index (PDF)"),
        ("00_Index_and_Log/Cycle_Index.docx", "Cycle index (Word)"),
        ("00_Index_and_Log/Running_Log.xlsx", "Running log (Excel)"),
        ("00_Index_and_Log/Running_Log.pdf", None),  # may not exist
    ]:
        url = link_for(drive_index, "cycle", path)
        if url:
            quick_links.append({"name": label or Path(path).name, "url": url, "type": ext_of(path)})

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cycle": {
            **meta["cycle"],
            "folderUrl": drive_map["cycle_root"]["webViewLink"],
            "backupUrl": drive_map["backup_root"]["webViewLink"],
            "previousFolderUrl": drive_map["previous_root"]["webViewLink"],
        },
        "hubPullRequest": meta.get("hubPullRequest"),
        "quickLinks": quick_links,
        "deadlines": meta["deadlines"],
        "openItems": meta["openItems"],
        "index": {
            "folderUrl": link_for(drive_index, "cycle", "00_Index_and_Log"),
            "files": index_files,
            "previews": preview_files,
        },
        "log": log_rows,
        "years": years,
        "assessment": {
            "folderUrl": link_for(drive_index, "cycle", "03_Assessment_Hub"),
            "latestUrl": link_for(drive_index, "cycle", "03_Assessment_Hub/Latest"),
            "previousUrl": link_for(drive_index, "cycle", "03_Assessment_Hub/Previous_Versions"),
            "dataUrl": link_for(drive_index, "cycle", "03_Assessment_Hub/Data"),
            "latest": files_in("cycle", "03_Assessment_Hub/Latest"),
            "previous": files_in("cycle", "03_Assessment_Hub/Previous_Versions"),
            "dataFiles": files_in("cycle", "03_Assessment_Hub/Data", include_readme=True),
            "note": "Current hub files live in Latest. Replaced files move to Previous Versions. Raw grade and assessment files go in Data. PR #3 is open and not live.",
        },
        "assessmentData": build_assessment_data(drive_index, warnings),
        "selfStudy": {
            "folderUrl": link_for(drive_index, "cycle", "01_Self_Study_and_Program_Review"),
            "files": files_in("cycle", "01_Self_Study_and_Program_Review", include_readme=True),
            "placeholder": True,
            "note": "Placeholder for this cycle’s self-study and program-review documents. The previous-cycle self-study stays in the archive and is not copied here.",
            "interim": {
                "folderUrl": link_for(drive_index, "cycle", "01_Self_Study_and_Program_Review/Interim_Review_Y3_2028-29"),
                "files": files_in("cycle", "01_Self_Study_and_Program_Review/Interim_Review_Y3_2028-29", include_readme=True),
                "placeholder": True,
                "note": "Year 3 (2028–29) mid-cycle interim review. This folder is ready for files when that work begins.",
            },
        },
        "outcomes": {
            "folderUrl": link_for(drive_index, "cycle", "02_Outcomes_and_HLC"),
            "files": files_in("cycle", "02_Outcomes_and_HLC", include_readme=True),
            "placeholder": True,
            "note": "Placeholder for this cycle’s outcomes-assessment and HLC documents.",
        },
        "previousCycle": {
            "folderUrl": drive_map["previous_root"]["webViewLink"],
            "note": "Archived final record from the last six-year cycle. Do not modify, move, or rename these files. The ETAC Self-Study is confidential and opens from your private Google Drive.",
            "readme": file_item(drive_index, "previous", "README.txt"),
            "sections": [
                {
                    "id": "01_Self_Study_and_Program_Review",
                    "title": "Self-Study and Program Review",
                    "folderUrl": link_for(drive_index, "previous", "01_Self_Study_and_Program_Review"),
                    "files": files_in("previous", "01_Self_Study_and_Program_Review"),
                    "confidential": ["OSUIT_ETAC_Self Study_2025.06.20_v2.pdf"],
                },
                {
                    "id": "02_Outcomes_and_HLC",
                    "title": "Outcomes and HLC",
                    "folderUrl": link_for(drive_index, "previous", "02_Outcomes_and_HLC"),
                    "files": files_in("previous", "02_Outcomes_and_HLC"),
                    "confidential": [],
                },
                {
                    "id": "03_Assessment_Hub",
                    "title": "Assessment Hub",
                    "folderUrl": link_for(drive_index, "previous", "03_Assessment_Hub"),
                    "files": [],
                    "latest": files_in("previous", "03_Assessment_Hub/Latest"),
                    "previous": files_in("previous", "03_Assessment_Hub/Previous_Versions"),
                    "latestUrl": link_for(drive_index, "previous", "03_Assessment_Hub/Latest"),
                    "previousUrl": link_for(drive_index, "previous", "03_Assessment_Hub/Previous_Versions"),
                    "confidential": [],
                },
                {
                    "id": "04_Meeting_Notes",
                    "title": "Meeting Notes (template)",
                    "folderUrl": link_for(drive_index, "previous", "04_Meeting_Notes"),
                    "files": files_in("previous", "04_Meeting_Notes"),
                    "confidential": [],
                },
            ],
        },
    }

    # Counts for the console and for a small stats block
    def count_urls(obj, acc=None):
        if acc is None:
            acc = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in {"url", "folderUrl", "backupUrl", "previousFolderUrl", "latestUrl", "previousUrl", "dataUrl", "readmeUrl"} and isinstance(v, str) and v:
                    acc.add(v)
                else:
                    count_urls(v, acc)
        elif isinstance(obj, list):
            for v in obj:
                count_urls(v, acc)
        return acc

    urls = count_urls(data)
    non_drive = [u for u in urls if "drive.google.com" not in u and "github.com" not in u]
    # hub PR is not a drive link and lives under hubPullRequest.url
    data["_meta"] = {
        "driveLinkCount": len([u for u in urls if "drive.google.com" in u]),
        "warnings": warnings,
    }
    if non_drive:
        warnings.append(f"Non-Drive URLs in data (excluding the hub PR): {non_drive}")

    return data, warnings


def write_data_js(data: dict, out: Path):
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Guard: the generated file must not embed raw document content.
    text = (
        "/* Generated by tools/generate-data.py — do not edit by hand. */\n"
        "/* This file lists titles, short summaries, and Google Drive links only. */\n"
        "window.ABET = "
        + payload
        + ";\n"
    )
    out.write_text(text, encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cycle", type=Path, default=DEFAULT_CYCLE)
    p.add_argument("--previous", type=Path, default=DEFAULT_PREVIOUS)
    p.add_argument("--out", type=Path, default=REPO / "data.js")
    args = p.parse_args(argv)

    data, warnings = build(args.cycle, args.previous)
    write_data_js(data, args.out)
    print(f"Wrote {args.out} ({args.out.stat().st_size} bytes)")
    print(f"Drive links: {data['_meta']['driveLinkCount']}")
    print(f"Log entries: {len(data['log'])}")
    meeting_count = sum(len(y['meetings']) for y in data['years'])
    print(f"Meetings: {meeting_count}")
    ad = data.get("assessmentData") or {}
    print(f"Assessment data: {'empty' if ad.get('empty') else str(len(ad.get('sections') or [])) + ' section(s)'}")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
