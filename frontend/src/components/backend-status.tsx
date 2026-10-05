"use client";
import {api} from "@/lib/api";
import {useResource} from "@/lib/use-resource";
export function BackendStatus() {
  const connection = useResource(api.health);
  return <div className="backend-status" role="status"><span className={`status-dot ${connection.error ? "offline" : connection.loading ? "pending" : ""}`} aria-hidden="true"/><span>{connection.loading ? "Checking backend..." : connection.error ? "Backend unavailable" : "Backend connected"}</span><button className="text-button" disabled={connection.loading} onClick={connection.reload} aria-label="Recheck backend connection">Retry</button></div>;
}
