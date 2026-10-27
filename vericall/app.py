"""Interfaz local y API para detección visual de deepfakes y decisión de tesorería."""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from vericall.audit import AlreadyResolved, AuditError, AuditStore
from vericall.config import MAX_VIDEO_BYTES, ROOT
from vericall.decision import InputError, evaluate, positive_money, resolve
from vericall.detector import ModelUnavailable, digest_file, model_status
from vericall.jobs import JobManager, QueueFull
from vericall.live import SOURCES, LiveMonitor, SessionNotFound, TooManySessions
from vericall.pipeline import analyze
from vericall.video import VideoError


ASSETS = json.loads((ROOT / "config/assets.json").read_text())["assets"]
PUBLIC_SAMPLES = {asset["id"]: asset for asset in ASSETS if asset["group"] == "samples"}
ALLOWED_SUFFIXES = {".avi", ".mp4", ".mov", ".webm"}


def transfer_inputs(form) -> dict:
    return {"amount": str(positive_money(form.get("amount", "500000"), "El monto")),
            "limit": str(positive_money(form.get("limit", "1000000"), "El límite")),
            "new_beneficiary": form.get("new_beneficiary") == "yes"}


def analyst_name(form) -> str:
    return (form.get("analyst") or "").strip()[:80] or "Analista de tesorería"


def create_app(audit_path: Path | None = None, analysis_function=None, live_detector=None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES + 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 100_000
    store = AuditStore(Path(audit_path or os.environ.get("VERICALL_DB_PATH", ROOT / "instance/vericall.sqlite3")))
    jobs = JobManager()
    live = LiveMonitor(live_detector)
    app.extensions.update(vericall_store=store, vericall_jobs=jobs, vericall_live=live)
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
            transfer, analyst = transfer_inputs(request.form), analyst_name(request.form)
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
                    decision = evaluate(**transfer, detection=detection)
                    progress(96, "Guardando la decisión y sus evidencias")
                    return store.record({"source": "upload" if sample_id == "custom" else "sample",
                                         "video_sha256": video_hash, "sample_id": None if sample_id == "custom" else sample_id,
                                         "analyst": analyst, "consent_declared": True, "detection": detection, "decision": decision})
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

    @app.post("/api/live/sessions")
    def start_live():
        try:
            if request.form.get("consent") != "yes":
                raise InputError("Confirma que los participantes autorizaron el análisis de la llamada.")
            source = request.form.get("source", "")
            if source not in SOURCES:
                raise InputError("Fuente de llamada no reconocida.")
            sample_id = request.form.get("sample_id") if source == "simulated" else None
            if source == "simulated" and sample_id not in PUBLIC_SAMPLES:
                raise InputError("Elige el video público que simulará la llamada.")
            video_sha256 = None
            if source == "file":
                # El video propio se reproduce solo en el navegador; aquí llega su huella para la bitácora.
                video_sha256 = (request.form.get("video_sha256") or "").lower()
                if not re.fullmatch(r"[0-9a-f]{64}", video_sha256):
                    raise InputError("Falta la huella SHA-256 del video propio.")
            caller = (request.form.get("caller") or "").strip()[:80] or "Interlocutor sin identificar"
            session = live.start(source, caller, sample_id, video_sha256)
        except InputError as error:
            return jsonify(error=str(error)), 400
        except TooManySessions as error:
            return jsonify(error=str(error)), 429
        return jsonify(session_id=session.id, model=model_status()), 201

    @app.post("/api/live/sessions/<session_id>/frames")
    def live_frame(session_id):
        upload = request.files.get("frame")
        try:
            return jsonify(live.analyze_frame(session_id, upload.read() if upload else b""))
        except SessionNotFound as error:
            return jsonify(error=str(error.args[0])), 404
        except VideoError as error:
            return jsonify(error=str(error)), 400
        except ModelUnavailable as error:
            return jsonify(error=str(error)), 503

    @app.post("/api/live/sessions/<session_id>/transfer")
    def live_transfer(session_id):
        try:
            transfer, analyst = transfer_inputs(request.form), analyst_name(request.form)
            session, detection = live.detection(session_id)
            decision = evaluate(**transfer, detection=detection)
            entry = store.record({"source": "live", "video_sha256": session.video_sha256, "sample_id": session.sample_id,
                                  "live_session_id": session.id, "analyst": analyst, "consent_declared": True,
                                  "detection": detection, "decision": decision})
        except InputError as error:
            return jsonify(error=str(error)), 400
        except SessionNotFound as error:
            return jsonify(error=str(error.args[0])), 404
        except AuditError as error:
            return jsonify(error=str(error)), 503
        return jsonify(entry), 201

    @app.post("/api/live/sessions/<session_id>/end")
    def end_live(session_id):
        live.end(session_id)
        return "", 204

    @app.post("/api/decisions/<decision_id>/resolution")
    def resolution(decision_id):
        form = request.form
        try:
            entry = store.resolve(decision_id, lambda decision: resolve(
                decision, outcome=form.get("outcome", ""), role=form.get("role", ""), actor=form.get("actor", ""),
                alternate_verified=form.get("alternate_verified") == "yes", channel=form.get("channel", ""),
                now=datetime.now(timezone.utc)))
        except KeyError:
            return jsonify(error="Decisión no encontrada."), 404
        except InputError as error:
            return jsonify(error=str(error)), 400
        except AlreadyResolved as error:
            return jsonify(error=str(error)), 409
        except AuditError as error:
            return jsonify(error=str(error)), 503
        return jsonify(entry), 201

    @app.get("/api/audit/verify")
    def verify_audit():
        return jsonify(store.verify())

    @app.get("/api/history")
    def history():
        return jsonify([{key: value for key, value in entry.items() if key != "detection"}
                        | {"source": entry.get("source", "sample" if entry.get("sample_id") else "upload"),
                           "verdict": entry["detection"]["verdict"], "fake_score": entry["detection"]["fake_score"],
                           "caller": entry["detection"].get("live", {}).get("caller_claimed_identity")}
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
    create_app().run(host="127.0.0.1", port=int(os.environ.get("VERICALL_PORT", "5000")), debug=False, threaded=True)
