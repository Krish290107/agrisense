"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {api,dateLabel,methodLabel,money,timeLabel,type Forecast,type Supported} from "@/lib/api";
import {useResource} from "@/lib/use-resource";
import {PriceHistoryChart} from "./price-history-chart";
import {DecisionSupport} from "./decision-support";

function ErrorNotice({message,retry}: {message: string; retry?: () => void}) {
  return <div className="error-notice" role="alert"><p>{message}</p>{retry && <button className="text-button" onClick={retry}>Retry</button>}</div>;
}
function SeriesDashboard({series}: {series: Supported}) {
  const history = useResource(useCallback((s: AbortSignal) => api.history(series.series_id,s),[series.series_id]));
  const saved = useResource(useCallback((s: AbortSignal) => api.saved(series.series_id,s),[series.series_id]));
  const [forecast,setForecast] = useState<Forecast | null>(null);
  const [busy,setBusy] = useState(false), [error,setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(),[]);
  async function generate() {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError(""); setForecast(null);
    try {const result = await api.forecast(series.series_id,controller.signal); if (!controller.signal.aborted) {setForecast(result); saved.reload();}}
    catch (error: unknown) {if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Forecast unavailable. Please retry.");}
    finally {if (!controller.signal.aborted) {setBusy(false); pending.current = null;}}
  }
  const rows = history.data?.observations ?? [], latest = rows.at(-1);
  return <>
    <div className="series-heading"><div><h2>{series.commodity} <span>in {series.market}</span></h2><p>{series.district}, {series.state} · Variety: {series.variety} · Grade: {series.grade}</p></div><span className="unit-label">All prices in INR / quintal</span></div>
    <div className="workspace-grid">
      <section className="panel forecast-panel" aria-labelledby="forecast-title" aria-busy={busy}>
        <div className="panel-heading"><h3 id="forecast-title">Forecast for next observation</h3><span className="small-tag">Estimate</span></div>
        <div className="forecast-output" aria-live="polite">
          {busy ? <p className="empty">Generating your estimate…</p> : forecast?.status === "ok" ? <><p className="forecast-price" title={`Exact API value: ${forecast.prediction}`}>{money(forecast.prediction)}<span> / quintal</span></p><p>Next reported market price estimate</p></> : forecast ?
            <div className="empty"><strong>No forecast available</strong><p>{forecast.status === "insufficient_history" ? "There are no valid earlier observations for this series." : "This series no longer has an active forecast policy. Reload the market list."}</p></div> :
            <div className="empty"><strong>Ready when you are</strong><p>Generate an estimate using this market’s latest available records.</p></div>}
        </div>
        {error && <ErrorNotice message={error}/>}
        <button className="primary-button" onClick={generate} disabled={busy}>{busy ? "Generating…" : forecast?.status === "ok" ? "Refresh forecast" : "Generate forecast"}<span aria-hidden="true">↗</span></button>
        <p className="quiet">Saved only when you generate. Unchanged records reuse the same forecast.</p>
        <dl className="forecast-details"><div><dt>Selected method</dt><dd>{methodLabel(forecast?.selected_method ?? series.selected_method)}</dd></div>
          {forecast?.status === "ok" && <><div><dt>Method used</dt><dd>{methodLabel(forecast.method_used)}</dd></div><div><dt>Fallback used</dt><dd>{forecast.fallback_used ? "Yes — latest valid price" : "No"}</dd></div><div><dt>Observations used</dt><dd>{forecast.history_observations_used}</dd></div><div><dt>Latest price used</dt><dd>{money(forecast.latest_observed_price)}</dd></div><div><dt>History cutoff</dt><dd>{dateLabel(forecast.history_cutoff_date!)}</dd></div><div><dt>Generated (IST)</dt><dd>{timeLabel(forecast.generated_at)}</dd></div></>}
        </dl>
        {forecast?.fallback_used && <p className="notice">Fewer than seven observations were available. The estimate uses the latest valid price.</p>}
        {forecast?.historical_benchmark_mae != null && <p className="benchmark">Historical mean absolute error: <strong>{money(forecast.historical_benchmark_mae)} / quintal</strong>. This is past performance, not a confidence interval.</p>}
        <p className="forecast-limit">Not a forecast for tomorrow or a fixed number of days ahead.</p>
      </section>
      <section className="panel history-panel" aria-labelledby="history-title" aria-busy={history.loading}>
        <div className="panel-heading"><h3 id="history-title">Recent market history</h3><button className="text-button" disabled={history.loading} onClick={history.reload}>Refresh</button></div>
        {history.loading ? <p role="status" className="empty">Loading market history…</p> : history.error ? <ErrorNotice message={history.error} retry={history.reload}/> : <>
          {latest && <div className="latest-price"><div><span className="label">Latest observed modal price</span><strong>{money(latest.modal_price)} <small>/ quintal</small></strong></div><div><span className="label">Latest available mandi record</span><time dateTime={latest.date}>{dateLabel(latest.date)}</time></div></div>}
          <PriceHistoryChart rows={rows}/>{latest && <p className="history-note">Historical records through {dateLabel(latest.date)}. These are not live prices.</p>}
        </>}
      </section>
    </div>
    <div className="tables-grid">
      <section className="panel" aria-labelledby="observations-title"><div className="panel-heading"><h3 id="observations-title">Recent observations</h3><span className="quiet">Latest {Math.min(rows.length,7)} records</span></div>
        {history.loading ? <p className="empty">Loading observations…</p> : history.error ? <p className="empty">Observations could not be loaded. Retry market history above.</p> : !rows.length ? <p className="empty">No observations available.</p> :
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Recent observations table"><table><thead><tr><th scope="col">Date</th><th scope="col">Min</th><th scope="col">Modal</th><th scope="col">Max</th></tr></thead><tbody>{rows.slice(-7).reverse().map(r => <tr key={r.date}><td>{dateLabel(r.date)}</td><td>{money(r.min_price)}</td><td className="modal-value">{money(r.modal_price)}</td><td>{money(r.max_price)}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="panel" aria-labelledby="saved-title" aria-busy={saved.loading}><div className="panel-heading"><h3 id="saved-title">Recent forecasts</h3><button className="text-button" disabled={saved.loading} onClick={saved.reload}>Refresh list</button></div>
        {saved.loading ? <p className="empty" role="status">Loading saved forecasts…</p> : saved.error ? <ErrorNotice message={saved.error} retry={saved.reload}/> : !saved.data?.length ? <p className="empty">No forecasts generated for this series yet.</p> :
          <ul className="saved-list">{saved.data.map(r => <li key={r.forecast_id}><div className="saved-top"><strong>{money(r.prediction)} <small>/ quintal</small></strong><span className="small-tag">{r.status === "available" ? "Saved" : r.status === "fallback" ? "Fallback" : "Unavailable"}</span></div><p>{methodLabel(r.method)} · Cutoff: {r.history_cutoff ? dateLabel(r.history_cutoff) : "Not available"}</p><time dateTime={r.generated_at}>{timeLabel(r.generated_at)} IST</time></li>)}</ul>}
      </section>
    </div>
    <DecisionSupport seriesId={series.series_id}/>
  </>;
}
export function ForecastDashboard() {
  const series = useResource(api.series);
  const [commodity,setCommodity] = useState(""), [selection,setSelection] = useState("");
  const items = [...(series.data ?? [])].sort((a,b) => `${a.commodity} ${a.market} ${a.variety}`.localeCompare(`${b.commodity} ${b.market} ${b.variety}`));
  const commodities = [...new Set(items.map(s => s.commodity))];
  const currentCommodity = commodities.includes(commodity) ? commodity : commodities[0] ?? "";
  const markets = items.filter(s => s.commodity === currentCommodity), selected = markets.find(s => s.series_id === selection) ?? markets[0];
  return <><section className="selector-panel" aria-labelledby="selector-title"><div className="selector-heading"><h2 id="selector-title">Select a market series</h2><button className="text-button" disabled={series.loading} onClick={series.reload}>Reload markets</button></div>
    {series.loading ? <p role="status">Loading supported markets…</p> : series.error ? <ErrorNotice message={series.error} retry={series.reload}/> : !items.length ? <p className="empty">No forecast-supported series are available yet. Please check again later.</p> :
      <div className="selectors"><label htmlFor="commodity">Commodity<select id="commodity" value={currentCommodity} onChange={e => {setCommodity(e.target.value); setSelection("");}}>{commodities.map(c => <option key={c}>{c}</option>)}</select></label><label htmlFor="series">Market / variety / grade<select id="series" value={selected?.series_id ?? ""} onChange={e => setSelection(e.target.value)}>{markets.map(s => <option key={s.series_id} value={s.series_id}>{s.market} · {s.district} · {s.variety} · {s.grade}</option>)}</select></label><p>{items.length} supported series<br/><span>Gujarat mandi records</span></p></div>}
    </section>{selected && <SeriesDashboard key={selected.series_id} series={selected}/>}
    <section className="how-it-works" aria-labelledby="explanation-title"><h2 id="explanation-title">How this forecast works</h2><p>AgriSense estimates the next reported market price. Depending on the selected series, it uses the latest valid price or the average of the latest seven observations. Missing calendar days are not filled. This is not a guaranteed 7-day or 30-day forecast.</p></section></>;
}
