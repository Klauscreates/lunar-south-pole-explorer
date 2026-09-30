"use client";

import { useCallback, type PointerEvent } from "react";
import type { SimulationSample } from "./types";

interface Segment {
  active: boolean;
  start: number;
  end: number;
  label: string;
}

function buildSegments(
  samples: SimulationSample[],
  predicate: (sample: SimulationSample) => boolean,
): Segment[] {
  if (samples.length === 0) return [];
  const segments: Segment[] = [];
  let start = 0;
  let active = predicate(samples[0]);
  for (let index = 1; index < samples.length; index += 1) {
    const next = predicate(samples[index]);
    if (next !== active) {
      segments.push({
        active,
        start,
        end: index,
        label: `${samples[start].timestamp} → ${samples[index].timestamp}`,
      });
      start = index;
      active = next;
    }
  }
  segments.push({
    active,
    start,
    end: samples.length - 1,
    label: `${samples[start].timestamp} → ${samples.at(-1)?.timestamp}`,
  });
  return segments;
}

function Track({
  label,
  accent,
  samples,
  predicate,
}: {
  label: string;
  accent: string;
  samples: SimulationSample[];
  predicate: (sample: SimulationSample) => boolean;
}) {
  const denominator = Math.max(1, samples.length - 1);
  return (
    <div className="timeline-row">
      <span className="timeline-label">{label}</span>
      <div className="timeline-track">
        {buildSegments(samples, predicate).map((segment) => (
          <span
            key={`${segment.start}-${segment.end}`}
            className={segment.active ? "timeline-segment active" : "timeline-segment"}
            title={`${segment.active ? "Available" : "Unavailable"}: ${segment.label} · ${(segment.end-segment.start)*10} minutes`}
            style={{
              left: `${(segment.start / denominator) * 100}%`,
              width: `${Math.max(0.12, ((segment.end - segment.start) / denominator) * 100)}%`,
              backgroundColor: segment.active ? accent : undefined,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function Timeline({
  samples,
  index,
  onChange,
}: {
  samples: SimulationSample[];
  index: number;
  onChange: (nextIndex: number) => void;
}) {
  const chooseFromPointer = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      const fraction = Math.min(1, Math.max(0, (event.clientX - bounds.left - 92) / (bounds.width - 92)));
      onChange(Math.round(fraction * (samples.length - 1)));
    },
    [onChange, samples.length],
  );
  const progress = samples.length > 1 ? (index / (samples.length - 1)) * 100 : 0;

  return (
    <div className="timeline" onPointerDown={chooseFromPointer} role="group" aria-label="Mission availability timeline">
      <Track label="SUNLIGHT" accent="#ffb74a" samples={samples} predicate={(sample) => sample.sun.visibility_fraction > 0} />
      <Track label="EARTH DTE" accent="#6ad4ff" samples={samples} predicate={(sample) => sample.earth.visibility_fraction > 0} />
      <Track label="BOTH" accent="#b7f071" samples={samples} predicate={(sample) => sample.sun.visibility_fraction > 0 && sample.earth.visibility_fraction > 0} />
      <span className="timeline-cursor" style={{ left: `calc(92px + (100% - 92px) * ${progress / 100})` }} aria-hidden="true" />
    </div>
  );
}
