"""Inferencia real con pesos locales: YuNet localiza y ViT clasifica rostros."""

import hashlib
import json
import threading
from pathlib import Path

import cv2
import numpy as np

from vericall.config import (FACE_MODEL, FACE_MODEL_SHA256, MODEL_DIR,
                             MODEL_ID, MODEL_REVISION, MODEL_SHA256)


class ModelUnavailable(RuntimeError):
    pass


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_status() -> dict:
    required = [FACE_MODEL, MODEL_DIR / "model.safetensors", MODEL_DIR / "config.json",
                MODEL_DIR / "preprocessor_config.json"]
    missing = [p.name for p in required if not p.exists()]
    return {"available": not missing, "missing": missing, "model_id": MODEL_ID,
            "revision": MODEL_REVISION, "device": "CPU", "runtime_network": False}


class FaceDetector:
    def __init__(self):
        if not FACE_MODEL.exists() or digest_file(FACE_MODEL) != FACE_MODEL_SHA256:
            raise ModelUnavailable("Falta el localizador de rostros o su archivo está dañado. Ejecuta scripts/download_assets.py.")
        self.detector = cv2.FaceDetectorYN_create(str(FACE_MODEL), "", (320, 320), 0.85, 0.3, 1000)

    def find(self, frame: np.ndarray) -> list[dict]:
        height, width = frame.shape[:2]
        scale = min(1.0, 640 / max(height, width))
        small = cv2.resize(frame, (round(width * scale), round(height * scale)))
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, found = self.detector.detect(small)
        if found is None:
            return []
        faces = []
        for face in sorted(found, key=lambda face: float(face[2] * face[3]), reverse=True)[:4]:
            x, y, w, h = (float(value) / scale for value in face[:4])
            if min(w, h) < 48:
                continue
            # Recorte cuadrado con contexto de contorno, igual en todos los casos.
            side = max(w, h) * 1.4
            cx, cy = x + w / 2, y + h / 2
            left, top = max(0, int(cx - side / 2)), max(0, int(cy - side / 2))
            right, bottom = min(width, int(cx + side / 2)), min(height, int(cy + side / 2))
            if right <= left or bottom <= top:
                continue
            faces.append({"crop": cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2RGB),
                          "box": [round(left / width, 5), round(top / height, 5),
                                  round((right-left) / width, 5), round((bottom-top) / height, 5)],
                          "confidence": round(float(face[-1]), 4)})
        return faces


class DeepfakeDetector:
    """Carga única, Safetensors, sin descargas ni código remoto durante el análisis."""

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is not None:
            return
        if not model_status()["available"]:
            raise ModelUnavailable("El modelo no está instalado. Ejecuta: python scripts/download_assets.py")
        if digest_file(MODEL_DIR / "model.safetensors") != MODEL_SHA256:
            raise ModelUnavailable("Los pesos no coinciden con el hash verificado. Descarga nuevamente los activos.")
        from vericall.config import ROOT
        manifest = json.loads((ROOT / "config/assets.json").read_text())["assets"]
        for filename in ("config.json", "preprocessor_config.json"):
            asset = next(row for row in manifest if row["path"] == f"models/deepfake-vit/{filename}")
            if digest_file(MODEL_DIR / filename) != asset["sha256"]:
                raise ModelUnavailable("La configuración del detector no coincide con la revisión verificada.")
        import torch
        from transformers import ViTForImageClassification, ViTImageProcessor
        torch.set_num_threads(4)
        self._processor = ViTImageProcessor.from_pretrained(str(MODEL_DIR), local_files_only=True)
        model = ViTForImageClassification.from_pretrained(
            str(MODEL_DIR), local_files_only=True, use_safetensors=True, trust_remote_code=False)
        labels = {int(key): str(value).lower() for key, value in model.config.id2label.items()}
        if labels != {0: "realism", 1: "deepfake"}:
            raise ModelUnavailable("Las etiquetas del modelo no coinciden con la configuración esperada.")
        self._model = model.cpu().eval()

    def predict(self, crops: list[np.ndarray]) -> list[float]:
        import torch
        with self._lock:
            self._load()
            values = []
            with torch.inference_mode():
                for start in range(0, len(crops), 8):
                    inputs = self._processor(images=crops[start:start+8], return_tensors="pt")
                    logits = self._model(**inputs).logits
                    values.extend(torch.softmax(logits, dim=-1)[:, 1].cpu().tolist())
        if not all(np.isfinite(value) and 0 <= value <= 1 for value in values):
            raise ModelUnavailable("El modelo devolvió una salida inválida; no se puede emitir una decisión.")
        return values


DETECTOR = DeepfakeDetector()
