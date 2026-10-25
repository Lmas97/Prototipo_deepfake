"""Cola acotada de inferencia: una ejecución a la vez y progreso consultable."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from vericall.audit import AuditError
from vericall.detector import ModelUnavailable
from vericall.video import VideoError


class QueueFull(RuntimeError):
    pass


class JobManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vericall")
        self.lock = threading.Lock()
        self.jobs = {}

    def submit(self, operation) -> str:
        with self.lock:
            now = time.monotonic()
            self.jobs = {key: row for key, row in self.jobs.items()
                         if row["status"] in ("queued", "running") or now-row["created"] < 1800}
            if sum(row["status"] in ("queued", "running") for row in self.jobs.values()) >= 3:
                raise QueueFull("Hay tres análisis pendientes. Espera a que termine uno y vuelve a intentar.")
            completed = [key for key, row in self.jobs.items() if row["status"] in ("done", "failed")]
            for key in completed[:-97]:
                del self.jobs[key]
            job_id = str(uuid4())
            self.jobs[job_id] = {"id": job_id, "created": now, "status": "queued",
                                 "progress": 0, "message": "Esperando turno"}
        self.executor.submit(self._run, job_id, operation)
        return job_id

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)

    def _run(self, job_id, operation):
        try:
            self._update(job_id, status="running", progress=1, message="Validando entrada")
            entry = operation(lambda value, message: self._update(job_id, progress=value, message=message))
            self._update(job_id, status="done", progress=100, message="Análisis registrado", result=entry)
        except (VideoError, ModelUnavailable, AuditError) as error:
            self._update(job_id, status="failed", message=str(error))
        except Exception:
            logging.exception("Error interno en el análisis %s", job_id)
            self._update(job_id, status="failed", message="Ocurrió un error interno. No se emitió una decisión; revisa la consola local.")

    def get(self, job_id):
        with self.lock:
            row = self.jobs.get(job_id)
            if row is None or (row["status"] in ("done", "failed") and time.monotonic()-row["created"] >= 1800):
                return None
            return {key: value for key, value in row.items() if key != "created"}
