import { cp, mkdir } from "node:fs/promises";
await mkdir(new URL("../public/cesium/", import.meta.url), { recursive: true });
await cp(
  new URL("../node_modules/cesium/Build/Cesium/", import.meta.url),
  new URL("../public/cesium/", import.meta.url),
  { recursive: true },
);
console.log("Local Cesium runtime and workers copied.");
