import type * as Cesium from "cesium";

export const CELESTIAL_TEXTURES = {
  earth: "/celestial/earth_daymap-4k.jpg",
  clouds: "/celestial/earth_clouds-4k.jpg",
  sun: "/celestial/sun-4k.jpg",
} as const;

const inputs = `in vec3 v_positionEC; in vec3 v_normalEC; in vec2 v_st;`;
const earthShader = `${inputs}
void main(){
  vec3 n=normalize(v_normalEC), eye=normalize(-v_positionEC), light=normalize(czm_lightDirectionEC);
  czm_materialInput mi; mi.normalEC=n; mi.positionToEyeEC=-v_positionEC; mi.st=v_st;
  czm_material m=czm_getMaterial(mi);
  float day=max(dot(n,light),0.0);
  float twilight=smoothstep(-0.12,0.18,dot(n,light));
  float rim=pow(1.0-max(dot(n,eye),0.0),3.0);
  float glint=pow(max(dot(n,normalize(eye+light)),0.0),48.0)*m.specular*day;
  vec3 color=m.diffuse*(0.035+1.05*day)+vec3(0.65,0.82,1.0)*glint*0.35;
  color+=vec3(0.08,0.32,0.72)*rim*twilight*0.45;
  out_FragColor=vec4(color,1.0);
}`;
const sunShader = `${inputs}
void main(){
  czm_materialInput mi; mi.normalEC=normalize(v_normalEC); mi.positionToEyeEC=-v_positionEC; mi.st=v_st;
  czm_material m=czm_getMaterial(mi);
  float mu=max(dot(normalize(v_normalEC),normalize(-v_positionEC)),0.0);
  // Display-only limb darkening. The texture is not epoch-specific solar telemetry.
  vec3 color=m.diffuse*(0.62+0.48*pow(mu,0.35));
  out_FragColor=vec4(color,1.0);
}`;

/** Visual materials only: never modify the ephemeris centers or physical radii. */
export function createCelestialAppearance(C:typeof Cesium,viewer:Cesium.Viewer,body:"earth"|"sun") {
  const earth=body==="earth";
  const material=earth ? new C.Material({fabric:{type:"LunarEarthCloudComposite4K",
    uniforms:{dayMap:CELESTIAL_TEXTURES.earth,cloudMap:CELESTIAL_TEXTURES.clouds},
    source:`czm_material czm_getMaterial(czm_materialInput mi){
      czm_material m=czm_getDefaultMaterial(mi);
      vec3 ground=texture(dayMap,mi.st).rgb;
      float cloud=pow(texture(cloudMap,mi.st).r,0.85);
      m.diffuse=mix(ground,vec3(0.97,0.98,1.0),cloud*0.92);
      m.specular=smoothstep(0.04,0.18,ground.b-ground.r)*(1.0-cloud);
      m.alpha=1.0;return m;}`},translucent:false}) : C.Material.fromType("Image",{image:CELESTIAL_TEXTURES.sun});
  const sphere=(appearance:Cesium.MaterialAppearance,partitions:number)=>viewer.scene.primitives.add(new C.Primitive({
    show:false,asynchronous:false,
    geometryInstances:new C.GeometryInstance({id:`celestial-${body}`,geometry:new C.EllipsoidGeometry({radii:new C.Cartesian3(1,1,1),stackPartitions:partitions,slicePartitions:partitions,vertexFormat:C.MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat})}),
    appearance,
  })) as Cesium.Primitive;
  const surface=sphere(new C.MaterialAppearance({material,closed:true,translucent:false,fragmentShaderSource:earth?earthShader:sunShader}),128);
  const shellScale=earth?1.025:1.16;
  const shellShader=`${inputs}
  void main(){
    vec3 n=normalize(v_normalEC),eye=normalize(-v_positionEC);
    float mu=clamp(dot(n,eye),0.0,1.0);
    float projected=sqrt(max(0.0,1.0-mu*mu))*${shellScale.toFixed(3)};
    float glow=exp(-pow((projected-1.0)/${earth?"0.027":"0.065"},2.0));
    float fade=smoothstep(0.0,0.12,mu);
    float day=${earth?"smoothstep(-0.2,0.5,dot(n,normalize(czm_lightDirectionEC)))":"1.0"};
    out_FragColor=vec4(${earth?"vec3(0.16,0.48,1.0)":"vec3(1.0,0.39,0.055)"},glow*fade*day*${earth?"0.48":"0.34"});
  }`;
  const halo=sphere(new C.MaterialAppearance({material:C.Material.fromType("Color"),translucent:true,closed:false,
    fragmentShaderSource:shellShader,renderState:{depthTest:{enabled:true},depthMask:false,cull:{enabled:true,face:C.CullFace.BACK},blending:C.BlendingState.ALPHA_BLEND}}),64);
  return {
    set show(value:boolean){surface.show=value;halo.show=value;},
    set modelMatrix(value:Cesium.Matrix4){surface.modelMatrix=value;halo.modelMatrix=C.Matrix4.multiplyByUniformScale(value,shellScale,new C.Matrix4());},
  };
}
