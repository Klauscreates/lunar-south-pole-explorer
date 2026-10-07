"use client";

import { useEffect, useMemo, useState } from "react";
import { loadStudy, type Study } from "./SpacecraftStudy";
import { weeklyMetrics } from "./weeklyMetrics";
import { SpacecraftControlPanel } from "./SpacecraftControlPanel";
import { DualSiteComparison, type SimulationLoader } from "./DualSiteComparison";
import type { IndexedSite } from "./types";
import "./moon-experience.css";
import { CoveredDate, useCoveredDate } from "./CoveredDate";
import { Methodology } from "./Methodology";
import { coveredEpoch, coveredInput, COVERAGE_LAST } from "./coverage";

function PotentialIcon({kind, value}: {kind: "energy" | "comms"; value: number | undefined}) {
  return kind === "energy" ? <svg viewBox="0 0 64 36" aria-hidden="true">
    <rect x="2" y="5" width="52" height="26" rx="7" fill="none" stroke="currentColor" strokeWidth="2.5"/>
    <path d="M59 14v8" stroke="currentColor" strokeWidth="4" strokeLinecap="round"/>
    {value !== undefined && <rect x="7" y="10" width={42*value/100} height="16" rx="3" fill="currentColor"/>}
  </svg> : <svg viewBox="0 0 64 36" aria-hidden="true">
    {[9,16,24,32].map((height,i)=><rect key={height} x={5+i*14} y={34-height} width="9" height={height} rx="3"
      fill="currentColor" opacity={value !== undefined && value > i*25 ? 1 : .18}/>)}
  </svg>;
}

