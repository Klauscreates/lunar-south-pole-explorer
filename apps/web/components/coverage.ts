export const COVERAGE_START = Date.parse("2026-10-01T00:00:00Z");
export const COVERAGE_END = Date.parse("2027-01-01T00:00:00Z");
export const COVERAGE_STEP = 600000;
export const COVERAGE_LAST = (COVERAGE_END - COVERAGE_START) / COVERAGE_STEP;
export function coveredEpoch(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const time = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0,16) !== value ||
      time < COVERAGE_START || time > COVERAGE_END || (time-COVERAGE_START)%COVERAGE_STEP !== 0) return null;
  return (time-COVERAGE_START)/COVERAGE_STEP;
}
export function coveredInput(epoch: number) {
  return new Date(COVERAGE_START + epoch*COVERAGE_STEP).toISOString().slice(0,16);
}
