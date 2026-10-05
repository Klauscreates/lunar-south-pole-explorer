import type { SimulationResult } from "./types";
import type { Study } from "./SpacecraftStudy";
import type { Report } from "./LocalTerrainStudy";
import spec from "../public/data/spacecraft/component-spec.json" with { type: "json" };

export const CELL_SPEC = spec;
export const EPOCHS = 1009;
export const START = Date.parse("2026-10-01T00:00:00Z");
export function epochTime(index: number) { return new Date(START + index * 600000).toISOString(); }

export function cellReference(temperatureK: number) {
  const [low, high] = spec.coefficient_temperature_range_k;
  if (!Number.isFinite(temperatureK) || temperatureK < low || temperatureK > high) return null;
  const p = spec.cell_properties;
  const delta = temperatureK - p.reference_temperature_k.value;
  return p.reference_efficiency.value *
    (1 + p.dvmp_dt_v_k.value * delta / p.vmp_v.value) *
    (1 + p.djmp_dt_a_m2_k.value * delta / p.jmp_a_m2.value);
}

export function comparisonSeries(simulation: SimulationResult, study: Study, scenarioId: string) {
  const scenario = study.scenarios.find(s => s.id === scenarioId);
  if (!scenario || simulation.samples.length !== EPOCHS || study.timestamps.length !== EPOCHS ||
      scenario.rows.length !== EPOCHS) return null;
  const cumulative = [0];
  for (let i = 0; i < EPOCHS; i++) {
    if (Date.parse(simulation.samples[i].timestamp) !== START + i * 600000 ||
        Date.parse(study.timestamps[i]) !== START + i * 600000 ||
        !Number.isFinite(scenario.rows[i][0]) || scenario.rows[i][0] < 0) return null;
    if (i > 0) cumulative.push(cumulative[i - 1] + scenario.rows[i - 1][0] / 6000);
  }
  return { rows: scenario.rows, cumulative };
}

export function terrainEvidence(report?: Report) {
  const qualified = report?.confidence_qualified === true && report.coregistration?.applied === true;
  const local = qualified ? report.roughness?.find(r => r.radius_m === 10 && r.valid_fraction === 1 && r.status === "SAMPLED_TERRAIN_ONLY") : undefined;
  const area = qualified ? report.roughness?.find(r => r.radius_m === 500 && r.valid_fraction === 1 && r.status === "SAMPLED_TERRAIN_ONLY") : undefined;
  const slope = Number.isFinite(local?.plane_slope_deg) ? local!.plane_slope_deg! : null;
  const roughness = Number.isFinite(area?.detrended_rms_m) ? area!.detrended_rms_m! : null;
  return { slope, roughness, complete: slope !== null && roughness !== null,
    source: qualified ? `Registered ${report.native_pixel_size_m} m NAC + LOLA — experimental` : "LOLA baseline; fine-scale coverage unqualified" };
}
