"""Bitácora SQLite encadenada por hash: metadatos y resultados, nunca videos o recortes."""

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

GENESIS = "0" * 64


class AuditError(RuntimeError):
    pass


class AlreadyResolved(RuntimeError):
    pass


def chain_hash(previous: str, payload: str) -> str:
    return hashlib.sha256(f"{previous}\n{payload}".encode()).hexdigest()


class AuditStore:
    """Registro de solo inserción. Cada fila sella la anterior: alterar una rompe la cadena."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, "
                       "kind TEXT NOT NULL, decision_id TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL, "
                       "prev_hash TEXT NOT NULL, hash TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS ledger_decision ON ledger(decision_id, kind)")
            # Migración de la tabla de la versión 2, sin encadenar.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='decisions'").fetchone():
                for row_id, created, payload in db.execute("SELECT id, created, payload FROM decisions ORDER BY created").fetchall():
                    if not db.execute("SELECT 1 FROM ledger WHERE id = ?", (row_id,)).fetchone():
                        self._append(db, "decision", row_id, row_id, created, payload)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _append(db, kind, row_id, decision_id, created, payload_text) -> dict:
        last = db.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else GENESIS
        digest = chain_hash(previous, payload_text)
        cursor = db.execute("INSERT INTO ledger (id, kind, decision_id, created, payload, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (row_id, kind, decision_id, created, payload_text, previous, digest))
        return {"seq": cursor.lastrowid, "hash": digest, "prev_hash": previous}

    def _write(self, kind, row_id, decision_id, entry) -> dict:
        try:
            with self._lock, self.connect() as db:
                return self._append(db, kind, row_id, decision_id, entry["timestamp_utc"],
                                    json.dumps(entry, ensure_ascii=False, allow_nan=False))
        except (sqlite3.Error, OSError) as error:
            raise AuditError("No se pudo guardar la bitácora. No se ha emitido una decisión.") from error

    def record(self, payload: dict) -> dict:
        entry = {**payload, "decision_id": str(uuid4()),
                 "timestamp_utc": datetime.now(timezone.utc).isoformat()}
        integrity = self._write("decision", entry["decision_id"], entry["decision_id"], entry)
        return {**entry, "integrity": integrity}

    def resolve(self, decision_id: str, build) -> dict:
        """`build(decision)` valida las reglas y devuelve la resolución; solo se admite una por decisión."""
        with self._lock:
            decision = self.get(decision_id)
            if decision is None:
                raise KeyError(decision_id)
            if decision.get("resolution"):
                raise AlreadyResolved("Esta decisión ya tiene una resolución registrada; no se puede modificar.")
            resolution = {**build(decision), "resolution_id": str(uuid4()), "decision_id": decision_id,
                          "timestamp_utc": datetime.now(timezone.utc).isoformat()}
            try:
                with self.connect() as db:
                    integrity = self._append(db, "resolution", resolution["resolution_id"], decision_id,
                                             resolution["timestamp_utc"], json.dumps(resolution, ensure_ascii=False, allow_nan=False))
            except (sqlite3.Error, OSError) as error:
                raise AuditError("No se pudo guardar la resolución; el pago sigue sin liberarse.") from error
        return {**resolution, "integrity": integrity}

    def _with_resolutions(self, db, rows) -> list[dict]:
        entries = []
        for payload, seq, digest, previous in rows:
            entry = json.loads(payload) | {"integrity": {"seq": seq, "hash": digest, "prev_hash": previous}}
            resolved = db.execute("SELECT payload, seq, hash, prev_hash FROM ledger WHERE decision_id = ? AND kind = 'resolution'",
                                  (entry["decision_id"],)).fetchone()
            if resolved:
                entry["resolution"] = json.loads(resolved[0]) | {"integrity": {"seq": resolved[1], "hash": resolved[2], "prev_hash": resolved[3]}}
            entries.append(entry)
        return entries

    def get(self, decision_id: str) -> dict | None:
        with self.connect() as db:
            rows = db.execute("SELECT payload, seq, hash, prev_hash FROM ledger WHERE id = ? AND kind = 'decision'", (decision_id,)).fetchall()
            entries = self._with_resolutions(db, rows)
        return entries[0] if entries else None

    def recent(self, limit=50) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT payload, seq, hash, prev_hash FROM ledger WHERE kind = 'decision' ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
            return self._with_resolutions(db, rows)

    def verify(self) -> dict:
        """Recalcula toda la cadena. Detecta filas editadas, borradas o insertadas fuera de la aplicación."""
        previous, count = GENESIS, 0
        with self.connect() as db:
            for seq, payload, prev_hash, digest in db.execute("SELECT seq, payload, prev_hash, hash FROM ledger ORDER BY seq"):
                count += 1
                if prev_hash != previous or chain_hash(prev_hash, payload) != digest:
                    return {"valid": False, "records": count, "first_invalid_seq": seq, "head": None}
                previous = digest
        return {"valid": True, "records": count, "first_invalid_seq": None, "head": previous}
