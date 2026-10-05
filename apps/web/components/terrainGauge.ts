import type { Report } from "./LocalTerrainStudy";

export function qualifiedTerrainRay(report: Report | null, siteId: string, parentSha: string,
  sampleIndex: number, timestamp: string, body: "sun" | "earth") {
  const row = report?.samples?.[sampleIndex];
  const ray = row?.[body];
  const fused = ray?.fused;
  if (report?.site_id !== siteId || report.parent_sha256 !== parentSha ||
    report.confidence_qualified !== true || report.coregistration?.applied !== true ||
    report.fusion?.status !== "APPLIED_RESEARCH_FUSION" || row?.timestamp !== timestamp ||
    fused?.complete !== true || !["BLOCKED", "CLEAR_SAMPLED_MULTISCALE_DOMAIN"].includes(fused.status) ||
    typeof fused.horizon_deg !== "number" || !Number.isFinite(fused.horizon_deg) ||
    typeof ray?.target_elevation_deg !== "number" || !Number.isFinite(ray.target_elevation_deg)) return null;
  return { status: fused.status === "BLOCKED" ? "Blocked" : "Clear",
    elevation: ray.target_elevation_deg, horizon: fused.horizon_deg,
    clearance: ray.target_elevation_deg - fused.horizon_deg };
}
