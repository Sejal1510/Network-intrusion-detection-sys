/**
 * Ghosted hero centerpiece for OverviewPage only -- a central detection
 * core with spokes fanning to satellite sensors. Deliberately not a
 * generic "network globe": the shape it draws is a literal description
 * of this product (one detection core, many monitored segments), masked
 * to fade out before the first stat card so it never fights the data
 * below it (see `.hero-visual` in index.css).
 */
export function CoreHubVisual() {
  return (
    <div className="hero-visual">
      <svg viewBox="0 0 900 600" fill="none" aria-hidden="true">
        <circle cx="640" cy="230" r="120" stroke={`rgb(var(--bg-line-rgb))`} strokeWidth="1" opacity="0.2" />
        <circle cx="640" cy="230" r="200" stroke={`rgb(var(--bg-line-rgb))`} strokeWidth="1" opacity="0.14" />
        <g stroke={`rgb(var(--bg-line-rgb))`} strokeWidth="1" opacity="0.3">
          <path d="M640,230 L440,120" />
          <path d="M640,230 L780,90" />
          <path d="M640,230 L860,200" />
          <path d="M640,230 L830,380" />
          <path d="M640,230 L640,430" />
          <path d="M640,230 L470,400" />
          <path d="M640,230 L400,260" />
          <path d="M640,230 L470,160" />
        </g>
        <circle cx="640" cy="230" r="6" fill={`rgb(var(--bg-node-rgb))`} opacity="0.55" />
        <g fill={`rgb(var(--bg-node-rgb))`} opacity="0.45">
          <circle cx="440" cy="120" r="2.4" />
          <circle cx="780" cy="90" r="2.4" />
          <circle cx="860" cy="200" r="2.4" />
          <circle cx="830" cy="380" r="2.4" />
          <circle cx="640" cy="430" r="2.4" />
          <circle cx="470" cy="400" r="2.4" />
          <circle cx="400" cy="260" r="2.4" />
          <circle cx="470" cy="160" r="2.4" />
        </g>
      </svg>
      <div className="hero-pulse" style={{ offsetPath: "path('M640,230 L440,120')" }} />
      <div className="hero-pulse" style={{ offsetPath: "path('M640,230 L830,380')", animationDelay: "-4s" }} />
    </div>
  )
}
