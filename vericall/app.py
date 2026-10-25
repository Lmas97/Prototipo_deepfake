"""Interfaz local y API para detección visual de deepfakes y decisión de tesorería."""

import json
import os
import tempfile
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from vericall.audit import AuditStore
from vericall.config import MAX_VIDEO_BYTES, ROOT
from vericall.decision import InputError, evaluate, positive_money
from vericall.detector import digest_file, model_status
from vericall.jobs import JobManager, QueueFull
from vericall.pipeline import analyze


ASSETS = json.loads((ROOT / "config/assets.json").read_text())["assets"]
PUBLIC_SAMPLES = {asset["id"]: asset for asset in ASSETS if asset["group"] == "samples"}
ALLOWED_SUFFIXES = {".avi", ".mp4", ".mov", ".webm"}


def create_app(audit_path: Path | None = None, analysis_function=None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES + 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 100_000
    store = AuditStore(Path(audit_path or os.environ.get("VERICALL_DB_PATH", ROOT / "instance/vericall.sqlite3")))
    jobs = JobManager()
    app.extensions.update(vericall_store=store, vericall_jobs=jobs)
    analysis_function = analysis_function or analyze

    @app.before_request
    def local_origin():
        if request.method == "POST" and request.headers.get("Origin"):
            if request.headers["Origin"].rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="La solicitud debe proceder de esta aplicación local."), 403

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "vericall-v2", "model": model_status()}

    @app.get("/api/samples")
    def samples():
        return jsonify([{**sample, "available": (ROOT / sample["path"]).exists(),
                         "media_url": f"/samples/{sample['id']}"} for sample in PUBLIC_SAMPLES.values()])

    @app.get("/samples/<sample_id>")
    def sample_video(sample_id):
        sample = PUBLIC_SAMPLES.get(sample_id)
        if not sample or not (ROOT / sample["path"]).exists():
            abort(404)
        return send_file(ROOT / sample["path"], conditional=True,
                         mimetype="video/mp4" if Path(sample["path"]).suffix == ".mp4" else "video/quicktime")

    @app.post("/api/analyses")
    def start_analysis():
        path, temporary, accepted = None, False, False
        try:
            if request.form.get("consent") != "yes":
                raise InputError("Confirma la autorización de uso del video antes de analizarlo.")
            amount = str(positive_money(request.form.get("amount", "500000"), "El monto"))
            limit = str(positive_money(request.form.get("limit", "1000000"), "El límite"))
            new_beneficiary = request.form.get("new_beneficiary") == "yes"
            alternate_verified = request.form.get("alternate_verified") == "yes"
            sample_id = request.form.get("sample_id", "custom")
            if sample_id == "custom":
                upload = request.files.get("video")
                if upload is None or not upload.filename:
                    raise InputError("Selecciona un video para analizar.")
                suffix = Path(upload.filename).suffix.lower()
                if suffix not in ALLOWED_SUFFIXES:
                    raise InputError("Formato no admitido. Usa MP4, MOV, AVI o WebM.")
                descriptor, name = tempfile.mkstemp(prefix="vericall_", suffix=suffix)
                os.close(descriptor)
                path, temporary = Path(name), True
                upload.save(path)
                if path.stat().st_size > MAX_VIDEO_BYTES:
                    raise InputError("El video supera los 100 MB admitidos.")
            else:
                sample = PUBLIC_SAMPLES.get(sample_id)
                if sample is None:
                    raise InputError("El ejemplo solicitado no existe.")
                path = ROOT / sample["path"]
                if not path.exists():
                    raise InputError("Falta descargar este ejemplo. Ejecuta python scripts/download_assets.py --only samples.")
                if digest_file(path) != sample["sha256"]:
                    raise InputError("El ejemplo no coincide con su hash original. Descárgalo nuevamente.")

            def operation(progress):
                try:
                    video_hash = digest_file(path)
                    detection = analysis_function(path, progress=progress)
                    decision = evaluate(amount=amount, limit=limit, new_beneficiary=new_beneficiary,
                                        alternate_verified=alternate_verified, detection=detection)
                    progress(96, "Guardando la decisión y sus evidencias")
                    return store.record({"video_sha256": video_hash, "sample_id": None if sample_id == "custom" else sample_id,
                                         "consent_declared": True, "detection": detection, "decision": decision})
                finally:
                    if temporary:
                        path.unlink(missing_ok=True)

            job_id = jobs.submit(operation)
            accepted = True
            return jsonify(job_id=job_id, status_url=f"/api/jobs/{job_id}"), 202
        except InputError as error:
            return jsonify(error=str(error)), 400
        except QueueFull as error:
            return jsonify(error=str(error)), 429
        except OSError:
            app.logger.exception("No se pudo leer o guardar la entrada temporal")
            return jsonify(error="No se pudo acceder al archivo. No se inició una decisión; revisa el espacio y los permisos locales."), 503
        finally:
            if temporary and not accepted and path is not None:
                path.unlink(missing_ok=True)

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id):
        job = jobs.get(job_id)
        return jsonify(job) if job else (jsonify(error="Análisis no encontrado o expirado."), 404)

    @app.get("/api/history")
    def history():
        return jsonify([{key: value for key, value in entry.items() if key != "detection"}
                        | {"verdict": entry["detection"]["verdict"], "fake_score": entry["detection"]["fake_score"]}
                        for entry in store.recent()])

    @app.get("/api/decisions/<decision_id>")
    def export(decision_id):
        entry = store.get(decision_id)
        if not entry:
            return jsonify(error="Decisión no encontrada."), 404
        response = jsonify(entry)
        response.headers["Content-Disposition"] = f'attachment; filename="vericall-{entry["decision_id"]}.json"'
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        return jsonify(error="El archivo supera los 100 MB o los datos del formulario exceden el límite."), 413

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("VERICALL_PORT", "5000")), debug=False)
