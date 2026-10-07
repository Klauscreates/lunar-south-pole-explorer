"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CoveredDate, useCoveredDate } from "./CoveredDate";
import { Methodology } from "./Methodology";
import type { BodyState, IndexedSite, SimulationResult } from "./types";
import { loadStudy, type Study } from "./SpacecraftStudy";
import { load as loadTerrain, type Report } from "./LocalTerrainStudy";
import { SpacecraftControlPanel } from "./SpacecraftControlPanel";
import { CELL_SPEC, EPOCHS, cellReference, comparisonSeries, epochTime, terrainEvidence } from "./comparisonMetrics";
import "./dual-comparison.css";
import { getMissionInsight } from "./missionInsight";
import { weeklyMetrics } from "./weeklyMetrics";

type Pair = { anchorId: string; targetId: string };
type Bundle = { simulation: SimulationResult; study: Study; terrain?: Report; terrainError?: string; hash: string };
type Resource = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Bundle };
export type SimulationLoader = (site: IndexedSite, signal: AbortSignal) => Promise<SimulationResult>;

function Insight({ site, resource, scenario, epoch }: { site: IndexedSite; resource?: Resource; scenario: string; epoch: number }) {
  const data = resource?.status === "ready" && resource.data.hash === site.sha256 ? resource.data : undefined;
  const series = useMemo(() => data ? comparisonSeries(data.simulation, data.study, scenario) : null, [data, scenario]);
  const row = series?.rows[epoch];
  const sample = data?.simulation.samples[epoch];
  const insight = getMissionInsight(row && sample ? { powerW: row[0], comms: row[7] ? sample.comms_potential.potential_index_percent : 0, earthDiskPct: sample.earth.visibility_fraction * 100, cellTempC: row[1] - 273.15 } : undefined);
  return <article className={`mission-insight insight-${insight.tone}`}><small>{site.name}</small><strong>{insight.title}</strong><p>{insight.text}</p><small>{insight.caveat}</small></article>;
}

