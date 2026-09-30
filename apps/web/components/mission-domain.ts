/** Future search keeps physical metrics separate; no synthetic aggregate score. */
export interface CandidateSite {
  id: string;
  latitudeDeg: number;
  longitudeDegEast: number;
  observerHeightM: number;
  evaluation: "not-evaluated" | "validated";
  resultUrl?: string;
}
export interface SiteConstraints {
  maximumSlopeDeg?: number;
  minimumSunlightPercent?: number;
  maximumDarknessHours?: number;
  minimumDtePercent?: number;
  maximumBlackoutHours?: number;
  maximumEvidenceDistanceM?: number;
}
export interface ResourceEvidenceLayer {
  id: string;
  status: "not-loaded" | "available";
  evidenceType:
    "hydrogen" | "ice-stability" | "direct-observation" | "model-inference";
  sourceUrl?: string;
  uncertaintyDescription?: string;
}
