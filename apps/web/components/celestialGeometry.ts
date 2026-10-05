/** Apparent sphere radius preserves the exported angular diameter at its measured range. */
export function celestialRadius(distanceKm: number, angularRadiusDeg: number): number | null {
  if (!Number.isFinite(distanceKm) || !Number.isFinite(angularRadiusDeg) || distanceKm <= 0 || angularRadiusDeg <= 0 || angularRadiusDeg >= 90) return null;
  return distanceKm * 1000 * Math.sin(angularRadiusDeg * Math.PI / 180);
}
