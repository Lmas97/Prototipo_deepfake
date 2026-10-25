"""Interfaz web local para evaluar una solicitud ficticia."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from vericall.audit import recent, record
from vericall.decision import InputError, evaluate, positive_money
from vericall.video import VideoError, analyze_video


ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "sample_data"
CASES = {case["id"]: case for case in json.loads((SAMPLES / "cases.json").read_text(encoding="utf-8"))}
ALLOWED_SUFFIXES = {".avi", ".mp4"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_app(audit_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("VERICALL_MAX_UPLOAD_MB", "25")) * 1024 * 1024
    app.config["AUDIT_PATH"] = Path(audit_path or os.environ.get("VERICALL_AUDIT_PATH", ROOT / "instance/decisions.jsonl"))

    @app.get("/")
    def home():
        return render_template("index.html", cases=CASES.values(), result=None, error=None)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "vericall-mvp"}

    @app.get("/samples/<sample_id>")
    def sample_download(sample_id: str):
        case = CASES.get(sample_id)
        if not case:
            abort(404)
        return send_file(SAMPLES / case["video"], as_attachment=True)

    @app.get("/audit")
    def audit_view():
        entries = recent(app.config["AUDIT_PATH"])
        return render_template("audit.html", entries=entries)

    @app.post("/assess")
    def assess():
        path = None
        temporary = False
        try:
            if request.form.get("consent") != "yes":
                raise InputError("Se requiere consentimiento declarado para procesar el video.")

            sample_id = request.form.get("sample_id", "custom")
            if sample_id == "custom":
                amount = request.form.get("amount")
                limit = request.form.get("limit")
                new_beneficiary = request.form.get("new_beneficiary") == "yes"
                alternate_verified = request.form.get("alternate_verified") == "yes"
                upload = request.files.get("video")
                if upload is None or not upload.filename:
                    raise InputError("Selecciona un archivo AVI o MP4.")
                filename = upload.filename
            else:
                case = CASES.get(sample_id)
                if case is None:
                    raise InputError("El caso de muestra solicitado no existe.")
                amount, limit = case["amount"], case["limit"]
                new_beneficiary = case["new_beneficiary"]
                alternate_verified = case["alternate_verified"]
                filename = case["video"]

            positive_money(amount, "El monto")
            positive_money(limit, "El límite")
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise InputError("Formato no admitido. Usa un video AVI o MP4.")

            if sample_id == "custom":
                with tempfile.NamedTemporaryFile(prefix="vericall_", suffix=suffix, delete=False) as file:
                    path = Path(file.name)
                    temporary = True
                    upload.save(file)
            else:
                path = SAMPLES / case["video"]

            video_hash = sha256_file(path)
            metrics = analyze_video(path)
            result = evaluate(amount=amount, limit=limit,
                              new_beneficiary=new_beneficiary,
                              alternate_verified=alternate_verified,
                              video_metrics=metrics)
            entry = record(app.config["AUDIT_PATH"], video_sha256=video_hash,
                           result=result, sample_id=None if sample_id == "custom" else sample_id)
            return render_template("index.html", cases=CASES.values(), result=entry, error=None)
        except (InputError, VideoError) as error:
            return render_template("index.html", cases=CASES.values(), result=None, error=str(error)), 400
        finally:
            if temporary and path is not None:
                path.unlink(missing_ok=True)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return render_template("index.html", cases=CASES.values(), result=None,
                               error="El archivo supera el tamaño máximo configurado."), 413

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
