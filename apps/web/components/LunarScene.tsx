"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import type * as Cesium from "cesium";
import type { BodyState, SimulationResult, SimulationSample } from "./types";

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
};
declare global {
  interface Window {
    Cesium: typeof Cesium;
    CESIUM_BASE_URL: string;
  }
}

export default function LunarScene({
  data,
  sample,
  layers,
  flight,
  onInspect,
  onStatus,
  onError,
  onRendererError,
}: {
  data: SimulationResult;
  sample: SimulationSample;
  layers: Layers;
  flight: { mode: string; id: number };
  onInspect: (value: Inspection) => void;
  onStatus: (value: SceneStatus) => void;
  onError: (message: string) => void;
  onRendererError: (message: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<Engine | null>(null);
  const pendingFlight = useRef(flight);
  const latest = useRef({
    sample,
    layers,
    onInspect,
    onStatus,
    onError,
    onRendererError,
  });
  const [ready, setReady] = useState(false);
  useEffect(() => {
    latest.current = {
      sample,
      layers,
      onInspect,
      onStatus,
      onError,
      onRendererError,
    };
    engine.current?.update(sample, layers);
  }, [sample, layers, onInspect, onStatus, onError, onRendererError]);
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
      skyBox: false,
      skyAtmosphere: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
      contextOptions: { webgl: { alpha: false, antialias: true } },
      shadows: false,
    });
    viewer.resolutionScale = Math.min(1, 1.5 / window.devicePixelRatio);
    viewer.scene.backgroundColor = C.Color.fromCssColorString("#080b10");
    if (viewer.scene.sun) viewer.scene.sun.show = false;
    if (viewer.scene.moon) viewer.scene.moon.show = false;
    viewer.scene.fog.enabled = false;
    viewer.scene.globe.baseColor = C.Color.fromCssColorString("#878785");
    viewer.scene.globe.maximumScreenSpaceError = 5;
    viewer.scene.globe.tileCacheSize = 350;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.shadows = C.ShadowMode.ENABLED;
    viewer.shadowMap.maximumDistance = 25000;
    viewer.shadowMap.size = 2048;
    viewer.scene.screenSpaceCameraController.minimumZoomDistance = 500;
    viewer.scene.screenSpaceCameraController.maximumZoomDistance = 12000000;
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
    C.SingleTileImageryProvider.fromUrl("/terrain/lroc_color_2k.jpg", {
      ellipsoid: moon,
      credit: "NASA SVS / LROC CGI Moon Kit",
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
    const site = C.Cartesian3.fromDegrees(
      data.site.longitude_deg_east,
      data.site.latitude_deg,
      data.site.observer_altitude_above_reference_sphere_m,
      moon,
    );
    const enu = C.Transforms.eastNorthUpToFixedFrame(site, moon);
    const marker = viewer.entities.add({
      id: "test-site-a",
      position: site,
      point: {
        pixelSize: 11,
        color: C.Color.WHITE,
        outlineColor: C.Color.fromCssColorString("#111820"),
        outlineWidth: 3,
        disableDepthTestDistance: Infinity,
      },
      label: {
        text: "TEST SITE A",
        font: "12px sans-serif",
        pixelOffset: new C.Cartesian2(0, -25),
        fillColor: C.Color.WHITE,
        showBackground: true,
        backgroundColor: C.Color.fromCssColorString("#10171ee6"),
        disableDepthTestDistance: Infinity,
      },
    });
    const vectors: Record<
      string,
      { line: Cesium.Entity; endpoint: Cesium.Entity }
    > = {};
    for (const name of ["sun", "earth"]) {
      vectors[name] = {
        line: viewer.entities.add({
          polyline: {
            positions: [site, site],
            width: 2,
            arcType: C.ArcType.NONE,
            material: C.Color.WHITE,
          },
        }),
        endpoint: viewer.entities.add({
          position: site,
          point: {
            pixelSize: name === "sun" ? 17 : 14,
            color:
              name === "sun"
                ? C.Color.fromCssColorString("#e9bd73")
                : C.Color.fromCssColorString("#8bc2dc"),
            disableDepthTestDistance: Infinity,
          },
          label: {
            text: name.toUpperCase(),
            font: "12px sans-serif",
            pixelOffset: new C.Cartesian2(0, -26),
            fillColor: C.Color.WHITE,
            showBackground: true,
            backgroundColor: C.Color.fromCssColorString("#10171edd"),
            disableDepthTestDistance: Infinity,
          },
        }),
      };
    }
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
        const selection = viewer.scene.pick(event.position);
        if (selection?.id === marker) {
          void inspect(site);
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
        if (!Number.isFinite(viewer.camera.positionCartographic.height)) return;
        const ray = viewer.camera.getPickRay(event.position);
        const point = ray && viewer.scene.globe.pick(ray, viewer.scene);
        if (point)
          viewer.camera.flyToBoundingSphere(new C.BoundingSphere(point, 0), {
            duration: 1.8,
            offset: new C.HeadingPitchRange(
              viewer.camera.heading,
              -0.7,
              Math.max(500, viewer.camera.positionCartographic.height * 0.4),
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
      const altitude = viewer.camera.positionCartographic.height;
      // An invalid camera value must never enter an entity position or its
      // bounding volume; Cesium's frustum bucketing cannot render NaNs.
      if (!Number.isFinite(altitude)) return;
      marker.show = active.sites;
      if (imagery.global) imagery.global.show = active.imagery;
      imagery.hillshade.show =
        active.imagery && altitude < 300000;
      if (active.imagery && altitude < 80000)
        loadAtlas("hillshade");
      if (active.slope) loadAtlas("slope");
      if (active.psr) loadAtlas("psr");
      if (active.uncertainty) loadAtlas("height_error");
      if (imagery.localRelief)
        imagery.localRelief.show =
          active.imagery && altitude < 80000;
      if (imagery.slope) imagery.slope.show = active.slope;
      if (imagery.psr) imagery.psr.show = active.psr;
      if (imagery.height_error) imagery.height_error.show = active.uncertainty;
      if (viewer.terrainProvider !== (active.terrain ? provider : flat))
        viewer.terrainProvider = active.terrain ? provider : flat;
      for (const name of ["sun", "earth"] as const) {
        const body = current[name],
          vector = direction(body);
        const length = Math.max(
          200,
          Math.min(3000, altitude * 0.18),
        );
        const end = C.Cartesian3.add(
          site,
          C.Cartesian3.multiplyByScalar(vector, length, new C.Cartesian3()),
          new C.Cartesian3(),
        );
        const visible = active[name] && altitude < 100000;
        vectors[name].line.show = visible;
        vectors[name].endpoint.show = visible;
        const color = C.Color.fromCssColorString(
          body.state === "BLOCKED"
            ? "#c87975"
            : name === "sun"
              ? "#e9bd73"
              : "#8bc2dc",
        );
        vectors[name].line.polyline!.positions = new C.ConstantProperty([
          site,
          end,
        ]);
        vectors[name].line.polyline!.material =
          body.state === "FULLY_VISIBLE"
            ? new C.ColorMaterialProperty(color)
            : new C.PolylineDashMaterialProperty({ color, dashLength: 14 });
        vectors[name].endpoint.position = new C.ConstantPositionProperty(end);
        vectors[name].endpoint.label!.text = new C.ConstantProperty(
          `${name.toUpperCase()} · ${body.state === "FULLY_VISIBLE" ? "CLEAR" : body.state === "BLOCKED" ? "BLOCKED" : "PARTIAL"}`,
        );
      }
      viewer.scene.globe.enableLighting = active.illumination;
      viewer.shadows = active.illumination;
      viewer.scene.light = new C.DirectionalLight({
        direction: C.Cartesian3.negate(
          direction(current.sun),
          new C.Cartesian3(),
        ),
        intensity: 2.2,
      });
      viewer.scene.requestRender();
    };
    const flat = new C.EllipsoidTerrainProvider({ ellipsoid: moon });
    const fly = (mode: string) => {
      viewer.camera.cancelFlight();
      if (mode === "moon")
        viewer.camera.flyTo({
          destination: C.Cartesian3.fromDegrees(10, -45, 8000000, moon),
          orientation: { heading: 0, pitch: -Math.PI / 2, roll: 0 },
          duration: 2.5,
        });
      else
        viewer.camera.flyToBoundingSphere(new C.BoundingSphere(site, 0), {
          duration: mode === "site" ? 3 : 2.2,
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
          data.site.longitude_deg_east,
          data.site.latitude_deg,
          data.site.observer_altitude_above_reference_sphere_m + 12000,
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
        !finiteVector(camera.positionWC) ||
        !finiteVector(camera.directionWC) ||
        !finiteVector(camera.upWC) ||
        !Number.isFinite(cartographic.height) ||
        !Number.isFinite(cartographic.longitude) ||
        !Number.isFinite(cartographic.latitude) ||
        !Number.isFinite(camera.frustum.near) ||
        !Number.isFinite(camera.frustum.far)
      ) {
        resetCamera();
        return;
      }
      const terrainHeight = viewer.scene.globe.getHeight(cartographic);
      const floor = Number.isFinite(terrainHeight)
        ? (terrainHeight as number) + 500
        : 3000;
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
            pitch: Math.min(camera.pitch, -0.2),
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
      if (!Number.isFinite(camera.positionCartographic.height)) return;
      const center = new C.Cartesian2(
        viewer.canvas.clientWidth * 0.5,
        viewer.canvas.clientHeight * 0.5,
      );
      const ray1 = camera.getPickRay(center),
        ray2 = camera.getPickRay(new C.Cartesian2(center.x + 100, center.y));
      const p1 = ray1 && viewer.scene.globe.pick(ray1, viewer.scene),
        p2 = ray2 && viewer.scene.globe.pick(ray2, viewer.scene);
      latest.current.onStatus({
        altitude: camera.positionCartographic.height,
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
      destination: C.Cartesian3.fromDegrees(10, -60, 8000000, moon),
    });
    engine.current = { viewer, update, fly };
    update(latest.current.sample, latest.current.layers);
    if (pendingFlight.current.id > 0) fly(pendingFlight.current.mode);
    return () => {
      disposed = true;
      controller.abort();
      clearInterval(stats);
      viewer.scene.preRender.removeEventListener(guardCamera);
      engine.current = null;
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [ready, data]);
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
    </>
  );
}
