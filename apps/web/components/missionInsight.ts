export type InsightInput = {
  powerW: number; comms: number; earthDiskPct: number; cellTempC: number;
};
export type MissionInsight = { tone: "unknown" | "warning" | "clear" | "blackout"; title: string; text: string; caveat: string };

/** Deterministic screening narrative; never infer vehicle operations from geometry. */
export function getMissionInsight(input?: InsightInput): MissionInsight {
  const unknown: MissionInsight = { tone: "unknown", title: "Awaiting verified telemetry", text: "This epoch cannot yet be evaluated. No operating condition is inferred.", caveat: "Battery reserve, heater activity and RF performance are not modeled." };
  if (!input || !Object.values(input).every(Number.isFinite) || input.powerW < 0 ||
    ![0, 30, 100].includes(input.comms) || input.earthDiskPct < 0 || input.earthDiskPct > 100) return unknown;
  const { powerW: p, comms: c, earthDiskPct: disk, cellTempC: t } = input;
  let result: MissionInsight;
  if (p === 0 && c === 0) result = { ...unknown, tone: "blackout", title: "Dark arrays. Earth-center path blocked.", text: "No solar generation is modeled and the direct Earth-center path is obstructed. Battery endurance and survival state remain unknown." };
  else if (p === 0) result = { ...unknown, tone: "warning", title: "Quiet arrays. Earth remains in view.", text: "Solar generation is zero in this configuration. Earth-center geometry remains available; this does not establish an operating radio link or battery drain." };
  else if (c === 0) result = { ...unknown, tone: "warning", title: "Harvesting sunlight. Earth-center path blocked.", text: "The array is generating modeled power, but terrain or the R1 structure obstructs the direct Earth-center path." };
  else if (c === 30) result = { ...unknown, tone: "warning", title: "Power available. Earth grazes the horizon.", text: "Earth-center elevation is at or below 2°. Treat this as a geometric caution window; multipath and radio dropouts are not predicted by this model." };
  else if (p > 150 && disk > 95) result = { ...unknown, tone: "clear", title: "Sunlight and Earth align.", text: "Modeled generation exceeds 150 W and more than 95% of the Earth disk clears the local skyline approximation. A promising screening window—not authorization for science operations." };
  else result = { ...unknown, tone: "clear", title: "Collecting sunlight. Watching Earth.", text: "Some solar power is modeled and Earth-center geometry is clear. Review the power and horizon margins before choosing this window." };
  const warnings: string[] = [];
  if (disk > 0 && disk < 100) warnings.push("Partial Earth-disk occultation; exposure is a local skyline approximation.");
  if (t < 15 || t > 125) warnings.push(`${t < 15 ? "Cryogenic" : "High-temperature"} coefficient range exceeded: XTJ efficiency projection Unknown.`);
  if (warnings.length) {
    if (result.tone === "clear") result.tone = "warning";
    result.caveat = warnings.join(" ") + " " + unknown.caveat;
  }
  return result;
}
