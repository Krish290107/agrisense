import Link from "next/link";
import {BackendStatus} from "@/components/backend-status";
import {ForecastDashboard} from "@/components/forecast-dashboard";
export default function Home() {
  return <><a className="skip-link" href="#main">Skip to dashboard</a><header className="site-header"><Link href="/" className="brand" aria-label="AgriSense home"><svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M14 24V13M14 18C6 18 4 13 4 7c7 0 10 4 10 11ZM14 13c0-7 4-10 10-10 0 6-3 10-10 10Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>AgriSense</Link><BackendStatus/></header><main id="main" className="page-shell"><div className="page-title"><p className="eyebrow">GUJARAT &middot; MARKET PRICES</p><h1>Market Forecast Dashboard</h1><p>View recent mandi prices and estimate the next reported market price.</p></div><ForecastDashboard/></main><footer className="site-footer"><span>AgriSense &middot; Krishkumar &middot; IIT Patna</span><span>Estimates are based on historical mandi data and are not live prices or guaranteed future prices.</span></footer></>;
}
