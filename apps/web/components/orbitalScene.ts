import type * as Cesium from "cesium";
import { displayPosition, earthTextureMatrix, type OrbitalRequest, type OrbitalFocus } from "./orbitalData";
import { createCelestialAppearance } from "./celestialAppearance";

/** Reuses the existing Moon terrain viewer; owns only orbital-mode scene objects. */
export function createOrbitalScene(C: typeof Cesium, viewer: Cesium.Viewer, earth: Cesium.Entity) {
  const moonRadius=1737400;
  // Cesium's stock Phong material includes camera-facing fill lights. Use an
  // explicit Sun-directed Lambert shader so the orbital view has real phases.
  const phaseShader=`in vec3 v_positionEC; in vec3 v_normalEC; in vec2 v_st;
    void main(){czm_materialInput inputValue; inputValue.normalEC=normalize(v_normalEC);
      inputValue.positionToEyeEC=-v_positionEC; inputValue.st=v_st;
      czm_material material=czm_getMaterial(inputValue);
      float day=max(dot(normalize(v_normalEC),normalize(czm_lightDirectionEC)),0.0);
      out_FragColor=vec4(material.diffuse*(0.025+0.975*day),1.0);}`;
  const texturedSphere=(image:string)=>viewer.scene.primitives.add(new C.Primitive({show:false,asynchronous:false,
    geometryInstances:new C.GeometryInstance({id:"celestial-moon",geometry:new C.EllipsoidGeometry({radii:new C.Cartesian3(1,1,1),stackPartitions:96,slicePartitions:96,vertexFormat:C.MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat})}),
    appearance:new C.MaterialAppearance({translucent:false,closed:true,fragmentShaderSource:phaseShader,
      material:C.Material.fromType("Image",{image})})})) as Cesium.Primitive;
  const moonProxy=texturedSphere("/terrain/lroc_color_4k.jpg");
  const earthGlobe=createCelestialAppearance(C,viewer,"earth");
  const sun=createCelestialAppearance(C,viewer,"sun");
  const labels=Object.fromEntries(["moon","earth","sun"].map(name=>[name,viewer.entities.add({show:false,position:C.Cartesian3.ZERO,
    label:{text:name.toUpperCase(),font:"12px sans-serif",fillColor:C.Color.WHITE,showBackground:true,
      backgroundColor:C.Color.fromCssColorString("#09131dcc"),pixelOffset:new C.Cartesian2(0,-22),disableDepthTestDistance:Infinity}})]));
  let active=false,lastKey="",lastCameraKey="",lastCenter:Cesium.Cartesian3|undefined;
  let inspectionFocus:OrbitalFocus|undefined;
  const light=new C.DirectionalLight({direction:new C.Cartesian3(1,0,0),intensity:1.7});
  const from=(v:number[])=>new C.Cartesian3(v[0],v[1],v[2]);

  function update(request:OrbitalRequest) {
    const {data,epoch,mode,revision}=request;
    const focus=inspectionFocus ?? request.focus;
    const key=`${epoch}:${mode}:${focus}:${revision}`;
    if(active && key===lastKey) return;
    active=true;lastKey=key;
    const sample=data.samples[epoch];
    if(!sample) throw new Error("Orbital epoch unavailable");
    const positions={moon:C.Cartesian3.ZERO,earth:from(displayPosition(sample.earth_km,mode,"earth")),sun:from(displayPosition(sample.sun_km,mode,"sun"))};
    const radii={moon:mode==="overview"?moonRadius*2:moonRadius,earth:mode==="overview"?moonRadius*3:data.radii_km.earth[0]*1000,sun:mode==="overview"?moonRadius*5:data.radii_km.sun[0]*1000};
    viewer.scene.globe.show=mode==="true-scale";
    viewer.scene.globe.enableLighting=true;
    viewer.shadows=false;
    viewer.scene.screenSpaceCameraController.maximumZoomDistance=1e13;
    viewer.scene.screenSpaceCameraController.enableCollisionDetection=false;
    viewer.scene.light=light;
    light.direction=C.Cartesian3.negate(C.Cartesian3.normalize(from(sample.sun_km),new C.Cartesian3()),new C.Cartesian3());
    moonProxy.show=mode==="overview";
    moonProxy.modelMatrix=C.Matrix4.fromTranslationQuaternionRotationScale(C.Cartesian3.ZERO,C.Quaternion.fromAxisAngle(C.Cartesian3.UNIT_Z,Math.PI),new C.Cartesian3(radii.moon,radii.moon,radii.moon));
    earth.show=false;earthGlobe.show=true;
    const matrix=C.Matrix3.fromRowMajorArray(earthTextureMatrix(sample.earth_fixed_to_scene));
    earthGlobe.modelMatrix=C.Matrix4.fromTranslationQuaternionRotationScale(positions.earth,C.Quaternion.fromRotationMatrix(matrix),mode==="overview"?new C.Cartesian3(radii.earth,radii.earth,radii.earth):from(data.radii_km.earth.map(x=>x*1000)));
    sun.show=true;
    sun.modelMatrix=C.Matrix4.fromTranslationQuaternionRotationScale(positions.sun,C.Quaternion.IDENTITY,new C.Cartesian3(radii.sun,radii.sun,radii.sun));
    for(const name of ["moon","earth","sun"] as const) {
      labels[name].show=focus==="system" || focus===name || (focus==="pair" && name!=="sun");
      labels[name].position=new C.ConstantPositionProperty(positions[name]);
    }
    const bodies=focus==="system"?["moon","earth","sun"] as const:focus==="pair"?["moon","earth"] as const:[focus] as const;
    const bounds=C.BoundingSphere.fromBoundingSpheres(bodies.map(name=>new C.BoundingSphere(positions[name],radii[name])));
    const cameraKey=`${mode}:${focus}:${revision}`;
    if(lastCameraKey!==cameraKey) {
      viewer.camera.cancelFlight();
      // Account for a portrait viewport's narrower horizontal field of view.
      const frustum=viewer.camera.frustum as Cesium.PerspectiveFrustum;
      const aspect=viewer.scene.canvas.clientWidth/viewer.scene.canvas.clientHeight;
      const angle=Math.atan(Math.tan((frustum.fov ?? Math.PI/3)/2)*Math.min(aspect,1/aspect));
      const distance=bounds.radius/Math.sin(angle)*1.12;
      viewer.camera.lookAtTransform(C.Matrix4.fromTranslation(bounds.center),new C.Cartesian3(0,-distance*.35,distance));
      lastCameraKey=cameraKey;
    } else if(lastCenter) {
      // Keep free camera orientation and user zoom while following the selected body.
      const offset=C.Cartesian3.clone(viewer.camera.position);
      viewer.camera.lookAtTransform(C.Matrix4.fromTranslation(bounds.center));
      viewer.camera.position=offset;
    }
    lastCenter=C.Cartesian3.clone(bounds.center);
    viewer.scene.requestRender();
  }
  function leave() {
    if(!active)return false;
    active=false;lastKey="";lastCameraKey="";lastCenter=undefined;inspectionFocus=undefined;
    moonProxy.show=false;sun.show=false;earthGlobe.show=false;
    Object.values(labels).forEach(entity=>{entity.show=false;});
    viewer.scene.globe.show=true;
    viewer.scene.screenSpaceCameraController.maximumZoomDistance=12000000;
    viewer.scene.screenSpaceCameraController.enableCollisionDetection=true;
    earth.orientation=new C.ConstantProperty(C.Quaternion.IDENTITY);
    viewer.camera.lookAtTransform(C.Matrix4.IDENTITY);
    return true;
  }
  function focusAt(point:Cesium.Cartesian2,request:OrbitalRequest) {
    const picked=viewer.scene.pick(point)?.id;
    inspectionFocus=(["earth","sun","moon"] as const).find(name=>picked===`celestial-${name}` || picked===labels[name]) ?? "system";
    lastKey="";lastCameraKey="";
    update(request);
  }
  return {update,leave,focusAt,recenter:(request:OrbitalRequest)=>{lastKey="";lastCameraKey="";update(request);}};
}