export function MoonExperience({sites, selected, focused, viewKey, epoch, onEpoch, loadSimulation, onSelect, onDetails, onGlobe, onSky}: {
  sites: IndexedSite[]; selected: IndexedSite; onSelect:(id:string)=>Promise<void>;
  focused: boolean; viewKey: string;
  epoch: number; onEpoch: (epoch: number) => void; loadSimulation: SimulationLoader;
  onDetails:()=>void; onGlobe:()=>void; onSky:()=>void;
}) {
  const [locationsOpen,setLocationsOpen] = useState(false);
  const [step,setStep] = useState<'dates' | 'locations'>('dates');
  const [startDate,setStartDate] = useState(coveredInput(0));
  const [endDate,setEndDate] = useState(coveredInput(COVERAGE_LAST));
  const [window,setWindow] = useState({start:0,end:COVERAGE_LAST});
  const startIndex=coveredEpoch(startDate), endIndex=coveredEpoch(endDate);
  const validWindow=startIndex!==null && endIndex!==null && startIndex<endIndex;
  const windowLabel=`${coveredInput(window.start).replace('T',' ')} → ${coveredInput(window.end).replace('T',' ')} UTC`;
  const [skyView,setSkyView] = useState(false);
  const [expandedView,setExpandedView] = useState<string | null>(null);
  const [compare,setCompare] = useState(false);
  const [scenario,setScenario] = useState("north--low_load");
  const [reports,setReports] = useState<Record<string,Study>>({});
  const [errors,setErrors] = useState<Record<string,string>>({});
  const [busy,setBusy] = useState("");
  const key = selected.id;
  const date = useCoveredDate(epoch,onEpoch,window.start,window.end);
  useEffect(()=>{
    const controller = new AbortController();
    const targets = locationsOpen ? sites : [selected];
    for (const site of targets) {
      loadStudy(site,controller.signal).then(study=>{
        if(!controller.signal.aborted) setReports(current=>({...current,[site.id]:study}));
      }).catch(error=>{
        if(!controller.signal.aborted) setErrors(current=>({...current,[site.id]:String(error)}));
      });
    }
    return ()=>controller.abort();
  },[locationsOpen,sites,selected]);
  const validReport = (site:IndexedSite) => reports[site.id]?.parent_sha256 === site.sha256 ? reports[site.id] : undefined;
  const study = validReport(selected);
  const metric = useMemo(()=>study ? weeklyMetrics(study,scenario,window.start,window.end) : null,[study,scenario,window]);
  const activeRow = date.available ? study?.scenarios.find(s=>s.id===scenario)?.rows[epoch] : undefined;
  const ranking = useMemo(()=>sites.map(site=>({site,metrics:reports[site.id]?.parent_sha256 === site.sha256 ? weeklyMetrics(reports[site.id],scenario,window.start,window.end) : null})),[sites,reports,scenario,window]);
  const complete = ranking.every(r=>r.metrics);
  async function choose(id:string) {
    setBusy(id);
    setExpandedView(null);
    try { await onSelect(id); setSkyView(false); setLocationsOpen(false); }
    finally {setBusy("");}
  }
  return <>
    <div className="moon-wordmark"><span>◒</span> lunar<span className="wordmark-sub">SOUTH POLE EXPLORER</span></div>
    <div className="moon-map-actions"><button onClick={()=>{onGlobe();setSkyView(false);setLocationsOpen(false);setExpandedView(null);}} aria-label="Moon overview">◎</button>
      <button onClick={()=>{setLocationsOpen(!locationsOpen);setCompare(false);setStep('dates');}} aria-pressed={locationsOpen} aria-expanded={locationsOpen} aria-controls="location-browser">Plan your mission</button>
      <button onClick={onDetails} aria-label="Open scientific instruments">＋</button></div>
    {focused && !locationsOpen && <button className="sky-view-button" onClick={()=>{setSkyView(true);onSky();}}>◉ Sky · toward Earth</button>}
    {skyView && !locationsOpen && <p className="sky-disclosure">Earth-facing camera · 30 m above selected observer<br/>Measured apparent direction and angular size · 4K display texture<br/>Artist-adjusted imagery; texture orientation illustrative, not Earth attitude.<br/>Rendered terrain is visual only; visibility gauges use backend masks.</p>}
    <section id="location-browser" className={`moon-dock ${compare ? "is-dual" : ""}`} aria-label="Plan your mission" hidden={!locationsOpen}
      onKeyDown={e=>{if(e.key === "Escape") setLocationsOpen(false);}}>
      <button className="dock-collapse" aria-label="Close mission planner" onClick={()=>setLocationsOpen(false)}>Close ×</button>
      {locationsOpen && compare ? <>
        <button className="locations-compare" onClick={()=>setCompare(false)}>← Back to locations</button>
        <DualSiteComparison sites={sites} anchor={selected} epoch={epoch} onEpoch={onEpoch} scenario={scenario} onScenario={setScenario} loadSimulation={loadSimulation} window={window}/>
      </> : step==='dates' ? <form className="picker-content mission-date-selection" onSubmit={e=>{
        e.preventDefault(); if(!validWindow) return;
        setWindow({start:startIndex!,end:endIndex!});onEpoch(startIndex!);setStep('locations');
      }}>
        <small>STEP 1 OF 2</small><h2>Pick your dates.</h2>
        <p>Choose your mission window. Next, explore each location’s modeled energy and Earth visibility for that period.</p>
        <label>Mission start · UTC<input type="datetime-local" step="600" value={startDate} onChange={e=>setStartDate(e.target.value)} required/></label>
        <label>Mission end · UTC<input type="datetime-local" step="600" value={endDate} onChange={e=>setEndDate(e.target.value)} required/></label>
        <p>Available: October 1, 00:00 – October 8, 00:00, 2026 UTC. 10-minute steps. Later dates are not generated yet.</p>
        {!validWindow && <p role="alert">Unavailable — choose dates within the available coverage, with the end after the start.</p>}
        <button className="locations-compare" type="submit" disabled={!validWindow}>See locations →</button>
      </form> :
      <div className="picker-content comparison">
        <button className="locations-compare" onClick={()=>setStep('dates')}>← Change dates</button>
        <small>STEP 2 OF 2</small>
        <div className="locations-heading"><h2>Pick your location.</h2>
          <button className="locations-compare" onClick={()=>setCompare(true)}>Compare</button></div>
        <p>{windowLabel}<br/>5 evaluated points · LOLA baseline. Potentials below are for your selected window. Select a location, then compare it with another.</p>
        <Methodology/>
        <details className="mission-methodology"><summary>Spacecraft configuration · R1</summary>
          <SpacecraftControlPanel study={study} value={scenario} onChange={setScenario}/>
        </details>
        {!complete && <p role="status">{Object.keys(errors).length ? "Some data unavailable; missing results are Unknown." : "Verifying all five spacecraft studies…"}</p>}
        {ranking.map(({site,metrics})=><button className="location-row" key={site.id} onClick={()=>void choose(site.id)} disabled={!!busy}>
          <span><strong>{site.name}</strong>
            <small>{site.latitude_deg.toFixed(4)}° · {site.longitude_deg_east.toFixed(4)}° E{site.kind === "validation" ? " · validation point" : ""}</small>
            <span className="location-potentials">
              <span className="potential-energy"><PotentialIcon kind="energy" value={metrics?.poweredPercent}/><span>{metrics ? `${metrics.kwh.toFixed(2)} kWh` : "Unknown energy"}</span></span>
              <span className="potential-comms"><PotentialIcon kind="comms" value={metrics?.commsPercent}/><span>{metrics ? `${metrics.commsPercent.toFixed(1)}% LOS` : "Unknown LOS"}</span></span>
            </span></span><span>{busy === site.id ? "…" : "↗"}</span></button>)}
        <small>Icons show generating time and Earth-center visibility—not battery charge or RF strength. Thermal inputs assumed; landing safety unassessed.</small>
      </div>}
    </section>
    {!locationsOpen && focused && <aside className={`potential-readout ${expandedView !== viewKey ? "is-compact" : ""}`} aria-label="Selected location potential" aria-busy={!!busy}
      onKeyDown={e=>{if(e.key === "Escape") setExpandedView(null);}}>
      <button className="potential-toggle" aria-label={expandedView === viewKey ? "Collapse location details" : "Expand location details"} aria-expanded={expandedView === viewKey} aria-controls="selected-location-details" onClick={()=>setExpandedView(expandedView === viewKey ? null : viewKey)}>
        <span>{selected.name}</span><span aria-hidden="true">{expandedView === viewKey ? "⌄" : "⌃"}</span>
      </button>
      <div id="selected-location-details" hidden={expandedView !== viewKey}>
          <strong className="potential-site">{selected.name}{selected.kind === "validation" ? " · validation point" : ""}</strong>
          <p className="mission-context">{selected.latitude_deg.toFixed(4)}° latitude · {selected.longitude_deg_east.toFixed(4)}° E</p>
          <p className="mission-context">{windowLabel} · R1 · {scenario.replace("--"," / ").replaceAll("_"," ")}</p>
          <CoveredDate {...date} epoch={epoch}/>
          <p className="epoch-potential" aria-live="polite">At selected time: <strong>{activeRow ? `${activeRow[0].toFixed(1)} W modeled generation` : "Unknown power"}</strong> · {activeRow ? (activeRow[7] ? "Earth-center LOS clear" : "Earth-center LOS blocked") : "Unknown LOS"}</p>
          {date.available && <>
          <p className="mission-context">Selected mission window (not the selected instant)</p>
          <div className="potential-grid">
            <div className="potential-energy"><PotentialIcon kind="energy" value={metric?.poweredPercent}/><span>Energy potential</span><strong>{metric?`${metric.kwh.toFixed(2)}`:"Unknown"}<small>{metric?" kWh":""}</small></strong><small>{metric?`${metric.poweredPercent.toFixed(0)}% of window generating`:"Awaiting qualified study"}</small></div>
            <div className="potential-comms"><PotentialIcon kind="comms" value={metric?.commsPercent}/><span>Comms potential</span><strong>{metric?`${metric.commsPercent.toFixed(0)}%`:"Unknown"}</strong><small>Earth-center visible time</small></div>
          </div>
          <p className="metric-qualification">LOLA + R1 study · assumed thermal inputs.<br/>Availability—not battery charge or RF signal.</p>
          </>}
          <button className="locations-compare" onClick={()=>{setLocationsOpen(true);setStep('locations');setCompare(true);}}>Compare this location</button>
          <Methodology/>
          {errors[key] && !study && <p role="alert">{errors[key]}</p>}
      </div>
    </aside>}
  </>;
}
