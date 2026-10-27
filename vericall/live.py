"""Monitoreo de una videollamada en curso. Analiza cuadros sueltos y descarta las imágenes."""

import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

import cv2
import numpy as np

from vericall.config import (LIVE_IDLE_SECONDS, LIVE_MAX_FRAME_BYTES, LIVE_MAX_FRAMES,
                             LIVE_MAX_SESSIONS, LIVE_PIPELINE_VERSION, LIVE_WINDOW_FRAMES,
                             MODEL_ID, MODEL_REVISION, MODEL_SHA256)
from vericall.detector import DETECTOR, FaceDetector
from vericall.pipeline import summarize
from vericall.video import VideoError

SOURCES = {"simulated": "Llamada simulada con video público",
           "file": "Llamada simulada con video propio",
           "camera": "Cámara web del equipo",
           "screen": "Ventana compartida de la videollamada"}


class SessionNotFound(KeyError):
    pass


class TooManySessions(RuntimeError):
    pass


def quality(brightness: list[float], differences: list[float]) -> dict:
    return {"dark_frame_ratio": round(sum(value < 25 for value in brightness) / len(brightness), 4) if brightness else 0,
            "frozen_transition_ratio": round(sum(value < 1.5 for value in differences) / len(differences), 4) if differences else 0}


def compact(summary: dict) -> dict:
    return {key: summary[key] for key in ("verdict", "predicted_label", "fake_score", "face_frames", "sampled_frames",
                                          "face_coverage", "sufficient_face_evidence", "multiple_faces", "quality")}


class LiveSession:
    def __init__(self, source: str, caller: str, sample_id: str | None, video_sha256: str | None = None):
        self.id = str(uuid4())
        self.source, self.caller, self.sample_id, self.video_sha256 = source, caller, sample_id, video_sha256
        self.started = self.last_seen = time.monotonic()
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self.frames, self.brightness, self.differences = [], [], []
        self.previous = None
        self.lock = threading.Lock()

    def summaries(self) -> tuple[dict, dict]:
        window = slice(-LIVE_WINDOW_FRAMES, None)
        call = summarize(self.frames, quality(self.brightness, self.differences))
        recent = summarize(self.frames[window], quality(self.brightness[window], self.differences[window]))
        return call, recent

    def snapshot(self) -> dict:
        call, recent = self.summaries()
        return {"session_id": self.id, "elapsed_seconds": round(time.monotonic() - self.started, 1),
                "call": compact(call), "recent_window": compact(recent),
                "alert": recent["verdict"] == "likely_manipulated"}


class LiveMonitor:
    def __init__(self, detector=None):
        self.detector = detector or DETECTOR
        self._faces = None
        self._lock = threading.Lock()
        self._inference = threading.Lock()
        self.sessions: dict[str, LiveSession] = {}

    def _purge(self):
        now = time.monotonic()
        self.sessions = {key: value for key, value in self.sessions.items() if now - value.last_seen < LIVE_IDLE_SECONDS}

    def start(self, source: str, caller: str, sample_id: str | None = None, video_sha256: str | None = None) -> LiveSession:
        with self._lock:
            self._purge()
            if len(self.sessions) >= LIVE_MAX_SESSIONS:
                raise TooManySessions("Hay tres llamadas monitoreadas a la vez. Finaliza una antes de iniciar otra.")
            session = LiveSession(source, caller, sample_id, video_sha256)
            self.sessions[session.id] = session
            return session

    def get(self, session_id: str) -> LiveSession:
        with self._lock:
            self._purge()
            session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound("La llamada no existe o expiró por inactividad. Inicia el monitoreo de nuevo.")
        session.last_seen = time.monotonic()
        return session

    def end(self, session_id: str):
        with self._lock:
            self.sessions.pop(session_id, None)

    def analyze_frame(self, session_id: str, data: bytes) -> dict:
        session = self.get(session_id)
        if not data or len(data) > LIVE_MAX_FRAME_BYTES:
            raise VideoError("El cuadro recibido está vacío o supera 3 MB.")
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise VideoError("El cuadro recibido no es una imagen válida.")
        height, width = frame.shape[:2]
        if width < 32 or height < 32 or width * height > 4096 * 2160:
            raise VideoError("El cuadro debe medir entre 32 px y 4096 × 2160.")
        with session.lock:
            if len(session.frames) >= LIVE_MAX_FRAMES:
                raise VideoError("La llamada alcanzó el máximo de cuadros analizables. Finalízala e inicia otra.")
            timestamp = round(time.monotonic() - session.started, 3)
            gray = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
            with self._inference:
                if self._faces is None:
                    self._faces = FaceDetector()
                faces = self._faces.find(frame)
                crops = [face.pop("crop") for face in faces]
                scores = self.detector.predict(crops) if crops else []
            # La imagen y los recortes salen de memoria aquí: solo se conservan señales.
            del frame, crops
            for face, score in zip(faces, scores, strict=True):
                face["fake_score"] = round(float(score), 5)
            row = {"timestamp": timestamp, "fake_score": max((face["fake_score"] for face in faces), default=None),
                   "faces": faces}
            session.brightness.append(float(gray.mean()))
            if session.previous is not None:
                session.differences.append(float(cv2.absdiff(gray, session.previous).mean()))
            session.previous = gray
            session.frames.append(row)
            return {"frame": row, **session.snapshot()}

    def detection(self, session_id: str) -> tuple[LiveSession, dict]:
        """Evidencia para una transferencia: la más desfavorable entre toda la llamada y los últimos segundos."""
        session = self.get(session_id)
        with session.lock:
            call, recent = session.summaries()
            frames = [dict(row) for row in session.frames]
        candidates = [("call", call), ("recent_window", recent)]
        sufficient = [item for item in candidates if item[1]["sufficient_face_evidence"]]
        basis, chosen = max(sufficient, key=lambda item: item[1]["fake_score"]) if sufficient else candidates[0]
        duration = round(time.monotonic() - session.started, 3)
        return session, {**chosen, "decision_basis": basis,
                         "call_summary": compact(call), "recent_window": compact(recent),
                         "recent_window_frames": LIVE_WINDOW_FRAMES,
                         "frames": frames, "duration_seconds": duration,
                         "live": {"source": session.source, "source_label": SOURCES[session.source],
                                  "caller_claimed_identity": session.caller, "sample_id": session.sample_id,
                                  "local_video_sha256": session.video_sha256,
                                  "call_started_utc": session.started_utc},
                         "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "sha256": MODEL_SHA256,
                                   "executed": any(row["faces"] for row in frames), "device": "cpu",
                                   "face_detector": "YuNet-2023mar"},
                         "pipeline_version": LIVE_PIPELINE_VERSION,
                         "scope": "Señal visual en vivo de manipulación facial; no verifica voz, identidad ni intención de fraude."}
