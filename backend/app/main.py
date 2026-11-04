"""Operon AI backend — FastAPI app."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from . import analytics, config
from .meta_client import MetaClient
from .models import AnalyzeRequest, AnalyzeResponse, Report, UploadResponse
from .orchestrator import DATASET_NAMES, DATASETS, REPORTS, run_analysis
from .report import render_markdown

app = FastAPI(title="Operon AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": config.MODEL_NAME,
        "llm_configured": bool(config.MODEL_API_KEY),
        "datasets": len(DATASETS),
        "runs": len(REPORTS),
    }


@app.post("/api/upload", response_model=UploadResponse)
def upload_csv(file: UploadFile = File(...)) -> UploadResponse:
    # Sync handler: FastAPI runs it in a threadpool; avoids an event loop entirely.
    raw = file.file.read()
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(413, f"File exceeds the {config.MAX_UPLOAD_MB} MB limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            raise HTTPException(400, "Could not decode file; please upload UTF-8 CSV.")
    try:
        df = analytics.read_csv_text(file.filename or "upload.csv", text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    DATASETS[dataset_id] = df
    DATASET_NAMES[dataset_id] = file.filename or "upload.csv"
    profile = analytics.profile_dataframe(df)
    return UploadResponse(
        dataset_id=dataset_id,
        filename=DATASET_NAMES[dataset_id],
        rows=int(df.shape[0]),
        columns=profile.columns,
        preview=analytics.preview_rows(df),
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    objective = req.objective.strip()
    if len(objective) < 10:
        raise HTTPException(400, "Objective must be at least 10 characters.")
    dataset_id = req.dataset_id
    if dataset_id is None:
        # Inline CSV path: parse, register as a dataset, then run the pipeline.
        assert req.csv_text is not None  # guaranteed by AnalyzeRequest validation
        try:
            df = analytics.read_csv_text(req.filename, req.csv_text)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        DATASETS[dataset_id] = df
        DATASET_NAMES[dataset_id] = req.filename
    try:
        return run_analysis(dataset_id, objective, MetaClient())
    except KeyError:
        raise HTTPException(404, "Unknown dataset_id. Upload a CSV first.")


@app.get("/api/report/{run_id}", response_model=Report)
def get_report(run_id: str) -> Report:
    if run_id not in REPORTS:
        raise HTTPException(404, "Unknown run_id.")
    return REPORTS[run_id]


@app.get("/api/report/{run_id}/download")
def download_report(run_id: str) -> PlainTextResponse:
    if run_id not in REPORTS:
        raise HTTPException(404, "Unknown run_id.")
    return PlainTextResponse(
        render_markdown(REPORTS[run_id]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="operon-report-{run_id}.md"'},
    )


@app.get("/api/sample.csv")
def sample_csv() -> PlainTextResponse:
    if not SAMPLE_PATH.exists():
        raise HTTPException(404, "Sample data not found.")
    return PlainTextResponse(
        SAMPLE_PATH.read_text(encoding="utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_sales.csv"'},
    )
