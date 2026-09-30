import { execFileSync, spawn } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL("../", import.meta.url));
const runtime = fileURLToPath(new URL("../.runtime/", import.meta.url));
const pidFile = `${runtime}/planner.pid`;
const logFile = `${runtime}/planner.log`;
const action = process.argv[2] || "start";

function trackedPid() {
  if (!existsSync(pidFile)) return null;
  const pid = Number(readFileSync(pidFile, "utf8"));
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  try {
    const command = execFileSync("ps", ["-p", String(pid), "-o", "command="], {
      encoding: "utf8",
    });
    return command.includes("scripts/planner.mjs --production") ? pid : null;
  } catch {
    return null;
  }
}

async function healthy() {
  try {
    const [page, terrain] = await Promise.all([
      fetch("http://127.0.0.1:3000/", {
        signal: AbortSignal.timeout(1000),
      }),
      fetch("http://127.0.0.1:3000/api/terrain/health", {
        signal: AbortSignal.timeout(1000),
      }),
    ]);
    return page.ok && terrain.ok && (await terrain.json()).status === "ok";
  } catch {
    return false;
  }
}

if (action === "status") {
  const pid = trackedPid();
  console.log(
    (await healthy())
      ? `Planner ready at http://127.0.0.1:3000/${pid ? ` (PID ${pid})` : ""}`
      : "Planner is not ready",
  );
} else if (action === "stop") {
  const pid = trackedPid();
  if (!pid) {
    console.error("No owned background planner process found; nothing stopped.");
    process.exitCode = 1;
  } else {
    process.kill(pid, "SIGTERM");
    unlinkSync(pidFile);
    console.log(`Stopped background planner PID ${pid}`);
  }
} else if (action === "start") {
  const pid = trackedPid();
  if (pid && (await healthy())) {
    console.log(`Planner already ready at http://127.0.0.1:3000/ (PID ${pid})`);
  } else if (pid) {
    console.error(`Owned planner PID ${pid} is running but not healthy. See ${logFile}`);
    process.exitCode = 1;
  } else if (await healthy()) {
    console.log("Planner already ready at http://127.0.0.1:3000/");
  } else {
    mkdirSync(runtime, { recursive: true });
    const log = openSync(logFile, "a");
    const child = spawn(
      process.execPath,
      ["scripts/planner.mjs", "--production"],
      { cwd: webRoot, detached: true, stdio: ["ignore", log, log] },
    );
    closeSync(log);
    if (!child.pid) throw new Error("Could not launch background planner");
    writeFileSync(pidFile, `${child.pid}\n`);
    child.unref();
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await healthy()) {
        ready = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    if (ready) {
      console.log(`Planner ready at http://127.0.0.1:3000/ (PID ${child.pid})`);
    } else {
      console.error(`Planner did not become ready. See ${logFile}`);
      process.exitCode = 1;
    }
  }
} else {
  console.error("Usage: node scripts/planner-service.mjs [start|status|stop]");
  process.exitCode = 2;
}
