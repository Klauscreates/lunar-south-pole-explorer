import type { Study } from "./SpacecraftStudy";

/** Read the selected export, never infer hardware state from display-label substrings. */
export function attitudeStatus(study: Study | undefined, scenarioId: string) {
  const scenario = study?.scenarios.find(item => item.id === scenarioId);
  const pose = study?.design.attitudes.find(item => item.id === scenario?.pose_id);
  const boundary = study?.design.boundary_cases.find(item => item.id === scenario?.boundary_id);
  if (!pose || !boundary || ![pose.yaw, pose.pitch, pose.roll,
    boundary.wall_reflected_solar_irradiance_w_m2, boundary.lunar_ir_irradiance_w_m2].every(Number.isFinite)) return null;
  const heading = ((pose.yaw % 360) + 360) % 360;
  const facing = new Map([[0, "North"], [90, "East"], [180, "South"], [270, "West"]]).get(heading) ?? `${heading}°`;
  return { heading, facing, pitch: pose.pitch, roll: pose.roll,
    isTilted: pose.pitch !== 0 || pose.roll !== 0,
    isAddedLoad: boundary.id === "added_load", loadLabel: boundary.label,
    wall: boundary.wall_reflected_solar_irradiance_w_m2, ir: boundary.lunar_ir_irradiance_w_m2 };
}
