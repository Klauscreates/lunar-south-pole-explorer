"use client";

import { memo, useEffect, useMemo, useState } from "react";
import type { IndexedSite } from "./types";
import { sharedResource } from "./sharedResource";
import "./spacecraft.css";

type Vec3 = [number, number, number];
type Row = [number, number, number, number, number, boolean, boolean, boolean, number, number];
export interface Study {
  schema_version: string;
  analysis_status: string;
  flight_certified: boolean;
  site_id: string;
  parent_sha256: string;
  columns: string[];
  timestamps: string[];
  scenarios: { id: string; pose_id: string; boundary_id: string; rows: Row[] }[];
  design: {
    name: string;
    identity: string;
    boxes: { id: string; min: Vec3; max: Vec3 }[];
    antenna: { phase_center_m: Vec3 };
    attitudes: { id: string; label: string; yaw: number; pitch: number; roll: number }[];
    boundary_cases: { id: string; label: string; wall_reflected_solar_irradiance_w_m2: number;
      lunar_ir_irradiance_w_m2: number; mount_temperature_k: number; radiation_sink_temperature_k: number }[];
    thermal_parameters: Record<string, number>;
    initial_cell_temperature_k: number;
    limitations: string[];
  };
  historical_evidence: {
    vehicle: string;
    source: { title: string; url: string; sha256: string };
    transit: { reported_average_solar_power_w: number; predicted_average_solar_power_w: number;
      reported_average_solar_voltage_v: number; reported_average_solar_current_a: number };
    surface_operations: { panel_lead_angle_deg: number[]; qualification: string };
    sunset: { camera_sunset_utc: string; solar_panel_zero_output_utc: string };
    missing_for_vehicle_prediction: string[];
  };
}
const columns = ["electrical_w", "cell_temperature_k", "efficiency", "incidence_cosine",
  "unoccluded_fraction", "earth_self_clear", "earth_terrain_clear", "earth_los_clear",
  "direct_incident_w", "reflected_incident_w"];

const studyResource = sharedResource<Study>();
export function loadStudy(site: IndexedSite, signal: AbortSignal): Promise<Study> {
  return studyResource(`${site.id}:${site.sha256}`, () =>
    fetchStudy(site, AbortSignal.timeout(60000)), signal);
}

async function fetchStudy(site: IndexedSite, signal: AbortSignal): Promise<Study> {
  const indexResponse = await fetch("/data/spacecraft/index.json", { signal, cache: "no-cache" });
  if (!indexResponse.ok) throw new Error("Reference lander catalogue unavailable");
  const catalogue = await indexResponse.json();
  const entry = catalogue.sites?.find((item: { site_id: string }) => item.site_id === site.id);
  if (catalogue.schema_version !== "1.0.0" || !entry || entry.parent_sha256 !== site.sha256 ||
      entry.url !== `/data/spacecraft/${site.id}.json` || !/^[a-f0-9]{64}$/.test(entry.sha256))
    throw new Error("Vehicle study does not match the current site export; rebuild it");
  const response = await fetch(entry.url, { signal });
  if (!response.ok) throw new Error("Reference lander data unavailable");
  const bytes = await response.arrayBuffer();
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
    .map((v) => v.toString(16).padStart(2, "0")).join("");
  if (hash !== entry.sha256) throw new Error("Reference lander data failed its checksum");
  const study: Study = JSON.parse(new TextDecoder().decode(bytes));
  if (study.schema_version !== "1.0.0" || study.parent_sha256 !== site.sha256 || study.site_id !== site.id ||
      study.flight_certified !== false || study.analysis_status !== "DESIGN_STUDY_UNVALIDATED" ||
      JSON.stringify(study.columns) !== JSON.stringify(columns) || !study.timestamps.length ||
      study.scenarios.length !== study.design.attitudes.length * study.design.boundary_cases.length)
    throw new Error("Unsupported reference lander data contract");
  const ids = new Set();
  for (const scenario of study.scenarios) {
    if (ids.has(scenario.id) || scenario.id !== `${scenario.pose_id}--${scenario.boundary_id}` ||
        !study.design.attitudes.some((pose) => pose.id === scenario.pose_id) ||
        !study.design.boundary_cases.some((boundary) => boundary.id === scenario.boundary_id) ||
        scenario.rows.length !== study.timestamps.length || scenario.rows.some((r) =>
          r.length !== columns.length || [0, 1, 2, 3, 4, 8, 9].some((i) => typeof r[i] !== "number" || !Number.isFinite(r[i])) ||
          [5, 6, 7].some((i) => typeof r[i] !== "boolean") || r[0] < 0 || r[1] <= 0 ||
          r[2] < 0 || r[2] > 1 || r[3] < 0 || r[3] > 1 || r[4] < 0 || r[4] > 1 ||
          r[7] !== (r[5] && r[6]))) throw new Error("Invalid vehicle epoch data");
    ids.add(scenario.id);
  }
  return study;
}

