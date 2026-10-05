# SPICE integrity and qualification boundary

The local provider already evaluates official NAIF `de440s.bsp`,
`moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`, `pck00011.tpc`, and
`naif0012.tls`. The lock manifest pins HTTPS origin, byte length and SHA-256.
Coverage and explicit `MOON_ME_DE440_ME421` frame identity are checked, and
the process-global kernel pool is isolated/restored. DE421 in the terrain
reference convention does not mean the orbital integration uses DE421.

SpiceyPy 8.2.0 is a third-party Python binding to NAIF CSPICE, not a
NAIF-maintained or NAIF-certified Python toolkit. No simplified orbital
propagator is used in this provider. The displayed baseline remains sourced
from Horizons and independently cross-checked with local SPICE; this change
does not silently replace or regenerate parent-linked terrain studies.

Every new provider result now records each UTC epoch, TDB and TT coordinates,
the periodic TDB-minus-TT term, and a <=1 microsecond numerical round-trip
check. This check tests internal consistency, not absolute time accuracy.
Leap seconds and the periodic conversion come from CSPICE's LSK-driven time
subsystem. They are not a spacecraft-clock or lunar proper-time solution.

Run `.venv/bin/python run_spice_audit.py` to verify all five indexed exports
offline and save `outputs/spice-integrity-audit.json`. Checks include parent
hashes, epoch alignment, kernel integrity/coverage, time conversion, and the
existing 1 arcsecond azimuth/elevation comparison gate. Shared JPL origins
mean Horizons agreement is not independent validation of underlying physics.

## Not flight ready

- CN+S provides converged Newtonian light time and Newtonian stellar aberration.
  Relativistic light deflection and Shapiro propagation delay are not implemented.
- DE440 orientation is an observational model with uncertainty, not exact truth.
- Antenna phase center is **Unknown**. No fabricated zero-offset calibration is
  substituted for measurements. Required inputs include surveyed phase-center
  offsets relative to the vehicle reference point, body-frame definition,
  attitude/articulation at each epoch, frequency/direction-dependent calibration,
  and the intended Earth station. Terrain and self-occlusion must subsequently
  be recomputed at that observer position.
- A flight claim additionally requires mission-specific error budgets,
  independent verification, clock calibration, approved kernel baselines, and
  validated relativistic light-propagation and RF models.

References: [NAIF interfaces](https://naif.jpl.nasa.gov/naif/links.html),
[NAIF time subsystem](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/time.html),
[NAIF aberration limitations](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/abcorr.html).
