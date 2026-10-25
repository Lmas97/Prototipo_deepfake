"""Registro local mínimo, sin conservar video ni biometría."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def record(audit_path: Path, *, video_sha256: str, result: dict, sample_id: str | None) -> dict:
    entry = {
        "decision_id": str(uuid4()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "video_sha256": video_sha256,
        "sample_id": sample_id,
        **result,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def recent(audit_path: Path, limit: int = 20) -> list[dict]:
    if not audit_path.exists():
        return []
    with audit_path.open(encoding="utf-8") as file:
        lines = file.readlines()[-limit:]
    return [json.loads(line) for line in reversed(lines)]
