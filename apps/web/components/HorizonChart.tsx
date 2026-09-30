import type { BodyState, HorizonPoint } from "./types";

const WIDTH = 920;
const HEIGHT = 330;
const MARGIN = { top: 34, right: 24, bottom: 44, left: 58 };

function pathFor(
  points: HorizonPoint[],
  x: (value: number) => number,
  y: (value: number) => number,
) {
  return points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${x(point.azimuth_deg).toFixed(2)},${y(
          point.elevation_deg,
        ).toFixed(2)}`,
    )
    .join(" ");
}

function statusLabel(body: BodyState) {
  if (body.state === "FULLY_VISIBLE") return "CLEAR";
  if (body.state === "PARTIALLY_VISIBLE") {
    return `${Math.round(body.visibility_fraction * 100)}% DISC`;
  }
  return "OCCULTED";
}

export function HorizonChart({
  profile,
  sun,
  earth,
}: {
  profile: HorizonPoint[];
  sun: BodyState;
  earth: BodyState;
}) {
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const values = profile.map((point) => point.elevation_deg);
  values.push(sun.elevation_deg, earth.elevation_deg, 0);
  const yMin = Math.floor(Math.min(...values) - 1);
  const yMax = Math.ceil(Math.max(...values) + 1);
  const x = (value: number) => MARGIN.left + (value / 360) * plotWidth;
  const y = (value: number) =>
    MARGIN.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
  const terrainPath = pathFor(profile, x, y);
  const fillPath = `${terrainPath} L${x(359.5)},${y(yMin)} L${x(0)},${y(
    yMin,
  )} Z`;
  const yTicks = Array.from({ length: 5 }, (_, index) =>
    yMin + ((yMax - yMin) * index) / 4,
  );
  const objects = [
    { key: "sun", label: "SUN", color: "#ffbc54", body: sun },
    { key: "earth", label: "EARTH", color: "#7ad9ff", body: earth },
  ];

  return (
    <section className="panel horizon-panel" aria-label="Terrain horizon plot">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">LOCAL SKY / TERRAIN OCCULTATION</span>
          <h2>360° horizon profile</h2>
        </div>
        <div className="chart-legend" aria-label="Plot legend">
          <span><i className="legend-dot terrain" />LOLA skyline</span>
          <span><i className="legend-dot sun" />Horizons Sun center</span>
          <span><i className="legend-dot earth" />Horizons Earth center</span>
        </div>
      </div>
      <svg
        className="horizon-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Terrain skyline. Sun ${statusLabel(sun)} at ${sun.elevation_deg.toFixed(
          2,
        )} degrees. Earth ${statusLabel(earth)} at ${earth.elevation_deg.toFixed(2)} degrees.`}
      >
        <defs>
          <linearGradient id="terrain-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#87909a" stopOpacity="0.72" />
            <stop offset="100%" stopColor="#343941" stopOpacity="0.97" />
          </linearGradient>
          <filter id="marker-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect
          x={MARGIN.left}
          y={MARGIN.top}
          width={plotWidth}
          height={plotHeight}
          rx="7"
          className="chart-backdrop"
        />
        {yTicks.map((tick) => (
          <g key={tick}>
            <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} className="grid-line" />
            <text x={MARGIN.left - 12} y={y(tick) + 4} textAnchor="end" className="axis-label">
              {tick.toFixed(0)}°
            </text>
          </g>
        ))}
        {[0, 90, 180, 270, 360].map((tick) => (
          <g key={tick}>
            <line x1={x(tick)} x2={x(tick)} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} className="grid-line vertical" />
            <text x={x(tick)} y={HEIGHT - 17} textAnchor={tick === 0 ? "start" : tick === 360 ? "end" : "middle"} className="axis-label cardinal">
              {tick === 0 || tick === 360 ? `${tick}° N` : tick === 90 ? "90° E" : tick === 180 ? "180° S" : "270° W"}
            </text>
          </g>
        ))}
        {yMin < 0 && yMax > 0 ? (
          <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(0)} y2={y(0)} className="zero-line" />
        ) : null}
        <path d={fillPath} fill="url(#terrain-fill)" />
        <path d={terrainPath} className="terrain-line" />
        {objects.map(({ key, label, color, body }) => {
          const markerX = x(body.azimuth_deg);
          const markerY = y(body.elevation_deg);
          const skylineY = y(body.terrain_horizon_deg);
          const radius = key === "sun" ? 7 : 8;
          return (
            <g key={key}>
              <line x1={markerX} x2={markerX} y1={markerY} y2={skylineY} stroke={color} className="clearance-line" />
              <circle cx={markerX} cy={skylineY} r="3" fill={color} className="skyline-intercept" />
              <circle cx={markerX} cy={markerY} r={radius + 5} fill={color} opacity="0.13" filter="url(#marker-glow)" />
              <circle cx={markerX} cy={markerY} r={radius} fill={color} className="object-marker" />
              {key === "earth" ? <path d={`M${markerX - 5},${markerY} q5,-4 10,0 q-5,4 -10,0`} className="earth-glyph" /> : null}
              <text x={markerX} y={Math.max(17, markerY - 16)} textAnchor="middle" fill={color} className="object-label">
                {label} · {statusLabel(body)}
              </text>
            </g>
          );
        })}
        <text x="18" y={MARGIN.top + plotHeight / 2} transform={`rotate(-90 18 ${MARGIN.top + plotHeight / 2})`} textAnchor="middle" className="axis-title">
          ELEVATION ABOVE LOCAL TANGENT
        </text>
      </svg>
      <div className="chart-footnote">
        <span>Highest obstruction from 10 m local + 240 m outer LOLA raycasts</span>
        <span>Disk / skyline geometry shown at true angular scale</span>
      </div>
    </section>
  );
}
