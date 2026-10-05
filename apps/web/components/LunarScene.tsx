"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import type * as Cesium from "cesium";
import { celestialRadius } from "./celestialGeometry";
import { CELESTIAL_TEXTURES } from "./celestialAppearance";
import { createOrbitalScene } from "./orbitalScene";
import { installTouchNavigation, panDistance } from "./touchNavigation";
import type { OrbitalRequest } from "./orbitalData";
import type { BodyState, IndexedSite, SimulationResult, SimulationSample } from "./types";

export interface Layers {
  terrain: boolean;
  imagery: boolean;
  sites: boolean;
  sun: boolean;
  earth: boolean;
  illumination: boolean;
  slope: boolean;
  psr: boolean;
  uncertainty: boolean;
}
export interface Inspection {
  latitude: number;
  longitude: number;
  elevation_m: number;
  resolution_m: number;
  dataset: string;
  slope?: number | null;
  height_error?: number | null;
  slope_error?: number | null;
  effective_resolution?: number | null;
  count?: number | null;
  psr?: number | null;
}
export interface SceneStatus {
  focusedSiteId?: string;
  altitude: number;
  heading: number;
  loaded: number;
  pending: number;
  fps: number;
  scale: number;
}
type Engine = {
  viewer: Cesium.Viewer;
  update: (sample: SimulationSample, layers: Layers) => void;
  fly: (mode: string) => void;
  selectSite: (data: SimulationResult, siteId: string) => void;
};
declare global {
  interface Window {
    Cesium: typeof Cesium;
    CESIUM_BASE_URL: string;
  }
}

/** Decorative, deterministic stars, not an astronomical catalog or science input. */
function createStarBackdrop(C: typeof Cesium): Cesium.SkyBox | false {
  const faces = ["positiveX", "negativeX", "positiveY", "negativeY", "positiveZ", "negativeZ"] as const;
  const sources = {} as Record<(typeof faces)[number], HTMLCanvasElement>;
  let seed = 1737400;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  for (const face of faces) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1024;
    const ctx = canvas.getContext("2d");
    if (!ctx) return false; // A black backdrop is safe if canvas is unavailable.
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, 1024, 1024);
    for (let i = 0; i < 170; i++) {
      const x = 4 + random() * 1016;
      const y = 4 + random() * 1016;
      const brightness = 0.25 + random() * 0.65;
      const radius = 0.45 + random() ** 3 * 0.95;
      ctx.fillStyle = `rgba(225,234,248,${brightness})`;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
    }
    sources[face] = canvas;
  }
  // Generated once per viewer, drawn behind terrain, and released with the viewer.
  return new C.SkyBox({ sources });
}

