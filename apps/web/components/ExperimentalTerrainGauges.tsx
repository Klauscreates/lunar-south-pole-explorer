"use client";

import { useEffect, useState } from "react";
import { load, type Report } from "./LocalTerrainStudy";
import type { IndexedSite } from "./types";
import { qualifiedTerrainRay } from "./terrainGauge";

// Never borrow a baseline value when an experimental ray is absent or incomplete.
export function ExperimentalTerrainGauges({ site, sampleIndex, timestamp }: {
  site: IndexedSite; sampleIndex: number; timestamp: string;
}) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    load(site, controller.signal).then((value) => {
      if (!controller.signal.aborted) setReport(value);
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(String(reason));
    });
    return () => controller.abort();
  }, [site]);
  const row = report?.samples?.[sampleIndex];
  const eligible = report?.site_id === site.id && report.parent_sha256 === site.sha256 &&
    report.confidence_qualified === true && report.coregistration?.applied === true &&
    report.fusion?.status === "APPLIED_RESEARCH_FUSION" && row?.timestamp === timestamp;
  return <section aria-label="Experimental terrain gauges">
    <p role="status">{error || (!report ? "Verifying experimental coverage…" :
      !eligible ? "Unknown: no qualified, registered coverage for this site and epoch." :
      "Experimental center-ray geometry · internal checks only, not independently validated.")}</p>
    {(["sun", "earth"] as const).map((body) => {
      const gauge = qualifiedTerrainRay(report, site.id, site.sha256, sampleIndex, timestamp, body);
      const angle = (value: number | undefined | null) => typeof value === "number" && Number.isFinite(value)
        ? `${value.toFixed(2)}°` : "Unknown";
      return <div className={`body-summary ${body}`} key={body}>
        <div><strong>{body === "sun" ? "Sun" : "Earth"} center visibility</strong>
          <span className="visibility">{gauge?.status ?? "Unknown"}</span></div>
        <dl>
          <div><dt>Elevation</dt><dd>{angle(gauge?.elevation)}</dd></div>
          <div><dt>Skyline</dt><dd>{angle(gauge?.horizon)}</dd></div>
          <div><dt>Clearance</dt><dd>{angle(gauge?.clearance)}</dd></div>
        </dl>
        {!gauge && <small>Unknown: complete qualified multiscale coverage is required. No LOLA substitution.</small>}
      </div>;
    })}
    <div className="power-readout"><span>ELECTRICAL OUTPUT / FULL-DISK ILLUMINATION</span>
      <strong>Unknown</strong><small>Experimental center rays do not qualify finite-disk illumination or panel power.</small></div>
    <div className="dte-detail"><span>FULL-DISK VISIBILITY WINDOWS</span><p>Unknown</p>
      <small>No qualified experimental disk-window calculation is available.</small></div>
  </section>;
}
