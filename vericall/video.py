"""Medidas técnicas de un video; no autentican personas ni detectan deepfakes."""

from pathlib import Path

import cv2
import numpy as np


class VideoError(ValueError):
    pass


def analyze_video(path: Path) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoError("No se pudo abrir el archivo como video AVI o MP4 válido.")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not 1 <= fps <= 120 or width < 1 or height < 1:
            raise VideoError("El video no tiene metadatos de cuadros válidos.")
        if width * height > 1920 * 1080 or declared_frames > 3600:
            raise VideoError("El video supera el límite de resolución o duración de esta demostración.")

        frames = 0
        dark = 0
        frozen = 0
        comparisons = 0
        previous = None
        while frames < 900:
            ok, frame = capture.read()
            if not ok:
                break
            frames += 1
            if frames % 3 != 1:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (64, 48), interpolation=cv2.INTER_AREA)
            if float(small.mean()) < 25:
                dark += 1
            if previous is not None:
                comparisons += 1
                difference = float(np.mean(cv2.absdiff(small, previous)))
                if difference < 1.5:
                    frozen += 1
            previous = small
        if frames < 12:
            raise VideoError("El video es demasiado corto o no contiene suficientes cuadros decodificables.")
        if frames >= 900 and declared_frames > 900:
            raise VideoError("El video supera los 900 cuadros admitidos en esta demostración.")
        sampled = (frames + 2) // 3
        return {
            "width": width,
            "height": height,
            "fps": round(fps, 2),
            "decoded_frames": frames,
            "duration_seconds": round(frames / fps, 2),
            "sampled_frames": sampled,
            "dark_frame_ratio": round(dark / sampled, 3),
            "frozen_transition_ratio": round(frozen / comparisons, 3) if comparisons else 0.0,
        }
    finally:
        capture.release()