const DesignView = memo(function DesignView({ design, angle }: { design: Study["design"]; angle: number }) {
  const a = angle * Math.PI / 180;
  const project = ([x, y, z]: Vec3) => {
    const u = x*Math.cos(a)-y*Math.sin(a), v = x*Math.sin(a)+y*Math.cos(a);
    return [160 + u*82, 185 + v*30-z*76, v+z*.15];
  };
  const faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
    [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5]];
  const polygons = design.boxes.flatMap((box) => {
    const [x,y,z] = box.min, [X,Y,Z] = box.max;
    const vertices: Vec3[] = [[x,y,z],[X,y,z],[X,Y,z],[x,Y,z],[x,y,Z],[X,y,Z],[X,Y,Z],[x,Y,Z]];
    return faces.map((face, index) => {
      const points = face.map((i) => project(vertices[i]));
      return { key: `${box.id}-${index}`, depth: points.reduce((s,p)=>s+p[2],0)/4,
        points: points.map((p)=>`${p[0]},${p[1]}`).join(" "),
        fill: box.id === "panel_backing" ? "#557ba7" : box.id === "forward_payload" ? "#a4735a" :
          box.id === "antenna_mast" ? "#b9aa79" : "#465461" };
    });
  }).sort((a,b)=>a.depth-b.depth);
  const antenna = project(design.antenna.phase_center_m);
  return <svg viewBox="0 0 320 225" role="img" aria-label="Reference lander cuboid geometry, matching the raycast mesh">
    <path d="M30 190 L160 220 L290 190 L160 160 Z" fill="#17252d" stroke="#334955" />
    {polygons.map((p)=><polygon key={p.key} points={p.points} fill={p.fill} stroke="#b8cbd766" strokeWidth=".7" />)}
    <circle cx={antenna[0]} cy={antenna[1]} r="3" fill="#9bf0b6" />
    <text x="10" y="16" fill="#b8cbd7" fontSize="10">DEFINED GEOMETRY · METRES</text>
  </svg>;
});

