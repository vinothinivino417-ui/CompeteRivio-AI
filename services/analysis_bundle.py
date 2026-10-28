"""Portable exports built only from the exact report snapshot; no external calls."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import uuid
import zipfile

from services.history_backup import SNAPSHOT_FIELDS
from services.keyword_analysis import build_keyword_analysis
from services.competitor_evidence import METRICS


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _csv_bytes(rows, columns):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        cells = {}
        for key in columns:
            value = row.get(key)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, allow_nan=False)
            # Names and user-entered text must remain text in spreadsheet apps.
            if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
                value = "'" + value
            cells[key] = value
        writer.writerow(cells)
    return output.getvalue().encode("utf-8-sig")


def create_analysis_bundle(snapshot, pdf_bytes, saved_record=None):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("business"), dict) or not isinstance(snapshot.get("competitors"), list) or not isinstance(snapshot.get("report"), str):
        raise ValueError("A complete report snapshot is required for this download.")
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("The PDF report is unavailable.")
    exported = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = {key: value for key, value in snapshot.items() if key in SNAPSHOT_FIELDS}
    business, competitors = snapshot["business"], snapshot["competitors"]
    entities = [("B1", business)] + [(f"C{index}", row) for index, row in enumerate(competitors, 1)]
    measurements = []
    for reference, entity in entities:
        evidence = entity.get("User-supplied evidence (not independently verified)", {})
        score = entity.get("Partial evidence scoring", {})
        evidence = evidence if isinstance(evidence, dict) else {}
        score = score if isinstance(score, dict) else {}
        measurements.append({"Reference": reference, "Name": entity.get("name" if reference == "B1" else "Name"),
                             **{key: evidence.get(key) for key in [*METRICS, "Source", "Observed On"]},
                             **{key: score.get(key) for key in ["Evidence score", "PRD weight coverage (%)", "Selected weight coverage (%)", "Applied weights", "Breakdown", "Category contributions", "Gap vs competitor average"]}})
    keywords = build_keyword_analysis(business, competitors)
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    record = {"id": saved_record["id"] if saved_record else uuid.uuid4().hex, "schema_version": 1,
              "created_at": saved_record["created_at"] if saved_record else exported,
              "fingerprint": fingerprint, "snapshot": snapshot}
    files = {
        "report.pdf": pdf_bytes,
        "report.md": snapshot["report"].encode("utf-8"),
        "analysis_snapshot.json": _json_bytes(snapshot),
        "history_backup.json": _json_bytes({"schema_version": 1, "analyses": [record]}),
        "competitors.csv": _csv_bytes(competitors, ["Name", "Category", "Distance (km)", "Classification", "Confidence", "AI Reason", "Discovery source", "OSM ID", "OSM Type", "Website"]),
        "evidence_and_scores.csv": _csv_bytes(measurements, ["Reference", "Name", *METRICS, "Source", "Observed On", "Evidence score", "PRD weight coverage (%)", "Selected weight coverage (%)", "Applied weights", "Breakdown", "Category contributions", "Gap vs competitor average"]),
        "captured_keyword_observations.csv": _csv_bytes(keywords["Observations"], ["Term", "Business", "Evidence ID", "Source URL", "Retrieved at (UTC)"]),
        "README.txt": (
            "CompeteRivio AI - complete analysis export\n\n"
            "report.pdf / report.md: the saved report.\n"
            "analysis_snapshot.json: business, selected competitors, website captures, manual evidence, scores, search settings and report.\n"
            "competitors.csv: selected map listings and AI classifications.\n"
            "evidence_and_scores.csv: supplied measurements, sources, observation dates and partial scoring configuration. Blank cells mean unavailable; sourced zero values stay zero.\n"
            "captured_keyword_observations.csv: terms found in captured page samples, with source URLs and retrieval times. A headers-only file means no terms were captured.\n"
            "history_backup.json: extract this file, then upload it under Analysis History > Restore a history backup. A current report is saved as of export time; an archived report keeps its original save date.\n"
            "manifest.json: export time and SHA-256 checksums for every other file. Checksums detect file changes; they do not verify business claims or evidence accuracy.\n\n"
            "No evidence was refreshed to make this export. Export/save time is not an observation date. AI classifications and suggestions remain unverified. Scores are partial and relative to the selected group. Captured terms do not establish search demand or rankings.\n"
            "CSV text that could be interpreted as a spreadsheet formula is prefixed with an apostrophe. Exact original values remain in analysis_snapshot.json.\n"
        ).encode("utf-8"),
    }
    files["manifest.json"] = _json_bytes({"schema_version": 1, "exported_at_utc": exported,
                                         "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in files.items()}})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()
