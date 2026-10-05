"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { HorizonChart } from "./HorizonChart";
import { Timeline } from "./Timeline";
import { OrbitalControls, useOrbitalData } from "./OrbitalControls";
import type { OrbitalFocus, OrbitalMode } from "./orbitalData";
import type {
  BodyState,
  IndexedSite,
  SimulationIndex,
  SimulationResult,
} from "./types";
import type { Inspection, Layers, SceneStatus } from "./LunarScene";
import "./planner.css";
import "./mobile.css";
import "cesium/Build/Cesium/Widgets/widgets.css";

const LunarScene = dynamic(() => import("./LunarScene"), { ssr: false });
const MoonExperience = dynamic(() => import("./MoonExperience").then(m=>m.MoonExperience), { ssr:false });
const SpacecraftStudy = dynamic(() => import("./SpacecraftStudy").then((module) => module.SpacecraftStudy), { ssr: false });
const LocalTerrainStudy = dynamic(() => import("./LocalTerrainStudy").then((module) => module.LocalTerrainStudy), { ssr: false });
const ExperimentalTerrainGauges = dynamic(() => import("./ExperimentalTerrainGauges").then((module) => module.ExperimentalTerrainGauges), { ssr: false, loading: () => <p>Unknown · loading experimental terrain</p> });
const initialLayers: Layers = {
  terrain: true,
  imagery: true,
  sites: true,
  sun: true,
  earth: true,
  illumination: false,
  slope: false,
  psr: false,
  uncertainty: false,
};
const stateName = (body: BodyState) =>
  body.state === "FULLY_VISIBLE"
    ? "Clear"
    : body.state === "PARTIALLY_VISIBLE"
      ? "Partial"
      : "Blocked";
function duration(seconds: number) {
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
function clock(iso: string) {
  return iso.slice(11, 16) + " UTC";
}
function coordinate(value: number, latitude: boolean) {
  const direction = latitude
    ? value < 0 ? "S" : "N"
    : value < 0 ? "W" : "E";
  return `${Math.abs(value).toFixed(4)}° ${direction}`;
}
function dateLabel(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).toUpperCase();
}
const powerScenarioOptions = [
  ["fixed_tilt_80_north", "Fixed 80° tilt · north"],
  ["fixed_vertical_north", "Fixed vertical · north"],
  ["limited_gimbal", "Limited gimbal"],
  ["ideal_tracking", "Ideal sun tracking"],
] as const;
const commsLabels = {
  BLOCKED: "Blocked",
  MARGINAL: "Marginal geometry",
  CLEAR: "Center LOS clear",
} as const;
const commsClearanceToleranceDeg = 5e-8;
function validCommsPotential(sample: SimulationResult["samples"][number]) {
  const comms = sample.comms_potential;
  const earth = sample.earth;
  if (!comms || comms.model !== "earth_center_terrain_clearance_v1" ||
      comms.low_elevation_threshold_deg !== 2 ||
      !Number.isFinite(earth.elevation_deg) ||
      !Number.isFinite(earth.terrain_horizon_deg) ||
      !Number.isFinite(earth.clearance_deg) ||
      !Number.isFinite(earth.visibility_fraction) ||
      earth.visibility_fraction < 0 || earth.visibility_fraction > 1 ||
      Math.abs(earth.elevation_deg - earth.terrain_horizon_deg - earth.clearance_deg) > commsClearanceToleranceDeg)
    return false;
  const centerClear = earth.clearance_deg > 0;
  const expectedClassification = !centerClear
    ? "BLOCKED"
    : earth.elevation_deg <= comms.low_elevation_threshold_deg ? "MARGINAL" : "CLEAR";
  const expectedIndex = !centerClear ? 0 : expectedClassification === "MARGINAL" ? 30 : 100;
  return comms.center_clear === centerClear &&
    comms.classification === expectedClassification &&
    comms.potential_index_percent === expectedIndex;
}
function validateIndex(value: unknown): SimulationIndex {
  if (!value || typeof value !== "object")
    throw new Error("Candidate simulation index is invalid");
  const index = value as SimulationIndex;
  if (index.schema_version !== "1.0.0" || !Array.isArray(index.sites))
    throw new Error("Candidate simulation index contract is missing");
  const candidateCount = index.sites.filter((site) => site.kind === "candidate").length;
  if (candidateCount < 3 || candidateCount > 5 ||
      index.sites.filter((site) => site.kind === "validation").length !== 1)
    throw new Error("Expected Test Site A and three to five evaluated candidate sites");
  const ids = new Set<string>();
  for (const site of index.sites) {
    if (!/^[a-z0-9-]+$/.test(site.id) || ids.has(site.id) ||
        !site.name ||
        !["candidate", "validation"].includes(site.kind) ||
        !Number.isFinite(site.latitude_deg) ||
        !Number.isFinite(site.longitude_deg_east) ||
        Math.abs(site.latitude_deg) > 90 ||
        Math.abs(site.longitude_deg_east) > 360 ||
        !Number.isFinite(site.summary?.sunlight_percentage) ||
        !Number.isFinite(site.summary?.earth_visible_percentage) ||
        (site.kind === "candidate" && !site.coordinate_source_url) ||
        !/^\/data\/[a-z0-9-]+\.json$/i.test(site.data_url) ||
        !/^[a-f0-9]{64}$/i.test(site.sha256))
      throw new Error(`Invalid candidate index entry: ${site.id || "unnamed"}`);
    ids.add(site.id);
  }
  return index;
}
async function loadSimulation(site: IndexedSite, signal: AbortSignal) {
  const response = await fetch(site.data_url, { signal });
  if (!response.ok) throw new Error(`${site.name}: simulation export unavailable (${response.status})`);
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (hash !== site.sha256.toLowerCase())
    throw new Error(`${site.name}: simulation SHA-256 does not match the index`);
  const result = JSON.parse(new TextDecoder().decode(bytes)) as SimulationResult;
  if (result.schema_version !== "1.3.0" ||
      result.validation?.independent_spice?.status !== "PASS" ||
      result.provenance_contract?.validator_used_for_operational_samples !== false ||
      result.samples?.length !== 1009 ||
      result.time_range?.sample_count !== result.samples.length ||
      result.horizon?.profile?.length !== 720 ||
      result.horizon_mask?.profile?.length !== 360 ||
      !result.panel_scenarios ||
      !result.samples.every((sample) =>
        validCommsPotential(sample) &&
        powerScenarioOptions.every(([key]) => {
          const power = sample.power_scenarios?.[key];
          return power &&
            Number.isFinite(power.incidence_cosine) &&
            Number.isFinite(power.estimated_electrical_output_w);
        })) ||
      Math.abs(result.site.latitude_deg - site.latitude_deg) > 0.000001 ||
      Math.abs(result.site.longitude_deg_east - site.longitude_deg_east) > 0.000001)
    throw new Error(`${site.name}: validated simulation contract is missing or coordinates disagree`);
  return result;
}
interface Manifest {
  sources: Array<{
    name: string;
    resolution_m: number;
    source_url: string;
    sha256: string;
  }>;
  imagery: { source_url: string };
  frame: string;
}

