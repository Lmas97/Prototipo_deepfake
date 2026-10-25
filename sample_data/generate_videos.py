"""Regenera dos videos AVI pequeños, enteramente sintéticos y sin personas."""

from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent / "videos"


def make_video(name: str, frozen: bool) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    destination = ROOT / name
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"MJPG"), 12, (320, 240))
    if not writer.isOpened():
        raise RuntimeError(f"No se pudo crear {destination}")
    try:
        for index in range(36):
            frame = np.full((240, 320, 3), (80, 70, 60), dtype=np.uint8)
            position = 30 if frozen else 20 + index * 6
            cv2.rectangle(frame, (position, 65), (position + 65, 165), (30, 200, 240), -1)
            cv2.circle(frame, (250, 50), 24, (230, 230, 70), -1)
            writer.write(frame)
    finally:
        writer.release()


if __name__ == "__main__":
    make_video("moving_shapes.avi", frozen=False)
    make_video("frozen_shapes.avi", frozen=True)
    print("Videos sintéticos generados en sample_data/videos")
