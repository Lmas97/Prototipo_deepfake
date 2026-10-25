"""Bitácora transaccional SQLite: metadatos y resultados, nunca videos o recortes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class AuditError(RuntimeError):
    pass


class AuditStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS decisions_created ON decisions(created DESC)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, payload: dict) -> dict:
        entry = {**payload, "decision_id": str(uuid4()),
                 "timestamp_utc": datetime.now(timezone.utc).isoformat()}
        try:
            with self.connect() as db:
                db.execute("INSERT INTO decisions VALUES (?, ?, ?)",
                           (entry["decision_id"], entry["timestamp_utc"], json.dumps(entry, ensure_ascii=False, allow_nan=False)))
        except (sqlite3.Error, OSError) as error:
            raise AuditError("No se pudo guardar la bitácora. No se ha emitido una decisión.") from error
        return entry

    def get(self, decision_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, limit=50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM decisions ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]
