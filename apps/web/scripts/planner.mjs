import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const webRoot = fileURLToPath(new URL("../", import.meta.url));
const terrain = spawn(
  `${root}/.venv/bin/python`,
  ["scripts/terrain_server.py"],
  { cwd: root, stdio: "inherit" },
);
let web;
let shuttingDown = false;

function shutdown(signal = "SIGTERM") {
  shuttingDown = true;
  if (terrain.exitCode === null) terrain.kill(signal);
  if (web?.exitCode === null) web.kill(signal);
}

for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => shutdown(signal));

terrain.on("error", (error) => {
  console.error("Unable to start local terrain service:", error);
  shutdown();
  process.exitCode = 1;
});
terrain.on("exit", (code) => {
  if (!shuttingDown) {
    console.error(`Local terrain service exited (${code ?? "signal"})`);
    shutdown();
    process.exitCode = code || 1;
  }
});

async function waitForTerrain() {
  // The web page requests an inspection immediately. Start Next only after
  // its terrain dependency responds, so opening the page cannot race startup.
  for (let attempt = 0; attempt < 100; attempt++) {
    if (terrain.exitCode !== null) throw new Error("Terrain service exited");
    try {
      const response = await fetch("http://127.0.0.1:8766/health", {
        signal: AbortSignal.timeout(500),
      });
      if (response.ok) return;
    } catch {
      // The Python service is still loading its verified terrain arrays.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("Terrain service did not become ready within 10 seconds");
}

try {
  await waitForTerrain();
  if (!shuttingDown) {
    web = spawn(
      process.execPath,
      [
        "node_modules/next/dist/bin/next",
        process.argv.includes("--production") ? "start" : "dev",
        "--hostname",
        process.env.PLANNER_HOST || "127.0.0.1",
      ],
      { cwd: webRoot, stdio: "inherit" },
    );
    web.on("error", (error) => {
      console.error("Unable to start planner web server:", error);
      shutdown();
      process.exitCode = 1;
    });
    web.on("exit", (code) => {
      if (!shuttingDown) {
        shutdown();
        process.exitCode = code || 1;
      }
    });
  }
} catch (error) {
  console.error(error);
  shutdown();
  process.exitCode = 1;
}
