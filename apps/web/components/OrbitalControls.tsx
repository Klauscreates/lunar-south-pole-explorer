"use client";
import { useEffect, useState } from "react";
import { loadOrbitalData, type OrbitalData } from "./orbitalData";
import "./orbital.css";

export function useOrbitalData(enabled: boolean) {
  const [data,setData]=useState<OrbitalData>();
  const [error,setError]=useState<string>();
  useEffect(()=>{
    if(!enabled || data) return;
    const controller=new AbortController();
    loadOrbitalData(controller.signal).then(result=>{if(!controller.signal.aborted){setData(result);setError(undefined);}})
      .catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return ()=>controller.abort();
  },[enabled,data]);
  return {data,error};
}

export function OrbitalControls({data,error,epoch,playing,onPlay,onEpoch,onClose}: {
  data?:OrbitalData;error?:string;epoch:number;playing:boolean;
  onPlay:()=>void;onEpoch:(n:number)=>void;onClose:()=>void;
}) {
  const sample=data?.samples[epoch];
  const date=sample ? new Date(sample.utc) : undefined;
  const dateLabel=date?.toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"});
  const timeLabel=sample?.utc.slice(11,16);
  return <>
    <button className="orbital-close" onClick={onClose} aria-label="Close orbital view">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg>
    </button>
    <p className="orbital-scale-caption">Scaled overview · sizes & distances not to scale</p>
    <section className="orbital-panel" aria-label="Orbital date scrubber">
      {!sample || !data ? <p role="status">{error ?? "Loading verified orbital data…"}</p> : <>
        <label htmlFor="orbital-time"><span>{dateLabel}</span><span>{timeLabel} <small>UTC</small></span></label>
        <div className="orbital-time">
          <button onClick={onPlay} aria-label={playing?"Pause orbital timeline":"Play orbital timeline"}>
            <svg viewBox="0 0 24 24" aria-hidden="true">{playing ? <path d="M8 6v12M16 6v12" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/> : <path d="m9 5 11 7-11 7Z" fill="currentColor"/>}</svg>
          </button>
          <input id="orbital-time" type="range" min="0" max={data.samples.length-1} step="1" value={epoch}
            style={{"--scrub-progress":`${epoch/(data.samples.length-1)*100}%`} as React.CSSProperties}
            aria-valuetext={`${dateLabel}, ${timeLabel} UTC`}
            onChange={e=>onEpoch(Number(e.target.value))}/>
        </div>
      </>}
    </section>
  </>;
}
