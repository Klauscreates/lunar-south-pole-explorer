"""Native-resolution, confidence-aware local terrain diagnostics.

No gap filling, image-to-height inference, or landing certification. Bilinear
sampling requires all four contributing posts to be valid. Rays are evaluated
at the requested Sun/Earth azimuth, not interpolated from a coarse skyline.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from rasterio.windows import from_bounds
from scipy.optimize import least_squares
from affine import Affine

from science.errors import TerrainDataError

RADIUS = 1737400.0
GEOGRAPHIC = CRS.from_proj4(f"+proj=longlat +R={RADIUS}")


@dataclass
class LocalGrid:
    values: np.ndarray
    transform: object
    crs: object
    resolution_m: float
    quality_qualified: bool

    def sample(self, x, y):
        c, r = ~self.transform * (np.asarray(x), np.asarray(y))
        c, r = c - .5, r - .5
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        valid = (r0 >= 0) & (c0 >= 0) & (r0+1 < self.values.shape[0]) & (c0+1 < self.values.shape[1])
        rr = np.clip(r0, 0, self.values.shape[0]-2)
        cc = np.clip(c0, 0, self.values.shape[1]-2)
        corners = np.array([self.values[rr,cc], self.values[rr,cc+1],
                            self.values[rr+1,cc], self.values[rr+1,cc+1]])
        valid &= np.isfinite(corners).all(axis=0)
        dx, dy = c-c0, r-r0
        z = corners[0]*(1-dx)*(1-dy)+corners[1]*dx*(1-dy)+corners[2]*(1-dx)*dy+corners[3]*dx*dy
        return np.where(valid, z, np.nan)


def read_local_grid(path: Path, longitude: float, latitude: float, radius_m=1200.,
                    confidence_path=None, accepted_codes=(14,)) -> LocalGrid:
    if not np.isfinite(radius_m) or not 0 < radius_m <= 5000:
        raise TerrainDataError("Local read radius must be within (0, 5000] m")
    with rasterio.open(path) as src:
        if src.count != 1 or src.crs is None:
            raise TerrainDataError("Expected one georeferenced elevation band")
        crs = CRS(src.crs)
        if not crs.is_projected or abs(crs.ellipsoid.semi_major_metre-RADIUS) > .01:
            raise TerrainDataError("Expected projected 1737400 m lunar sphere")
        if not all(abs(axis.unit_conversion_factor-1) < 1e-12 for axis in crs.axis_info):
            raise TerrainDataError("Projected DEM coordinates must be meters")
        if src.transform.b or src.transform.d or src.transform.a <= 0 or src.transform.e >= 0:
            raise TerrainDataError("Expected north-up unrotated DEM")
        resolution = max(abs(src.transform.a), abs(src.transform.e))
        if not .1 <= resolution <= 20:
            raise TerrainDataError("Unsupported local DEM spacing")
        x,y = Transformer.from_crs(GEOGRAPHIC, crs, always_xy=True).transform(longitude,latitude)
        window = from_bounds(x-radius_m,y-radius_m,x+radius_m,y+radius_m,src.transform).round_offsets().round_lengths()
        if window.width*window.height > 16_000_000:
            raise TerrainDataError("Local crop exceeds 16 million native pixels; reduce radius")
        values = src.read(1, window=window, boundless=True, masked=True).astype(float).filled(np.nan)
        values = values * src.scales[0] + src.offsets[0]
        transform = src.window_transform(window)
        if confidence_path:
            with rasterio.open(confidence_path) as conf:
                # PDS may label meter units "unknown"; exact projection parameters,
                # shape and grid must still agree with this fixed source product.
                if conf.shape != src.shape or conf.transform != src.transform:
                    raise TerrainDataError("Confidence raster grid does not match DEM")
                a, b = CRS(conf.crs).to_dict(), crs.to_dict()
                if any(a.get(k) != b.get(k) for k in ('proj','lat_0','lon_0','x_0','y_0','R')):
                    raise TerrainDataError("Confidence raster projection does not match DEM")
                quality = conf.read(1, window=window, boundless=True, fill_value=0)
                values[~np.isin(quality, accepted_codes)] = np.nan
    return LocalGrid(values, transform, crs, resolution, confidence_path is not None)


def roughness(grid: LocalGrid, x: float, y: float, radius_m: float) -> dict:
    """Plane-detrended RMS over an explicitly stated footprint, not boulder counts."""
    offsets = np.arange(-radius_m, radius_m+grid.resolution_m/2,grid.resolution_m)
    dx,dy = np.meshgrid(offsets,offsets)
    inside = dx**2+dy**2 <= radius_m**2
    z = grid.sample(x+dx[inside],y+dy[inside])
    valid = np.isfinite(z)
    result = {"radius_m": radius_m, "valid_fraction": float(valid.mean()),
              "status": "UNQUALIFIED" if not grid.quality_qualified else "INCOMPLETE"}
    if not valid.all() or len(z) < 6:
        return result
    matrix = np.column_stack([dx[inside],dy[inside],np.ones(len(z))])
    fit = np.linalg.lstsq(matrix,z,rcond=None)[0]
    residual = z-matrix@fit
    result.update(plane_slope_deg=float(np.degrees(np.arctan(np.hypot(*fit[:2])))),
                  detrended_rms_m=float(np.sqrt(np.mean(residual**2))),
                  detrended_peak_to_peak_m=float(np.ptp(residual)))
    if grid.quality_qualified:
        result['status'] = 'SAMPLED_TERRAIN_ONLY'
    return result


def trace_local(grid: LocalGrid, longitude: float, latitude: float, height_m: float,
                azimuths, radius_m=500.) -> dict:
    azimuths = np.asarray(azimuths,dtype=float)
    if azimuths.ndim != 1 or not np.isfinite(azimuths).all() or len(azimuths)>40000:
        raise TerrainDataError("Invalid or oversized azimuth list")
    if not np.isfinite(height_m) or height_m <= 0 or not 2*grid.resolution_m <= radius_m <= 1000:
        raise TerrainDataError("Invalid height or local ray radius")
    project = Transformer.from_crs(GEOGRAPHIC,grid.crs,always_xy=True)
    x,y = project.transform(longitude,latitude)
    anchor = float(grid.sample(x,y))
    if not np.isfinite(anchor):
        raise TerrainDataError("Observer is outside confidence-qualified elevation coverage")
    # Subpixel sampling interpolates native data; it does NOT improve resolution.
    distances = np.arange(grid.resolution_m,radius_m+1e-8,grid.resolution_m/2)
    result = trace_distances(grid, longitude, latitude, height_m, azimuths, distances, anchor)
    return {"observer_elevation_m": anchor, "observer_height_m": height_m,
            "minimum_distance_m": grid.resolution_m, "maximum_distance_m": radius_m,
            "radial_step_m": grid.resolution_m/2, "rays": result}


def trace_distances(grid, longitude, latitude, height_m, azimuths, distances, anchor):
    """Trace one scale with a caller-specified, shared observer elevation."""
    azimuths, distances = np.asarray(azimuths,dtype=float),np.asarray(distances,dtype=float)
    if (azimuths.ndim != 1 or distances.ndim != 1 or not len(distances) or
        len(azimuths)>40000 or len(distances)>10000 or
        not np.isfinite(azimuths).all() or not np.isfinite(distances).all() or
        np.any(distances<=0) or np.any(np.diff(distances)<=0) or distances[-1]>200000 or
        not np.isfinite(anchor) or not np.isfinite(height_m) or height_m<=0):
        raise TerrainDataError("Invalid multiscale ray inputs")
    project = Transformer.from_crs(GEOGRAPHIC,grid.crs,always_xy=True)
    result = []
    geod = Geod(a=RADIUS,b=RADIUS)
    for start in range(0,len(azimuths),128):
        az = azimuths[start:start+128]
        azg,dist = np.meshgrid(az,distances,indexing='ij')
        lon,lat,_ = geod.fwd(np.full(azg.shape,longitude),np.full(azg.shape,latitude),azg,dist)
        px,py = project.transform(lon,lat)
        z = grid.sample(px,py)
        valid = np.isfinite(z)
        sigma = dist/RADIUS
        angle = np.degrees(np.arctan2((RADIUS+z)*np.cos(sigma)-(RADIUS+anchor+height_m),
                                      (RADIUS+z)*np.sin(sigma)))
        safe = np.where(valid,angle,-np.inf)
        for i,a in enumerate(az):
            k = int(np.argmax(safe[i]))
            result.append({"azimuth_deg": float(a%360),
                           "sampled_max_elevation_deg": float(safe[i,k]) if valid[i].any() else None,
                           "obstruction_distance_m": float(distances[k]) if valid[i].any() else None,
                           "valid_fraction": float(valid[i].mean()),
                           "complete": bool(valid[i].all() and grid.quality_qualified)})
    return result


def apply_registration(grid: LocalGrid, diagnostic: dict):
    """Apply an internally checked correction without resampling native posts.

    Thresholds are explicit engineering screening rules, not flight accuracy
    certification. Shared-control residuals cannot establish absolute accuracy.
    """
    result = {**diagnostic, 'applied':False, 'application_scope':'LOCAL_500_M_RESEARCH_FUSION',
              'gate_policy':{'minimum_holdout_count':100,'minimum_rmse_reduction_fraction':.2,
                             'maximum_jacobian_condition':10000,'nmad_must_not_increase':True}}
    reasons = []
    if not grid.quality_qualified:
        reasons.append('Fine-scale pixel provenance is not qualified')
    if diagnostic.get('status') != 'REVIEW_REQUIRED' or diagnostic.get('fit_at_bound',True):
        reasons.append('Fit failed or reached translation bounds')
    translation = np.asarray(diagnostic.get('translation_m',[]),dtype=float)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        reasons.append('Translation is invalid')
    elif np.any(abs(translation)>=np.array([19.8,19.8,99.])):
        reasons.append('Translation exceeds application limits')
    before,after = diagnostic.get('holdout_before',{}),diagnostic.get('holdout_after',{})
    if diagnostic.get('holdout_count',0)<100:
        reasons.append('Insufficient held-out samples')
    values = [before.get('rmse_m',np.nan),after.get('rmse_m',np.nan),
              before.get('nmad_m',np.nan),after.get('nmad_m',np.nan)]
    if not np.isfinite(values).all() or values[0]<=0 or values[1]>.8*values[0] or values[3]>values[2]+1e-9:
        reasons.append('Held-out residual improvement gate not met')
    condition = diagnostic.get('jacobian_condition')
    if condition is None or not np.isfinite(condition) or condition>10000:
        reasons.append('Translation fit is underconstrained')
    result['gate_failures'] = reasons
    if reasons:
        result['status'] = 'APPLICATION_REJECTED'
        return grid,result
    dx,dy,dz = translation
    corrected = LocalGrid(grid.values+dz,Affine.translation(-dx,-dy)*grid.transform,
                          grid.crs,grid.resolution_m,grid.quality_qualified)
    result.update(applied=True,status='APPLIED_INTERNAL_CHECKS_ONLY',
                  sample_mapping='corrected(x,y) = original(x+dx,y+dy) + dz')
    return corrected,result


def fuse_rays(near: dict, local: dict, regional: dict, elevation_deg: float) -> dict:
    """Maximum sampled obstruction, preserving unknown near-field coverage."""
    rays = [near,local,regional]
    if not np.isfinite(elevation_deg):
        raise TerrainDataError('Target elevation must be finite')
    present = [(i,r) for i,r in enumerate(rays) if r['sampled_max_elevation_deg'] is not None]
    if not present:
        return {'status':'UNKNOWN','horizon_deg':None,'source':None,'complete':False}
    i,highest = max(present,key=lambda pair:pair[1]['sampled_max_elevation_deg'])
    complete = all(r['complete'] for r in rays)
    status = 'UNKNOWN'
    # Any complete, qualified scale may demonstrate a blockage, but all scales
    # must be complete to report clearance. No missing near-field is filled.
    if any(r['complete'] and r['sampled_max_elevation_deg'] is not None and
           elevation_deg<=r['sampled_max_elevation_deg'] for r in rays):
        status = 'BLOCKED'
    elif complete:
        status = 'CLEAR_SAMPLED_MULTISCALE_DOMAIN'
    return {'status':status,'horizon_deg':highest['sampled_max_elevation_deg'],
            'source':['registered_nac','lola_10m','lola_240m'][i],
            'obstruction_distance_m':highest['obstruction_distance_m'],'complete':complete}


def classify_local(ray: dict, target_elevation_deg: float) -> str:
    # Unqualified or incomplete terrain must never produce a clear decision.
    if not ray['complete']:
        return 'UNKNOWN'
    return 'BLOCKED' if target_elevation_deg <= ray['sampled_max_elevation_deg'] else 'CLEAR_SAMPLED_LOCAL_DOMAIN'


def coregistration_diagnostic(reference, moving, x, y, spacing_m=10.) -> dict:
    """Bounded translation fit with spatial holdout; never auto-apply the fit.

    Both inputs use the same projection. Residuals include differing resolution,
    interpolation, correlated LOLA controls and actual DTM error. They are not
    independent accuracy estimates. A failed/edge fit is explicitly flagged.
    """
    offsets = np.arange(-500,501,spacing_m)
    dx,dy = np.meshgrid(offsets,offsets)
    xx,yy = x+dx.ravel(),y+dy.ravel()
    base = reference.sample(xx,yy)
    # Common valid samples for all allowed shifts avoid optimizing data selection.
    valid = np.isfinite(base)
    for sx in (-20,0,20):
        for sy in (-20,0,20):
            valid &= np.isfinite(moving.sample(xx+sx,yy+sy))
    xx,yy,base = xx[valid],yy[valid],base[valid]
    if len(base)<100:
        return {"status":"INSUFFICIENT_OVERLAP", "sample_count":len(base), "applied":False}
    train = ((np.floor((xx-x)/100)+np.floor((yy-y)/100)).astype(int)%2)==0
    if min(train.sum(),(~train).sum())<40:
        return {"status":"INSUFFICIENT_HOLDOUT", "applied":False}
    def residual(p, subset):
        values = moving.sample(xx[subset]+p[0],yy[subset]+p[1])+p[2]-base[subset]
        return np.where(np.isfinite(values),values,1e4)
    initial = float(np.median(base-moving.sample(xx,yy)))
    fit = least_squares(lambda p:residual(p,train),[0,0,np.clip(initial,-100,100)],
                        bounds=([-20,-20,-100],[20,20,100]),loss='soft_l1',diff_step=.01,max_nfev=100)
    def stats(values):
        return {"median_m":float(np.median(values)), "nmad_m":float(1.4826*np.median(abs(values-np.median(values)))),
                "rmse_m":float(np.sqrt(np.mean(values**2)))}
    before,after = stats(residual([0,0,0],~train)),stats(residual(fit.x,~train))
    at_bound = bool(np.any(abs(fit.x)>=np.array([19.8,19.8,99.])))
    condition = float(np.linalg.cond(fit.jac))
    return {"status":"REVIEW_REQUIRED" if fit.success and not at_bound else "FIT_REJECTED",
            "applied":False, "shift_convention":"NAC(x+dx,y+dy)+dz compared with LOLA(x,y)",
            "translation_m":fit.x.tolist(), "fit_at_bound":at_bound,
            "training_count":int(train.sum()), "holdout_count":int((~train).sum()),
            "holdout_before":before,"holdout_after":after,
            "jacobian_condition":condition if np.isfinite(condition) else None,
            "independent_accuracy_validation":False}
