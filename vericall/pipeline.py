"""Muestreo de video y detección visual. No recibe etiquetas ni nombres del dataset."""

import math
import time
from pathlib import Path

import cv2
import numpy as np

from vericall.config import (HIGH_THRESHOLD, LOW_THRESHOLD, MAX_DURATION_SECONDS,
                             MAX_VIDEO_BYTES, MIN_COVERAGE, MIN_FACE_FRAMES,
                             MODEL_ID, MODEL_REVISION, MODEL_SHA256, PIPELINE_VERSION, SAMPLE_FRAMES)
from vericall.detector import DETECTOR, FaceDetector
from vericall.video import VideoError


def summarize(frame_results: list[dict], quality: dict) -> dict:
    scores = [row["fake_score"] for row in frame_results if row["fake_score"] is not None]
    coverage = len(scores) / len(frame_results) if frame_results else 0
    average = float(np.mean(scores)) if scores else None
    enough = len(scores) >= MIN_FACE_FRAMES and coverage >= MIN_COVERAGE
    if not enough:
        verdict = "inconclusive"
    elif average >= HIGH_THRESHOLD:
        verdict = "likely_manipulated"
    elif average <= LOW_THRESHOLD:
        verdict = "no_strong_signals"
    else:
        verdict = "inconclusive"
    return {
        "verdict": verdict,
        "predicted_label": ("fake" if average >= 0.5 else "real") if enough else "unknown",
        "classification_threshold": 0.5,
        "fake_score": round(average, 5) if average is not None else None,
        "score_std": round(float(np.std(scores)), 5) if scores else None,
        "face_frames": len(scores), "sampled_frames": len(frame_results),
        "face_coverage": round(coverage, 4), "sufficient_face_evidence": enough,
        "multiple_faces": any(len(row["faces"]) > 1 for row in frame_results),
        "quality": quality,
        "thresholds": {"low": LOW_THRESHOLD, "high": HIGH_THRESHOLD,
                       "minimum_face_frames": MIN_FACE_FRAMES, "minimum_coverage": MIN_COVERAGE},
        "aggregation": "mean_of_frame_max_face_scores",
    }


def analyze(path: Path, progress=None, detector=None) -> dict:
    progress = progress or (lambda percent, message: None)
    detector = detector or DETECTOR
    started = time.monotonic()
    if path.stat().st_size > MAX_VIDEO_BYTES:
        raise VideoError("El video supera los 100 MB admitidos.")
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise VideoError("No se pudo abrir el archivo como video válido.")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not all(math.isfinite(value) for value in (fps, count, width, height)):
            raise VideoError("El video contiene metadatos inválidos.")
        if not 1 <= fps <= 120 or count < 12 or width < 32 or height < 32:
            raise VideoError("El video necesita al menos 12 cuadros y metadatos válidos.")
        duration = count / fps
        if duration > MAX_DURATION_SECONDS or width * height > 4096 * 2160:
            raise VideoError("Usa un video de hasta 2 minutos y resolución máxima de 4096 × 2160.")
        progress(10, "Localizando rostros en el video")
        face_detector = FaceDetector()
        indices = np.unique(np.linspace(0, int(count)-1, min(SAMPLE_FRAMES, int(count)), dtype=int))
        frame_results, crops, associations, brightness, sharpness = [], [], [], [], []
        differences, previous = [], None
        for number, index in enumerate(indices):
            if time.monotonic() - started > 90:
                raise VideoError("La decodificación excedió el tiempo permitido. Prueba un clip más corto.")
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
            brightness.append(float(gray.mean()))
            sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            if previous is not None:
                differences.append(float(cv2.absdiff(gray, previous).mean()))
            previous = gray
            faces = face_detector.find(frame)
            row = {"timestamp": round(int(index) / fps, 3), "frame_index": int(index),
                   "fake_score": None, "faces": []}
            for face in faces:
                associations.append((len(frame_results), len(row["faces"])))
                crops.append(face.pop("crop"))
                row["faces"].append(face)
            frame_results.append(row)
            progress(10 + round(35 * (number+1)/len(indices)), "Extrayendo rostros y midiendo calidad")
        if len(frame_results) < len(indices) * 0.8:
            raise VideoError("No se pudieron decodificar suficientes cuadros. El archivo puede estar incompleto.")
    finally:
        capture.release()
    if crops:
        progress(50, "Ejecutando el modelo de deepfakes en CPU")
        scores = detector.predict(crops)
        for (row_index, face_index), score in zip(associations, scores, strict=True):
            frame_results[row_index]["faces"][face_index]["fake_score"] = round(float(score), 5)
        for row in frame_results:
            if row["faces"]:
                row["fake_score"] = max(face["fake_score"] for face in row["faces"])
    progress(90, "Agregando evidencia del video")
    quality = {"dark_frame_ratio": round(sum(value < 25 for value in brightness) / len(brightness), 4),
               "frozen_transition_ratio": round(sum(value < 1.5 for value in differences) / len(differences), 4) if differences else 0,
               "mean_sharpness": round(float(np.mean(sharpness)), 2)}
    result = summarize(frame_results, quality)
    result.update({"frames": frame_results, "duration_seconds": round(duration, 3),
                   "width": int(width), "height": int(height), "fps": round(fps, 3),
                   "declared_frame_count": int(count), "elapsed_seconds": round(time.monotonic()-started, 3),
                   "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "sha256": MODEL_SHA256,
                             "executed": bool(crops), "device": "cpu", "face_detector": "YuNet-2023mar"},
                   "pipeline_version": PIPELINE_VERSION,
                   "scope": "Señal visual de manipulación facial; no verifica voz, identidad ni intención de fraude."})
    return result
