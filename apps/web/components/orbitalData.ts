export type Vector3 = [number, number, number];
export type OrbitalMode = "overview" | "true-scale";
export type OrbitalFocus = "system" | "pair" | "moon" | "earth" | "sun";
export type OrbitalSample = { utc: string; earth_km: Vector3; sun_km: Vector3; earth_fixed_to_scene: number[] };
export type OrbitalData = { schema: 1; frame: string; origin: "MOON"; correction: "NONE"; step_seconds: 600;
  matrix_layout: "row-major"; earth_orientation: string; radii_km: {earth: Vector3; sun: Vector3; moon: Vector3}; samples: OrbitalSample[] };
export type OrbitalRequest = { data: OrbitalData; epoch: number; mode: OrbitalMode; focus: OrbitalFocus; revision: number };
/** Cesium ellipsoid UVs put the equirectangular prime meridian on mesh -X. */
export function earthTextureMatrix(bodyToScene: number[]): number[] {
  return bodyToScene.map((v,i)=>i%3===2?v:-v);
}
const start = Date.parse("2026-10-01T00:00:00Z");
const vector = (v: unknown): v is Vector3 => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);

export function validateOrbitalData(value: unknown): OrbitalData {
  const d = value as OrbitalData;
  if (!d || d.schema !== 1 || d.frame !== "MOON_ME_DE440_ME421" || d.origin !== "MOON" || d.correction !== "NONE" ||
      d.step_seconds !== 600 || d.matrix_layout !== "row-major" || !d.radii_km ||
      ![d.radii_km.earth,d.radii_km.sun,d.radii_km.moon].every(r => vector(r) && r.every(x=>x>0)) ||
      !Array.isArray(d.samples) || d.samples.length !== 1009) throw new Error("Unsupported orbital frame or sample coverage");
  for (const [i,s] of d.samples.entries()) {
    if (!s || Date.parse(s.utc) !== start+i*600000 || !vector(s.earth_km) || !vector(s.sun_km) ||
        Math.hypot(...s.earth_km) < 300000 || Math.hypot(...s.sun_km) < 100000000 ||
        !Array.isArray(s.earth_fixed_to_scene) || s.earth_fixed_to_scene.length !== 9 || !s.earth_fixed_to_scene.every(Number.isFinite))
      throw new Error(`Invalid orbital epoch ${i}`);
    const m=s.earth_fixed_to_scene;
    for (let r=0;r<3;r++) for(let c=0;c<3;c++) {
      const dot=m[r*3]*m[c*3]+m[r*3+1]*m[c*3+1]+m[r*3+2]*m[c*3+2];
      if(Math.abs(dot-(r===c?1:0))>1e-10) throw new Error(`Non-orthogonal Earth attitude at ${i}`);
    }
    const determinant=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]);
    if(Math.abs(determinant-1)>1e-10) throw new Error(`Reflected Earth attitude at ${i}`);
  }
  return d;
}

export async function loadOrbitalData(signal: AbortSignal): Promise<OrbitalData> {
  const response=await fetch("/data/orbital-index.json",{signal,cache:"no-cache"});
  if(!response.ok) throw new Error(`Orbital manifest HTTP ${response.status}`);
  const manifest=await response.json();
  if(manifest.url!=="/data/orbital-scene.json" || !/^[a-f0-9]{64}$/.test(manifest.sha256)) throw new Error("Invalid orbital manifest");
  const data=await fetch(manifest.url,{signal,cache:"no-cache"});
  if(!data.ok) throw new Error(`Orbital data HTTP ${data.status}`);
  const bytes=await data.arrayBuffer();
  if(bytes.byteLength!==manifest.bytes) throw new Error("Orbital byte count mismatch");
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
  if(hash!==manifest.sha256) throw new Error("Orbital checksum mismatch");
  return validateOrbitalData(JSON.parse(new TextDecoder().decode(bytes)));
}

/** Visualization-only transform: directions preserved, separations explicitly compressed. */
export function displayPosition(km: Vector3, mode: OrbitalMode, body: "earth"|"sun"): Vector3 {
  const scale=mode==="true-scale" ? 1000 : (body==="earth"?12:30)*1737400/Math.hypot(...km);
  return km.map(v=>v*scale) as Vector3;
}
