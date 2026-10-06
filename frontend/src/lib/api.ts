export type Method = "naive" | "rolling_mean_7";
export type Series = {series_id: string; state: string; district: string; market: string; commodity: string; variety: string; grade: string; price_unit: "INR/quintal"};
export type Supported = Series & {selected_method: Method; policy_version: string};
export type Observation = {date: string; min_price: string; modal_price: string; max_price: string};
export type History = {series: Series; forecast_supported: boolean; observations: Observation[]};
export type Forecast = {status: "ok" | "insufficient_history" | "unsupported_series"; series: Series; forecast_type: "next_observation"; prediction: string | null; selected_method: Method | null; method_used: Method | null; fallback_used: boolean; history_observations_used: number; history_cutoff_date: string | null; latest_observed_price: string | null; generated_at: string; historical_benchmark_mae: number | null};
export type Saved = {forecast_id: string; generated_at: string; prediction: string | null; method: string | null; history_cutoff: string | null; status: string};
export type ComparisonRow = {forecast: Forecast & {latest_observation_date: string | null}; difference: string | null; percentage: string | null; signal: "above" | "near" | "below" | null};
export type Comparison = {selected_series_id: string; scope: "exact_variety_grade" | "commodity"; warning: string | null; markets: ComparisonRow[]};
const obj = (x: unknown): x is Record<string, unknown> => typeof x === "object" && x !== null && !Array.isArray(x);
const text = (x: unknown): x is string => typeof x === "string" && x.length > 0;
export const price = (x: unknown): x is string => typeof x === "string" && /^\d+(\.\d+)?$/.test(x) && Number.isFinite(Number(x)) && Number(x) > 0;
const day = (x: unknown): x is string => typeof x === "string" && /^\d{4}-\d{2}-\d{2}$/.test(x) && !Number.isNaN(Date.parse(x)) && new Date(x).toISOString().slice(0,10) === x;
const stamp = (x: unknown): x is string => text(x) && /(?:Z|[+-]\d{2}:\d{2})$/.test(x) && !Number.isNaN(Date.parse(x));
const method = (x: unknown): x is Method => x === "naive" || x === "rolling_mean_7";
function isSeries(x: unknown): x is Series {
  return obj(x) && typeof x.series_id === "string" && /^[a-f0-9]{16}$/.test(x.series_id) && [x.state,x.district,x.market,x.commodity,x.variety,x.grade].every(text) && x.price_unit === "INR/quintal";
}
export function isSupported(x: unknown): x is Supported[] {
  return Array.isArray(x) && x.every(r => obj(r) && method(r.selected_method) && text(r.policy_version) && isSeries(r)) && new Set(x.map(r => r.series_id)).size === x.length;
}
export function isHistory(x: unknown): x is History {
  return obj(x) && isSeries(x.series) && typeof x.forecast_supported === "boolean" && Array.isArray(x.observations) && x.observations.length <= 365 &&
    x.observations.every((r,i,rows) => obj(r) && day(r.date) && price(r.min_price) && price(r.modal_price) && price(r.max_price) &&
      Number(r.min_price) <= Number(r.modal_price) && Number(r.modal_price) <= Number(r.max_price) && (i === 0 || rows[i-1].date < r.date));
}
export function isForecast(x: unknown): x is Forecast {
  if (!obj(x) || !isSeries(x.series) || x.forecast_type !== "next_observation" || x.price_unit !== "INR/quintal" || !stamp(x.generated_at) || typeof x.fallback_used !== "boolean" || !Number.isInteger(x.history_observations_used) ||
      !(x.historical_benchmark_mae === null || (typeof x.historical_benchmark_mae === "number" && Number.isFinite(x.historical_benchmark_mae) && x.historical_benchmark_mae >= 0))) return false;
  if (x.status === "ok") return price(x.prediction) && method(x.selected_method) && method(x.method_used) && day(x.history_cutoff_date) && price(x.latest_observed_price) &&
    x.history_observations_used === (x.method_used === "naive" ? 1 : 7) && (x.fallback_used ? x.selected_method === "rolling_mean_7" && x.method_used === "naive" : x.selected_method === x.method_used);
  return ["insufficient_history","unsupported_series"].includes(String(x.status)) && x.prediction === null && x.method_used === null && x.history_observations_used === 0 && x.history_cutoff_date === null && (x.selected_method === null || method(x.selected_method));
}
export function isSaved(x: unknown): x is Saved[] {
  return Array.isArray(x) && x.length <= 100 && x.every(r => obj(r) && text(r.forecast_id) && stamp(r.generated_at) && (r.history_cutoff === null || day(r.history_cutoff)) &&
    (["available","fallback"].includes(String(r.status)) ? price(r.prediction) && method(r.method) && day(r.history_cutoff) :
      ["insufficient_history","unsupported_series","error"].includes(String(r.status)) && r.prediction === null && r.method === null));
}
async function request<T>(path: string, validate: (x: unknown) => x is T, signal: AbortSignal, body?: object): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!base) throw new Error("The market service is not configured. Please try again later.");
  let url: URL;
  try {url = new URL(`${base.replace(/\/+$/, "")}${path}`); if (!["http:","https:"].includes(url.protocol)) throw new Error();}
  catch {throw new Error("The market service address is unavailable. Please try again later.");}
  try {
    const response = await fetch(url, {method: body ? "POST" : "GET", body: body ? JSON.stringify(body) : undefined,
      headers: {Accept: "application/json", ...(body ? {"Content-Type": "application/json"} : {})}, cache: "no-store", signal: AbortSignal.any([signal,AbortSignal.timeout(15000)])});
    if (!response.ok) throw new Error(response.status === 404 ? "This market series is no longer available. Reload the market list." : response.status === 503 ? "Market data is temporarily unavailable. Please retry shortly." : "The request could not be completed. Please retry.");
    let data: unknown;
    try {data = await response.json();} catch {throw new Error("The market service returned an unexpected response. Please retry.");}
    if (!validate(data)) throw new Error("The market service returned incomplete or unexpected data. Please retry.");
    return data;
  } catch (error) {
    if (signal.aborted) throw error;
    if (error instanceof Error && error.name === "TimeoutError") throw new Error("The request took too long. Please retry; an earlier forecast may already have been saved.");
    if (error instanceof TypeError) throw new Error("Cannot reach the backend. Check your connection and retry.");
    throw error;
  }
}
export const api = {
  decision: (id: string, s: AbortSignal) => request(`/api/v1/decision/markets?series_id=${encodeURIComponent(id)}`, (x): x is Comparison => isComparison(x) && x.selected_series_id === id, s),
  health: (s: AbortSignal) => request("/health", (x): x is {status: "ok"} => obj(x) && x.status === "ok" && x.service === "agrisense-api", s),
  series: (s: AbortSignal) => request("/api/v1/forecast/series", isSupported, s),
  history: (id: string, s: AbortSignal) => request(`/api/v1/forecast/series/${encodeURIComponent(id)}/history?limit=30`, (x): x is History => isHistory(x) && x.series.series_id === id, s),
  forecast: (id: string, s: AbortSignal) => request("/api/v1/forecast", (x): x is Forecast => isForecast(x) && x.series.series_id === id, s, {series_id: id}),
  saved: (id: string, s: AbortSignal) => request(`/api/v1/forecast/series/${encodeURIComponent(id)}/forecasts?limit=5`, isSaved, s),
};
export function isComparison(x: unknown): x is Comparison {
  const signed = (v: unknown) => typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v) && Number.isFinite(Number(v));
  return obj(x) && typeof x.selected_series_id === "string" && /^[a-f0-9]{16}$/.test(x.selected_series_id) &&
    ["exact_variety_grade","commodity"].includes(String(x.scope)) && (x.warning === null || text(x.warning)) && Array.isArray(x.markets) &&
    x.markets.every(r => obj(r) && isForecast(r.forecast) && "latest_observation_date" in r.forecast &&
      (r.forecast.status === "ok" ? day(r.forecast.latest_observation_date) && signed(r.difference) && signed(r.percentage) && ["above","near","below"].includes(String(r.signal)) :
        r.difference === null && r.percentage === null && r.signal === null && r.forecast.latest_observation_date === null)) &&
    new Set(x.markets.map(r => r.forecast.series.series_id)).size === x.markets.length;
}
export const money = (x: string | number | null | undefined) => x == null ? "—" : new Intl.NumberFormat("en-IN", {style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2}).format(Number(x));
export const dateLabel = (x: string) => new Intl.DateTimeFormat("en-IN", {day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata"}).format(new Date(x));
export const timeLabel = (x: string) => new Intl.DateTimeFormat("en-IN", {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata"}).format(new Date(x));
export const methodLabel = (x: string | null) => x === "naive" ? "Latest observed price" : x === "rolling_mean_7" ? "Average of 7 observations" : "Not available";
