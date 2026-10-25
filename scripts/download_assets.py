"""Descarga activos fijados por revisión y verifica integridad. Solo instalación."""

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset):
    target = ROOT / asset["path"]
    if target.exists() and (not asset.get("sha256") or file_digest(target) == asset["sha256"]):
        print(f"Disponible: {asset['path']}", flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    for attempt in range(3):
        try:
            print(f"Descargando {asset['path']}...", flush=True)
            request = urllib.request.Request(asset["url"], headers={"User-Agent": "VeriCall-academic-prototype/2.0"})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
                size = 0
                last_report = time.monotonic()
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > asset.get("max_bytes", 400_000_000):
                        raise ValueError("La descarga supera el límite esperado.")
                    output.write(chunk)
                    if time.monotonic() - last_report > 15:
                        print(f"  {size / 1_000_000:.1f} MB", flush=True)
                        last_report = time.monotonic()
            if asset.get("sha256") and file_digest(temporary) != asset["sha256"]:
                raise ValueError("El hash SHA-256 no coincide con la fuente fijada.")
            temporary.replace(target)
            print(f"Listo: {target.name} ({size / 1_000_000:.1f} MB)", flush=True)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["model", "samples", "all"], default="all")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "config/assets.json").read_text())
    print("Modelo Apache-2.0. Videos de Unidata CC BY-NC-ND 4.0, para demostración académica sin modificaciones.", flush=True)
    for asset in manifest["assets"]:
        if args.only in ("all", asset["group"]):
            download(asset)


if __name__ == "__main__":
    main()
