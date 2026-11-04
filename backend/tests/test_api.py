"""API handler tests: call route handlers directly (no ASGI transport).

This covers routing logic, validation, status codes and the full
upload -> analyze -> download flow with the LLM stubbed (no network).
"""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app import main
from test_orchestrator import StubMeta

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"


def _upload(filename: str, data: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=filename)


def test_health():
    body = main.health()
    assert body["status"] == "ok"
    assert "llm_configured" in body


def test_sample_csv_serves():
    resp = main.sample_csv()
    assert resp.body.decode().splitlines()[0].startswith("date,order_id")


def test_upload_rejects_non_csv():
    with pytest.raises(HTTPException) as exc:
        main.upload_csv(_upload("data.xlsx", b"junk"))
    assert exc.value.status_code == 400


def test_upload_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        main.upload_csv(_upload("empty.csv", b"   \n"))
    assert exc.value.status_code == 400


def test_upload_then_analyze_then_download(monkeypatch):
    monkeypatch.setattr(main, "MetaClient", lambda: StubMeta())
    data = SAMPLE.read_bytes()
    upload = main.upload_csv(_upload("sample_sales.csv", data))
    assert upload.rows > 100
    assert upload.preview

    req = main.AnalyzeRequest
    resp = main.analyze(req(dataset_id=upload.dataset_id, objective="Grow revenue next quarter efficiently"))
    assert resp.status == "complete"
    assert len(resp.transitions) == 6
    assert resp.report.insights and resp.report.actions

    stored = main.get_report(resp.run_id)
    assert stored.run_id == resp.run_id

    dl = main.download_report(resp.run_id)
    assert "Operon AI" in dl.body.decode()


def test_analyze_unknown_dataset_404(monkeypatch):
    monkeypatch.setattr(main, "MetaClient", lambda: StubMeta())
    with pytest.raises(HTTPException) as exc:
        main.analyze(main.AnalyzeRequest(dataset_id="ds_nope", objective="Grow revenue fast now"))
    assert exc.value.status_code == 404


def test_download_unknown_run_404():
    with pytest.raises(HTTPException) as exc:
        main.download_report("run_nope")
    assert exc.value.status_code == 404
