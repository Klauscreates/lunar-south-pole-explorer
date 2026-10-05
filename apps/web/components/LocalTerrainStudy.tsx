"use client";

import { useEffect, useState } from "react";
import type { IndexedSite } from "./types";
import "./spacecraft.css";

type Ray = { local_status: string; sampled_max_elevation_deg: number | null;
  target_elevation_deg?: number; azimuth_deg?: number;
  obstruction_distance_m: number | null; valid_fraction: number; complete: boolean;
  uncorrected_local_horizon_deg?: number | null;
  fused?: {status:string; horizon_deg:number|null; source:string|null; complete:boolean} };
export type Report = {
  schema_version: string; site_id: string; parent_sha256: string; status: string;
  landing_safety_certified: boolean; operational_visibility_changed: boolean;
  reason?: string; native_pixel_size_m?: number; confidence_qualified?: boolean;
  product?: { product_id: string; method: string; product_page: string };
  coregistration?: { status: string; translation_m?: number[]; applied: boolean; gate_failures?: string[];
    holdout_before?: { rmse_m: number }; holdout_after?: { rmse_m: number } };
  fusion?: {status:string; independently_validated:boolean};
  roughness?: { radius_m: number; valid_fraction: number; status: string;
    plane_slope_deg?: number; detrended_rms_m?: number }[];
  limitations: string[];
  nearfield?: { minimum_distance_m: number; maximum_distance_m: number; observer_height_m: number };
  samples?: { timestamp: string; sun: Ray; earth: Ray }[];
};
const labels: Record<string,string> = {UNKNOWN:"Unknown", BLOCKED:"Blocked locally",
  CLEAR_SAMPLED_LOCAL_DOMAIN:"Clear in sampled local terrain"};
const fusionLabels: Record<string,string> = {UNKNOWN:"Unknown",BLOCKED:"Blocked",
  CLEAR_SAMPLED_MULTISCALE_DOMAIN:"Clear across sampled scales"};

export async function load(site: IndexedSite, signal: AbortSignal): Promise<Report> {
  const response = await fetch("/data/local-terrain/index.json",{signal,cache:"no-cache"});
  if (!response.ok) throw new Error("Local terrain catalogue unavailable");
  const catalogue = await response.json();
  const entry = catalogue.sites?.find((s: {site_id:string})=>s.site_id === site.id);
  if (catalogue.schema_version !== "1.0.0" || !entry || entry.parent_sha256 !== site.sha256 ||
      entry.url !== `/data/local-terrain/${site.id}.json` || !/^[a-f0-9]{64}$/.test(entry.sha256))
    throw new Error("Terrain study does not match the current site export");
  const res = await fetch(entry.url,{signal});
  if (!res.ok) throw new Error("Local terrain report unavailable");
  const bytes = await res.arrayBuffer();
  const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)))
    .map((b)=>b.toString(16).padStart(2,"0")).join("");
  if (sha !== entry.sha256) throw new Error("Local terrain checksum failed");
  const report: Report = JSON.parse(new TextDecoder().decode(bytes));
  if (report.schema_version !== "1.1.0" || report.site_id !== site.id || report.parent_sha256 !== site.sha256 ||
      report.landing_safety_certified !== false || report.operational_visibility_changed !== false ||
      !["NO_QUALIFIED_PRODUCT","NATIVE_RESOLUTION_DIAGNOSTIC"].includes(report.status))
    throw new Error("Invalid local terrain contract");
  if (report.status === "NATIVE_RESOLUTION_DIAGNOSTIC" && (!report.samples?.length ||
      !report.product || !report.nearfield || !report.roughness || !report.coregistration || typeof report.coregistration.applied !== "boolean" ||
      report.fusion?.independently_validated !== false ||
      (report.coregistration.applied && (report.coregistration.status !== "APPLIED_INTERNAL_CHECKS_ONLY" || report.fusion?.status !== "APPLIED_RESEARCH_FUSION")) ||
      report.samples.some((row)=>[row.sun,row.earth].some((ray)=>
        !(ray.local_status in labels) || !Number.isFinite(ray.valid_fraction) || ray.valid_fraction < 0 || ray.valid_fraction > 1 ||
        (ray.sampled_max_elevation_deg !== null && !Number.isFinite(ray.sampled_max_elevation_deg)) ||
        (ray.local_status !== "UNKNOWN" && (!ray.complete || ray.valid_fraction !== 1 || ray.sampled_max_elevation_deg === null))))))
    throw new Error("Invalid local terrain samples");
  if (report.coregistration?.applied && report.samples?.some((row)=>[row.sun,row.earth].some((ray)=>
    !ray.fused || !(ray.fused.status in fusionLabels) ||
    (ray.fused.horizon_deg !== null && !Number.isFinite(ray.fused.horizon_deg)) ||
    (ray.fused.status === "CLEAR_SAMPLED_MULTISCALE_DOMAIN" && !ray.fused.complete))))
    throw new Error("Invalid registered fusion samples");
  return report;
}

