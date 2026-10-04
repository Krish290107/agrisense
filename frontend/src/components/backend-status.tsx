"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ?? "";
const TIMEOUT_MS = 5_000;

type ConnectionState =
  | { status: "loading" }
  | { status: "connected" }
  | { status: "error"; message: string };

async function requestHealth(signal: AbortSignal): Promise<void> {
  if (!API_BASE_URL) {
    throw new Error(
      "Set NEXT_PUBLIC_API_BASE_URL in frontend/.env.local, then restart the frontend.",
    );
  }

  let endpoint: URL;
  try {
    endpoint = new URL(`${API_BASE_URL.replace(/\/+$/, "")}/health`);
    if (!["http:", "https:"].includes(endpoint.protocol)) {
      throw new Error("Unsupported protocol");
    }
  } catch {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL must be a complete http:// or https:// address. Update it and restart the frontend.",
    );
  }

  const response = await fetch(endpoint, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`The API returned HTTP ${response.status}. Check the backend terminal and retry.`);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error("The API did not return JSON. Check that the API address points to the AgriSense backend.");
  }

  if (
    typeof data !== "object" ||
    data === null ||
    Array.isArray(data) ||
    Object.keys(data).length !== 2 ||
    !("status" in data) ||
    !("service" in data) ||
    data.status !== "ok" ||
    data.service !== "agrisense-api"
  ) {
    throw new Error("The API response was unexpected. Check that this is the AgriSense /health endpoint.");
  }
}

export function BackendStatus() {
  const [connection, setConnection] = useState<ConnectionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, TIMEOUT_MS);

    requestHealth(controller.signal)
      .then(() => {
        if (active) setConnection({ status: "connected" });
      })
      .catch((error: unknown) => {
        if (!active) return;

        let message = "Could not reach the API. Start the backend, check its URL and allowed frontend origins, then retry.";
        if (timedOut) {
          message = "The API did not respond within 5 seconds. Check that the backend is running, then retry.";
        } else if (error instanceof Error && !(error instanceof TypeError)) {
          message = error.message;
        }
        setConnection({ status: "error", message });
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  function retry() {
    setConnection({ status: "loading" });
    setAttempt((value) => value + 1);
  }

  const loading = connection.status === "loading";
  const title = loading
    ? "Checking connection"
    : connection.status === "connected"
      ? "Backend connected"
      : "Backend unavailable";

  return (
    <section id="connection" className="connection-card" aria-labelledby="connection-title">
      <div className="connection-header">
        <span className="section-kicker">LIVE CONNECTION</span>
        <span className="endpoint-tag">FastAPI</span>
      </div>
      <div className="connection-body">
        <div className={`connection-icon ${connection.status}`} aria-hidden="true">
          {loading ? (
            <span className="spinner" />
          ) : connection.status === "connected" ? (
            <svg viewBox="0 0 24 24" fill="none"><path d="m6 12 4 4 8-8" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none"><path d="M12 6v7m0 4v.1" /></svg>
          )}
        </div>
        <div className="connection-copy" role="status" aria-live="polite" aria-atomic="true">
          <h2 id="connection-title">{title}</h2>
          <p>
            {loading
              ? "Sending a health request from your browser to the AgriSense API."
              : connection.status === "connected"
                ? "Your browser reached the AgriSense API and verified its health response."
                : connection.message}
          </p>
        </div>
        <button type="button" className="retry-button" onClick={retry} disabled={loading}>
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M15.8 7.4A6 6 0 1 0 16 12M16 3.5v4.3h-4.3" /></svg>
          {loading ? "Checking…" : "Retry connection"}
        </button>
      </div>
      <div className="connection-footer">
        <span>API endpoint</span>
        <code>{API_BASE_URL ? `${API_BASE_URL.replace(/\/+$/, "")}/health` : "Not configured"}</code>
        <span className="health-note">Checked on page load and retry</span>
      </div>
    </section>
  );
}
