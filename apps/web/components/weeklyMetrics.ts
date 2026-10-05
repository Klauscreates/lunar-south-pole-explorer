import type { Study } from "./SpacecraftStudy";

// Left-endpoint integration matches the exported 10-minute state intervals.
// The terminal epoch has zero duration; it must not inflate weekly availability.
export function weeklyMetrics(study: Study, scenarioId: string) {
  const scenario = study.scenarios.find((s) => s.id === scenarioId);
  if (!scenario || study.timestamps.length !== scenario.rows.length || scenario.rows.length < 2) return null;
  let hours = 0, wattHours = 0, poweredHours = 0, commsHours = 0;
  for (let i = 0; i < scenario.rows.length - 1; i++) {
    const dt = (Date.parse(study.timestamps[i+1]) - Date.parse(study.timestamps[i])) / 3600000;
    const row = scenario.rows[i];
    if (!Number.isFinite(dt) || dt <= 0 || !Number.isFinite(row[0]) || row[0] < 0 || typeof row[7] !== "boolean") return null;
    hours += dt; wattHours += row[0] * dt;
    if (row[0] > 0) poweredHours += dt;
    if (row[7]) commsHours += dt;
  }
  return { hours, kwh: wattHours / 1000, poweredPercent: poweredHours / hours * 100,
    commsPercent: commsHours / hours * 100, commsHours, averageWatts: wattHours / hours };
}
