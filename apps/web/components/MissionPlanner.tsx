"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { HorizonChart } from "./HorizonChart";
import { Timeline } from "./Timeline";
import type { BodyState, SimulationResult } from "./types";
import type { Inspection, Layers, SceneStatus } from "./LunarScene";
import "./planner.css";
import "cesium/Build/Cesium/Widgets/widgets.css";

const LunarScene = dynamic(() => import("./LunarScene"), { ssr: false });
const initialLayers: Layers = {
  terrain: true,
  imagery: true,
  sites: true,
  sun: true,
  earth: true,
  illumination: false,
  slope: false,
  psr: false,
  uncertainty: false,
};
const stateName = (body: BodyState) =>
  body.state === "FULLY_VISIBLE"
    ? "Clear"
    : body.state === "PARTIALLY_VISIBLE"
      ? "Partial"
      : "Blocked";
function duration(seconds: number) {
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
function clock(iso: string) {
  return iso.slice(11, 16) + " UTC";
}
interface Manifest {
  sources: Array<{
    name: string;
    resolution_m: number;
    source_url: string;
    sha256: string;
  }>;
  imagery: { source_url: string };
  frame: string;
}

export function MissionPlanner() {
  const [data, setData] = useState<SimulationResult | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState("");
  const [rendererKey, setRendererKey] = useState(0);
  const rendererRestarts = useRef(0);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1000);
  const [layers, setLayers] = useState(initialLayers);
  const [flight, setFlight] = useState({ mode: "moon", id: 0 });
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [siteInfo, setSiteInfo] = useState<Inspection | null>(null);
  const [status, setStatus] = useState<SceneStatus>({
    altitude: 8000000,
    heading: 0,
    loaded: 0,
    pending: 0,
    fps: 0,
    scale: 0,
  });
  const [panel, setPanel] = useState<"none" | "horizon" | "data">("none");
  const [query, setQuery] = useState("");
  const [help, setHelp] = useState(false);
  const remainder = useRef(0);
  const ended = index === 1008;
  const running = playing && !ended;
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch("/data/simulation.json", { signal: controller.signal }).then(
        (r) => {
          if (!r.ok) throw new Error("Simulation export unavailable");
          return r.json();
        },
      ),
      fetch("/terrain/manifest.json", { signal: controller.signal }).then(
        (r) => {
          if (!r.ok) throw new Error("Run terrain preprocessing first");
          return r.json();
        },
      ),
    ])
      .then(([result, sources]) => {
        if (
          result.schema_version !== "1.1.0" ||
          result.validation.independent_spice.status !== "PASS" ||
          result.provenance_contract.validator_used_for_operational_samples !==
            false ||
          result.samples.length !== 1009
        )
          throw new Error(
            "The required validated simulation contract is missing",
          );
        setData(result);
        setManifest(sources);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    fetch("/api/terrain/inspect?lon=0&lat=-89.9", { signal: controller.signal })
      .then((r) => {
        if (!r.ok)
          throw new Error("Terrain service unavailable; start npm run planner");
        return r.json();
      })
      .then(setSiteInfo)
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!playing || !data || ended) return;
    let previous = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      remainder.current += ((now - previous) / 1000) * speed;
      previous = now;
      const steps = Math.floor(remainder.current / 600);
      if (steps) {
        remainder.current %= 600;
        setIndex((current) =>
          Math.min(data.samples.length - 1, current + steps),
        );
      }
    }, 100);
    return () => clearInterval(timer);
  }, [playing, speed, data, ended]);
  const inspect = useCallback((value: Inspection) => setInspection(value), []);
  const report = useCallback((value: SceneStatus) => setStatus(value), []);
  const failure = useCallback((value: string) => {
    setError(
      value.includes("Failed to fetch")
        ? "Local planner connection lost. Restart the background planner, then retry this view."
        : value,
    );
  }, []);
  const rendererFailure = useCallback((value: string) => {
    if (rendererRestarts.current < 1) {
      rendererRestarts.current++;
      setRendererKey((current) => current + 1);
      return;
    }
    setError(`3D rendering stopped: ${value}`);
  }, []);
  const restartRenderer = () => {
    rendererRestarts.current = 0;
    setError("");
    setRendererKey((current) => current + 1);
  };
  const fly = (mode: string) =>
    setFlight((current) => ({ mode, id: current.id + 1 }));
  const scrub = (next: number) => {
    setIndex(next);
    remainder.current = 0;
  };
  if (!data)
    return (
      <main className="planner-loading">
        <span className="mission-kicker">LUNAR / MISSION PLANNER</span>
        <h1>Opening the Moon</h1>
        <p>
          {error || "Loading the validated mission and NASA terrain catalogue…"}
        </p>
      </main>
    );
  const sample = data.samples[index];
  const now = Date.parse(sample.timestamp);
  const next = data.samples
    .slice(index + 1)
    .find((s) => s.combined_state !== sample.combined_state);
  const dte = data.windows.earth.dte_visible.intervals.find(
    (w) => Date.parse(w.start_utc) <= now && Date.parse(w.end_utc) > now,
  );
  const blackout = data.windows.earth.dte_blackout.intervals.find(
    (w) => Date.parse(w.start_utc) > now,
  );
  const available = (name: string) =>
    !!manifest?.sources.some((s) => s.name === name);
  const toggle = (key: keyof Layers) =>
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  return (
    <main className="mission-planner">
      <LunarScene
        key={rendererKey}
        data={data}
        sample={sample}
        layers={layers}
        flight={flight}
        onInspect={inspect}
        onStatus={report}
        onError={failure}
        onRendererError={rendererFailure}
      />
      <header className="planner-header">
        <div className="planner-brand">
          <span className="moon-glyph">◒</span>
          <div>
            <span className="mission-kicker">SURFACE OPERATIONS / 01</span>
            <h1>Lunar mission planner</h1>
          </div>
        </div>
        <div className="header-center">
          <i />
          NASA / JPL DATA <span>SPICE VERIFIED</span>
        </div>
        <div className="header-actions">
          <button onClick={() => setPanel(panel === "data" ? "none" : "data")}>
            Data & methodology
          </button>
          <button
            className="help-button"
            aria-label="Navigation help"
            onClick={() => setHelp(!help)}
          >
            ?
          </button>
        </div>
      </header>
      <aside className="map-sidebar">
        <span className="mission-kicker">EXPLORE THE SOUTH POLE</span>
        <label className="site-search">
          <span>⌕</span>
          <input
            aria-label="Search sites"
            placeholder="Find a site or region"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {"test site a south pole".includes(query.toLowerCase()) ? (
          <button
            className="site-option"
            onClick={() => {
              fly("site");
              setInspection(null);
            }}
          >
            <span className="site-pin">◎</span>
            <span>
              <strong>Test Site A</strong>
              <small>89.9000° S · 0.0000° E</small>
            </span>
            <span>↗</span>
          </button>
        ) : (
          <p className="empty-sites">
            No matching evaluated site. Only Test Site A has mission results.
          </p>
        )}
        <div className="view-presets">
          <button onClick={() => fly("moon")}>Moon</button>
          <button onClick={() => fly("pole")}>South pole</button>
          <button onClick={() => fly("site")}>Site</button>
        </div>
        <div className="layer-heading">
          <span className="mission-kicker">MAP LAYERS</span>
          <span>{Object.values(layers).filter(Boolean).length} active</span>
        </div>
        {(
          [
            [
              "SURFACE",
              [
                ["imagery", "Lunar imagery / relief", true],
                ["terrain", "LOLA elevation", true],
                ["sites", "Landing site", true],
              ],
            ],
            [
              "MISSION",
              [
                ["sun", "Sun direction", true],
                ["earth", "Earth direction", true],
                ["illumination", "Sun-driven lighting", true],
              ],
            ],
            [
              "ENGINEERING",
              [
                ["slope", "Slope", available("slope")],
                [
                  "uncertainty",
                  "Height uncertainty",
                  available("height_error"),
                ],
              ],
            ],
            ["SCIENCE", [["psr", "Permanent shadow", available("psr")]]],
          ] as Array<[string, Array<[keyof Layers, string, boolean]>]>
        ).map(([group, items]) => (
          <section className="layer-group" key={group}>
            <h2>{group}</h2>
            {items.map(([key, title, enabled]) => (
              <label
                className={`layer-control ${!enabled ? "disabled" : ""}`}
                key={key}
              >
                <input
                  type="checkbox"
                  checked={layers[key]}
                  disabled={!enabled}
                  onChange={() => toggle(key)}
                />
                <span>{title}</span>
                {!enabled && <small>Not loaded</small>}
              </label>
            ))}
          </section>
        ))}
        <label className="layer-control disabled resource">
          <input type="checkbox" disabled />
          <span>
            Resource evidence<small>Dataset not loaded</small>
          </span>
        </label>
        {layers.slope && (
          <div className="layer-legend">
            <span>Slope · degrees</span>
            <div className="slope-ramp" />
            <div className="legend-values">
              <span>0</span>
              <span>5</span>
              <span>10</span>
              <span>20+</span>
            </div>
            <small>NASA 20 m product · no safety threshold</small>
          </div>
        )}
        {layers.psr && (
          <p className="layer-note">
            PSR describes long-term shadow. It does not establish a water-ice
            deposit.
          </p>
        )}
        {layers.uncertainty && (
          <div className="layer-legend">
            <span>Height uncertainty · metres</span>
            <div className="slope-ramp" />
            <div className="legend-values">
              <span>0</span>
              <span>1.25</span>
              <span>2.5</span>
              <span>5+</span>
            </div>
          </div>
        )}
        <div className="sidebar-foot">
          <i /> REAL TERRAIN · TRUE SCALE
          <small>1737.4 km lunar reference sphere</small>
        </div>
      </aside>
      <div className="map-title">
        <span className="mission-kicker">
          {status.altitude > 500000
            ? "THE MOON"
            : status.altitude > 50000
              ? "LUNAR SOUTH POLE"
              : "TEST SITE A / SURFACE"}
        </span>
        <h2>
          {status.altitude > 500000
            ? "A world of possibilities."
            : status.altitude > 50000
              ? "At the edge of sunlight."
              : "Read the terrain. Plan the mission."}
        </h2>
        <p>
          {status.altitude > 300000
            ? "Global LOLA relief · LROC context imagery"
            : status.altitude > 30000
              ? "240 m regional LOLA · progressive terrain"
              : "10 m local LOLA · 20 m science overlays"}
        </p>
      </div>
      <section className="site-card">
        <div className="card-title">
          <span className="mission-kicker">EVALUATED SITE</span>
          <span className="verified-dot">● VERIFIED</span>
        </div>
        <h2>
          Test Site A{" "}
          <button title="Fly to Test Site A" onClick={() => fly("site")}>
            ↗
          </button>
        </h2>
        <p className="coordinates">89.9000° S, 0.0000° E</p>
        <div className="site-metrics">
          <div>
            <span>ELEVATION</span>
            <strong>
              628.23 <small>m</small>
            </strong>
          </div>
          <div>
            <span>SLOPE / 20 m</span>
            <strong>
              {siteInfo?.slope != null
                ? siteInfo.slope.toFixed(1) + "°"
                : "Not loaded"}
            </strong>
          </div>
          <div>
            <span>OBSERVER</span>
            <strong>
              +2 <small>m</small>
            </strong>
          </div>
        </div>
        {(["sun", "earth"] as const).map((name) => (
          <div key={name} className={`body-summary ${name}`}>
            <div>
              <span className="body-symbol">{name === "sun" ? "☀" : "◉"}</span>
              <strong>
                {name === "sun" ? "Sunlight" : "Earth visibility"}
              </strong>
              <span
                className={`visibility ${sample[name].state.toLowerCase()}`}
              >
                {stateName(sample[name])}
              </span>
            </div>
            <dl>
              <div>
                <dt>Azimuth</dt>
                <dd>{sample[name].azimuth_deg.toFixed(2)}°</dd>
              </div>
              <div>
                <dt>Elevation</dt>
                <dd>{sample[name].elevation_deg.toFixed(2)}°</dd>
              </div>
              <div>
                <dt>Clearance</dt>
                <dd>{sample[name].clearance_deg.toFixed(2)}°</dd>
              </div>
            </dl>
          </div>
        ))}
        <div className="power-readout">
          <span>SOLAR POWER POTENTIAL</span>
          <strong>
            {Math.round(sample.power.estimated_electrical_output_w)}{" "}
            <small>W</small>
          </strong>
          <small>
            {data.panel.panel_area_m2} m² · {data.panel.efficiency * 100}% · sun
            tracking
          </small>
        </div>
        <div className="next-event">
          <span>NEXT STATE CHANGE</span>
          <strong>
            {next
              ? `${duration((Date.parse(next.timestamp) - now) / 1000)} from now`
              : "End of evaluated interval"}
          </strong>
          <small>
            {next
              ? `${next.sun.state !== sample.sun.state ? "Sunlight" : "Earth visibility"} changes · ${clock(next.timestamp)}`
              : "No extrapolation beyond October 8"}
          </small>
        </div>
        <div className="dte-detail">
          <span>GEOMETRIC DTE</span>
          <p>
            {dte
              ? `${duration((Date.parse(dte.end_utc) - now) / 1000)} remaining in window`
              : "Earth line of sight unavailable"}
          </p>
          {blackout && (
            <small>
              Next blackout {clock(blackout.start_utc)} ·{" "}
              {duration(blackout.duration_seconds)}
            </small>
          )}
        </div>
        <button
          className="analysis-button"
          onClick={() => setPanel(panel === "horizon" ? "none" : "horizon")}
        >
          360° horizon analysis <span>↗</span>
        </button>
      </section>
      <div className="map-controls">
        <button onClick={() => fly("moon")} title="Moon overview">
          ◯
        </button>
        <button onClick={() => fly("site")} title="Center on site">
          ⌖
        </button>
        <button onClick={() => fly("los")} title="Sun and Earth line of sight">
          ↗
        </button>
      </div>
      <div className="map-reference">
        <span>N ↗ {status.heading.toFixed(0)}°</span>
        <span>
          CAMERA{" "}
          {(status.altitude / 1000).toFixed(status.altitude < 10000 ? 2 : 0)} km
        </span>
        {status.scale > 0 && (
          <span className="scale-bar">
            {status.scale >= 1000
              ? (status.scale / 1000).toFixed(1) + " km"
              : status.scale.toFixed(0) + " m"}
          </span>
        )}
      </div>
      <div className="render-caption">
        {layers.illumination
          ? "Sun-driven WebGL lighting · visual approximation"
          : "Relief lighting for terrain readability"}{" "}
        <span>Mission visibility uses backend ray tracing</span>
      </div>
      {help && (
        <section className="help-popover">
          <button onClick={() => setHelp(false)}>×</button>
          <h3>Explore the Moon</h3>
          <p>
            Drag to pan or rotate. Scroll to zoom. Right-drag or Ctrl-drag to
            tilt. Double-click terrain to fly closer. Click to inspect a point.
          </p>
          <p>
            Only Test Site A has evaluated Sun, Earth, and power states.
            Direction markers are distance-scaled visual proxies.
          </p>
        </section>
      )}
      {inspection && (
        <section className="inspection-card">
          <button
            className="close-panel"
            aria-label="Close terrain inspector"
            onClick={() => setInspection(null)}
          >
            ×
          </button>
          <span className="mission-kicker">TERRAIN INSPECTOR</span>
          <h3>
            {inspection.latitude.toFixed(5)}°, {inspection.longitude.toFixed(5)}
            ° E
          </h3>
          <dl>
            <div>
              <dt>Elevation</dt>
              <dd>{inspection.elevation_m.toFixed(2)} m</dd>
            </div>
            <div>
              <dt>Pixel spacing</dt>
              <dd>{inspection.resolution_m} m</dd>
            </div>
            <div>
              <dt>Slope (20 m product)</dt>
              <dd>
                {inspection.slope != null
                  ? inspection.slope.toFixed(2) + "°"
                  : "Outside slope coverage"}
              </dd>
            </div>
            {inspection.height_error != null && (
              <div>
                <dt>Height uncertainty</dt>
                <dd>{inspection.height_error.toFixed(2)} m</dd>
              </div>
            )}
            {inspection.slope_error != null && (
              <div>
                <dt>Slope uncertainty</dt>
                <dd>{inspection.slope_error.toFixed(2)}°</dd>
              </div>
            )}
            {inspection.effective_resolution != null && (
              <div>
                <dt>Effective resolution</dt>
                <dd>{inspection.effective_resolution.toFixed(1)} m</dd>
              </div>
            )}
            {inspection.count != null && (
              <div>
                <dt>LOLA returns / pixel</dt>
                <dd>{inspection.count}</dd>
              </div>
            )}
            {inspection.psr != null && (
              <div>
                <dt>NASA PSR map</dt>
                <dd>{inspection.psr >= 0.5 ? "PSR" : "Not PSR"}</dd>
              </div>
            )}
          </dl>
          <p>{inspection.dataset}</p>
          <small>
            Point inspection only. Mission states remain at Test Site A.
          </small>
        </section>
      )}
      {panel !== "none" && (
        <section className={`analysis-drawer ${panel}`}>
          <button
            className="close-panel"
            aria-label="Close analysis"
            onClick={() => setPanel("none")}
          >
            ×
          </button>
          {panel === "horizon" ? (
            <>
              <HorizonChart
                profile={data.horizon.profile}
                sun={sample.sun}
                earth={sample.earth}
              />
              <div className="obstructions">
                {(["sun", "earth"] as const).map((name) => {
                  const b = sample[name],
                    p =
                      data.horizon.profile[Math.round(b.azimuth_deg * 2) % 720];
                  return (
                    <div key={name}>
                      <strong>
                        {name.toUpperCase()} · {stateName(b)}
                      </strong>
                      <span>
                        Visible disk {(b.visibility_fraction * 100).toFixed(1)}%
                        · skyline {b.terrain_horizon_deg.toFixed(2)}°
                      </span>
                      <span>
                        Dominant skyline sample{" "}
                        {(p.obstruction_distance_m / 1000).toFixed(2)} km away
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <span className="mission-kicker">DATA / METHODOLOGY</span>
              <h2>A traceable view of the Moon.</h2>
              <p>
                NASA terrain and JPL celestial geometry meet at a fixed lunar
                observer. Every displayed mission state comes from the retained,
                SPICE-validated simulation.
              </p>
              <div className="provenance-grid">
                <article>
                  <h3>Terrain</h3>
                  <p>
                    LOLA global 4 pixels/degree (~7.6 km); 240 m regional crop;
                    10 m local crop, 20 × 20 km.
                  </p>
                  <small>
                    MOON_ME / DE421 · sphere radius 1737.4 km · true elevation
                    scale
                  </small>
                </article>
                <article>
                  <h3>Geometry / PASS</h3>
                  <p>JPL Horizons DE441 · local SPICE DE440s cross-check</p>
                  <small>
                    Max sky difference: Sun 0.000034″ · Earth 0.001800″. Both
                    share JPL ephemeris lineage.
                  </small>
                </article>
                <article>
                  <h3>Resolution & uncertainty</h3>
                  <p>
                    NASA slope, PSR, height/slope error, effective resolution
                    and counts are 20 m products in a 24 × 24 km crop.
                  </p>
                  <small>
                    Pixel spacing is not a guarantee of effective resolution.
                    Inspect a point for actual metadata.
                  </small>
                </article>
                <article>
                  <h3>Mission limits</h3>
                  <p>
                    1,009 epochs · 10 minute cadence · 2 m observer above local
                    terrain.
                  </p>
                  <small>
                    Geometric DTE is not a radio link budget. WebGL lighting
                    does not determine mission visibility. Power uses the stated
                    idealized panel.
                  </small>
                </article>
              </div>
              <div className="data-links">
                <a href="/data/simulation.json" download>
                  Simulation JSON ↗
                </a>
                <a href="/terrain/manifest.json" download>
                  Terrain provenance ↗
                </a>
                <a
                  href="https://pgda.gsfc.nasa.gov/products/90"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA PGDA ↗
                </a>
                <a
                  href="https://svs.gsfc.nasa.gov/4720/"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA global map ↗
                </a>
              </div>
              <small>
                Resource evidence: dataset not loaded. PSR does not establish
                ice. Cross-site metrics and mission constraints are reserved for
                future evaluation.
              </small>
            </>
          )}
        </section>
      )}
      <footer className="mission-time">
        <div className="time-header">
          <div>
            <span className="mission-kicker">MISSION TIME / UTC</span>
            <strong>
              {sample.timestamp.slice(0, 10)} <em>{clock(sample.timestamp)}</em>
            </strong>
          </div>
          <div className="time-actions">
            <button
              aria-label="Step backward"
              onClick={() => scrub(Math.max(0, index - 1))}
            >
              −10m
            </button>
            <button
              className="play-control"
              aria-label={running ? "Pause simulation" : "Play simulation"}
              onClick={() => {
                if (index === 1008) scrub(0);
                setPlaying(!running);
              }}
            >
              {running ? "Ⅱ" : "▶"}
            </button>
            <button
              aria-label="Step forward"
              onClick={() => scrub(Math.min(1008, index + 1))}
            >
              +10m
            </button>
            <select
              aria-label="Simulation speed"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {[1, 10, 100, 1000].map((x) => (
                <option key={x} value={x}>
                  {x}×
                </option>
              ))}
            </select>
          </div>
          <span className="time-count">
            {index + 1} / 1,009 <small>10 minute samples</small>
          </span>
        </div>
        <Timeline samples={data.samples} index={index} onChange={scrub} />
        <input
          className="time-slider"
          aria-label="Simulation timestamp"
          type="range"
          min={0}
          max={1008}
          value={index}
          onChange={(e) => scrub(Number(e.target.value))}
        />
        <div className="time-dates">
          <span>OCT 01, 2026</span>
          <span>
            Sun + Earth overlap{" "}
            {data.windows.combined[
              "SUN_VISIBLE_EARTH_VISIBLE"
            ].percentage.toFixed(1)}
            % · transitions resolved to 10 min
          </span>
          <span>OCT 08, 2026</span>
        </div>
      </footer>
      <div className="stream-status">
        {status.pending
          ? `STREAMING ${status.pending} TILES`
          : `${status.loaded} TERRAIN TILES`}{" "}
        · {status.fps.toFixed(0)} render fps <span>idle rendering sleeps</span>
      </div>
      {error && (
        <div className="planner-error" role="alert">
          <strong>Data or renderer issue</strong>
          <span>{error}</span>
          {(error.startsWith("3D rendering stopped") ||
            error.startsWith("Local planner connection lost")) && (
            <button onClick={restartRenderer}>Retry 3D view</button>
          )}
          <button onClick={() => setError("")}>Dismiss</button>
        </div>
      )}
    </main>
  );
}
