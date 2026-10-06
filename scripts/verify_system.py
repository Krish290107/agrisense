"""Cross-language HTTP smoke check; optionally rebuild canonical data in a temporary DB."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn
from backend.app import app
from database.store import Repository
from scripts.init_database import (OUT, csv_rows, import_metadata, read_json,
                                   verify_database, verify_hashes)
from tests.test_forecast_api import ForecastTests


def rebuild(url):
    frozen = read_json(OUT / "robustness_summary.json")
    hashes = {**frozen["protected_sha256"], **frozen["output_sha256"]}
    verify_hashes(hashes)
    cleaned = ROOT / "data/processed/market_prices_clean.csv"
    policy_path = ROOT / "configs/forecast_policy.json"
    rows, policy = csv_rows(cleaned), read_json(policy_path)
    imports = []
    with Repository(url) as repo:
        repo.initialize()
        for _ in range(2):
            with repo.transaction():
                repo.import_observations(cleaned)
                repo.import_policy(policy_path)
                import_metadata(repo)
                imports.append(verify_database(repo, rows, policy))
        assert imports[0] == imports[1], "Import is not idempotent"
    verify_hashes(hashes)
    return {"first": imports[0]["table_counts"], "second": imports[1]["table_counts"],
            "integrity": imports[1]["integrity_check"], "protected_hashes": len(hashes)}


def smoke(url):
    previous = getattr(app.state, "database_url", None)
    app.state.database_url = url
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("Smoke API did not start")
                time.sleep(.05)
            with Repository(url, read_only=True) as repo:
                before = repo.connection.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
            result = subprocess.run(["node", "scripts/smoke.mjs"], cwd=ROOT / "frontend",
                                    env={**os.environ, "NEXT_PUBLIC_API_BASE_URL": f"http://127.0.0.1:{port}"},
                                    check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
            report = json.loads(result.stdout)
            with Repository(url, read_only=True) as repo:
                after = repo.connection.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
            assert after - before == report["generated_series"], "Unexpected forecast persistence"
            return {**report, "forecast_rows_before": before, "forecast_rows_after": after}
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            app.state.database_url = previous
            if thread.is_alive():
                raise RuntimeError("Smoke API did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="Requires existing local canonical/provenance/model artifacts; never used in CI")
    args = parser.parse_args()
    if args.rebuild:
        with tempfile.TemporaryDirectory(prefix="agrisense-rebuild-") as folder:
            url = "sqlite:///" + (Path(folder) / "verification.db").as_posix()
            database = rebuild(url)
            result = {"mode": "canonical", "database": database, "http": smoke(url)}
    else:
        fixture = ForecastTests()
        fixture.setUp()
        try:
            result = {"mode": "fixture", "http": smoke(fixture.url)}
        finally:
            fixture.tearDown()
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
