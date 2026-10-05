import {dateLabel,money,type Observation} from "@/lib/api";
export function PriceHistoryChart({rows}: {rows: Observation[]}) {
  if (!rows.length) return <p className="empty">No price observations are available for this series.</p>;
  const values = rows.map(r => Number(r.modal_price)), dates = rows.map(r => Date.parse(r.date));
  const low = Math.min(...values), high = Math.max(...values), padding = Math.max((high-low)*.15,high*.025,1);
  const floor = Math.max(0,low-padding), ceiling = high+padding;
  const x = (i: number) => rows.length === 1 ? 365 : 80+(dates[i]-dates[0])/(dates.at(-1)!-dates[0])*570;
  const y = (price: number) => 205-(price-floor)/(ceiling-floor)*160;
  return <figure className="price-chart"><svg viewBox="0 0 700 255" role="img" aria-labelledby="chart-title chart-desc">
    <title id="chart-title">Recent modal price in INR per quintal</title><desc id="chart-desc">{rows.length} observations from {dateLabel(rows[0].date)} to {dateLabel(rows.at(-1)!.date)}. Modal prices range from {money(low)} to {money(high)}. See the recent observations table below.</desc>
    <text x="80" y="19">INR / quintal</text>
    {[0,1,2,3].map(i => {const v = floor+(ceiling-floor)*i/3; return <g key={i}><line x1="80" x2="650" y1={y(v)} y2={y(v)} className="grid-line"/><text x="68" y={y(v)+4} textAnchor="end">{Math.round(v).toLocaleString("en-IN")}</text></g>;})}
    <polyline points={rows.map((r,i) => `${x(i)},${y(Number(r.modal_price))}`).join(" ")} fill="none" stroke="#286349" strokeWidth="2.5"/>
    {rows.map((r,i) => <circle key={r.date} cx={x(i)} cy={y(Number(r.modal_price))} r="3.5" fill="#286349"><title>{dateLabel(r.date)}: {money(r.modal_price)} / quintal</title></circle>)}
    <text x={x(0)} y="234">{dateLabel(rows[0].date)}</text>{rows.length > 1 && <text x={x(rows.length-1)} y="234" textAnchor="end">{dateLabel(rows.at(-1)!.date)}</text>}
  </svg><figcaption><span className="legend-line"/>Modal price · observed dates only. Lines connect records; gaps are not filled.</figcaption></figure>;
}