export function SpacecraftStudy({ site, sampleIndex, timestamp, onClose }: {
  site: IndexedSite; sampleIndex: number; timestamp: string; onClose: () => void;
}) {
  const [loadedStudy, setStudy] = useState<Study | null>(null);
  // A different site can share identical timestamps: never show the old site's rows.
  const study = loadedStudy?.site_id === site.id && loadedStudy.parent_sha256 === site.sha256 ? loadedStudy : null;
  const [error, setError] = useState("");
  const [pose, setPose] = useState("north");
  const [boundary, setBoundary] = useState("low_load");
  const [view, setView] = useState(135);
  useEffect(() => {
    const controller = new AbortController();
    loadStudy(site, controller.signal).then((value) => {
      if (!controller.signal.aborted) setStudy(value);
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(String(reason));
    });
    return () => controller.abort();
  }, [site]);
  const scenario = study?.scenarios.find((s)=>s.pose_id === pose && s.boundary_id === boundary);
  const row = study?.timestamps[sampleIndex] === timestamp ? scenario?.rows[sampleIndex] : undefined;
  const flux = study?.design.boundary_cases.find((b)=>b.id === boundary);
  const evidence = study?.historical_evidence;
  const chart = useMemo(() => {
    const rows = study?.scenarios.find((s)=>s.pose_id === pose && s.boundary_id === boundary)?.rows;
    const maximum = rows ? Math.max(1, ...rows.map((r)=>r[0])) : 1;
    return { maximum, points: rows?.map((r,i)=>`${(i*600/Math.max(1,rows.length-1)).toFixed(2)},${(80-r[0]*70/maximum).toFixed(2)}`).join(" ") ?? "" };
  }, [study, pose, boundary]);
  return <section id="spacecraft-study" className="spacecraft-study" aria-label="Spacecraft design study">
    <header><div><span className="mission-kicker">SPACECRAFT LAB · DESIGN STUDY</span>
      <h2>Open Reference Lander R1</h2></div><button onClick={onClose} aria-label="Close spacecraft study">×</button></header>
    <p className="study-status">Defined research design · hardware assumptions · no flight validation</p>
    {!study ? <p role="status">{error || "Verifying site-linked spacecraft data…"}</p> : <>
      <p className="study-site">{site.name} · {timestamp.replace("T", " ")} · synced to main timeline</p>
      <div className="study-controls">
        <label>Body attitude<select value={pose} onChange={(e)=>setPose(e.target.value)}>
          {study.design.attitudes.map((p)=><option key={p.id} value={p.id}>{p.label}</option>)}
        </select></label>
        <label>Assumed thermal environment<select value={boundary} onChange={(e)=>setBoundary(e.target.value)}>
          {study.design.boundary_cases.map((b)=><option key={b.id} value={b.id}>{b.label}</option>)}
        </select></label>
      </div>
      {row ? <>
        <div className="study-layout"><div>
          <DesignView design={study.design} angle={view} />
          <label className="study-view">Rotate diagram (view only)<input type="range" min="0" max="360" value={view}
            onChange={(e)=>setView(Number(e.target.value))} /></label>
          <p className="study-caption">Blue: 1 m² array · rust: forward payload · green: Earth sensor. Diagram uses the raycaster’s cuboid dimensions; shading is not a spatial shadow map.</p>
        </div><dl className="study-metrics">
          <div><dt>Modeled panel output</dt><dd>{row[0].toFixed(1)} <small>W</small></dd></div>
          <div><dt>Modeled cell temperature</dt><dd>{(row[1]-273.15).toFixed(1)} <small>°C</small></dd></div>
          <div><dt>Temperature-adjusted efficiency</dt><dd>{(row[2]*100).toFixed(1)} <small>%</small></dd></div>
          <div><dt>Panel incidence cosine</dt><dd>{row[3].toFixed(3)}</dd></div>
          <div><dt>Structurally unblocked Sun samples</dt><dd>{(row[4]*100).toFixed(1)} <small>%</small></dd></div>
          <div><dt>Earth center: terrain + structure</dt><dd className={row[7]?"study-clear":"study-blocked"}>{row[7]?"Clear":"Blocked"}</dd>
            <small>Terrain {row[6]?"clear":"blocked"} · structure {row[5]?"clear":"blocked"}; RF unassessed</small></div>
        </dl></div>
        <div className="study-chart"><span>MODELED POWER OVER THE EVALUATED WEEK · MAX {chart.maximum.toFixed(1)} W</span>
          <svg viewBox="0 0 600 85" role="img" aria-label="Reference lander coverage-wide power with selected epoch marker">
            <polyline fill="none" stroke="#a8c6df" strokeWidth="1.5" points={chart.points} />
            <line x1={sampleIndex*600/Math.max(1,scenario!.rows.length-1)} x2={sampleIndex*600/Math.max(1,scenario!.rows.length-1)} y1="3" y2="82" stroke="#e0b86b" />
          </svg><small>Use the main timeline below to inspect any epoch.</small>
        </div>
      </> : <p role="alert">The spacecraft series does not align with the selected epoch. Results unavailable.</p>}
      <details><summary>Design assumptions and model limits</summary>
        <p>The geometry is defined by this project. Thermal properties are study inputs, not measured component specifications. {study.design.identity}</p>
        <p>Constant panel-plane wall flux: {flux?.wall_reflected_solar_irradiance_w_m2} W/m²; lunar IR: {flux?.lunar_ir_irradiance_w_m2} W/m²; mount: {flux?.mount_temperature_k} K; sink: {flux?.radiation_sink_temperature_k} K. These are sensitivity cases, not measured site conditions or uncertainty bounds.</p>
        <dl className="study-parameters">{Object.entries(study.design.thermal_parameters).map(([k,v])=><div key={k}><dt>{k.replaceAll("_"," ")}</dt><dd>{v}</dd></div>)}</dl>
        <p>Initial cell temperature: {study.design.initial_cell_temperature_k} K. Effective radiating area and imposed fluxes already represent assumed view factors; no mesh radiation-exchange solution is claimed.</p>
        <ul>{study.design.limitations.map((limit)=><li key={limit}>{limit}</li>)}</ul>
        <p><a href="/data/spacecraft/reference.obj" download>Download geometry OBJ</a> · <a href={`/data/spacecraft/${site.id}.json`} download>Download this study</a></p>
      </details>
      {evidence && <details className="study-history"><summary>Surveyor VII · historical evidence</summary>
        <p>JPL TR 32-1264, p. 64, Table IV-12: coast-phase average solar power was <strong>{evidence.transit.reported_average_solar_power_w} W reported</strong>, versus {evidence.transit.predicted_average_solar_power_w} W predicted. The report gives averages of {evidence.transit.reported_average_solar_voltage_v} V and {evidence.transit.reported_average_solar_current_a} A. These are transit observations, not south-pole output ratings.</p>
        <p>On the lunar surface, the panel generally led the Sun by {evidence.surface_operations.panel_lead_angle_deg.join("–")}° for charge control and equipment shade (p. 65). Full Sun orientation was used in the final 24 hours.</p>
        <p>23 January 1968: camera sunset 06:06 UTC; panel zero output 06:24 UTC (p. 161). These are distinct historical observables, not computed events for the current site.</p>
        <p><strong>Correlation status: not run.</strong> R1 is a different design; these records are not used to tune or validate its power model.</p>
        <ul>{evidence.missing_for_vehicle_prediction.map((item)=><li key={item}>{item}</li>)}</ul>
        <a href={evidence.source.url} target="_blank" rel="noreferrer">Open original NASA/JPL mission report ↗</a>
      </details>}
    </>}
  </section>;
}