export function LocalTerrainStudy({site,sampleIndex,timestamp,onClose}: {
  site: IndexedSite; sampleIndex:number; timestamp:string; onClose:()=>void;
}) {
  const [report,setReport] = useState<Report|null>(null);
  const [error,setError] = useState("");
  useEffect(()=>{
    const controller = new AbortController();
    load(site,controller.signal).then((data)=>{if(!controller.signal.aborted) setReport(data);})
      .catch((reason)=>{if(!controller.signal.aborted) setError(String(reason));});
    return ()=>controller.abort();
  },[site]);
  const sample = report?.samples?.[sampleIndex];
  const aligned = sample?.timestamp === timestamp;
  return <section className="spacecraft-study" id="local-terrain-study" aria-label="Native terrain study">
    <header><div><span className="mission-kicker">NATIVE TERRAIN · LOCAL DIAGNOSTICS</span>
      <h2>{site.name}</h2></div><button onClick={onClose} aria-label="Close native terrain study">×</button></header>
    <p className="study-status">Not a landing-safety assessment · gauge source is selected separately in the site card</p>
    {!report ? <p role="status">{error || "Verifying terrain data…"}</p> : <>
      {report.reason ? <p>{report.reason}</p> : <>
        <p>{report.product?.product_id} · <strong>{report.native_pixel_size_m} m native posts</strong></p>
        <p className="study-caption">{report.product?.method}. Pixel spacing is not elevation accuracy.</p>
        <p className="study-status">{report.coregistration?.applied
          ? "Registration applied · research fusion recomputed to 200 km · not independently validated"
          : "Registration not applied: application checks did not pass"}</p>
        <p className="study-site">{timestamp} · observer +{report.nearfield?.observer_height_m} m · sampled radius {report.nearfield?.minimum_distance_m}–{report.nearfield?.maximum_distance_m} m</p>
        {!report.confidence_qualified && <p className="study-status">Fine-scale pixel provenance unresolved. All local visibility decisions remain unknown.</p>}
        {aligned && sample ? <dl className="study-metrics">{(["sun","earth"] as const).map((body)=><div key={body}>
          <dt>{body === "sun" ? "Sun" : "Earth"} center · near-field only</dt>
          <dd>{labels[sample[body].local_status]}</dd>
          <small>Sampled skyline {sample[body].sampled_max_elevation_deg?.toFixed(2) ?? "unavailable"}° · valid samples {(sample[body].valid_fraction*100).toFixed(1)}%</small>
          {sample[body].fused && <><dt>Registered NAC + regional LOLA · center LOS</dt>
            <dd>{fusionLabels[sample[body].fused!.status]}</dd>
            <small>Fused skyline {sample[body].fused!.horizon_deg?.toFixed(2) ?? "unavailable"}° · {sample[body].fused!.source}</small></>}
        </div>)}</dl> : <p role="alert">No epoch-aligned local terrain sample available.</p>}
        <h3>Resolved terrain roughness</h3>
        <p className="study-caption">Plane-detrended RMS and fitted slope; not boulder detection or certification.</p>
        <dl className="study-parameters">{report.roughness?.map((r)=><div key={r.radius_m}>
          <dt>{r.radius_m} m radius · {r.status.toLowerCase().replaceAll("_"," ")}</dt>
          <dd>{r.detrended_rms_m?.toFixed(3) ?? "—"} m RMS · {r.plane_slope_deg?.toFixed(2) ?? "—"}°</dd>
        </div>)}</dl>
        <details><summary>NAC–LOLA registration check</summary>
          <p>Fit status: {report.coregistration?.status}. {report.coregistration?.applied
            ? "Correction is applied to this native terrain study, including observer elevation, roughness and the fused skyline. The original LOLA baseline remains separate."
            : report.coregistration?.gate_failures?.join("; ")}</p>
          <p>{report.coregistration?.applied ? "Applied" : "Rejected"} sample-coordinate dx, dy, dz: {report.coregistration?.translation_m?.map((v)=>v.toFixed(2)).join(", ") ?? "unavailable"} m.
            Spatial holdout RMS: {report.coregistration?.holdout_before?.rmse_m.toFixed(3) ?? "—"} → {report.coregistration?.holdout_after?.rmse_m.toFixed(3) ?? "—"} m.</p>
          <p>Shared LOLA control and differing terrain resolution mean this is not an independent absolute-accuracy measurement.</p>
        </details>
      </>}
      <details open><summary>Coverage and safety limits</summary><ul>{report.limitations.map((text)=><li key={text}>{text}</li>)}</ul></details>
      <p><a href={`/data/local-terrain/${site.id}.json`} download>Download source-linked terrain report</a></p>
    </>}
  </section>;
}
