"""Evalúa TODAS las muestras declaradas; no selecciona solo los aciertos."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vericall.detector import digest_file
from vericall.pipeline import analyze


def main():
    assets = json.loads((ROOT / "config/assets.json").read_text())["assets"]
    rows = []
    for sample in [a for a in assets if a["group"] == "samples"]:
        path = ROOT / sample["path"]
        if digest_file(path) != sample["sha256"]:
            raise RuntimeError(f"Hash incorrecto: {sample['id']}")
        detection = analyze(path)
        row = {"id": sample["id"], "reference_label": sample["reference_label"],
               "video_sha256": sample["sha256"], "source_url": sample["url"],
               "correct_binary_prediction": sample["reference_label"] == detection["predicted_label"],
               "detection": detection}
        rows.append(row)
        print(f"{row['id']}: referencia={row['reference_label']}, predicción={detection['predicted_label']}, señal={detection['fake_score']}, certeza={detection['verdict']}", flush=True)
    report = {"evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "Demostración de desarrollo: seis ejemplos, no una validación independiente de desempeño.",
              "selection": "IDs 1, 4 y 5 elegidos por tamaño antes de observar predicciones.",
              "total": len(rows), "correct_binary_predictions": sum(row["correct_binary_prediction"] for row in rows),
              "false_negatives": [row["id"] for row in rows if row["reference_label"] == "fake" and row["detection"]["predicted_label"] == "real"],
              "false_positives": [row["id"] for row in rows if row["reference_label"] == "real" and row["detection"]["predicted_label"] == "fake"],
              "uncertain": [row["id"] for row in rows if row["detection"]["verdict"] == "inconclusive"], "results": rows}
    output = ROOT / "reports/sample_evaluation.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Informe completo: {output}", flush=True)


if __name__ == "__main__":
    main()
