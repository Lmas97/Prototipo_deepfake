import io
import json
from pathlib import Path

import pytest

from vericall.app import create_app
from vericall.decision import evaluate
from vericall.video import analyze_video


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(tmp_path):
    app = create_app(audit_path=tmp_path / "audit.jsonl")
    app.config["TESTING"] = True
    return app.test_client(), app.config["AUDIT_PATH"]


def test_videos_are_actually_decoded_and_have_different_motion():
    moving = analyze_video(ROOT / "sample_data/videos/moving_shapes.avi")
    frozen = analyze_video(ROOT / "sample_data/videos/frozen_shapes.avi")
    assert moving["decoded_frames"] == frozen["decoded_frames"] == 36
    assert moving["frozen_transition_ratio"] < 0.8
    assert frozen["frozen_transition_ratio"] >= 0.8


@pytest.mark.parametrize("sample_id,expected_action,expected_score", [
    ("normal", "autorizar_pendiente_confirmacion", 0),
    ("edge", "bloquear_y_escalar", 80),
])
def test_sample_end_to_end(client, sample_id, expected_action, expected_score):
    browser, audit_path = client
    response = browser.post("/assess", data={"sample_id": sample_id, "consent": "yes"})
    assert response.status_code == 200
    entries = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == expected_action
    assert entry["score"] == expected_score
    assert entry["video_metrics"]["decoded_frames"] == 36
    assert entry["video_sha256"]
    assert entry["decision_id"] in response.get_data(as_text=True)
    assert "video" not in entry or "video_metrics" in entry


def test_missing_alternate_verification_forces_review():
    metrics = analyze_video(ROOT / "sample_data/videos/moving_shapes.avi")
    result = evaluate(amount=500000, limit=1000000, new_beneficiary=False,
                      alternate_verified=False, video_metrics=metrics)
    assert result["score"] == 0
    assert result["action"] == "revisar_canal_alterno"


def test_invalid_sample_is_rejected_without_audit_entry(client):
    browser, audit_path = client
    response = browser.post("/assess", data={"sample_id": "invalid", "consent": "yes"})
    assert response.status_code == 400
    assert "Formato no admitido" in response.get_data(as_text=True)
    assert not audit_path.exists()


def test_consent_and_bad_video_are_rejected(client):
    browser, audit_path = client
    without_consent = browser.post("/assess", data={"sample_id": "normal"})
    assert without_consent.status_code == 400
    bad_video = browser.post("/assess", data={
        "sample_id": "custom", "consent": "yes", "amount": "500000", "limit": "1000000",
        "video": (io.BytesIO(b"This is not an AVI file"), "fake.avi"),
    }, content_type="multipart/form-data")
    assert bad_video.status_code == 400
    assert "No se pudo abrir" in bad_video.get_data(as_text=True)
    assert not audit_path.exists()


def test_custom_upload_uses_real_video_and_audits_without_raw_file(client):
    browser, audit_path = client
    video_bytes = (ROOT / "sample_data/videos/moving_shapes.avi").read_bytes()
    response = browser.post("/assess", data={
        "sample_id": "custom", "consent": "yes", "amount": "500000", "limit": "1000000",
        "alternate_verified": "yes", "video": (io.BytesIO(video_bytes), "demo.avi"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    entry = json.loads(audit_path.read_text().strip())
    assert entry["sample_id"] is None
    assert entry["video_metrics"]["decoded_frames"] == 36
    assert "video_bytes" not in entry and "filename" not in entry
    assert browser.get("/audit").status_code == 200
