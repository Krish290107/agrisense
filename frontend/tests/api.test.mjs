import test from "node:test";
import assert from "node:assert/strict";
import {api,isSupported,isHistory,isForecast,isSaved,isComparison,money,methodLabel} from "../src/lib/api.ts";

const series = {series_id:"0123456789abcdef",state:"Gujarat",district:"Fixture",market:"Fixture",commodity:"Onion",variety:"Other",grade:"FAQ",price_unit:"INR/quintal",selected_method:"rolling_mean_7",policy_version:"test-v1"};
const row = {date:"2025-01-01",min_price:"100",modal_price:"150",max_price:"200"};
const forecast = {status:"ok",series,forecast_type:"next_observation",price_unit:"INR/quintal",prediction:"142.857143",selected_method:"rolling_mean_7",method_used:"rolling_mean_7",fallback_used:false,history_observations_used:7,history_cutoff_date:"2025-01-01",latest_observed_price:"150",generated_at:"2026-10-06T06:00:00+00:00",historical_benchmark_mae:10};

test("decision contract and GET client preserve exact identity, dates and unavailable values", async () => {
  const comparison = {selected_series_id:series.series_id,scope:"commodity",warning:"Compare varieties carefully",markets:[{forecast:{...forecast,latest_observation_date:"2025-01-01"},difference:"-7.142857",percentage:"-4.7619046667",signal:"below"}]};
  assert.ok(isComparison(comparison));
  assert.equal(isComparison({...comparison,markets:[comparison.markets[0],comparison.markets[0]]}), false);
  assert.equal(isComparison({...comparison,markets:[{...comparison.markets[0],difference:null}]}), false);
  const original = globalThis.fetch, env = process.env.NEXT_PUBLIC_API_BASE_URL;
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://localhost:8000";
  globalThis.fetch = async (url,options) => {
    assert.equal(url.pathname,"/api/v1/decision/markets");
    assert.equal(url.searchParams.get("series_id"),series.series_id);
    assert.equal(options.method,"GET"); assert.equal(options.body,undefined);
    return new Response(JSON.stringify(comparison));
  };
  try {assert.deepEqual(await api.decision(series.series_id,new AbortController().signal),comparison);}
  finally {globalThis.fetch=original; if (env===undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL; else process.env.NEXT_PUBLIC_API_BASE_URL=env;}
});

test("supported series require exact identities and unique IDs", () => {
  assert.ok(isSupported([series])); assert.ok(isSupported([]));
  assert.equal(isSupported([{...series,grade:""}]),false);
  assert.equal(isSupported([series,series]),false);
  assert.equal(isSupported([{...series,selected_method:"ml"}]),false);
});
test("history rejects malformed dates, prices, ordering and duplicates", () => {
  const h = {series,forecast_supported:true,observations:[row]};
  assert.ok(isHistory(h)); assert.ok(isHistory({...h,observations:[]}));
  for (const invalid of [{...row,modal_price:"0"},{...row,date:"2025-02-30"},{...row,max_price:"125"},{...row,min_price:null}]) assert.equal(isHistory({...h,observations:[invalid]}),false);
  assert.equal(isHistory({...h,observations:[row,row]}),false);
});
test("forecast contract requires next-observation semantics and correct method metadata", () => {
  assert.ok(isForecast(forecast));
  for (const invalid of [{...forecast,prediction:"0"},{...forecast,forecast_type:"7_day"},{...forecast,method_used:"ml"},{...forecast,history_observations_used:8},{...forecast,generated_at:"invalid"}]) assert.equal(isForecast(invalid),false);
  assert.ok(isForecast({...forecast,method_used:"naive",fallback_used:true,history_observations_used:1}));
});
test("unavailable forecast uses null, never an invented price", () => {
  const unavailable = {...forecast,status:"insufficient_history",prediction:null,method_used:null,history_observations_used:0,history_cutoff_date:null};
  assert.ok(isForecast(unavailable)); assert.equal(isForecast({...unavailable,prediction:"0"}),false);
  assert.ok(isForecast({...unavailable,status:"unsupported_series",selected_method:null}));
  assert.equal(money(null),"—"); assert.equal(money(undefined),"—");
});
test("saved forecasts and display precision preserve their meaning", () => {
  const saved = {forecast_id:"test",generated_at:forecast.generated_at,prediction:forecast.prediction,method:"rolling_mean_7",history_cutoff:row.date,status:"available"};
  assert.ok(isSaved([saved])); assert.ok(isSaved([])); assert.equal(isSaved([{...saved,prediction:null}]),false);
  assert.match(money("142.857143"),/142\.86/); assert.equal(methodLabel("rolling_mean_7"),"Average of 7 observations");
});
test("client calls all five endpoints, encodes POST identity and rejects cross-series replies", async () => {
  const original = globalThis.fetch, env = process.env.NEXT_PUBLIC_API_BASE_URL;
  process.env.NEXT_PUBLIC_API_BASE_URL="http://localhost:8000/";
  const calls=[]; let wrong=false;
  globalThis.fetch=async (url,options) => {
    calls.push({url:String(url),...options});
    const data = url.pathname==="/health" ? {status:"ok",service:"agrisense-api"} : url.pathname.endsWith("/series") ? [series] : url.pathname.endsWith("/history") ? {series:{...series,series_id:wrong ? "aaaaaaaaaaaaaaaa" : series.series_id},forecast_supported:true,observations:[row]} : url.pathname.endsWith("/forecasts") ? [] : forecast;
    return new Response(JSON.stringify(data),{status:200});
  };
  try {
    const signal=new AbortController().signal;
    await api.health(signal); await api.series(signal); await api.history(series.series_id,signal); await api.forecast(series.series_id,signal); await api.saved(series.series_id,signal);
    assert.equal(calls.length,5); assert.equal(calls.filter(c=>c.method==="POST").length,1);
    assert.deepEqual(JSON.parse(calls[3].body),{series_id:series.series_id});
    assert.match(calls[2].url,/limit=30$/); assert.match(calls[4].url,/limit=5$/);
    wrong=true; await assert.rejects(api.history(series.series_id,signal),/unexpected data/);
  } finally {globalThis.fetch=original; if(env===undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL; else process.env.NEXT_PUBLIC_API_BASE_URL=env;}
});
test("network, HTTP and invalid-response errors are safe for display", async () => {
  const original=globalThis.fetch, env=process.env.NEXT_PUBLIC_API_BASE_URL;
  process.env.NEXT_PUBLIC_API_BASE_URL="http://localhost:8000";
  try {
    globalThis.fetch=async()=>new Response('private SQL details',{status:503});
    await assert.rejects(api.series(new AbortController().signal),/temporarily unavailable/);
    globalThis.fetch=async()=>new Response('not JSON',{status:200});
    await assert.rejects(api.series(new AbortController().signal),/unexpected response/);
    globalThis.fetch=async()=>{throw new TypeError('internal connection detail');};
    await assert.rejects(api.series(new AbortController().signal),/Cannot reach/);
  } finally {globalThis.fetch=original; if(env===undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL; else process.env.NEXT_PUBLIC_API_BASE_URL=env;}
});
