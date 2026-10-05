"use client";

import { useId } from "react";
import type { Study } from "./SpacecraftStudy";
import { attitudeStatus } from "./attitudeStatus";
import "./attitude-control.css";

export function SpacecraftControlPanel({ study, value, onChange }: {
  study?: Study; value: string; onChange: (value: string) => void;
}) {
  const id = useId();
  const current = attitudeStatus(study, value);
  const available = study?.scenarios.some(item => item.id === value);
  return <section className="attitude-control" aria-label="R1 attitude and thermal configuration">
    <div className="attitude-kicker">R1 attitude + thermal environment</div>
    <div className="attitude-controller-row">
      <label htmlFor={id}>Study configuration
        <select id={id} value={value} disabled={!study?.scenarios.length}
          onChange={event => onChange(event.target.value)}>
          {!available && <option value={value}>{study ? "Configuration unavailable" : "Loading configurations…"}</option>}
          {study?.scenarios.map(item => <option key={item.id} value={item.id}>
            {item.pose_id.replaceAll("_", " ")} · {item.boundary_id.replaceAll("_", " ")}
          </option>)}
        </select>
      </label>
      <div className={`attitude-compass ${current?.isTilted ? "is-tilted" : ""}`} aria-hidden="true">
        <span className="compass-north">N</span><span className="compass-east">E</span>
        <span className="compass-south">S</span><span className="compass-west">W</span>
        {current && <>
          <svg className="compass-needle" viewBox="0 0 24 24" style={{transform:`rotate(${current.heading}deg)`}}>
            <path d="M12 2L16 10H8Z" fill="currentColor"/><path d="M12 22L8 14H16Z" fill="#536174"/>
          </svg>
          <span className="alignment-dot" style={{transform:current.isTilted ? "translate(8px,-4px)" : "none"}}/>
        </>}
      </div>
    </div>
    <div className="attitude-badges" role="status" aria-live="polite">
      {current ? <>
        <span className="attitude-badge"><i/>{current.facing} · yaw {current.heading}°</span>
        <span className={`attitude-badge ${current.isTilted ? "is-tilted" : "is-level"}`}><i/>
          {current.isTilted ? `Tilted · pitch ${current.pitch}° / roll ${current.roll}°` : "Level · pitch 0° / roll 0°"}</span>
        <span className={`attitude-badge ${current.isAddedLoad ? "is-added" : ""}`}><i/>{current.loadLabel}</span>
        <small>Wall {current.wall} W/m² · lunar IR {current.ir} W/m²</small>
      </> : <span className="attitude-badge">Configuration Unknown</span>}
    </div>
    <p className="attitude-note">Assumed environmental heating, not electrical demand. Alignment dot is schematic; R1 is a design study.</p>
  </section>;
}
