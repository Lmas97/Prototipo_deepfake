"""Límites explícitos de la demostración local."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models/deepfake-vit"
FACE_MODEL = ROOT / "models/face_detection_yunet_2023mar.onnx"
MODEL_ID = "prithivMLmods/Deep-Fake-Detector-v2-Model"
MODEL_REVISION = "3a99ae26f52c7ac7c3a53103b6cf3a8b617f7093"
MODEL_SHA256 = "88ac0939285009e3700cfc9b9a0912b14b092d200ef0df86efe4f2cf190ea4de"
FACE_MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
PIPELINE_VERSION = "faces-vit-v2.0"
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_DURATION_SECONDS = 120
SAMPLE_FRAMES = 24
LOW_THRESHOLD = 0.25
HIGH_THRESHOLD = 0.75
MIN_FACE_FRAMES = 4
MIN_COVERAGE = 0.5

# Monitoreo en vivo: cuadros sueltos enviados por el navegador durante la llamada.
LIVE_PIPELINE_VERSION = "live-faces-vit-v1.0"
LIVE_WINDOW_FRAMES = 16
LIVE_MAX_FRAMES = 3600
LIVE_MAX_FRAME_BYTES = 3 * 1024 * 1024
LIVE_MAX_SESSIONS = 3
LIVE_IDLE_SECONDS = 600
# Entregable 2, criterio de oportunidad: liberar un pago retenido en ≤ 15 minutos.
RESOLUTION_SLA_SECONDS = 15 * 60
