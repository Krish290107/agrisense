"use client";
import {useCallback,useState} from "react";
import {api,dateLabel,methodLabel,money} from "@/lib/api";
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
    <div className="panel-heading"><h2 id="decision-title">Market decision support</h2><button className="text-button" onClick={comparison.reload} disabled={comparison.loading}>Refresh comparison</button></div>
    {comparison.loading ? <p role="status">Loading comparisons...</p> : comparison.error ? <div role="alert" className="error-notice">{comparison.error}<button className="text-button" onClick={comparison.reload}>Retry</button></div> : !rows.length ? <p>No comparable supported markets are available.</p> : <>
      <div className="tables-grid">
        <div><h3>Price signal</h3>{selected?.signal ? <>
          <strong>{selected.signal === "above" ? "Above" : selected.signal === "below" ? "Below" : "Near"} latest observed price</strong>
          <p>Latest: {money(forecast?.latest_observed_price)} / quintal<br/>Next-observation estimate: {money(forecast?.prediction)} / quintal<br/>Difference: {money(selected.difference)} / quintal ({Number(selected.percentage).toFixed(2)}%)</p>
          {forecast?.latest_observation_date && <p className="quiet">Latest available mandi record: {dateLabel(forecast.latest_observation_date)}. Historical data.</p>}
        </> : <p>Price signal unavailable: latest price or forecast is missing.</p>}
        <p className="quiet">Near means an absolute change below 2%. This fixed threshold is not tuned to past results.</p></div>
        <div><h3>Gross proceeds calculator</h3><label htmlFor="decision-quantity">Quantity in quintals</label>
          <input id="decision-quantity" inputMode="decimal" type="text" value={quantity} onChange={e => setQuantity(e.target.value)} aria-invalid={quantity !== "" && !validQuantity} aria-describedby="quantity-help" placeholder="Enter quantity"/>
          <p id="quantity-help" className="quiet">{quantity && !validQuantity ? "Enter a finite quantity greater than zero, using decimal digits." : "Enter a positive quantity. Costs are not included."}</p>
          {validQuantity && (totals.estimated === null || totals.observed === null) && <p role="status">Proceeds unavailable: missing price or quantity exceeds the calculation range.</p>}
          <dl className="forecast-details"><div><dt>At latest modal price</dt><dd>{money(totals.observed)}</dd></div><div><dt>At forecast price</dt><dd>{money(totals.estimated)}</dd></div><div><dt>Difference in gross proceeds</dt><dd>{money(totals.difference)}</dd></div></dl>
        </div>
      </div>
      <h3>Estimated price comparison</h3>
      <p className="quiet">{rows.length} supported series. {data?.scope === "exact_variety_grade" ? "Matching commodity, variety and grade." : "Broader commodity comparison: exact matches are limited."} Ordered by forecast price, highest first; ties by series ID. Unavailable estimates appear last.</p>
      {data?.warning && <p className="notice">{data.warning}</p>}
      <div className="comparison-grid">{rows.map(({forecast: f,difference,percentage}) => <article className="comparison-market" key={f.series.series_id}>
        <h4>{f.series.market}</h4><p>{f.series.district}, {f.series.state}<br/>{f.series.commodity} / {f.series.variety} / {f.series.grade}</p>
        <p className="quiet">Series: {f.series.series_id}</p>
        <dl className="forecast-details"><div><dt>Latest modal price</dt><dd>{money(f.latest_observed_price)}</dd></div><div><dt>Record date</dt><dd>{f.latest_observation_date ? dateLabel(f.latest_observation_date) : "Unavailable"}</dd></div><div><dt>Next-observation estimate</dt><dd>{money(f.prediction)}</dd></div><div><dt>Method</dt><dd>{methodLabel(f.method_used)}{f.fallback_used ? " (fallback)" : ""}</dd></div><div><dt>Difference / change</dt><dd>{money(difference)} / {percentage === null ? "Unavailable" : `${Number(percentage).toFixed(2)}%`}</dd></div><div><dt>Historical MAE</dt><dd>{money(f.historical_benchmark_mae)}</dd></div><div><dt>Estimated gross proceeds</dt><dd>{money(grossProceeds(quantity,f.prediction))}</dd></div></dl>
      </article>)}</div>
      {forecast?.status === "ok" && selected?.percentage != null && <p className="decision-summary">{forecast.series.market} {forecast.series.commodity} ({forecast.series.variety}, {forecast.series.grade}) has a latest recorded modal price of {money(forecast.latest_observed_price)}/quintal. The next-observation estimate is {money(forecast.prediction)}/quintal, {Math.abs(Number(selected.percentage)).toFixed(2)}% {Number(selected.percentage) < 0 ? "lower" : Number(selected.percentage) > 0 ? "higher" : "different"}.{totals.estimated !== null && ` For ${quantity.trim()} quintals, that corresponds to approximately ${money(totals.estimated)} in estimated gross proceeds.`}</p>}
      <p className="quiet">Prices and historical MAE are in INR/quintal. MAE is historical forecast error, not a guaranteed range. Comparison estimates are not saved. Historical records and next-observation estimates do not guarantee where or when to sell; costs and market access are not evaluated.</p>
    </>}
  </section>;
}
