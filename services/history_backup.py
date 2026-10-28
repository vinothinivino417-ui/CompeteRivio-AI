"""Validate and merge local report backups without replacing active analysis data."""
import copy
from datetime import datetime
import hashlib
import json
import math
import uuid

from services.analysis_history import MAX_HISTORY

MAX_BACKUP_BYTES = 20 * 1024 * 1024
SNAPSHOT_FIELDS = {"business", "competitors", "category", "radius_km", "discovered_count", "selection_mode", "report", "report_version"}


def _fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _check_json(value, depth=0):
    if depth > 20:
        raise ValueError("The backup contains excessively nested data.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("The backup contains an invalid number.")
    if isinstance(value, dict):
        for child in value.values():
            _check_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json(child, depth + 1)


def _validate_record(record):
    if not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        raise ValueError("Unsupported saved analysis format in backup.")
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("A saved analysis is missing its snapshot.")
    business, rows, report = snapshot.get("business"), snapshot.get("competitors"), snapshot.get("report")
    if not isinstance(business, dict) or not isinstance(business.get("name"), str) or not business["name"].strip():
        raise ValueError("Each saved analysis must have a business name.")
    if not isinstance(rows, list) or len(rows) > 1000 or not all(isinstance(row, dict) and isinstance(row.get("Name"), str) for row in rows):
        raise ValueError("A saved competitor list is invalid.")
    if not isinstance(report, str) or not report.strip() or len(report) > 2_000_000:
        raise ValueError("Each saved analysis must contain a valid report.")
    for entity in [business] + rows:
        for key in ("osm_type", "osm_id", "latitude", "longitude", "OSM Type", "OSM ID", "Latitude", "Longitude", "Classification", "Category", "location"):
            if key in entity and entity[key] is not None and not isinstance(entity[key], (str, int, float)):
                raise ValueError("A saved listing contains an invalid field.")
    for field in ("category", "selection_mode"):
        if snapshot.get(field) is not None and not isinstance(snapshot[field], str):
            raise ValueError("Saved search settings are invalid.")
    radius = snapshot.get("radius_km")
    if radius is not None and (isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius < 0):
        raise ValueError("Saved search radius is invalid.")
    try:
        created = datetime.fromisoformat(record["created_at"])
        if created.tzinfo is None:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ValueError("A saved analysis has an invalid save time.") from None
    clean = copy.deepcopy({key: value for key, value in snapshot.items() if key in SNAPSHOT_FIELDS})
    return {"schema_version": 1, "created_at": created.isoformat(timespec="seconds"), "snapshot": clean, "fingerprint": _fingerprint(clean)}


def prepare_history_restore(state, payload):
    """Return a validated merge preview. Never modify state or trust supplied hashes/IDs."""
    if not isinstance(payload, bytes) or len(payload) > MAX_BACKUP_BYTES:
        raise ValueError("Choose a JSON history backup no larger than 20 MB.")
    try:
        document = json.loads(payload.decode("utf-8-sig"))
        _check_json(document)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("This file is not a readable JSON history backup.") from None
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("Unsupported history backup format.")
    records = document.get("analyses")
    if not isinstance(records, list) or len(records) > MAX_HISTORY:
        raise ValueError("A backup must contain a list of at most 50 analyses.")
    validated = [_validate_record(record) for record in records]
    existing = list(state.get("analysis_history", []))
    fingerprints = {_fingerprint(record["snapshot"]) for record in existing}
    ids = {record["id"] for record in existing}
    added, duplicates = [], 0
    for record in sorted(validated, key=lambda row: datetime.fromisoformat(row["created_at"])):
        if record["fingerprint"] in fingerprints:
            duplicates += 1
            continue
        identifier = uuid.uuid4().hex
        while identifier in ids:
            identifier = uuid.uuid4().hex
        record["id"] = identifier
        ids.add(identifier)
        fingerprints.add(record["fingerprint"])
        added.append(record)
    if len(existing) + len(added) > MAX_HISTORY:
        raise ValueError(f"This backup would exceed 50 saved runs. Make space for {len(existing) + len(added) - MAX_HISTORY} run(s) before restoring. Nothing was imported.")
    return {"history": existing + added, "added": len(added), "duplicates": duplicates}


def restore_history(state, payload):
    result = prepare_history_restore(state, payload)
    if result["added"]:
        state["analysis_history"] = result["history"]
        state.pop("analysis_history_warning", None)
    return {key: result[key] for key in ("added", "duplicates")}
