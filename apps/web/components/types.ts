export type VisibilityState =
  | "FULLY_VISIBLE"
  | "PARTIALLY_VISIBLE"
  | "BLOCKED";

export type ValidationStatus = "PASS" | "FAIL" | "WARN" | "NOT_RUN";

export interface ErrorSummary {
  maximum: number;
  mean: number;
  rms: number;
  p95: number;
  signed_bias?: number;
}

export interface SpiceTargetComparison {
  status: ValidationStatus;
  target: string;
  sample_count: number;
  pass_criterion: {
    maximum_allowed_arcsec: number;
    maximum_range_error_ppm: number;
    maximum_angular_diameter_error_arcsec: number;
  };
  angular_separation_arcsec: ErrorSummary;
  range_error_ppm: ErrorSummary;
  angular_diameter_error_arcsec: ErrorSummary;
}

export interface IndependentSpiceValidation {
  status: ValidationStatus;
  required: boolean;
  used_for_simulation: boolean;
  scope: string;
  targets: {
    sun: SpiceTargetComparison;
    earth: SpiceTargetComparison;
  };
  limitations: string[];
}

export interface BodyState {
  azimuth_deg: number;
  elevation_deg: number;
  angular_radius_deg: number;
  angular_diameter_arcsec: number;
  distance_km: number;
  terrain_horizon_deg: number;
  clearance_deg: number;
  visibility_fraction: number;
  state: VisibilityState;
}

export interface PowerState {
  geometric_sunlight_available: boolean;
  panel_illuminated: boolean;
  orientation_mode: string;
  incidence_cosine: number;
  relative_irradiance_vs_1au: number;
  direct_irradiance_w_m2: number;
  estimated_incident_power_w: number;
  estimated_electrical_output_w: number;
}

export interface CommsPotential {
  model: "earth_center_terrain_clearance_v1";
  classification: "BLOCKED" | "MARGINAL" | "CLEAR";
  potential_index_percent: 0 | 30 | 100;
  center_clear: boolean;
  low_elevation_threshold_deg: number;
}

export interface SimulationSample {
  timestamp: string;
  sun: BodyState;
  earth: BodyState;
  power: PowerState;
  power_scenarios?: Record<string, PowerState>;
  geometric_dte_available: boolean;
  comms_potential: CommsPotential;
  combined_state: string;
}

export interface IndexedSite {
  id: string;
  name: string;
  latitude_deg: number;
  longitude_deg_east: number;
  kind: "validation" | "candidate";
  region_status: "current_2024_cohort" | "historical_2022_cohort" | null;
  coordinate_source_url: string | null;
  data_url: string;
  sha256: string;
  summary: {
    sunlight_percentage: number;
    earth_visible_percentage: number;
  };
}

export interface SimulationIndex {
  schema_version: "1.0.0";
  sites: IndexedSite[];
}

export interface HorizonPoint {
  azimuth_deg: number;
  elevation_deg: number;
  obstruction_distance_m: number;
}

export interface HorizonMaskPoint {
  azimuth_deg: number;
  minimum_clearance_elevation_deg: number;
  obstruction_distance_m: number;
}

export interface WindowStats {
  interval_count: number;
  total_duration_seconds: number;
  total_duration_hours: number;
  percentage: number;
  longest_duration_seconds: number;
  longest_duration_hours: number;
  intervals: Array<{
    start_utc: string;
    end_utc: string;
    duration_seconds: number;
    duration_hours: number;
  }>;
}

export interface SimulationResult {
  schema_version: string;
  software: {
    name: string;
    version: string;
    generated_utc: string;
    dependencies: Record<string, string>;
  };
  site: {
    name: string;
    latitude_deg: number;
    longitude_deg_east: number;
    terrain_elevation_m: number;
    observer_height_m: number;
    observer_altitude_above_reference_sphere_m: number;
  };
  time_range: {
    start_utc: string;
    end_utc: string;
    step_minutes: number;
    sample_count: number;
    window_boundary_precision_minutes: number;
  };
  data_sources: {
    terrain: {
      strategy: string;
      local: Record<string, unknown>;
      outer: Record<string, unknown>;
    };
    sun_ephemeris: Record<string, unknown>;
    earth_ephemeris: Record<string, unknown>;
    spice_validation: {
      role: "independent_validator_only";
      used_for_operational_samples: false;
      sun: Record<string, unknown>;
      earth: Record<string, unknown>;
    };
  };
  provenance_contract: {
    operational_ephemeris: string;
    independent_validator: string;
    validator_used_for_operational_samples: boolean;
  };
  reference_frames: Record<string, unknown>;
  assumptions: Record<string, unknown>;
  panel: {
    panel_area_m2: number;
    efficiency: number;
    orientation_mode: string;
  };
  panel_scenarios?: Record<string, { description?: string; [key: string]: unknown }>;
  horizon: {
    metadata: Record<string, unknown>;
    profile: HorizonPoint[];
  };
  horizon_mask?: {
    metadata: Record<string, unknown>;
    profile: HorizonMaskPoint[];
  };
  samples: SimulationSample[];
  windows: {
    method: string;
    solar: {
      sunlight: WindowStats;
      shadow: WindowStats;
      illumination_percentage: number;
      longest_continuous_sunlight_seconds: number;
      longest_continuous_darkness_seconds: number;
    };
    earth: {
      dte_visible: WindowStats;
      dte_blackout: WindowStats;
      earth_visible_percentage: number;
      longest_dte_window_seconds: number;
      longest_dte_blackout_seconds: number;
    };
    combined: Record<string, WindowStats>;
  };
  validation: {
    overall_status: ValidationStatus;
    source_integrity_status: ValidationStatus;
    independent_ephemeris_status: ValidationStatus;
    sun: Record<string, unknown>;
    earth: Record<string, unknown>;
    terrain: Record<string, unknown>;
    independent_spice: IndependentSpiceValidation;
    limitations: string[];
  };
}
