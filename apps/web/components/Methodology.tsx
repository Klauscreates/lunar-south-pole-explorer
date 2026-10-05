export function Methodology() {
  return <details className="mission-methodology"><summary>How to use · methods & data</summary>
    <ol><li>Choose a location to fly to its evaluated point, then expand its name card.</li>
      <li>Move the date slider to see the modeled power and Earth visibility change.</li>
      <li>Open Locations → Compare, choose Site A and Site B, and scrub their shared time.</li></ol>
    <p><strong>Coverage:</strong> four candidate-region points plus Test Site A, a pipeline validation coordinate—not a proposed landing site. October 1–8, 2026, ending at 00:00 UTC on October 8. No predictions outside this window.</p>
    <p><strong>Geometry:</strong> <a href="https://ssd.jpl.nasa.gov/horizons/" target="_blank" rel="noreferrer">JPL Horizons</a> surface-observer Sun/Earth directions, checked with local <a href="https://naif.jpl.nasa.gov/naif/" target="_blank" rel="noreferrer">NAIF SPICE</a>. Backend LOLA skyline masks determine terrain visibility, not the rendered shadows. The separate orbital view uses SPICE DE440; displayed sizes and distances are compressed, not to scale.</p>
    <p><strong>Power:</strong> watts and kWh are modeled generation under the selected R1 attitude and assumed thermal environment—not guaranteed output, stored battery charge, or net energy after electrical loads.</p>
    <p><strong>Communication:</strong> visibility is geometric line of sight (LOS), not RF signal strength or a guaranteed link. The 0/30/100 index is a geometry screening tier; antennas, ground stations, interference and a link budget are not qualified.</p>
    <p><strong>Terrain:</strong> <a href="https://lola.gsfc.nasa.gov/" target="_blank" rel="noreferrer">LRO LOLA</a> baseline and separately labeled experimental registered NAC studies. Missing qualified fine terrain remains Unknown. Visibility does not certify landing safety.</p>
    <p>Exports are SHA-256 verified. <a href="/data/simulation-index.json" target="_blank" rel="noreferrer">Inspect site provenance</a>. Research and education prototype; not flight-certified.</p>
  </details>;
}