export default function LunarScene({
  data,
  sites,
  selectedSiteId,
  sample,
  layers,
  flight,
  orbital,
  onInspect,
  onStatus,
  onError,
  onRendererError,
  onSelectSite,
}: {
  data: SimulationResult;
  sites: IndexedSite[];
  selectedSiteId: string;
  sample: SimulationSample;
  layers: Layers;
  flight: { mode: string; id: number };
  orbital: OrbitalRequest | null;
  onInspect: (value: Inspection) => void;
  onStatus: (value: SceneStatus) => void;
  onError: (message: string) => void;
  onRendererError: (message: string) => void;
  onSelectSite: (siteId: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [navigationMode, setNavigationMode] = useState<'pan' | 'look'>('pan');
  const navigationModeRef = useRef<'pan' | 'look'>('pan');
  const engine = useRef<Engine | null>(null);
  const pendingFlight = useRef(flight);
  const latest = useRef({
    data,
    selectedSiteId,
    sample,
    layers,
    orbital,
    onInspect,
    onStatus,
    onError,
    onRendererError,
    onSelectSite,
  });
  const [ready, setReady] = useState(false);
  useEffect(() => {
    latest.current = {
      data,
      selectedSiteId,
      sample,
      layers,
      orbital,
      onInspect,
      onStatus,
      onError,
      onRendererError,
      onSelectSite,
    };
    engine.current?.selectSite(data, selectedSiteId);
    engine.current?.update(sample, layers);
  }, [data, selectedSiteId, sample, layers, orbital, onInspect, onStatus, onError, onRendererError, onSelectSite]);
  useEffect(() => {
    pendingFlight.current = flight;
    engine.current?.fly(flight.mode);
  }, [flight]);
  useEffect(() => {
    if (!ready || !host.current) return;
    const C = window.Cesium;
    window.CESIUM_BASE_URL = "/cesium/";
    const moon = new C.Ellipsoid(1737400, 1737400, 1737400);
    C.Ellipsoid.default = moon;
    const tiling = new C.GeographicTilingScheme({ ellipsoid: moon });
    let loaded = 0,
      pending = 0,
      disposed = false;
    const controller = new AbortController();
    const provider = new C.CustomHeightmapTerrainProvider({
      width: 65,
      height: 65,
      tilingScheme: tiling,
      credit: "NASA / GSFC / LOLA · MOON_ME · 1737.4 km",
      callback: () => new Float32Array(65 * 65),
    });
    const baseError = provider.getLevelMaximumGeometricError(0);
    provider.getLevelMaximumGeometricError = (level: number) =>
      baseError / (4 * 2 ** level);
    // Explicit leaf masks prevent endless upsampling past the available source.
    provider.requestTileGeometry = (x: number, y: number, level: number) => {
      if (pending >= 12) return undefined;
      pending++;
      const rect = tiling.tileXYToRectangle(x, y, level);
      const south = C.Math.toDegrees(rect.south);
      const max = south < -89.5 ? 11 : south < -83 ? 7 : 5;
      const polar = C.Math.toDegrees(rect.north) <= -80;
      const width = polar ? 17 : 65,
        height = polar ? 513 : 65;
      return fetch(`/api/terrain/height/${level}/${x}/${y}?v=2`, {
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok)
            throw new Error(`Terrain tile failed (${response.status})`);
          const buffer = new Float32Array(await response.arrayBuffer());
          if (buffer.length !== width * height)
            throw new Error("Invalid NASA terrain tile length");
          loaded++;
          return new C.HeightmapTerrainData({
            buffer,
            width,
            height,
            childTileMask: level >= max ? 0 : 15,
          });
        })
        .catch((error) => {
          if (!disposed) latest.current.onError(String(error));
          throw error;
        })
        .finally(() => {
          pending--;
        });
    };
    const flightDuration = (seconds: number) => window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : seconds;
    const viewer = new C.Viewer(host.current, {
      globe: new C.Globe(moon),
      mapProjection: new C.GeographicProjection(moon),
      terrainProvider: provider,
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      selectionIndicator: false,
      infoBox: false,
      skyBox: createStarBackdrop(C),
      skyAtmosphere: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
      // Cesium otherwise defaults to CSS pixels, ignoring devicePixelRatio.
      // resolutionScale below assumes device pixels: keep these paired.
      useBrowserRecommendedResolution: false,
      contextOptions: { webgl: { alpha: false, antialias: true } },
      shadows: false,
    });
    viewer.resolutionScale = Math.min(1, 2 / window.devicePixelRatio);
    viewer.scene.backgroundColor = C.Color.BLACK;
    if (viewer.scene.sun) viewer.scene.sun.show = false;
    if (viewer.scene.moon) viewer.scene.moon.show = false;
    viewer.scene.fog.enabled = false;
    viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit('Earth/Sun textures: <a href="https://www.solarsystemscope.com/textures/" target="_blank" rel="noopener">Solar System Scope</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a> · resized to 4K; artist-adjusted, not live observations'));
    viewer.scene.globe.baseColor = C.Color.fromCssColorString("#878785");
    viewer.scene.globe.maximumScreenSpaceError = 2;
    viewer.scene.globe.tileCacheSize = window.matchMedia("(max-width: 950px)").matches ? 100 : 350;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.shadows = C.ShadowMode.ENABLED;
    viewer.shadowMap.maximumDistance = 25000;
    viewer.shadowMap.size = 2048;
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 500;
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 12000000;
    const navigation = viewer.scene.screenSpaceCameraController;
    navigation.rotateEventTypes = [C.CameraEventType.LEFT_DRAG];
    navigation.inertiaSpin = .82;
    navigation.inertiaZoom = .75;
    const removeTouchNavigation = installTouchNavigation(viewer.scene.canvas, {
      mode: () => navigationModeRef.current,
      interrupt: () => viewer.camera.cancelFlight(),
      rotate: enabled => { navigation.enableRotate = enabled; },
      pan: (dx,dy) => {
        const camera=viewer.camera;
        // Use distance to the scene center even when looking away from it.
        // Near terrain, use altitude so panning does not leap across the Moon.
        const depth=latest.current.orbital ? C.Cartesian3.magnitude(camera.position) : Math.max(500,camera.positionCartographic?.height ?? 500);
        const shift=panDistance(dx,dy,depth,(camera.frustum as Cesium.PerspectiveFrustum).fovy ?? NaN,viewer.scene.canvas.clientHeight);
        if (!shift) return;
        camera.moveRight(shift.right); camera.moveUp(shift.up);
        viewer.scene.requestRender();
      },
      look: (dx,dy) => {
        const height=viewer.scene.canvas.clientHeight;
        if (!Number.isFinite(dx) || !Number.isFinite(dy) || height<=0 || Math.abs(dx)>height || Math.abs(dy)>height) return;
        // Rotate the viewing basis, not the position: unrestricted local look,
        // without globe-pivot snapping or geographic pole clamping.
        viewer.camera.lookRight(-dx*Math.PI/height);
        viewer.camera.lookUp(dy*Math.PI/height);
        viewer.scene.requestRender();
      },
    });
    viewer.scene.screenSpaceCameraController.tiltEventTypes = [
      C.CameraEventType.RIGHT_DRAG,
      {
        eventType: C.CameraEventType.LEFT_DRAG,
        modifier: C.KeyboardEventModifier.CTRL,
      },
    ];
    viewer.scene.screenSpaceCameraController.zoomEventTypes = [
      C.CameraEventType.WHEEL,
      C.CameraEventType.PINCH,
    ];
    viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
      C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
    );
    const imagery: Record<string, Cesium.ImageryLayer> = {};
    C.SingleTileImageryProvider.fromUrl("/terrain/lroc_color_4k.jpg", {
      ellipsoid: moon,
      credit: "NASA SVS / LROC CGI Moon Kit · 4K visual context, not science radiometry",
    })
      .then((source) => {
        if (disposed) return;
        imagery.global = viewer.imageryLayers.addImageryProvider(source, 0);
        imagery.global.show = latest.current.layers.imagery;
        viewer.scene.requestRender();
      })
      .catch((error) => latest.current.onError(String(error)));
    for (const name of ["hillshade", "slope", "psr", "height_error"]) {
      if (name !== "hillshade") continue;
      const source = new C.UrlTemplateImageryProvider({
        url: `/api/terrain/${name}/{z}/{x}/{y}`,
        tilingScheme: tiling,
        rectangle: C.Rectangle.fromDegrees(
          -180,
          -90,
          180,
          name === "hillshade" ? -83 : -89.3,
        ),
        maximumLevel: 7,
        minimumLevel: 0,
        tileWidth: 256,
        tileHeight: 256,
        enablePickFeatures: false,
        credit: "NASA PGDA LOLA",
      });
      imagery[name] = viewer.imageryLayers.addImageryProvider(source);
      imagery[name].show = name === "hillshade";
    }
    const atlasRequested = new Set<string>();
    const loadAtlas = (name: string) => {
      if (atlasRequested.has(name)) return;
      atlasRequested.add(name);
      C.SingleTileImageryProvider.fromUrl(`/terrain/local-${name}.png`, {
        ellipsoid: moon,
        rectangle: C.Rectangle.fromDegrees(-180, -90, 180, -89.3),
        credit: "NASA PGDA · local polar atlas",
      })
        .then((source) => {
          if (disposed) return;
          const key = name === "hillshade" ? "localRelief" : name;
          imagery[key] = viewer.imageryLayers.addImageryProvider(source);
          for (const overlay of [
            "hillshade",
            "localRelief",
            "slope",
            "psr",
            "height_error",
          ]) {
            if (imagery[overlay])
              viewer.imageryLayers.raiseToTop(imagery[overlay]);
          }
          update(latest.current.sample, latest.current.layers);
        })
        .catch((error) => {
          atlasRequested.delete(name);
          if (!disposed) latest.current.onError(String(error));
        });
    };
    let site = C.Cartesian3.fromDegrees(
      latest.current.data.site.longitude_deg_east,
      latest.current.data.site.latitude_deg,
      latest.current.data.site.observer_altitude_above_reference_sphere_m,
      moon,
    );
    let enu = C.Transforms.eastNorthUpToFixedFrame(site, moon);
    const siteMarkers = new Map<string, Cesium.Entity>();
    const markerToSite = new Map<Cesium.Entity, string>();
    for (const entry of sites) {
      const selected = entry.id === latest.current.selectedSiteId;
      const marker = viewer.entities.add({
        id: `evaluated-site-${entry.id}`,
        position: selected
          ? site
          : C.Cartesian3.fromDegrees(
              entry.longitude_deg_east,
              entry.latitude_deg,
              0,
              moon,
            ),
        point: {
          pixelSize: selected ? 11 : 8,
          color: selected
            ? C.Color.WHITE
            : C.Color.fromCssColorString(
                entry.kind === "validation" ? "#f0c58a" : "#86c6d8",
              ),
          outlineColor: C.Color.fromCssColorString("#111820"),
          outlineWidth: selected ? 3 : 2,
          disableDepthTestDistance: Infinity,
        },
        label: {
          text: entry.name.toUpperCase(),
          font: "11px sans-serif",
          pixelOffset: new C.Cartesian2(0, -23),
          fillColor: C.Color.WHITE,
          showBackground: true,
          backgroundColor: C.Color.fromCssColorString("#10171ee6"),
          disableDepthTestDistance: Infinity,
          distanceDisplayCondition: new C.DistanceDisplayCondition(0, 500000),
        },
      });
      siteMarkers.set(entry.id, marker);
      markerToSite.set(marker, entry.id);
    }
    const celestial: Record<string, Cesium.Entity> = {};
    for (const name of ["sun", "earth"] as const) {
      celestial[name] = viewer.entities.add({
        name: name === "earth" ? "Earth · NASA Blue Marble · illustrative texture orientation" : "Sun · apparent disk",
        position: site, show: false,
        // Identity orientation is deliberately fixed in the lunar scene: no invented Earth attitude.
        orientation: C.Quaternion.IDENTITY,
        ellipsoid: { radii: new C.Cartesian3(1, 1, 1), stackPartitions: 64, slicePartitions: 64,
          material: new C.ImageMaterialProperty({ image: CELESTIAL_TEXTURES[name] }),
        },
      });
    }
    const sunlight = new C.DirectionalLight({direction: new C.Cartesian3(1,0,0), intensity: 2.2});
    viewer.scene.light = sunlight;
    const orbitScene=createOrbitalScene(C,viewer,celestial.earth);
    const selectSite = (selectedData: SimulationResult, siteId: string) => {
      if (disposed) return;
      site = C.Cartesian3.fromDegrees(
        selectedData.site.longitude_deg_east,
        selectedData.site.latitude_deg,
        selectedData.site.observer_altitude_above_reference_sphere_m,
        moon,
      );
      enu = C.Transforms.eastNorthUpToFixedFrame(site, moon);
      for (const entry of sites) {
        const marker = siteMarkers.get(entry.id);
        if (!marker?.point) continue;
        const selected = entry.id === siteId;
        marker.position = new C.ConstantPositionProperty(
          selected
            ? site
            : C.Cartesian3.fromDegrees(
                entry.longitude_deg_east,
                entry.latitude_deg,
                0,
                moon,
              ),
        );
        marker.point.pixelSize = new C.ConstantProperty(selected ? 11 : 8);
        marker.point.outlineWidth = new C.ConstantProperty(selected ? 3 : 2);
        marker.point.color = new C.ConstantProperty(
          selected
            ? C.Color.WHITE
            : C.Color.fromCssColorString(
                entry.kind === "validation" ? "#f0c58a" : "#86c6d8",
              ),
        );
      }
      viewer.scene.requestRender();
    };
    let picked: Cesium.Entity | undefined;
    let inspectSequence = 0;
    const inspect = async (point: Cesium.Cartesian3) => {
      const sequence = ++inspectSequence;
      const coord = moon.cartesianToCartographic(point);
      try {
        const response = await fetch(
          `/api/terrain/inspect?lon=${C.Math.toDegrees(coord.longitude)}&lat=${C.Math.toDegrees(coord.latitude)}`,
        );
        if (!response.ok) throw new Error("Terrain inspection unavailable");
        const result: Inspection = await response.json();
        if (disposed || sequence !== inspectSequence) return;
        if (picked) viewer.entities.remove(picked);
        picked = viewer.entities.add({
          position: C.Cartesian3.fromDegrees(
            result.longitude,
            result.latitude,
            result.elevation_m + 3,
            moon,
          ),
          point: {
            pixelSize: 9,
            color: C.Color.TRANSPARENT,
            outlineColor: C.Color.WHITE,
            outlineWidth: 2,
            disableDepthTestDistance: Infinity,
          },
        });
        latest.current.onInspect(result);
        viewer.scene.requestRender();
      } catch (error) {
        if (!disposed) latest.current.onError(String(error));
      }
    };
    viewer.screenSpaceEventHandler.setInputAction(
      (event: { position: Cesium.Cartesian2 }) => {
        if(latest.current.orbital) return;
        const selection = viewer.scene.pick(event.position);
        const selectedMarker = selection?.id as Cesium.Entity | undefined;
        const siteId = selectedMarker && markerToSite.get(selectedMarker);
        if (siteId) {
          latest.current.onSelectSite(siteId);
          return;
        }
        const ray = viewer.camera.getPickRay(event.position);
        const point = ray && viewer.scene.globe.pick(ray, viewer.scene);
        if (point) void inspect(point);
      },
      C.ScreenSpaceEventType.LEFT_CLICK,
    );
    viewer.screenSpaceEventHandler.setInputAction(
      (event: { position: Cesium.Cartesian2 }) => {
        if(latest.current.orbital) { orbitScene.focusAt(event.position,latest.current.orbital); return; }
        const cartographic = viewer.camera.positionCartographic;
        if (!cartographic || !Number.isFinite(cartographic.height)) return;
        const ray = viewer.camera.getPickRay(event.position);
        const point = ray && viewer.scene.globe.pick(ray, viewer.scene);
        if (point)
          viewer.camera.flyToBoundingSphere(new C.BoundingSphere(point, 0), {
            duration: flightDuration(1),
            offset: new C.HeadingPitchRange(
              viewer.camera.heading,
              -0.7,
              Math.max(500, cartographic.height * 0.4),
            ),
          });
      },
      C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
    );
    function direction(body: BodyState) {
      const az = C.Math.toRadians(body.azimuth_deg),
        el = C.Math.toRadians(body.elevation_deg);
      return C.Matrix4.multiplyByPointAsVector(
        enu,
        new C.Cartesian3(
          Math.cos(el) * Math.sin(az),
          Math.cos(el) * Math.cos(az),
          Math.sin(el),
        ),
        new C.Cartesian3(),
      );
    }
    const update = (current: SimulationSample, active: Layers) => {
      if (disposed) return;
      if(latest.current.orbital) {
        siteMarkers.forEach(marker=>{marker.show=false;});
        celestial.sun.show=false;
        orbitScene.update(latest.current.orbital);
        return;
      }
      if(orbitScene.leave()) fly("moon");
      viewer.scene.light=sunlight;
      // An invalid camera value must never enter an entity position or its
      // bounding volume; Cesium's frustum bucketing cannot render NaNs.
      const cartographic = viewer.camera.positionCartographic;
      if (!cartographic || !Number.isFinite(cartographic.height)) return;
      const altitude = cartographic.height;
      const testSiteOverlay = sites.find((entry) => entry.id === latest.current.selectedSiteId)?.kind === "validation";
      for (const siteMarker of siteMarkers.values())
        siteMarker.show = active.sites;
      if (imagery.global) imagery.global.show = active.imagery;
      imagery.hillshade.show =
        active.imagery && altitude < 300000;
      if (testSiteOverlay && active.imagery && altitude < 80000)
        loadAtlas("hillshade");
      if (testSiteOverlay && active.slope) loadAtlas("slope");
      if (testSiteOverlay && active.psr) loadAtlas("psr");
      if (testSiteOverlay && active.uncertainty) loadAtlas("height_error");
      if (imagery.localRelief)
        imagery.localRelief.show =
          testSiteOverlay && active.imagery && altitude < 80000;
      if (imagery.slope) imagery.slope.show = testSiteOverlay && active.slope;
      if (imagery.psr) imagery.psr.show = testSiteOverlay && active.psr;
      if (imagery.height_error) imagery.height_error.show = testSiteOverlay && active.uncertainty;
      if (viewer.terrainProvider !== (active.terrain ? provider : flat))
        viewer.terrainProvider = active.terrain ? provider : flat;
      for (const name of ["sun", "earth"] as const) {
        const body = current[name],
          vector = direction(body);
        const length = body.distance_km * 1000;
        const radius = celestialRadius(body.distance_km, body.angular_radius_deg);
        celestial[name].show = active[name] && radius !== null;
        if (radius === null) continue;
        const end = C.Cartesian3.add(
          site,
          C.Cartesian3.multiplyByScalar(vector, length, new C.Cartesian3()),
          new C.Cartesian3(),
        );
        celestial[name].position = new C.ConstantPositionProperty(end);
        celestial[name].ellipsoid!.radii = new C.ConstantProperty(new C.Cartesian3(radius, radius, radius));
      }
      viewer.scene.globe.enableLighting = active.illumination;
      viewer.shadows = active.illumination;
      sunlight.direction = C.Cartesian3.negate(
          direction(current.sun),
          new C.Cartesian3(),
        );
      viewer.scene.requestRender();
    };
    const flat = new C.EllipsoidTerrainProvider({ ellipsoid: moon });
    let skyMode = false;
    const fly = (mode: string) => {
      skyMode = mode === "sky";
      viewer.camera.cancelFlight();
      if (mode === "sky") {
        const current = latest.current.sample.earth;
        viewer.camera.flyTo({destination: C.Cartesian3.add(site, C.Matrix4.multiplyByPointAsVector(enu, new C.Cartesian3(0,0,30), new C.Cartesian3()), new C.Cartesian3()),
          orientation: {heading:C.Math.toRadians(current.azimuth_deg),pitch:C.Math.toRadians(current.elevation_deg),roll:0}, duration:flightDuration(1.5)});
        return;
      }
      if (mode === "moon")
        viewer.camera.flyTo({
          destination: C.Cartesian3.fromDegrees(10, -35, 6400000, moon),
          orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
          duration: flightDuration(1.5),
        });
      else
        viewer.camera.flyToBoundingSphere(new C.BoundingSphere(site, 0), {
          duration: flightDuration(mode === "site" ? 1.6 : 1.3),
          offset: new C.HeadingPitchRange(
            C.Math.toRadians(mode === "los" ? 155 : 25),
            C.Math.toRadians(
              mode === "pole" ? -80 : mode === "los" ? -22 : -48,
            ),
            mode === "pole" ? 180000 : mode === "los" ? 10000 : 14000,
          ),
        });
    };
    const finiteVector = (value: Cesium.Cartesian3) =>
      Number.isFinite(value.x) &&
      Number.isFinite(value.y) &&
      Number.isFinite(value.z);
    const resetCamera = () => {
      viewer.camera.cancelFlight();
      viewer.camera.setView({
        destination: C.Cartesian3.fromDegrees(
          latest.current.data.site.longitude_deg_east,
          latest.current.data.site.latitude_deg,
          latest.current.data.site.observer_altitude_above_reference_sphere_m + 12000,
          moon,
        ),
        orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
      });
      viewer.scene.requestRender();
    };
    const guardCamera = () => {
      const camera = viewer.camera;
      const cartographic = camera.positionCartographic;
      if (
        !cartographic ||
        !finiteVector(camera.positionWC) ||
        !finiteVector(camera.directionWC) ||
        !finiteVector(camera.upWC) ||
        !Number.isFinite(cartographic.height) ||
        !Number.isFinite(cartographic.longitude) ||
        !Number.isFinite(cartographic.latitude) ||
        !Number.isFinite(camera.frustum.near) ||
        !Number.isFinite(camera.frustum.far)
      ) {
        if(latest.current.orbital) orbitScene.recenter(latest.current.orbital);
        else resetCamera();
        return;
      }
      if(latest.current.orbital) return;
      const terrainHeight = viewer.scene.globe.getHeight(cartographic);
      const floor = Number.isFinite(terrainHeight)
        ? (terrainHeight as number) + (skyMode ? 20 : 500)
        : skyMode ? latest.current.data.site.observer_altitude_above_reference_sphere_m + 20 : 3000;
      if (cartographic.height < floor) {
        camera.setView({
          destination: C.Cartesian3.fromRadians(
            cartographic.longitude,
            cartographic.latitude,
            floor,
            moon,
          ),
          orientation: {
            heading: camera.heading,
            pitch: skyMode ? camera.pitch : Math.min(camera.pitch, -0.2),
            roll: 0,
          },
        });
      }
    };
    viewer.scene.preRender.addEventListener(guardCamera);
    let frames = 0,
      last = performance.now(),
      fps = 0;
    viewer.scene.postRender.addEventListener(() => {
      frames++;
    });
    const stats = window.setInterval(() => {
      const now = performance.now();
      fps = (frames * 1000) / (now - last);
      frames = 0;
      last = now;
      const camera = viewer.camera;
      const cartographic = camera.positionCartographic;
      if (!cartographic || !Number.isFinite(cartographic.height)) return;
      const center = new C.Cartesian2(
        viewer.canvas.clientWidth * 0.5,
        viewer.canvas.clientHeight * 0.5,
      );
      const ray1 = camera.getPickRay(center),
        ray2 = camera.getPickRay(new C.Cartesian2(center.x + 100, center.y));
      const p1 = ray1 && viewer.scene.globe.pick(ray1, viewer.scene),
        p2 = ray2 && viewer.scene.globe.pick(ray2, viewer.scene);
      latest.current.onStatus({
        // Presentation gate only: the camera is near and looking at this site.
        focusedSiteId: C.Cartesian3.distance(camera.positionWC, site) < 30000 &&
          p1 && C.Cartesian3.distance(p1, site) < 20000
          ? latest.current.selectedSiteId : undefined,
        altitude: cartographic.height,
        heading: C.Math.toDegrees(camera.heading),
        loaded,
        pending,
        fps,
        scale: p1 && p2 ? C.Cartesian3.distance(p1, p2) : 0,
      });
    }, 1000);
    viewer.camera.changed.addEventListener(() =>
      update(latest.current.sample, latest.current.layers),
    );
    viewer.scene.renderError.addEventListener((_scene: unknown, error: Error) =>
      latest.current.onRendererError(error.message),
    );
    viewer.camera.setView({
      destination: C.Cartesian3.fromDegrees(10, -35, 6400000, moon),
    });
    engine.current = { viewer, update, fly, selectSite };
    selectSite(latest.current.data, latest.current.selectedSiteId);
    update(latest.current.sample, latest.current.layers);
    if (pendingFlight.current.id > 0) fly(pendingFlight.current.mode);
    return () => {
      disposed = true;
      controller.abort();
      clearInterval(stats);
      removeTouchNavigation();
      viewer.scene.preRender.removeEventListener(guardCamera);
      engine.current = null;
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [ready, sites]);
  return (
    <>
      <Script
        src="/cesium/Cesium.js"
        strategy="afterInteractive"
        onReady={() => setReady(true)}
        onError={() => onError("Unable to load local Cesium runtime")}
      />
      <div
        className="lunar-canvas"
        ref={host}
        aria-label="Interactive 3D lunar terrain"
      />
      {!ready && <div className="map-loading">Opening the Moon…</div>}
      {ready && <div className="camera-gesture-control" role="group" aria-label="Touch camera controls">
        {(['pan','look'] as const).map(mode => <button key={mode} type="button" aria-pressed={navigationMode===mode} onClick={() => {
          navigationModeRef.current=mode; setNavigationMode(mode);
        }}>{mode==='pan' ? '↔ Pan' : '↻ Look 360°'}</button>)}
        <span>Drag to {navigationMode==='pan' ? 'move' : 'look'} · pinch to zoom</span>
      </div>}
    </>
  );
}
