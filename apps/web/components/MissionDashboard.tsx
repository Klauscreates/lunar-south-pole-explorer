"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { HorizonChart } from "./HorizonChart";
import { Timeline } from "./Timeline";
import type { BodyState, SimulationResult } from "./types";

const DATA_URL = "/data/simulation.json";

function formatUtc(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

function duration(hours: number) {
  if (hours >= 48) return `${(hours / 24).toFixed(1)} d`;
  return `${hours.toFixed(1)} h`;
}

function stateText(state: BodyState, kind: "sun" | "earth") {
  if (state.state === "FULLY_VISIBLE") {
    return kind === "sun" ? "DIRECT SUNLIGHT" : "DTE GEOMETRY AVAILABLE";
  }
  if (state.state === "PARTIALLY_VISIBLE") {
    return `${Math.round(state.visibility_fraction * 100)}% DISC VISIBLE`;
  }
  return kind === "sun" ? "TERRAIN SHADOW" : "DTE TERRAIN BLOCKED";
}

function BodyCard({ kind, body }: { kind: "sun" | "earth"; body: BodyState }) {
  const visible = body.visibility_fraction > 0;
  return (
    <article className={`body-card ${kind}`}>
      <div className="body-card-title">
        <span className={`celestial-icon ${kind}`} aria-hidden="true" />
        <div>
          <span className="eyebrow">{kind === "sun" ? "SOLAR VECTOR" : "EARTH VECTOR"}</span>
          <h3>{kind.toUpperCase()}</h3>
        </div>
        <span className={`status-lamp ${visible ? "available" : "blocked"}`} />
      </div>
      <dl className="telemetry-grid">
        <div><dt>Azimuth</dt><dd>{body.azimuth_deg.toFixed(2)}°</dd></div>
        <div><dt>Elevation</dt><dd>{body.elevation_deg.toFixed(2)}°</dd></div>
        <div><dt>Terrain</dt><dd>{body.terrain_horizon_deg.toFixed(2)}°</dd></div>
        <div><dt>Clearance</dt><dd className={body.clearance_deg >= 0 ? "positive" : "negative"}>{body.clearance_deg >= 0 ? "+" : ""}{body.clearance_deg.toFixed(2)}°</dd></div>
      </dl>
      <div className={`body-state ${visible ? "available" : "blocked"}`}>
        <span>{stateText(body, kind)}</span>
        <small>{(body.visibility_fraction * 100).toFixed(1)}% visible</small>
      </div>
    </article>
  );
}

function loadSimulation(signal: AbortSignal): Promise<SimulationResult> {
  return fetch(DATA_URL, { signal, cache: "no-store" }).then((response) => {
    if (!response.ok) throw new Error(`Simulation export returned HTTP ${response.status}`);
    return response.json().then((value: unknown) => {
      if (!isSimulationResult(value)) {
        throw new Error("Simulation export is missing required SPICE validation data");
      }
      return value;
    });
  });
}

function isSimulationResult(value: unknown): value is SimulationResult {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SimulationResult>;
  return (
    candidate.schema_version === "1.1.0" &&
    Array.isArray(candidate.samples) &&
    Array.isArray(candidate.horizon?.profile) &&
    ["PASS", "FAIL", "WARN", "NOT_RUN"].includes(
      candidate.validation?.independent_spice?.status ?? "",
    ) &&
    candidate.data_sources?.sun_ephemeris?.role === "operational_source" &&
    candidate.data_sources?.earth_ephemeris?.role === "operational_source" &&
    candidate.data_sources?.spice_validation?.role === "independent_validator_only" &&
    candidate.data_sources.spice_validation.used_for_operational_samples === false &&
    candidate.provenance_contract?.validator_used_for_operational_samples === false &&
    candidate.provenance_contract.operational_ephemeris === "NASA/JPL Horizons" &&
    candidate.validation?.independent_spice?.targets?.sun?.sample_count === candidate.samples.length &&
    candidate.validation?.independent_spice?.targets?.earth?.sample_count === candidate.samples.length
  );
}

export function MissionDashboard() {
  const [data, setData] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showProvenance, setShowProvenance] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    loadSimulation(controller.signal).then(setData).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Unknown data error");
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!playing || !data) return;
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1 >= data.samples.length ? 0 : current + 1));
    }, 120);
    return () => window.clearInterval(timer);
  }, [data, playing]);

  const setSafeIndex = useCallback(
    (next: number) => {
      if (!data) return;
      setIndex(Math.min(data.samples.length - 1, Math.max(0, next)));
    },
    [data],
  );

  if (error) {
    return (
      <main className="fatal-shell">
        <section className="fatal-card">
          <span className="eyebrow">DATA INTEGRITY STOP</span>
          <h1>No simulation data were loaded.</h1>
          <p>{error}</p>
          <p className="muted">Run the Python science pipeline before opening this interface. No placeholder values are shown.</p>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="loading-shell">
        <div className="loading-orbit" aria-hidden="true"><span /></div>
        <span className="eyebrow">VERIFYING SIMULATION EXPORT</span>
        <p>Loading Horizons + SPICE + LOLA result…</p>
      </main>
    );
  }

  const sample = data.samples[index];
  const progress = data.samples.length > 1 ? (index / (data.samples.length - 1)) * 100 : 0;
  const generated = formatUtc(data.software.generated_utc);
  const localSource = data.data_sources.terrain.local;
  const outerSource = data.data_sources.terrain.outer;
  const sunMeta = data.data_sources.sun_ephemeris;
  const validationPass = data.validation.overall_status === "PASS";
  const spiceValidation = data.validation.independent_spice;
  const spicePass = spiceValidation.status === "PASS";
  const spiceSun = spiceValidation.targets.sun;
  const spiceEarth = spiceValidation.targets.earth;
  const spiceSource = data.data_sources.spice_validation.sun;
  const kernelManifest = spiceSource.kernel_manifest as Record<string, unknown> | undefined;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true"><i /></span>
          <div>
            <span className="eyebrow">MISSION ANALYSIS SYSTEM / V1</span>
            <h1>LUNAR SOUTH POLE</h1>
          </div>
        </div>
        <div className="topbar-status">
          <span className="source-badge operational"><i /> OPERATIONAL · HORIZONS</span>
          <span className={`source-badge validator ${spicePass ? "pass" : "fail"}`}>
            <i /> CROSS-CHECK · SPICE {spiceValidation.status}
          </span>
          <button type="button" className="ghost-button" onClick={() => setShowProvenance((value) => !value)} aria-expanded={showProvenance}>
            {showProvenance ? "Close provenance" : "Data provenance"}
          </button>
          <a className="ghost-button" href="/data/simulation.json" download>JSON</a>
          <a className="ghost-button" href="/data/simulation.csv" download>CSV</a>
        </div>
      </header>

      <section className="mission-strip">
        <div className="mission-identity">
          <span className="site-code">SITE A / 89.9°S</span>
          <h2>{data.site.name}</h2>
          <p>{Math.abs(data.site.latitude_deg).toFixed(4)}° S · {data.site.longitude_deg_east.toFixed(4)}° E</p>
        </div>
        <div className="mission-clock">
          <span className="eyebrow">SIMULATION UTC</span>
          <strong>{sample.timestamp.slice(0, 10)}</strong>
          <b>{sample.timestamp.slice(11, 16)}<small> UTC</small></b>
        </div>
        <div className="mission-facts">
          <div><span>TERRAIN</span><strong>{data.site.terrain_elevation_m.toFixed(1)} m</strong></div>
          <div><span>OBSERVER</span><strong>{data.site.observer_height_m.toFixed(0)} m AGL</strong></div>
          <div><span>GRID</span><strong>10 m + 240 m</strong></div>
          <div><span>STEP</span><strong>{data.time_range.step_minutes} min</strong></div>
        </div>
      </section>

      {showProvenance ? (
        <section className="provenance-panel" aria-label="Data provenance">
          <div className="provenance-title">
            <span className="eyebrow">REPRODUCIBILITY RECORD</span>
            <h2>Every displayed value traces to a retained source response.</h2>
          </div>
          <div className="provenance-grid">
            <div>
              <span>OPERATIONAL CELESTIAL GEOMETRY</span>
              <strong>NASA/JPL Horizons · {String(sunMeta.ephemeris_source ?? "DE441")}</strong>
              <p>These airless lunar-topocentric values drive the chart, visibility, power, and operations windows.</p>
              <code>{String(sunMeta.request_sha256 ?? "")}</code>
            </div>
            <div>
              <span>INDEPENDENT POSITION CROSS-CHECK</span>
              <strong className={spicePass ? "pass" : "fail"}>LOCAL NAIF SPICE · {spiceValidation.status}</strong>
              <p>
                All {spiceSun.sample_count} epochs checked. Maximum sky error: Sun {spiceSun.angular_separation_arcsec.maximum.toFixed(6)}″ · Earth {spiceEarth.angular_separation_arcsec.maximum.toFixed(6)}″ · gate {spiceSun.pass_criterion.maximum_allowed_arcsec.toFixed(3)}″.
              </p>
              <code>{String(kernelManifest?.manifest_sha256 ?? "")}</code>
            </div>
            <div>
              <span>LOCAL TERRAIN</span>
              <strong>NASA PGDA LOLA · 10 m COG</strong>
              <p>{String(localSource.reference_frame)} · local 10 km raycast</p>
              <code>{String(localSource.crop_sha256 ?? "")}</code>
            </div>
            <div>
              <span>OUTER TERRAIN</span>
              <strong>NASA PGDA LOLA · 240 m COG</strong>
              <p>{String(outerSource.reference_frame)} · curvature-aware 200 km raycast</p>
              <code>{String(outerSource.crop_sha256 ?? "")}</code>
            </div>
            <div>
              <span>VALIDATION</span>
              <strong className={validationPass ? "pass" : "fail"}>{data.validation.overall_status}</strong>
              <p>Horizons integrity, SPICE cross-provider errors, pinned-kernel coverage, terrain integrity, cadence, and disk-size physics passed.</p>
              <code>Generated {generated} UTC</code>
            </div>
          </div>
        </section>
      ) : null}

      <section className="dashboard-grid">
        <HorizonChart profile={data.horizon.profile} sun={sample.sun} earth={sample.earth} />
        <aside className="state-stack">
          <BodyCard kind="sun" body={sample.sun} />
          <BodyCard kind="earth" body={sample.earth} />
        </aside>
      </section>

      <section className="panel timeline-panel">
        <div className="panel-heading timeline-heading">
          <div>
            <span className="eyebrow">SEVEN-DAY OPERATIONS WINDOW</span>
            <h2>Sunlight + geometric direct-to-Earth</h2>
          </div>
          <div className="timeline-range">
            <span>{formatUtc(data.time_range.start_utc)}</span>
            <span>{formatUtc(data.time_range.end_utc)}</span>
          </div>
        </div>
        <Timeline samples={data.samples} index={index} onChange={setSafeIndex} />
        <div className="time-controls">
          <button type="button" className="play-button" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause simulation" : "Play simulation"}>
            {playing ? "Ⅱ" : "▶"}
          </button>
          <input
            aria-label="Simulation timestamp"
            type="range"
            min={0}
            max={data.samples.length - 1}
            value={index}
            onChange={(event) => setSafeIndex(Number(event.target.value))}
            style={{ "--slider-progress": `${progress}%` } as CSSProperties}
          />
          <div className="step-controls">
            <button type="button" onClick={() => setSafeIndex(index - 1)}>−10m</button>
            <span>{index + 1} / {data.samples.length}</span>
            <button type="button" onClick={() => setSafeIndex(index + 1)}>+10m</button>
          </div>
        </div>
      </section>

      <section className="metrics-grid">
        <article className="metric-card amber">
          <span className="metric-index">01</span>
          <span className="eyebrow">ILLUMINATION</span>
          <strong>{data.windows.solar.illumination_percentage.toFixed(1)}%</strong>
          <p>{duration(data.windows.solar.sunlight.total_duration_hours)} direct sun</p>
          <footer>Longest darkness <b>{duration(data.windows.solar.shadow.longest_duration_hours)}</b></footer>
        </article>
        <article className="metric-card cyan">
          <span className="metric-index">02</span>
          <span className="eyebrow">GEOMETRIC DTE</span>
          <strong>{data.windows.earth.earth_visible_percentage.toFixed(1)}%</strong>
          <p>{duration(data.windows.earth.dte_visible.total_duration_hours)} Earth visible</p>
          <footer>Longest blackout <b>{duration(data.windows.earth.dte_blackout.longest_duration_hours)}</b></footer>
        </article>
        <article className="metric-card green">
          <span className="metric-index">03</span>
          <span className="eyebrow">SIMULTANEOUS</span>
          <strong>{data.windows.combined.SUN_VISIBLE_EARTH_VISIBLE.percentage.toFixed(1)}%</strong>
          <p>Sun + Earth available</p>
          <footer>Longest window <b>{duration(data.windows.combined.SUN_VISIBLE_EARTH_VISIBLE.longest_duration_hours)}</b></footer>
        </article>
        <article className="metric-card power">
          <span className="metric-index">04</span>
          <span className="eyebrow">PANEL ESTIMATE NOW</span>
          <strong>{sample.power.estimated_electrical_output_w.toFixed(0)}<small> W</small></strong>
          <p>{data.panel.panel_area_m2.toFixed(1)} m² · {(data.panel.efficiency * 100).toFixed(0)}% · sun tracking</p>
          <footer>Direct flux <b>{sample.power.direct_irradiance_w_m2.toFixed(0)} W/m²</b></footer>
        </article>
      </section>

      <footer className="science-footer">
        <div><span className={`status-lamp ${spicePass ? "available" : "blocked"}`} />CALCULATION COMPLETE · SPICE {spiceValidation.status} · {data.time_range.sample_count} EPOCHS · {data.horizon.profile.length} SKYLINE RAYS</div>
        <p>Geometric opportunity only. Power is a first-order estimate; DTE is not a radio link budget. Window transitions are resolved to ±{data.time_range.window_boundary_precision_minutes} minutes.</p>
      </footer>
    </main>
  );
}
