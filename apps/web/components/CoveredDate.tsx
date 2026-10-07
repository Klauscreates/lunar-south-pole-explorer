"use client";
import { useId, useState } from "react";
import { coveredEpoch, coveredInput, COVERAGE_LAST } from "./coverage";

export function useCoveredDate(epoch: number, onEpoch: (value: number)=>void, min = 0, max = COVERAGE_LAST) {
  const [draft, setDraft] = useState<string|null>(null);
  const value = draft ?? coveredInput(epoch);
  const index = coveredEpoch(value);
  const available = index !== null && index >= min && index <= max;
  const scrub = (next: number) => { setDraft(null); onEpoch(next); };
  const change = (next: string) => {
    setDraft(next);
    const index = coveredEpoch(next);
    if (index !== null && index >= min && index <= max) { setDraft(null); onEpoch(index); }
  };
  return {value, available, scrub, change, min, max};
}
export function CoveredDate({value, available, change, scrub, epoch, min, max, slider=true}: ReturnType<typeof useCoveredDate> & {epoch:number; slider?:boolean}) {
  const id = useId();
  return <section className="coverage-date" aria-label="Date and dataset coverage">
    <label htmlFor={id}>Date & time · UTC</label>
    <input id={id} type="datetime-local" step="600" value={value} onChange={e=>change(e.target.value)} aria-invalid={!available} aria-describedby={`${id}-coverage`}/>
    <p id={`${id}-coverage`}>5 evaluated points · Oct 1–Dec 31, 2026 · through Jan 1, 2027 at 00:00 UTC · 10-minute samples.</p>
    {!available && <p role="alert">Unavailable — choose a covered 10-minute sample within the selected window. No extrapolation; the globe remains at its last supported epoch.</p>}
    {(slider || !available) && <><label htmlFor={`${id}-range`}>Scrub the selected window</label>
    <input id={`${id}-range`} type="range" min={min} max={max} step="1" value={epoch} onChange={e=>scrub(Number(e.target.value))} aria-valuetext={`${coveredInput(epoch).replace("T"," ")} UTC`}/></>}
  </section>;
}
