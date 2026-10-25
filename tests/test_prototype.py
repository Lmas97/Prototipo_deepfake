import io
import json
import threading
import time
from pathlib import Path

import pytest

from vericall.app import create_app
from vericall.audit import AuditError
from vericall.config import FACE_MODEL, ROOT
from vericall.decision import InputError, evaluate, positive_money
from vericall.detector import digest_file, model_status
from vericall.jobs import JobManager, QueueFull
from vericall.pipeline import analyze, summarize


def detection(score=0.1, face_count=12):
    frames = [{"timestamp": i / 2, "fake_score": score if i < face_count else None,
               "faces": [{"fake_score": score}] if i < face_count else []} for i in range(12)]
    result = summarize(frames, {"dark_frame_ratio": 0, "frozen_transition_ratio": 0})
    result["frames"] = frames
    return result


def decision(result=None, **overrides):
    values = dict(amount="500000", limit="1000000", new_beneficiary=False,
                  alternate_verified=True, detection=result or detection())
    values.update(overrides)
    return evaluate(**values)


def wait_job(client, response):
    assert response.status_code == 202
    end = time.monotonic() + 10
    while time.monotonic() < end:
        value = client.get(response.json["status_url"]).json
        if value["status"] in ("done", "failed"):
            return value
        time.sleep(0.01)
    raise AssertionError("El trabajo no terminó")


@pytest.fixture
def application(tmp_path):
    seen = []
    def test_analysis(path, progress):
        seen.append(path)
        progress(50, "Analizador de prueba")
        return detection(0.8)
    app = create_app(tmp_path / "audit.sqlite3", analysis_function=test_analysis)
    app.config["TESTING"] = True
    yield app, seen
    app.extensions["vericall_jobs"].executor.shutdown(wait=True)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-5", "0", "foo", "1000000000001", "0.001"])
def test_invalid_amounts(bad):
    with pytest.raises(InputError):
        positive_money(bad, "Monto")


def test_business_gates_and_risk_separation():
    assert decision()["action"] == "autorizar_pendiente_confirmacion"
    assert decision(alternate_verified=False)["action"] == "revisar_canal_alterno"
    assert decision(new_beneficiary=True)["action"] == "revisar_canal_alterno"
    assert decision(amount="1000001")["action"] == "revisar_canal_alterno"
    assert decision(detection(0.9))["action"] == "bloquear_y_escalar"
    assert decision(detection(0.9), new_beneficiary=True, amount="1000001")["score"] == 100
    # La cuenta nueva modifica el puntaje de pago, no la evidencia visual.
    evidence = detection(.1)
    original = json.dumps(evidence)
    decision(evidence, new_beneficiary=True)
    assert json.dumps(evidence) == original


def test_missing_or_uncertain_evidence_cannot_authorize():
    no_faces = detection(.1, face_count=0)
    assert no_faces["predicted_label"] == "unknown" and no_faces["fake_score"] is None
    assert decision(no_faces)["action"] == "revisar_canal_alterno"
    assert decision(detection(.4))["action"] == "revisar_canal_alterno"
    assert detection(.9, face_count=3)["predicted_label"] == "unknown"
    assert decision(detection(.9, face_count=3))["action"] == "revisar_canal_alterno"


def test_quality_problem_forces_review():
    low = detection(.01)
    low["quality"]["frozen_transition_ratio"] = 1
    assert decision(low)["action"] == "revisar_canal_alterno"


def test_binary_class_and_uncertainty_are_distinct():
    assert detection(.7)["predicted_label"] == "fake"
    assert detection(.7)["verdict"] == "inconclusive"
    assert detection(.75)["verdict"] == "likely_manipulated"
    assert detection(.25)["verdict"] == "no_strong_signals"


def test_upload_job_audit_export_and_cleanup(application):
    app, seen = application
    client = app.test_client()
    response = client.post("/api/analyses", data={"consent": "yes", "sample_id": "custom",
        "video": (io.BytesIO(b"test bytes for dependency-injected analysis"), "name.mp4")})
    job = wait_job(client, response)
    assert job["status"] == "done"
    assert seen and not seen[0].exists()
    result = job["result"]
    assert result["decision"]["action"] == "bloquear_y_escalar"
    assert len(result["video_sha256"]) == 64
    export = client.get(f"/api/decisions/{result['decision_id']}")
    assert export.status_code == 200 and export.json == result
    assert "attachment" in export.headers["Content-Disposition"]
    assert len(client.get("/api/history").json) == 1
    assert "crop" not in json.dumps(result) and "video_bytes" not in json.dumps(result)


