"use client";
import {useCallback,useState} from "react";
import {api,money} from "@/lib/api";
import {grossProceeds,proceeds,quantityValue} from "@/lib/decision";
import {useResource} from "@/lib/use-resource";

export function DecisionSupport({seriesId}: {seriesId: string}) {
  const comparison = useResource(useCallback((s: AbortSignal) => api.decision(seriesId,s),[seriesId]));
  const [quantity,setQuantity] = useState("");
  const data = comparison.data, rows = data?.markets ?? [];
  const selected = rows.find(r => r.forecast.series.series_id === seriesId), forecast = selected?.forecast;
  const totals = proceeds(quantity,forecast?.latest_observed_price ?? null,forecast?.prediction ?? null);
  const validQuantity = quantityValue(quantity) !== null;
  return <section className="panel decision-support" aria-labelledby="decision-title" aria-busy={comparison.loading}>
    <div className="panel-heading"><h2 id="decision-title">Market decision support</h2></div>
    {comparison.loading ? <p role="status">Loading comparisons...</p> : comparison.error ? <div role="alert" className="error-notice">{comparison.error}<button className="text-button" onClick={comparison.reload}>Retry</button></div> : !rows.length ? <p>No comparable supported markets are available.</p> : <>
      <div className="tables-grid">
        <div><h3>Price signal</h3>{selected?.signal ? <>
          <strong>{selected.signal === "above" ? "Above" : selected.signal === "below" ? "Below" : "Near"} latest observed price</strong>
          <p>Latest: {money(forecast?.latest_observed_price)} / quintal<br/>Next-observation estimate: {money(forecast?.prediction)} / quintal<br/>Difference: {money(selected.difference)} / quintal ({Number(selected.percentage).toFixed(2)}%)</p>
        </> : <p>Price signal unavailable: latest price or forecast is missing.</p>}</div>
        <div><h3>Gross proceeds calculator</h3><label htmlFor="decision-quantity">Quantity in quintals</label>
          <input id="decision-quantity" inputMode="decimal" type="text" value={quantity} onChange={e => setQuantity(e.target.value)} aria-invalid={quantity !== "" && !validQuantity} aria-describedby="quantity-help" placeholder="Enter quantity"/>
          <p id="quantity-help" className="quiet">{quantity && !validQuantity ? "Enter a finite quantity greater than zero, using decimal digits." : "Enter quantity in quintals."}</p>
          {validQuantity && (totals.estimated === null || totals.observed === null) && <p role="status">Proceeds unavailable: missing price or quantity exceeds the calculation range.</p>}
          <dl className="forecast-details"><div><dt>At latest modal price</dt><dd>{money(totals.observed)}</dd></div><div><dt>At forecast price</dt><dd>{money(totals.estimated)}</dd></div><div><dt>Difference in gross proceeds</dt><dd>{money(totals.difference)}</dd></div></dl>
        </div>
      </div>
      <h3>Estimated price comparison</h3>
      {data?.warning && <p className="notice">{data.warning}</p>}
      <div className="comparison-grid">{rows.map(({forecast: f,difference,percentage}) => <article className="comparison-market" key={f.series.series_id}>
        <h4>{f.series.market}</h4><p>{f.series.district}, {f.series.state}<br/>{f.series.commodity} / {f.series.variety} / {f.series.grade}</p>
        <dl className="forecast-details"><div><dt>Latest modal price</dt><dd>{money(f.latest_observed_price)}</dd></div><div><dt>Next-observation estimate</dt><dd>{money(f.prediction)}</dd></div><div><dt>Difference / change</dt><dd>{money(difference)} / {percentage === null ? "Unavailable" : `${Number(percentage).toFixed(2)}%`}</dd></div><div><dt>Estimated gross proceeds</dt><dd>{money(grossProceeds(quantity,f.prediction))}</dd></div></dl>
      </article>)}</div>
    </>}
  </section>;
}
