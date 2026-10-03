import { BackendStatus } from "@/components/backend-status";

const plannedFeatures = [
  {
    number: "01",
    name: "Real market data",
    description: "Bring agricultural price records into a reliable, well-documented dataset.",
    stage: "Data collection & preparation",
    path: "M5 5h14v14H5zM5 10h14M10 5v14M5 14.5h14",
  },
  {
    number: "02",
    name: "Price forecasting",
    description: "Explore historical patterns, build baselines, and evaluate prediction models.",
    stage: "Models & evaluation",
    path: "M4 4v16h16M7 15l4-5 4 2 5-7",
  },
  {
    number: "03",
    name: "Market dashboard",
    description: "Make verified market trends and model results easier to explore and understand.",
    stage: "Insights & visualization",
    path: "M4 4h6v7H4zM14 4h6v4h-6zM4 15h6v5H4zM14 12h6v8h-6z",
  },
  {
    number: "04",
    name: "Selling calculator",
    description: "Compare selling scenarios using market data and clearly stated assumptions.",
    stage: "Decision support",
    path: "M6 3h12v18H6zM9 7h6M9 11h.1M15 11h.1M9 15h.1M15 15h.1M9 18h.1M15 18h.1",
  },
];

function PlantMark({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <path d="M14 24V13M14 18C6 18 4 13 4 7c7 0 10 4 10 11ZM14 13c0-7 4-10 10-10 0 6-3 10-10 10Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Home() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="site-header">
        <a href="#" className="brand" aria-label="AgriSense home">
          <span className="brand-mark"><PlantMark /></span>
          <span>Agri<span className="brand-accent">Sense</span></span>
        </a>
        <nav aria-label="Main navigation" className="main-nav">
          <a href="#connection">Connection</a>
          <a href="#roadmap">What&apos;s next</a>
        </nav>
        <span className="project-tag"><span />College project</span>
      </header>

      <main id="main" className="page-shell">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-line" />AGRICULTURE, INFORMED.</div>
            <h1 id="hero-title">Better data.<br />More informed<br /><span>market decisions.</span></h1>
            <p className="hero-purpose">Agricultural Price Forecasting and<br className="desktop-break" /> Market Decision Support</p>
            <p className="hero-description">AgriSense is a college project exploring how agricultural price data can support clearer, evidence-based selling decisions.</p>
            <a className="text-link" href="#roadmap">Explore the project <span aria-hidden="true">↗</span></a>
          </div>

          <aside className="foundation-panel" aria-labelledby="foundation-title">
            <div className="panel-topline"><span className="section-kicker">THE PROJECT JOURNEY</span><span className="day-tag">DAY 01 / 14</span></div>
            <div className="field-art" aria-hidden="true">
              <svg viewBox="0 0 440 224" fill="none">
                <path d="M-30 185C54 73 131 62 248 137c70 45 123 30 218-57M-30 208C54 96 131 85 248 160c70 45 123 30 218-57M-30 231C54 119 131 108 248 183c70 45 123 30 218-57M-30 254C54 142 131 131 248 206c70 45 123 30 218-57M-30 277C54 165 131 154 248 229c70 45 123 30 218-57" stroke="currentColor" strokeWidth="1.2" />
                <circle cx="334" cy="48" r="23" stroke="currentColor" strokeWidth="1.2" />
                <path d="M184 123V72m0 35c-25 0-34-14-34-34 23 0 34 12 34 34Zm0-20c0-25 13-39 38-39 0 24-14 39-38 39Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div className="foundation-copy">
              <span className="small-label">CURRENT MILESTONE</span>
              <h2 id="foundation-title">Planting the foundation.</h2>
              <p>A local frontend, a working API, and a real connection between them. This is where AgriSense begins.</p>
            </div>
            <div className="journey-progress" aria-label="Day 1 of 14">
              {Array.from({ length: 14 }, (_, index) => <span key={index} className={index === 0 ? "current" : ""} />)}
            </div>
            <div className="progress-caption"><span>Setup & connection</span><span>Day 1 of 14</span></div>
          </aside>
        </section>

        <BackendStatus />

        <section id="roadmap" className="roadmap" aria-labelledby="roadmap-title">
          <div className="roadmap-heading">
            <div><span className="section-kicker">GROWING FROM HERE</span><h2 id="roadmap-title">The work ahead</h2></div>
            <p>Planned for the coming days.<br />These features are not available yet.</p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {plannedFeatures.map((feature) => (
              <article className="feature-card" key={feature.number}>
                <div className="feature-topline"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d={feature.path} /></svg><span className="planned-tag">Planned</span></div>
                <h3>{feature.name}</h3>
                <p>{feature.description}</p>
                <div className="feature-stage"><span>{feature.number}</span>{feature.stage}</div>
              </article>
            ))}
          </div>
          <p className="data-note"><span aria-hidden="true">↳</span> Market prices, forecasts, and model scores will appear only after real data is connected and evaluated.</p>
        </section>
      </main>

      <footer className="site-footer"><span className="footer-brand"><PlantMark />AgriSense</span><p>From agricultural data to informed decisions.</p><span>Day 01 · Foundation</span></footer>
    </>
  );
}
