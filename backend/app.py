"""AgriSense's Day 1 API and environment configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# Resolve this file's directory so configuration also works from another terminal
# directory or when backend/ is the deployment root. Hosted settings take priority.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

app = FastAPI(
    title="AgriSense API",
    description="Agricultural Price Forecasting and Market Decision Support. Day 1 health API.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Confirm the API is reachable; no data or model is needed on Day 1."""
    return {"status": "ok", "service": "agrisense-api"}