def test_audit_failure_prevents_decision_and_deletes_upload(application, monkeypatch):
    app, seen = application
    def fail(_payload):
        raise AuditError("No se pudo guardar la bitácora.")
    monkeypatch.setattr(app.extensions["vericall_store"], "record", fail)
    client = app.test_client()
    job = wait_job(client, client.post("/api/analyses", data={"consent": "yes", "video": (io.BytesIO(b"bytes"), "demo.mp4")}))
    assert job["status"] == "failed" and "result" not in job
    assert not seen[0].exists()
    assert client.get("/api/history").json == []


def test_validation_and_consent_before_processing(application):
    app, seen = application
    client = app.test_client()
    assert client.post("/api/analyses", data={"sample_id": "real_01"}).status_code == 400
    response = client.post("/api/analyses", data={"consent": "yes", "video": (io.BytesIO(b"text"), "bad.txt")})
    assert response.status_code == 400 and "Formato" in response.json["error"]
    assert client.post("/api/analyses", data={"consent": "yes", "amount": "NaN"}).status_code == 400
    assert seen == []
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.get("/api/decisions/missing").status_code == 404
    assert client.get("/health").json["status"] == "ok"


def test_upload_limit_and_external_origin(application):
    app, _ = application
    client = app.test_client()
    assert client.post("/api/analyses", headers={"Origin": "https://outside.example"}).status_code == 403
    app.config["MAX_CONTENT_LENGTH"] = 100
    assert client.post("/api/analyses", data={"consent": "yes", "video": (io.BytesIO(b"x" * 200), "demo.mp4")}).status_code == 413


def test_real_decoder_rejects_disguised_text(tmp_path):
    path = tmp_path / "false.mp4"
    path.write_text("This is text, not a video.")
    from vericall.video import VideoError
    with pytest.raises(VideoError, match="video válido"):
        analyze(path)


def test_missing_model_fails_instead_of_inventing_a_score(tmp_path, monkeypatch):
    import vericall.detector as module
    monkeypatch.setattr(module, "MODEL_DIR", tmp_path)
    assert module.model_status()["available"] is False
    with pytest.raises(module.ModelUnavailable, match="no está instalado"):
        module.DeepfakeDetector()._load()


def test_corrupt_metadata_is_rejected(tmp_path, monkeypatch):
    import vericall.detector as module
    # No copiar los 343 MB: enlazar los pesos aprobados y dañar solo el preprocesador.
    if not model_status()["available"]:
        pytest.skip("Requiere activos descargados.")
    for name in ("model.safetensors", "config.json"):
        (tmp_path / name).symlink_to(module.MODEL_DIR / name)
    (tmp_path / "preprocessor_config.json").write_text('{}')
    monkeypatch.setattr(module, "MODEL_DIR", tmp_path)
    with pytest.raises(module.ModelUnavailable, match="configuración"):
        module.DeepfakeDetector()._load()


def test_bounded_queue():
    manager = JobManager()
    gate = threading.Event()
    def wait(_progress):
        gate.wait(timeout=5)
        return {"done": True}
    try:
        ids = [manager.submit(wait) for _ in range(3)]
        with pytest.raises(QueueFull):
            manager.submit(wait)
    finally:
        gate.set()
        manager.executor.shutdown(wait=True)
    assert all(manager.get(job_id)["status"] == "done" for job_id in ids)


def test_no_face_video_does_not_invoke_classifier():
    if not FACE_MODEL.exists():
        pytest.skip("Requiere el pequeño modelo YuNet descargado.")
    class MustNotRun:
        def predict(self, _crops):
            raise AssertionError("No debe clasificar figuras geométricas como rostros")
    result = analyze(ROOT / "sample_data/videos/moving_shapes.avi", detector=MustNotRun())
    assert result["predicted_label"] == "unknown"
    assert result["model"]["executed"] is False
    assert result["fake_score"] is None


@pytest.mark.model
def test_trained_model_offline_and_filename_independence(tmp_path, monkeypatch):
    assert model_status()["available"], "Ejecuta python scripts/download_assets.py"
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    genuine = analyze(ROOT / "sample_data/public/real_01.mp4")
    manipulated = ROOT / "sample_data/public/fake_01.mp4"
    renamed = tmp_path / "video_completamente_real.mp4"
    renamed.write_bytes(manipulated.read_bytes())
    result = analyze(renamed)
    assert genuine["predicted_label"] == "real"
    assert result["predicted_label"] == "fake"
    assert result["model"]["executed"] is True
    assert result["fake_score"] > genuine["fake_score"]
    assert result["sampled_frames"] == 24
    assert digest_file(renamed) == digest_file(manipulated)