export function MissionPlanner() {
  const [data, setData] = useState<SimulationResult | null>(null);
  const [siteIndex, setSiteIndex] = useState<SimulationIndex | null>(null);
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [loadingSiteId, setLoadingSiteId] = useState("");
  const [powerScenario, setPowerScenario] = useState<string>("fixed_tilt_80_north");
  const [spacecraftOpen, setSpacecraftOpen] = useState(false);
  const [localTerrainOpen, setLocalTerrainOpen] = useState(false);
  const [terrainModel, setTerrainModel] = useState("baseline");
  const [mobileSheet, setMobileSheet] = useState("map");
  const [instruments, setInstruments] = useState(false);
  const dataCache = useRef(new Map<string, Promise<SimulationResult>>());
  const lifetimeController = useRef<AbortController | null>(null);
  const selectionSequence = useRef(0);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState("");
  const [rendererKey, setRendererKey] = useState(0);
  const rendererRestarts = useRef(0);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1000);
  const [layers, setLayers] = useState(initialLayers);
  const [flight, setFlight] = useState({ mode: "moon", id: 0 });
  const [orbitalOpen,setOrbitalOpen]=useState(false);
  const orbitalMode: OrbitalMode = "overview";
  const orbitalFocus: OrbitalFocus = "moon";
  const [orbitalRevision,setOrbitalRevision]=useState(0);
  const orbitalResource=useOrbitalData(orbitalOpen);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [siteInfo, setSiteInfo] = useState<Inspection | null>(null);
  const [status, setStatus] = useState<SceneStatus>({
    altitude: 8000000,
    heading: 0,
    loaded: 0,
    pending: 0,
    fps: 0,
    scale: 0,
  });
  const [panel, setPanel] = useState<"none" | "horizon" | "data">("none");
  const [query, setQuery] = useState("");
  const [help, setHelp] = useState(false);
  const remainder = useRef(0);
  const selectedKind = siteIndex?.sites.find((site) => site.id === selectedSiteId)?.kind;
  const sceneLayers = useMemo(
    () => selectedKind === "validation"
      ? layers
      : { ...layers, slope: false, psr: false, uncertainty: false },
    [layers, selectedKind],
  );
  const ended = !!data && index >= data.samples.length - 1;
  const running = playing && !ended;
  const loadSite = useCallback((site: IndexedSite) => {
    const existing = dataCache.current.get(site.id);
    if (existing) return existing;
    const controller = lifetimeController.current;
    if (!controller) return Promise.reject(new Error("Simulation loader is not ready"));
    const pending = loadSimulation(site, controller.signal).catch((error) => {
      if (dataCache.current.get(site.id) === pending)
        dataCache.current.delete(site.id);
      throw error;
    });
    dataCache.current.set(site.id, pending);
    return pending;
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const cache = dataCache.current;
    lifetimeController.current = controller;
    Promise.all([
      fetch("/data/simulation-index.json", { signal: controller.signal }).then(
        (r) => {
          if (!r.ok) throw new Error("Candidate simulation index unavailable; run the candidate precomputation");
          return r.json();
        },
      ),
      fetch("/terrain/manifest.json", { signal: controller.signal }).then(
        (r) => {
          if (!r.ok) throw new Error("Run terrain preprocessing first");
          return r.json();
        },
      ),
    ])
      .then(async ([rawIndex, sources]) => {
        const indexFile = validateIndex(rawIndex);
        const initialSite = indexFile.sites.find((site) => site.kind === "validation")!;
        const result = await loadSite(initialSite);
        if (controller.signal.aborted) return;
        setData(result);
        setSiteIndex(indexFile);
        setSelectedSiteId(initialSite.id);
        setManifest(sources);
        // Avoid decoding four unused multi-megabyte exports on phones.
        if (!window.matchMedia("(max-width: 950px)").matches) {
          for (const site of indexFile.sites) {
            if (site.id !== initialSite.id) void loadSite(site).catch(() => {});
          }
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => {
      controller.abort();
      cache.clear();
      lifetimeController.current = null;
    };
  }, [loadSite]);
  useEffect(() => {
    if (!data) return;
    const controller = new AbortController();
    fetch(`/api/terrain/inspect?lon=${encodeURIComponent(data.site.longitude_deg_east)}&lat=${encodeURIComponent(data.site.latitude_deg)}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok)
          throw new Error("Terrain service unavailable; start npm run planner");
        return r.json();
      })
      .then(setSiteInfo)
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => controller.abort();
  }, [data]);
  useEffect(() => {
    if (!playing || !data || ended) return;
    let previous = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      remainder.current += ((now - previous) / 1000) * speed;
      previous = now;
      const steps = Math.floor(remainder.current / 600);
      if (steps) {
        remainder.current %= 600;
        setIndex((current) =>
          Math.min(data.samples.length - 1, current + steps),
        );
      }
    }, 100);
    return () => clearInterval(timer);
  }, [playing, speed, data, ended]);
  const inspect = useCallback((value: Inspection) => setInspection(value), []);
  const report = useCallback((value: SceneStatus) => setStatus(value), []);
  const failure = useCallback((value: string) => {
    setError(
      value.includes("Failed to fetch")
        ? "Local planner connection lost. Restart the background planner, then retry this view."
        : value,
    );
  }, []);
  const rendererFailure = useCallback((value: string) => {
    if (rendererRestarts.current < 1) {
      rendererRestarts.current++;
      setRendererKey((current) => current + 1);
      return;
    }
    setError(`3D rendering stopped: ${value}`);
  }, []);
  const restartRenderer = () => {
    rendererRestarts.current = 0;
    setError("");
    setRendererKey((current) => current + 1);
  };
  const fly = (mode: string) =>
    setFlight((current) => ({ mode, id: current.id + 1 }));
  const selectSite = useCallback(async (siteId: string) => {
    const selected = siteIndex?.sites.find((site) => site.id === siteId);
    if (!selected) return;
    if (siteId === selectedSiteId) {
      setFlight((current) => ({ mode: "site", id: current.id + 1 }));
      return;
    }
    const sequence = ++selectionSequence.current;
    setLoadingSiteId(siteId);
    setError("");
    try {
      const result = await loadSite(selected);
      if (sequence !== selectionSequence.current ||
          !lifetimeController.current || lifetimeController.current.signal.aborted) return;
      setData(result);
      setSelectedSiteId(siteId);
      setIndex((current) => Math.min(current, result.samples.length - 1));
      remainder.current = 0;
      setPlaying(false);
      setInspection(null);
      setSiteInfo(null);
      setFlight((current) => ({ mode: "site", id: current.id + 1 }));
    } catch (error) {
      if (sequence === selectionSequence.current && lifetimeController.current &&
          !lifetimeController.current.signal.aborted)
        setError(String(error));
    } finally {
      if (sequence === selectionSequence.current && lifetimeController.current &&
          !lifetimeController.current.signal.aborted) setLoadingSiteId("");
    }
  }, [loadSite, selectedSiteId, siteIndex]);
  const scrub = (next: number) => {
    setIndex(next);
    remainder.current = 0;
  };
  if (!data || !siteIndex)
    return (
      <main className="planner-loading">
        <span className="mission-kicker">LUNAR / MISSION PLANNER</span>
        <h1>Opening the Moon</h1>
        <p>
          {error || "Loading the validated site array and NASA terrain catalogue…"}
        </p>
      </main>
    );
  const sample = data.samples[index];
  const comms = sample.comms_potential;
  const partialDiskWithClearCenter = comms.classification === "CLEAR" && sample.earth.visibility_fraction < 1;
  const commsDisplayLabel = partialDiskWithClearCenter
    ? "Center clear · disk partial"
    : commsLabels[comms.classification];
  const selectedEntry = siteIndex.sites.find((site) => site.id === selectedSiteId)!;
  const selectedPower = sample.power_scenarios?.[powerScenario] ?? sample.power;
  const selectedPowerLabel = powerScenarioOptions.find(([key]) => key === powerScenario)?.[1] ?? "Ideal sun tracking";
  const now = Date.parse(sample.timestamp);
  const next = data.samples
    .slice(index + 1)
    .find((s) => s.sun.state !== sample.sun.state ||
      s.earth.state !== sample.earth.state ||
      s.comms_potential.classification !== comms.classification);
  const dte = data.windows.earth.dte_visible.intervals.find(
    (w) => Date.parse(w.start_utc) <= now && Date.parse(w.end_utc) > now,
  );
  const blackout = data.windows.earth.dte_blackout.intervals.find(
    (w) => Date.parse(w.start_utc) > now,
  );
  const available = (name: string) =>
    selectedEntry.kind === "validation" &&
    !!manifest?.sources.some((s) => s.name === name);
  const toggle = (key: keyof Layers) =>
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  return (
    <main className={`mission-planner ${instruments ? "instruments-mode" : "map-experience"} ${orbitalOpen ? "orbital-active" : ""}`} data-mobile-sheet={mobileSheet}>
      <div style={{display:orbitalOpen || instruments ? "none":"contents"}}><MoonExperience sites={siteIndex.sites} selected={selectedEntry} onSelect={selectSite}
        epoch={index} onEpoch={next=>{setPlaying(false);scrub(next);}} loadSimulation={loadSimulation}
        focused={status.focusedSiteId === selectedEntry.id && flight.mode !== "moon"}
        viewKey={`${selectedEntry.id}:${flight.id}`}
        onGlobe={()=>fly("moon")} onSky={()=>fly("sky")} onDetails={()=>{setInstruments(true);setMobileSheet("gauges");}}/></div>
      {!orbitalOpen && !instruments && <button className="orbit-launch" onClick={()=>{setPlaying(false);setOrbitalOpen(true);setOrbitalRevision(n=>n+1);}}>◌ Orbital view</button>}
      {orbitalOpen && <OrbitalControls data={orbitalResource.data} error={orbitalResource.error}
        epoch={index} playing={playing && !ended} onPlay={()=>{if(ended){scrub(0);setPlaying(true);}else setPlaying(p=>!p);}} onEpoch={n=>{setPlaying(false);scrub(n);}}
        onClose={()=>{setOrbitalOpen(false);setPlaying(false);fly("moon");}}/>}
      {instruments && <button className="return-explorer" onClick={()=>{setInstruments(false);setPanel("none");setSpacecraftOpen(false);setLocalTerrainOpen(false);}}>← Moon explorer</button>}
      <nav className="mobile-navigation" aria-label="Mobile planner views">
        {(["map", "sites", "gauges", "time", "tools"] as const).map((view) =>
          <button key={view} aria-pressed={mobileSheet === view}
            aria-controls={view === "map" ? undefined : `planner-${view}`}
            onClick={() => {
              setMobileSheet((current) => current === view ? "map" : view);
              setSpacecraftOpen(false); setLocalTerrainOpen(false); setPanel("none"); setHelp(false);
            }}>{view === "map" ? "Globe" : view[0].toUpperCase() + view.slice(1)}</button>)}
      </nav>
      <LunarScene
        orbital={orbitalOpen && orbitalResource.data ? {data:orbitalResource.data,epoch:index,mode:orbitalMode,focus:orbitalFocus,revision:orbitalRevision} : null}
        key={rendererKey}
        data={data}
        sites={siteIndex.sites}
        selectedSiteId={selectedSiteId}
        sample={sample}
        layers={sceneLayers}
        flight={flight}
        onInspect={inspect}
        onStatus={report}
        onError={failure}
        onRendererError={rendererFailure}
        onSelectSite={selectSite}
      />
      <header className="planner-header">
        <div className="planner-brand">
          <span className="moon-glyph">◒</span>
          <div>
            <span className="mission-kicker">SURFACE OPERATIONS / 01</span>
            <h1>Lunar mission planner</h1>
          </div>
        </div>
        <div className="header-center">
          <i />
          NASA / JPL DATA <span>SPICE VERIFIED</span>
        </div>
        <div className="header-actions" id="planner-tools" onClick={() => setMobileSheet("map")}>
          <button onClick={() => {setLocalTerrainOpen((open)=>!open); setSpacecraftOpen(false);}} aria-expanded={localTerrainOpen} aria-controls="local-terrain-study">Native terrain</button>
          <button onClick={() => {setSpacecraftOpen((open) => !open); setLocalTerrainOpen(false);}} aria-expanded={spacecraftOpen} aria-controls="spacecraft-study">
            Spacecraft lab
          </button>
          <button onClick={() => setPanel(panel === "data" ? "none" : "data")}>
            Data & methodology
          </button>
          <button
            className="help-button"
            aria-label="Navigation help"
            onClick={() => setHelp(!help)}
          >
            ?
          </button>
        </div>
      </header>
      <aside className="map-sidebar" id="planner-sites" aria-label="Sites and map layers">
        <span className="mission-kicker">EXPLORE THE SOUTH POLE</span>
        <label className="site-search">
          <span>⌕</span>
          <input
            aria-label="Search sites"
            placeholder="Find a site or region"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {siteIndex.sites.filter((site) =>
          `${site.name} ${site.kind}`.toLowerCase().includes(query.trim().toLowerCase()),
        ).map((site) => (
          <button
            key={site.id}
            className={`site-option ${site.id === selectedSiteId ? "selected" : ""}`}
            aria-current={site.id === selectedSiteId ? "true" : undefined}
            aria-busy={site.id === loadingSiteId}
            onClick={() => void selectSite(site.id)}
          >
            <span className="site-pin">{site.kind === "validation" ? "◎" : "◉"}</span>
            <span>
              <strong>{site.name}</strong>
              <small>{coordinate(site.latitude_deg, true)} · {coordinate(site.longitude_deg_east, false)}</small>
              <small>{site.kind === "validation"
                ? "Pipeline validation point"
                : site.region_status === "historical_2022_cohort"
                  ? "Historical NASA candidate region · evaluated point"
                  : "NASA candidate region · evaluated point"}</small>
              <small>LOLA baseline · Sun {site.summary.sunlight_percentage.toFixed(1)}% · Earth {site.summary.earth_visible_percentage.toFixed(1)}%</small>
            </span>
            <span>{site.id === loadingSiteId ? "…" : "↗"}</span>
          </button>
        ))}
        {!siteIndex.sites.some((site) =>
          `${site.name} ${site.kind}`.toLowerCase().includes(query.trim().toLowerCase()),
        ) && (
          <p className="empty-sites">
            No matching evaluated site.
          </p>
        )}
        <div className="view-presets">
          <button onClick={() => fly("moon")}>Moon</button>
          <button onClick={() => fly("pole")}>South pole</button>
          <button onClick={() => fly("site")}>Site</button>
        </div>
        <div className="layer-heading">
          <span className="mission-kicker">MAP LAYERS</span>
          <span>{Object.values(sceneLayers).filter(Boolean).length} active</span>
        </div>
        {(
          [
            [
              "SURFACE",
              [
                ["imagery", "Lunar imagery / relief", true],
                ["terrain", "LOLA elevation", true],
                ["sites", "Evaluated sites", true],
              ],
            ],
            [
              "MISSION",
              [
                ["sun", "Sun direction", true],
                ["earth", "Earth direction", true],
                ["illumination", "Sun-driven lighting", true],
              ],
            ],
            [
              "ENGINEERING",
              [
                ["slope", "Slope", available("slope")],
                [
                  "uncertainty",
                  "Height uncertainty",
                  available("height_error"),
                ],
              ],
            ],
            ["SCIENCE", [["psr", "Permanent shadow", available("psr")]]],
          ] as Array<[string, Array<[keyof Layers, string, boolean]>]>
        ).map(([group, items]) => (
          <section className="layer-group" key={group}>
            <h2>{group}</h2>
            {items.map(([key, title, enabled]) => (
              <label
                className={`layer-control ${!enabled ? "disabled" : ""}`}
                key={key}
              >
                <input
                  type="checkbox"
                  checked={enabled && layers[key]}
                  disabled={!enabled}
                  onChange={() => toggle(key)}
                />
                <span>{title}</span>
                {!enabled && <small>{selectedEntry.kind === "validation" ? "Not loaded" : "Test Site A coverage only"}</small>}
              </label>
            ))}
          </section>
        ))}
        <label className="layer-control disabled resource">
          <input type="checkbox" disabled />
          <span>
            Resource evidence<small>Dataset not loaded</small>
          </span>
        </label>
        {sceneLayers.slope && (
          <div className="layer-legend">
            <span>Slope · degrees</span>
            <div className="slope-ramp" />
            <div className="legend-values">
              <span>0</span>
              <span>5</span>
              <span>10</span>
              <span>20+</span>
            </div>
            <small>NASA 20 m product · no safety threshold</small>
          </div>
        )}
        {sceneLayers.psr && (
          <p className="layer-note">
            PSR describes long-term shadow. It does not establish a water-ice
            deposit.
          </p>
        )}
        {sceneLayers.uncertainty && (
          <div className="layer-legend">
            <span>Height uncertainty · metres</span>
            <div className="slope-ramp" />
            <div className="legend-values">
              <span>0</span>
              <span>1.25</span>
              <span>2.5</span>
              <span>5+</span>
            </div>
          </div>
        )}
        <div className="sidebar-foot">
          <i /> REAL TERRAIN · TRUE SCALE
          <small>1737.4 km lunar reference sphere · thematic overlays cover Test Site A only</small>
        </div>
      </aside>
      <div className="map-title">
        <span className="mission-kicker">
          {status.altitude > 500000
            ? "THE MOON"
            : status.altitude > 50000
              ? "LUNAR SOUTH POLE"
              : `${data.site.name.toUpperCase()} / SURFACE`}
        </span>
        <h2>
          {status.altitude > 500000
            ? "A world of possibilities."
            : status.altitude > 50000
              ? "At the edge of sunlight."
              : "Read the terrain. Plan the mission."}
        </h2>
        <p>
          {status.altitude > 300000
            ? "Global LOLA relief · LROC context imagery"
            : status.altitude > 30000
              ? "240 m regional LOLA · progressive terrain"
              : selectedEntry.kind === "validation"
                ? "10 m local LOLA viewer terrain · 20 m thematic overlays"
                : "240 m regional viewer terrain · 10 m backend skyline"}
        </p>
      </div>
      <section className="site-card" id="planner-gauges" aria-label="Site gauges">
        <div className="card-title">
          <span className="mission-kicker">EVALUATED SITE</span>
          <span className="verified-dot">● SPICE PASS</span>
        </div>
        <h2>
          {data.site.name}{" "}
          <button title={`Fly to ${data.site.name}`} onClick={() => fly("site")}>
            ↗
          </button>
        </h2>
        <p className="coordinates">
          {coordinate(data.site.latitude_deg, true)}, {coordinate(data.site.longitude_deg_east, false)}
        </p>
        <p className="site-kind">
          {selectedEntry.kind === "validation"
            ? "Neutral pipeline-validation coordinate · not a landing site"
            : selectedEntry.region_status === "historical_2022_cohort"
              ? "Evaluation point in a historical NASA candidate region · not a selected landing site"
              : "Evaluation point in a NASA candidate region · not a selected landing site"}
        </p>
        <div className="power-readout">
          <label htmlFor="terrain-model">GAUGE TERRAIN MODEL</label>
          <select id="terrain-model" value={terrainModel} onChange={(event) => setTerrainModel(event.target.value)}>
            <option value="baseline">LOLA baseline</option>
            <option value="experimental">Registered NAC + LOLA — experimental</option>
          </select>
          <small>Globe, timeline strips, site summaries and 360° chart remain labeled LOLA baseline references.</small>
        </div>
        <p className="site-kind">Landing safety: not assessed. RF link quality: unknown — geometric visibility is not a link budget.</p>
        {terrainModel === "experimental" ? <ExperimentalTerrainGauges key={`${selectedEntry.id}:${selectedEntry.sha256}`} site={selectedEntry} sampleIndex={index} timestamp={sample.timestamp} /> : <>
        <div className="site-metrics">
          <div>
            <span>ELEVATION</span>
            <strong>
              {data.site.terrain_elevation_m.toFixed(2)} <small>m</small>
            </strong>
          </div>
          <div>
            <span>SLOPE / 20 m</span>
            <strong>
              {siteInfo?.slope != null
                && selectedEntry.kind === "validation"
                ? siteInfo.slope.toFixed(1) + "°"
                : "Not mapped"}
            </strong>
          </div>
          <div>
            <span>OBSERVER</span>
            <strong>
              +{data.site.observer_height_m.toFixed(0)} <small>m</small>
            </strong>
          </div>
        </div>
        {(["sun", "earth"] as const).map((name) => (
          <div key={name} className={`body-summary ${name}`}>
            <div>
              <span className="body-symbol">{name === "sun" ? "☀" : "◉"}</span>
              <strong>
                {name === "sun" ? "Sunlight" : "Earth visibility"}
              </strong>
              <span
                className={`visibility ${sample[name].state.toLowerCase()}`}
              >
                {stateName(sample[name])}
              </span>
            </div>
            {name === "earth" && (
              <div className={`comms-mini ${comms.classification.toLowerCase()}`}>
                <span>GEOMETRIC SCREENING INDEX</span>
                <strong>{comms.potential_index_percent}%</strong>
                <i aria-hidden="true"><b style={{ width: `${comms.potential_index_percent}%` }} /></i>
              </div>
            )}
            <dl>
              <div>
                <dt>Azimuth</dt>
                <dd>{sample[name].azimuth_deg.toFixed(2)}°</dd>
              </div>
              <div>
                <dt>Elevation</dt>
                <dd>{sample[name].elevation_deg.toFixed(2)}°</dd>
              </div>
              <div>
                <dt>Clearance</dt>
                <dd>{sample[name].clearance_deg.toFixed(2)}°</dd>
              </div>
            </dl>
          </div>
        ))}
        <section className={`comms-readout ${comms.classification.toLowerCase()}`} aria-label="Direct-to-Earth comms potential">
          <div className="comms-heading">
            <span>DIRECT-TO-EARTH / CENTER LOS</span>
            <span>GEOMETRY ONLY</span>
          </div>
          <div className="comms-value">
            <strong>{comms.potential_index_percent}<small>% index</small></strong>
            <span>{commsDisplayLabel}</span>
          </div>
          <div
            className="comms-meter"
            role="meter"
            aria-label="Heuristic geometric comms potential index"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={comms.potential_index_percent}
            aria-valuetext={`${comms.potential_index_percent} index, ${commsDisplayLabel}; not measured signal strength`}
          >
            <span style={{ width: `${comms.potential_index_percent}%` }} />
          </div>
          <dl className="comms-geometry">
            <div><dt>Earth elevation</dt><dd>{sample.earth.elevation_deg.toFixed(2)}°</dd></div>
            <div><dt>Terrain skyline</dt><dd>{sample.earth.terrain_horizon_deg.toFixed(2)}°</dd></div>
            <div><dt>Center clearance</dt><dd>{sample.earth.clearance_deg.toFixed(2)}°</dd></div>
            <div><dt>Visible Earth disk</dt><dd>{(sample.earth.visibility_fraction * 100).toFixed(1)}%</dd></div>
          </dl>
          <small>
            0 = center blocked · 30 = clear center at ≤{comms.low_elevation_threshold_deg}° Earth elevation · 100 = clear center above {comms.low_elevation_threshold_deg}°.
            User-specified illustrative geometric screening index, not measured signal strength or an RF link budget.
          </small>
          {comms.classification === "BLOCKED" && sample.earth.visibility_fraction > 0 && (
            <small className="comms-limb-note">An exposed Earth limb is visible, but its center is terrain-blocked.</small>
          )}
          {partialDiskWithClearCenter && (
            <small className="comms-partial-note">The 100 index checks center LOS and &gt;2° absolute Earth elevation only. The disk remains partly terrain-hidden; RF link strength is unassessed.</small>
          )}
        </section>
        <div className="power-readout">
          <label htmlFor="panel-scenario">PANEL ORIENTATION MODEL</label>
          <select
            id="panel-scenario"
            value={powerScenario}
            onChange={(event) => setPowerScenario(event.target.value)}
          >
            {powerScenarioOptions.map(([key, title]) => (
              <option key={key} value={key}>{title}</option>
            ))}
          </select>
          <span>ESTIMATED ELECTRICAL OUTPUT</span>
          <strong>
            {Math.round(selectedPower.estimated_electrical_output_w)}{" "}
            <small>W</small>
          </strong>
          <small>
            {data.panel.panel_area_m2} m² · {data.panel.efficiency * 100}% · {selectedPowerLabel}
            {" · cosine "}{selectedPower.incidence_cosine.toFixed(3)}
          </small>
          <small className="power-limit">Illustrative orientation model, not a flight-qualified lander power forecast.</small>
          <button className="analysis-button" onClick={() => {setSpacecraftOpen(!spacecraftOpen); setLocalTerrainOpen(false);}} aria-expanded={spacecraftOpen}>
            Spacecraft lab · CAD + thermal <span>↗</span>
          </button>
        </div>
        <div className="next-event">
          <span>NEXT GEOMETRIC STATE CHANGE</span>
          <strong>
            {next
              ? `${duration((Date.parse(next.timestamp) - now) / 1000)} from now`
              : "End of evaluated interval"}
          </strong>
          <small>
            {next
              ? `${next.comms_potential.classification !== comms.classification
                ? "Comms potential index"
                : next.sun.state !== sample.sun.state ? "Sunlight disk" : "Earth disk visibility"} changes · ${clock(next.timestamp)}`
              : `No extrapolation beyond ${dateLabel(data.time_range.end_utc)}`}
          </small>
        </div>
        <div className="dte-detail">
          <span>ANY VISIBLE EARTH DISK</span>
          <p>
            {dte
              ? `${duration((Date.parse(dte.end_utc) - now) / 1000)} remaining in window`
              : "No exposed Earth disk"}
          </p>
          {blackout && (
            <small>
              Next blackout {clock(blackout.start_utc)} ·{" "}
              {duration(blackout.duration_seconds)}
            </small>
          )}
          <small>Disk visibility windows can include epochs with a blocked Earth-center LOS.</small>
        </div>
        </>}
        <button
          className="analysis-button"
          onClick={() => setPanel(panel === "horizon" ? "none" : "horizon")}
        >
          LOLA baseline · 360° horizon <span>↗</span>
        </button>
      </section>
      {spacecraftOpen && <SpacecraftStudy key={selectedSiteId} site={selectedEntry} sampleIndex={index}
        timestamp={sample.timestamp} onClose={() => setSpacecraftOpen(false)} />}
      {localTerrainOpen && <LocalTerrainStudy key={selectedSiteId} site={selectedEntry} sampleIndex={index}
        timestamp={sample.timestamp} onClose={() => setLocalTerrainOpen(false)} />}
      <div className="map-controls">
        <button onClick={() => fly("moon")} title="Moon overview">
          ◯
        </button>
        <button onClick={() => fly("site")} title="Center on site">
          ⌖
        </button>
        <button onClick={() => fly("los")} title="Sun and Earth line of sight">
          ↗
        </button>
      </div>
      <div className="map-reference">
        <span>N ↗ {status.heading.toFixed(0)}°</span>
        <span>
          CAMERA{" "}
          {(status.altitude / 1000).toFixed(status.altitude < 10000 ? 2 : 0)} km
        </span>
        {status.scale > 0 && (
          <span className="scale-bar">
            {status.scale >= 1000
              ? (status.scale / 1000).toFixed(1) + " km"
              : status.scale.toFixed(0) + " m"}
          </span>
        )}
      </div>
      <div className="render-caption">
        {layers.illumination
          ? "Sun-driven WebGL lighting · visual approximation"
          : "Relief lighting for terrain readability"}{" "}
        <span>Mission visibility uses backend ray tracing</span>
      </div>
      {help && (
        <section className="help-popover">
          <button onClick={() => setHelp(false)}>×</button>
          <h3>Explore the Moon</h3>
          <p>
            Drag to pan or rotate. Scroll to zoom. Right-drag or Ctrl-drag to
            tilt. Double-click terrain to fly closer. Click a marker to load its
            precomputed simulation, or click terrain to inspect a point.
          </p>
          <p>
            All listed sites have evaluated Sun, Earth, and illustrative panel
            power states. Direction markers are distance-scaled visual proxies.
          </p>
        </section>
      )}
      {inspection && (
        <section className="inspection-card">
          <button
            className="close-panel"
            aria-label="Close terrain inspector"
            onClick={() => setInspection(null)}
          >
            ×
          </button>
          <span className="mission-kicker">TERRAIN INSPECTOR</span>
          <h3>
            {inspection.latitude.toFixed(5)}°, {inspection.longitude.toFixed(5)}
            ° E
          </h3>
          <dl>
            <div>
              <dt>Elevation</dt>
              <dd>{inspection.elevation_m.toFixed(2)} m</dd>
            </div>
            <div>
              <dt>Pixel spacing</dt>
              <dd>{inspection.resolution_m} m</dd>
            </div>
            <div>
              <dt>Slope (20 m product)</dt>
              <dd>
                {inspection.slope != null
                  ? inspection.slope.toFixed(2) + "°"
                  : "Outside slope coverage"}
              </dd>
            </div>
            {inspection.height_error != null && (
              <div>
                <dt>Height uncertainty</dt>
                <dd>{inspection.height_error.toFixed(2)} m</dd>
              </div>
            )}
            {inspection.slope_error != null && (
              <div>
                <dt>Slope uncertainty</dt>
                <dd>{inspection.slope_error.toFixed(2)}°</dd>
              </div>
            )}
            {inspection.effective_resolution != null && (
              <div>
                <dt>Effective resolution</dt>
                <dd>{inspection.effective_resolution.toFixed(1)} m</dd>
              </div>
            )}
            {inspection.count != null && (
              <div>
                <dt>LOLA returns / pixel</dt>
                <dd>{inspection.count}</dd>
              </div>
            )}
            {inspection.psr != null && (
              <div>
                <dt>NASA PSR map</dt>
                <dd>{inspection.psr >= 0.5 ? "PSR" : "Not PSR"}</dd>
              </div>
            )}
          </dl>
          <p>{inspection.dataset}</p>
          <small>
            Point inspection only. Mission states remain at {data.site.name}.
            Test Site A is the only location with 20 m science overlays in this viewer.
          </small>
        </section>
      )}
      {panel !== "none" && (
        <section className={`analysis-drawer ${panel}`}>
          <button
            className="close-panel"
            aria-label="Close analysis"
            onClick={() => setPanel("none")}
          >
            ×
          </button>
          {panel === "horizon" ? (
            <>
              <p>LOLA baseline reference · independent of selected gauge model</p>
              <HorizonChart
                profile={data.horizon.profile}
                sun={sample.sun}
                earth={sample.earth}
              />
              <div className="obstructions">
                {(["sun", "earth"] as const).map((name) => {
                  const b = sample[name],
                    p =
                      data.horizon.profile[Math.round(b.azimuth_deg * 2) % 720];
                  return (
                    <div key={name}>
                      <strong>
                        {name.toUpperCase()} · {stateName(b)}
                      </strong>
                      <span>
                        Visible disk {(b.visibility_fraction * 100).toFixed(1)}%
                        · skyline {b.terrain_horizon_deg.toFixed(2)}°
                      </span>
                      <span>
                        Dominant skyline sample{" "}
                        {(p.obstruction_distance_m / 1000).toFixed(2)} km away
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <span className="mission-kicker">DATA / METHODOLOGY</span>
              <h2>A traceable view of the Moon.</h2>
              <p>
                NASA terrain and JPL celestial geometry meet at a fixed lunar
                observer. Each selected site loads its own retained,
                SPICE-cross-checked simulation export; candidate evaluation
                points are not certified landing sites.
              </p>
              <div className="provenance-grid">
                <article>
                  <h3>Terrain</h3>
                  <p>
                    LOLA global 4 pixels/degree (~7.6 km); 240 m regional and
                    10 m local DEM raycasts at each evaluated site.
                  </p>
                  <small>
                    MOON_ME / DE421 · sphere radius 1737.4 km · true elevation
                    scale
                  </small>
                </article>
                <article>
                  <h3>Geometry / PASS</h3>
                  <p>JPL Horizons DE441 · local SPICE DE440s cross-check</p>
                  <small>
                    Site max sky difference: Sun {data.validation.independent_spice.targets.sun.angular_separation_arcsec.maximum.toFixed(6)}″
                    {" · "}Earth {data.validation.independent_spice.targets.earth.angular_separation_arcsec.maximum.toFixed(6)}″.
                    Both share JPL ephemeris lineage.
                  </small>
                </article>
                <article>
                  <h3>Resolution & uncertainty</h3>
                  <p>
                    NASA slope, PSR, height/slope error, effective resolution
                    and counts are 20 m products in a Test Site A 24 × 24 km crop.
                  </p>
                  <small>
                    Candidate backend horizons use their own DEM crops, but
                    these 20 m viewer overlays have not been prepared there.
                  </small>
                </article>
                <article>
                  <h3>Mission limits</h3>
                  <p>
                    {data.samples.length.toLocaleString()} epochs · {data.time_range.step_minutes} minute cadence · {data.site.observer_height_m} m observer above local
                    terrain; {data.horizon.profile.length}-ray horizon mask from this export.
                  </p>
                  <small>
                    Earth-disk visibility and the conservative center-LOS
                    comms potential index are distinct. The user-specified 0/30/100
                    screening index uses an illustrative 2° absolute Earth-elevation
                    cutoff, not a calibrated RF link budget. WebGL lighting
                    does not determine mission visibility. Panel orientation
                    models include cosine loss, but not hardware-specific thermal,
                    dust, degradation, or electrical losses.
                  </small>
                </article>
              </div>
              <div className="data-links">
                <a href={selectedEntry.data_url} download>
                  Selected-site JSON ↗
                </a>
                <a href="/data/simulation-index.json" download>
                  Site index ↗
                </a>
                <a href="/terrain/manifest.json" download>
                  Terrain provenance ↗
                </a>
                <a
                  href="https://pgda.gsfc.nasa.gov/products/90"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA PGDA ↗
                </a>
                <a
                  href="https://svs.gsfc.nasa.gov/4720/"
                  target="_blank"
                  rel="noreferrer"
                >
                  NASA global map ↗
                </a>
                {selectedEntry.coordinate_source_url && (
                  <a href={selectedEntry.coordinate_source_url} target="_blank" rel="noreferrer">
                    Candidate coordinate source ↗
                  </a>
                )}
              </div>
              <small>
                Resource evidence: dataset not loaded. PSR does not establish
                ice. Cross-site comparisons and mission constraints still need
                flight-system specifications and independent review.
              </small>
            </>
          )}
        </section>
      )}
      <footer className="mission-time" id="planner-time">
        <div className="time-header">
          <div>
            <span className="mission-kicker">MISSION TIME / UTC</span>
            <strong>
              {sample.timestamp.slice(0, 10)} <em>{clock(sample.timestamp)}</em>
            </strong>
          </div>
          <div className="time-actions">
            <button
              aria-label="Step backward"
              onClick={() => scrub(Math.max(0, index - 1))}
            >
              −10m
            </button>
            <button
              className="play-control"
              aria-label={running ? "Pause simulation" : "Play simulation"}
              onClick={() => {
                if (ended) scrub(0);
                setPlaying(!running);
              }}
            >
              {running ? "Ⅱ" : "▶"}
            </button>
            <button
              aria-label="Step forward"
              onClick={() => scrub(Math.min(data.samples.length - 1, index + 1))}
            >
              +10m
            </button>
            <select
              aria-label="Simulation speed"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {[1, 10, 100, 1000].map((x) => (
                <option key={x} value={x}>
                  {x}×
                </option>
              ))}
            </select>
          </div>
          <span className="time-count">
            {index + 1} / {data.samples.length.toLocaleString()} <small>{data.time_range.step_minutes} minute samples</small>
          </span>
        </div>
        <small>LOLA baseline · visibility strips (time control applies to both models)</small>
        <Timeline samples={data.samples} index={index} onChange={scrub} />
        <input
          className="time-slider"
          aria-label="Simulation timestamp"
          type="range"
          min={0}
          max={data.samples.length - 1}
          value={index}
          onChange={(e) => scrub(Number(e.target.value))}
        />
        <div className="time-dates">
          <span>{dateLabel(data.time_range.start_utc)}</span>
          <span>
            Sun + Earth disk overlap{" "}
            {data.windows.combined[
              "SUN_VISIBLE_EARTH_VISIBLE"
            ].percentage.toFixed(1)}
            % · transitions resolved to {data.time_range.window_boundary_precision_minutes} min
          </span>
          <span>{dateLabel(data.time_range.end_utc)}</span>
        </div>
      </footer>
      <div className="stream-status">
        {status.pending
          ? `STREAMING ${status.pending} TILES`
          : `${status.loaded} TERRAIN TILES`}{" "}
        · {status.fps.toFixed(0)} render fps <span>idle rendering sleeps</span>
      </div>
      {error && (
        <div className="planner-error" role="alert">
          <strong>Data or renderer issue</strong>
          <span>{error}</span>
          {(error.startsWith("3D rendering stopped") ||
            error.startsWith("Local planner connection lost")) && (
            <button onClick={restartRenderer}>Retry 3D view</button>
          )}
          <button onClick={() => setError("")}>Dismiss</button>
        </div>
      )}
      {loadingSiteId && (
        <div className="site-loading" role="status">
          Opening {siteIndex.sites.find((site) => site.id === loadingSiteId)?.name} simulation…
        </div>
      )}
    </main>
  );
}