function Count({ value, digits = 1, unit = "" }: { value: number | null; digits?: number; unit?: string }) {
  const element = useRef<HTMLSpanElement>(null);
  const previous = useRef<number | null>(null);
  useEffect(() => {
    const node = element.current;
    if (!node) return;
    if (value === null) { node.textContent = "Unknown"; previous.current = null; return; }
    const from = previous.current ?? value;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      node.textContent = value.toFixed(digits) + unit; previous.current = value; return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const fraction = Math.min(1, (now - start) / 220);
      const current = from + (value - from) * (1 - (1 - fraction) ** 3);
      node.textContent = current.toFixed(digits) + unit;
      previous.current = current;
      if (fraction < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, digits, unit]);
  return <span className="telemetry-count" aria-label={value === null ? "Unknown" : value.toFixed(digits) + unit} ref={element}>{value === null ? "Unknown" : value.toFixed(digits) + unit}</span>;
}

function Sky({ simulation, sun, earth }: { simulation: SimulationResult; sun: BodyState; earth: BodyState }) {
  const profile = simulation.horizon.profile;
  // A fixed full-week axis prevents apparent terrain motion while scrubbing.
  const [low, high] = useMemo(() => {
    const elevations = [...profile.map(p => p.elevation_deg),
      ...simulation.samples.flatMap(s => [s.sun.elevation_deg, s.earth.elevation_deg])];
    return [Math.min(-5, ...elevations) - 1, Math.max(10, ...elevations) + 1];
  }, [profile, simulation]);
  const y = (elevation: number) => 100 - (elevation - low) / (high - low) * 70;
  const x = (azimuth: number) => 10 + azimuth / 360 * 180;
  const path = profile.map((p, i) => `${i ? "L" : "M"}${x(p.azimuth_deg)},${y(p.elevation_deg)}`).join(" ");
  return <svg className="sky-dome" viewBox="0 0 200 120" role="img" aria-label="LOLA skyline by azimuth with Sun and Earth elevations; diagram, not camera view">
    <path d="M10 100 A90 85 0 0 1 190 100" fill="#101e2a" stroke="#355069"/>
    <path d={`${path} L190 106 L10 106 Z`} fill="#34424d" stroke="#6d8294" strokeWidth=".7"/>
    <path d={`M10 ${y(0)} H190`} stroke="#9faeb055" strokeDasharray="3 3"/>
    <circle cx={x(sun.azimuth_deg)} cy={y(sun.elevation_deg)} r="4" fill="#ffd37e"/>
    <circle cx={x(earth.azimuth_deg)} cy={y(earth.elevation_deg)} r="4" fill="#82caff"/>
    <text x="10" y="117">0° AZ</text><text x="154" y="117">360°</text>
  </svg>;
}

function SiteColumn({ slot, site, resource, scenario, epoch, window }: {
  slot: "A" | "B"; site: IndexedSite; resource?: Resource; scenario: string; epoch: number; window:{start:number;end:number};
}) {
  const bundle = resource?.status === "ready" && resource.data.hash === site.sha256 ? resource.data : undefined;
  const series = useMemo(() => bundle ? comparisonSeries(bundle.simulation, bundle.study, scenario) : null, [bundle, scenario]);
  const totals = useMemo(()=>bundle ? weeklyMetrics(bundle.study,scenario,window.start,window.end) : null,[bundle,scenario,window.start,window.end]);
  const sample = bundle?.simulation.samples[epoch];
  const row = series?.rows[epoch];
  const terrain = terrainEvidence(bundle?.terrain);
  if (!bundle || !sample || !row || !series) return <article className="dual-site status-warning">
    <header><small>SITE {slot}</small><h3>{site.name}</h3></header>
    <p role="status">{resource?.status === "error" ? resource.message : resource?.status === "ready" ? "Unknown — scenario or timestamp contract mismatch" : "Loading checksum-verified samples…"}</p>
  </article>;
  const temperature = row[1] - 273.15;
  const referenceEfficiency = cellReference(row[1]);
  const cold = row[1] < CELL_SPEC.coefficient_temperature_range_k[0];
  const tier = row[7] ? sample.comms_potential.potential_index_percent : 0;
  const partial = sample.earth.visibility_fraction > 0 && sample.earth.visibility_fraction < 1;
  const blocked = tier === 0;
  const state = blocked || row[0] === 0 ? "blackout" : referenceEfficiency === null || tier === 30 || partial ? "warning" : "clear";
  // Use the source-pinned cell reference as an explicitly labeled visual scale.
  const referenceWatts = CELL_SPEC.cell_properties.reference_irradiance_w_m2.value *
    bundle.study.design.thermal_parameters.collecting_area_m2 * CELL_SPEC.cell_properties.reference_efficiency.value;
  const fill = referenceWatts ? Math.min(100, row[0] / referenceWatts * 100) : 0;
  return <article className={`dual-site status-${state}`}>
    <header><small>{slot === "A" ? "A / ANCHOR SITE" : "B / COMPARISON TARGET"}</small><h3>{site.name}</h3>
      <p>{site.latitude_deg.toFixed(4)}° · {site.longitude_deg_east.toFixed(4)}° E</p>
      <span className="state-tag">{blocked ? "CENTER LOS BLOCKED" : row[0] === 0 ? "NO MODELED GENERATION" : state === "warning" ? "MODEL LIMIT / CAUTION" : "GEOMETRY CLEAR"}</span>
      <p>Selected window: {totals ? `${totals.kwh.toFixed(2)} kWh modeled · ${totals.commsPercent.toFixed(1)}% Earth-center LOS` : 'Unknown'}</p>
    </header>
    <section className="dual-pillar"><h4>01 / Horizon Clearance Profiles</h4>
      <Sky simulation={bundle.simulation} sun={sample.sun} earth={sample.earth}/>
      {(["sun", "earth"] as const).map(body => <div className="clearance-values" data-blocked={sample[body].clearance_deg <= 0} key={body}>
        <b>{body === "sun" ? "☀ Sun" : "◉ Earth"}</b>
        <span>Elevation <Count value={sample[body].elevation_deg} unit="°"/></span>
        <span>LOLA mask <Count value={sample[body].terrain_horizon_deg} unit="°"/></span>
        <span>Clearance <Count value={sample[body].clearance_deg} unit="°"/></span>
      </div>)}
      <small>720-ray baseline skyline. Moving dots: azimuth/elevation diagram.</small>
    </section>
    <section className={`dual-pillar ${row[0] === 0 ? "power-zero" : ""}`}><h4>02 / Net Power Extraction</h4>
      <div className="power-instrument"><div className={`vertical-battery ${row[0] > 150 ? "power-high" : ""}`} aria-hidden="true">
        <div className="battery-fluid" style={{height:`${fill}%`}}/></div>
        <div><strong><Count value={row[0]} unit=" W"/></strong><small>R1 modeled generation</small>
          <strong><Count value={series.cumulative[epoch]-series.cumulative[window.start]} digits={3} unit=" kWh"/></strong><small>Accumulated since mission start</small></div></div>
      <p>Net after vehicle loads: <b>Unknown</b>.</p>
      <small>Legacy assumed-efficiency R1 output; not calibrated XTJ power. Fill is relative to {referenceWatts ? `${referenceWatts.toFixed(0)} W` : "unknown reference"}, not battery charge.</small>
    </section>
    <section className={`dual-pillar ${referenceEfficiency === null ? "thermal-warning" : ""}`}><h4>03 / GaAs Array Thermal State</h4>
      <strong className="large-reading"><Count value={temperature} unit=" °C"/></strong><small>Modeled R1 temperature, not measured XTJ temperature</small>
      {referenceEfficiency === null && <p className="warning-banner">⚠️ {cold ? "UNCALIBRATED CRYOGENIC REGIME — COEFFICIENT RANGE EXCEEDED" : "COEFFICIENT RANGE EXCEEDED — HOT REGIME"}</p>}
      <p>XTJ AM0 cell-reference efficiency: <Count value={referenceEfficiency === null ? null : referenceEfficiency * 100} unit="%"/></p>
      <small>15–125°C coefficients only. Candidate cell reference, not array qualification.</small>
    </section>
    <section className={`dual-pillar rf-${tier}`}><h4>04 / DTE Communication Windows</h4>
      <div className="rf-instrument"><svg viewBox="0 0 100 60" aria-hidden="true">
        <path d="M40 55L50 20L60 55M43 44H57M46 34H54" fill="none" stroke="currentColor" strokeWidth="2"/>
        <circle cx="50" cy="16" r="3" fill="currentColor"/>
        {tier > 0 ? <g className="broadcast"><path d="M39 7Q29 16 39 25M61 7Q71 16 61 25"/>{tier === 100 && <path d="M29 1Q13 16 29 31M71 1Q87 16 71 31"/>}</g> : <path d="M33 4L67 30M67 4L33 30" stroke="#ed7d7d" strokeWidth="3"/>}
      </svg><strong><Count value={tier} digits={0}/> <small>/ 100</small></strong></div>
      <p>{blocked ? "Terrain or vehicle center LOS blocked" : tier === 30 ? "Grazing geometry ≤ 2° elevation" : "Center LOS clear > 2° elevation"}</p>
      <p>Terrain-model Earth disk: <Count value={sample.earth.visibility_fraction * 100} unit="%"/></p>
      <div className="exposure-track"><div style={{width:`${sample.earth.visibility_fraction * 100}%`}}/></div>
      {partial && <p className="warning-banner">⚠️ FRACTIONAL DISK OCCULTATION</p>}
      {tier === 30 && <p className="warning-banner">Potential multipath / surface fading hazard — not modeled.</p>}
      <small>0/30/100 geometry index, not RF quality. Disk fraction uses a local straight skyline approximation; vehicle disk exposure and ground-station link budget Unknown.</small>
    </section>
    <section className="dual-pillar"><h4>05 / Landed Trafficability Matrix</h4>
      <svg className={`inclinometer ${terrain.slope !== null && terrain.slope > 15 ? "slope-warning" : ""}`} viewBox="0 0 100 65" aria-hidden="true">
        <circle cx="50" cy="32" r="28"/><path d="M22 32H78M50 4V60" strokeDasharray="3 3"/>
        {terrain.slope !== null && <path d="M24 32H42L46 36H54L58 32H76" transform={`rotate(${terrain.slope} 50 32)`} strokeWidth="2"/>}
      </svg>
      {!terrain.complete && <p className="unknown-traffic">UNKNOWN TRAFFICABILITY</p>}
      <p>10 m plane slope: <Count value={terrain.slope} unit="°"/></p>
      <p>500 m radius RMS roughness: <Count value={terrain.roughness} unit=" m"/></p>
      {terrain.slope !== null && terrain.slope > 15 && <p className="warning-banner">Slope exceeds 15° screening threshold.</p>}
      <small>{terrain.source}. {bundle.terrainError || bundle.terrain?.reason || "500 m roughness and measured boulder geometry are not supplied by this export."}</small>
      <small>Visibility above remains LOLA baseline. No landing-safety certification or silent NAC substitution.</small>
    </section>
    <footer>SHA-256 verified · {bundle.hash.slice(0, 12)}…<br/>Epoch {epoch + 1} / {EPOCHS} · 10-minute samples</footer>
  </article>;
}

export function DualSiteComparison({ sites, anchor, epoch, onEpoch, scenario, onScenario, loadSimulation, window = {start:0,end:EPOCHS-1} }: {
  sites: IndexedSite[]; anchor: IndexedSite; epoch: number; onEpoch: (epoch: number) => void;
  scenario: string; onScenario: (scenario: string) => void; loadSimulation: SimulationLoader;
  window?: {start:number;end:number};
}) {
  const [pair, setPair] = useState<Pair>(() => ({ anchorId: anchor.id, targetId: sites.find(s => s.id !== anchor.id)!.id }));
  const [resources, setResources] = useState<Record<string, Resource>>({});
  const date = useCoveredDate(epoch,onEpoch,window.start,window.end);
  const a = sites.find(s => s.id === pair.anchorId)!;
  const b = sites.find(s => s.id === pair.targetId)!;
  useEffect(() => {
    const controller = new AbortController();
    for (const site of [a,b]) {
      Promise.all([loadSimulation(site, controller.signal), loadStudy(site, controller.signal),
        loadTerrain(site, controller.signal).then(terrain => ({terrain, terrainError:undefined})).catch(error => ({terrain:undefined, terrainError:String(error)}))])
        .then(([simulation, study, terrain]) => {
          if (!controller.signal.aborted) setResources(previous => ({
            ...Object.fromEntries(Object.entries(previous).filter(([id])=>id===a.id || id===b.id)),
            [site.id]: {status:"ready", data:{simulation, study, ...terrain, hash:site.sha256}},
          }));
        }).catch(error => {
          if (!controller.signal.aborted) setResources(previous => ({...previous,[site.id]:{status:"error",message:String(error)}}));
        });
    }
    return () => controller.abort();
  }, [a,b,loadSimulation]);
  const resource = resources[a.id];
  return <div className="dual-dashboard">
    <div className="dual-title"><small>DUAL-SITE / CROSS-EXAMINATION</small><h2>One moment. Two horizons.</h2><p>Same UTC epoch, same R1 configuration. Research screening—not flight safety.</p></div>
    <Methodology/>
    <div className="dual-selectors">
      <label>Anchor Site A<select value={a.id} onChange={e=>setPair(current => ({...current,anchorId:e.target.value}))}>{sites.map(s=><option key={s.id} value={s.id} disabled={s.id===b.id}>{s.name}</option>)}</select></label>
      <label>Comparison Target B<select value={b.id} onChange={e=>setPair(current => ({...current,targetId:e.target.value}))}>{sites.map(s=><option key={s.id} value={s.id} disabled={s.id===a.id}>{s.name}</option>)}</select></label>
    </div>
    <details className="dual-configuration"><summary>R1 configuration · {scenario.replace("--"," / ").replaceAll("_"," ")}</summary>
      <SpacecraftControlPanel study={resource?.status === "ready" ? resource.data.study : undefined} value={scenario} onChange={onScenario}/>
    </details>
    <CoveredDate {...date} epoch={epoch} slider={false}/>
    {date.available && <>
    <div className="mission-insights" aria-label="Mission status at selected epoch"><Insight site={a} resource={resources[a.id]} scenario={scenario} epoch={epoch}/><Insight site={b} resource={resources[b.id]} scenario={scenario} epoch={epoch}/></div>
    <div className="dual-timeline"><label htmlFor="dual-epoch">Synchronized epoch <output>{epochTime(epoch).replace("T"," ").replace(".000Z"," UTC")}</output></label>
      <div><button disabled={epoch<=window.start} onClick={()=>onEpoch(epoch-1)} aria-label="Previous ten minutes">−</button>
        <input id="dual-epoch" type="range" min={window.start} max={window.end} step="1" value={epoch} onChange={e=>onEpoch(Number(e.target.value))} aria-valuetext={epochTime(epoch)}/>
        <button disabled={epoch>=window.end} onClick={()=>onEpoch(epoch+1)} aria-label="Next ten minutes">＋</button></div>
      <small>{epochTime(window.start).replace('T',' ')} → {epochTime(window.end).replace('T',' ')} · selected mission window.</small>
    </div>
    <div className="dual-grid"><SiteColumn key={`A-${a.id}`} slot="A" site={a} resource={resources[a.id]} scenario={scenario} epoch={epoch} window={window}/>
      <SiteColumn key={`B-${b.id}`} slot="B" site={b} resource={resources[b.id]} scenario={scenario} epoch={epoch} window={window}/></div>
    </>}
    <p className="dual-source">XTJ reference: <a href={CELL_SPEC.source.url} target="_blank" rel="noreferrer">Spectrolab datasheet</a> · {CELL_SPEC.source.revision} · not promoted to the R1 assembly model. Green means geometry clear only; amber means model limits; red means modeled center LOS blackout.</p>
  </div>;
}
