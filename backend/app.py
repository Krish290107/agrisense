"""AgriSense health and next-observation forecast API."""

import os
import shutil
import tempfile
from pathlib import Path
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.forecast_api import router as forecast_router
from backend.decision_api import router as decision_router


load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)
# Vercel's deployed filesystem is read-only except for /tmp.
# Use the bundled Day 9 database as the seed for an ephemeral writable copy.
if os.getenv("VERCEL"):
    bundled_db = Path(__file__).resolve().parents[1] / "data" / "agrisense.db"
    runtime_db = Path(tempfile.gettempdir()) / "agrisense.db"

    if not bundled_db.is_file():
        raise RuntimeError("Bundled AgriSense database is missing")

    if not runtime_db.exists():
        shutil.copy2(bundled_db, runtime_db)

    os.environ["DATABASE_URL"] = f"sqlite:///{runtime_db}"

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
def parse_origins(value):
    origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
    try:
        if not origins:
            raise ValueError()
        for origin in origins:
            url = urlsplit(origin)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
                    or url.password is not None or url.path or url.query or url.fragment
                    or "*" in origin or any(c.isspace() for c in origin)):
                raise ValueError()
            _ = url.port
    except ValueError:
        raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins without credentials, paths or wildcards") from None
    return list(dict.fromkeys(origins))


allowed_origins = parse_origins(os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS))

app = FastAPI(
    title="AgriSense API",
    description="Agricultural Price Forecasting and Market Decision Support. Next-observation estimates from validated baseline policies.",
    version="0.1.0",
    docs_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)

app.include_router(forecast_router)
app.include_router(decision_router)


@app.get("/docs", include_in_schema=False)
async def api_docs() -> HTMLResponse:
    """Keep interactive documentation without displaying the schema URL link."""
    page = get_swagger_ui_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} - Swagger UI",
    )
    html = page.body.decode("utf-8").replace(
        "</head>",
        '<style>.swagger-ui .info a.link[href="/openapi.json"] '
        '{ display: none; }</style></head>',
    )
    return HTMLResponse(html)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Confirm the API is reachable; no data or model is needed on Day 1."""
    return {"status": "ok", "service": "agrisense-api"}
