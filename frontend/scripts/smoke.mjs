import assert from "node:assert/strict";
import {api} from "../src/lib/api.ts";
import {proceeds} from "../src/lib/decision.ts";

const signal = new AbortController().signal;
await api.health(signal);
const schema = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/openapi.json`).then(r => r.json());
for (const path of ["/health","/api/v1/forecast/series","/api/v1/forecast","/api/v1/decision/markets"]) assert.ok(schema.paths[path]);
const series = await api.series(signal);
assert.ok(series.length);
const rolling = series.filter(s => s.selected_method === "rolling_mean_7");
assert.ok(rolling.length);
const results = [];
for (const selected of rolling) {
  const history = await api.history(selected.series_id,signal);
  const savedBefore = await api.saved(selected.series_id,signal);
  const comparison = await api.decision(selected.series_id,signal);
  assert.deepEqual(await api.saved(selected.series_id,signal),savedBefore);
  const row = comparison.markets.find(r => r.forecast.series.series_id === selected.series_id);
  assert.ok(row);
  const forecast = await api.forecast(selected.series_id,signal);
  assert.equal(forecast.forecast_type,"next_observation");
  assert.equal(forecast.prediction,row.forecast.prediction);
  if (!history.observations.length) {
    assert.equal(forecast.status,"insufficient_history");
    assert.equal(forecast.prediction,null);
    assert.deepEqual(await api.saved(selected.series_id,signal),savedBefore);
    continue;
  }
  assert.equal(forecast.status,"ok");
  assert.equal(forecast.latest_observed_price,history.observations.at(-1).modal_price);
  const used = history.observations.length < 7 ? history.observations.slice(-1) : history.observations.slice(-7);
  const expected = used.reduce((sum,r) => sum + Number(r.modal_price),0) / used.length;
  assert.ok(Math.abs(Number(forecast.prediction) - expected) <= .000001);
  assert.equal(forecast.fallback_used,history.observations.length < 7);
  const totals = proceeds("10.5",forecast.latest_observed_price,forecast.prediction);
  assert.ok(Number.isFinite(totals.estimated));
  assert.ok(Math.abs(totals.difference - 10.5 * Number(row.difference)) < .000001);
  assert.ok(Math.abs(Number(row.percentage) - Number(row.difference) / Number(forecast.latest_observed_price) * 100) < .000001);
  const saved = await api.saved(selected.series_id,signal);
  assert.equal(saved.length,savedBefore.length + 1);
  await api.forecast(selected.series_id,signal);
  await api.decision(selected.series_id,signal);
  assert.deepEqual(await api.saved(selected.series_id,signal),saved);
  results.push({series_id:selected.series_id,commodity:selected.commodity,market:selected.market,latest:forecast.latest_observed_price,prediction:forecast.prediction,date:forecast.history_cutoff_date});
}
assert.ok(results.length);
console.log(JSON.stringify({supported_series:series.length,generated_series:results.length,rolling:results}));
