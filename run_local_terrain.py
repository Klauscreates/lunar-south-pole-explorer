#!/usr/bin/env python3
"""Build separate NAC near-field studies; do not alter operational LOLA exports."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np
import rasterio
from pyproj import Transformer

from science.terrain.nearfield import (GEOGRAPHIC, classify_local, coregistration_diagnostic,
                                     read_local_grid, roughness, trace_local, LocalGrid,
                                     apply_registration, trace_distances, fuse_rays)
from science.export import write_json

ROOT = Path(__file__).resolve().parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            result.update(chunk)
    return result.hexdigest()


def acquire(record, download):
    folder = ROOT/'data/cache/nac'
    folder.mkdir(parents=True,exist_ok=True)
    path = folder/record['file']
    if path.parent != folder or not record['url'].startswith('https://'):
        raise ValueError('Invalid product path or URL')
    if not path.exists() and download:
        temporary = path.with_suffix(path.suffix+'.download')
        with urllib.request.urlopen(record['url'],timeout=60) as source, temporary.open('wb') as dest:
            total = 0
            while chunk := source.read(1024*1024):
                total += len(chunk)
                if total>800*1024*1024:
                    raise ValueError('Product exceeds 800 MiB download limit')
                dest.write(chunk)
        if digest(temporary)!=record['sha256']:
            raise ValueError('Downloaded source checksum mismatch; not promoted')
        temporary.replace(path)
    if not path.exists() or digest(path)!=record['sha256']:
        raise ValueError(f'Missing or changed source {path}; use --download for missing files')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    args = parser.parse_args()
    manifest_path = ROOT/'data/nac-products.json'
    manifest = json.loads(manifest_path.read_text())
    parents = json.loads((ROOT/'outputs/simulation-index.json').read_text())
    products = {p['site_id']:p for p in manifest['products']}
    out = ROOT/'outputs/local-terrain'
    out.mkdir(parents=True,exist_ok=True)
    entries = []
    for site in parents['sites']:
        path = ROOT/'outputs'/('simulation.json' if site['id']=='test-site-a' else f"candidates/{site['id']}.json")
        if digest(path)!=site['sha256']:
            raise ValueError('Parent simulation checksum mismatch')
        parent = json.loads(path.read_text())
        report = {'schema_version':'1.1.0','site_id':site['id'],'parent_sha256':site['sha256'],
                  'manifest_sha256':digest(manifest_path),'landing_safety_certified':False,
                  'operational_visibility_changed':False,
                  'implementation_sha256':{name:digest(ROOT/name) for name in
                      ['run_local_terrain.py','science/terrain/nearfield.py']},
                  'limitations':['No verified boulder inventory or sub-meter hazard completeness.',
                                 'The first native pixel around the observer is unresolved.',
                                 'Near-field center rays only; no RF, finite disk or landing-safety certification.',
                                 'Registered fusion is a separately labeled research series; main LOLA gauges remain unchanged.',
                                 'Internal residual checks are not independent absolute-accuracy validation.']}
        product = products.get(site['id'])
        if not product:
            report.update(status='NO_QUALIFIED_PRODUCT',reason=manifest['other_sites'][site['id']])
        else:
            files = {k:acquire(product[k],args.download) for k in ('dem','confidence','readme') if k in product}
            lon,lat = parent['site']['longitude_deg_east'],parent['site']['latitude_deg']
            grid = read_local_grid(files['dem'],lon,lat,confidence_path=files.get('confidence'))
            if grid.resolution_m != product['pixel_size_m']:
                raise ValueError('Unexpected native pixel spacing')
            terrain = parent['data_sources']['terrain']['local']
            lola_path = ROOT/'data/processed'/Path(terrain['crop_path']).name
            if digest(lola_path)!=terrain['crop_sha256']:
                raise ValueError('LOLA crop checksum mismatch')
            lola = read_local_grid(lola_path,lon,lat)
            if not grid.crs.equals(lola.crs,ignore_axis_order=True):
                # Lunar CRS names differ. Compare physical projection of controls.
                tx = Transformer.from_crs(lola.crs,grid.crs,always_xy=True)
                a,b = tx.transform([0,1000,-1000],[0,1000,-1000])
                if not np.allclose(a,[0,1000,-1000],atol=1e-6) or not np.allclose(b,[0,1000,-1000],atol=1e-6):
                    raise ValueError('Different projections require explicit reprojection')
            x,y = Transformer.from_crs(GEOGRAPHIC,grid.crs,always_xy=True).transform(lon,lat)
            original_grid = grid
            diagnostic = coregistration_diagnostic(lola,grid,x,y)
            grid,registration = apply_registration(grid,diagnostic)
            report.update(status='NATIVE_RESOLUTION_DIAGNOSTIC',product=product,
                          source_sha256={k:digest(v) for k,v in files.items()},
                          lola_sha256=digest(lola_path),native_pixel_size_m=grid.resolution_m,
                          confidence_qualified=grid.quality_qualified,
                          coregistration=registration,
                          roughness=[roughness(grid,x,y,r) for r in (10,25,50)])
            report['limitations'] += product['limitations']
            all_az = [s[body]['azimuth_deg'] for s in parent['samples'] for body in ('sun','earth')]
            trace = trace_local(grid,lon,lat,parent['site']['observer_height_m'],all_az)
            uncorrected = trace_local(original_grid,lon,lat,parent['site']['observer_height_m'],all_az) if registration['applied'] else trace
            scales = []
            if registration['applied']:
                # Re-raycast both LOLA scales from the corrected observer. Reusing
                # old skyline angles would mix inconsistent observer elevations.
                for scale,distances in [('local',np.arange(500.,10000.1,10.)),
                                        ('outer',np.append(np.arange(10000.,200000.,240.),200000.))]:
                    metadata = parent['data_sources']['terrain'][scale]
                    raster_path = ROOT/'data/processed'/Path(metadata['crop_path']).name
                    if digest(raster_path)!=metadata['crop_sha256']:
                        raise ValueError('Regional LOLA checksum mismatch')
                    with rasterio.open(raster_path) as src:
                        raster_grid = LocalGrid(src.read(1,masked=True).astype(float).filled(np.nan),
                                                src.transform,src.crs,abs(src.transform.a),True)
                    scales.append(trace_distances(raster_grid,lon,lat,parent['site']['observer_height_m'],
                                                  all_az,distances,trace['observer_elevation_m']))
                report['fusion'] = {'status':'APPLIED_RESEARCH_FUSION','independently_validated':False,
                                    'strategy':'registered NAC native pixel–500m; LOLA 10m 500m–10km; LOLA 240m 10–200km; no gap fill',
                                    'observer_elevation_m':trace['observer_elevation_m'],
                                    'lola_outer_sha256':parent['data_sources']['terrain']['outer']['crop_sha256'],
                                    'submeter_elevation_available':False,'measured_boulder_geometry_available':False}
            else:
                report['fusion'] = {'status':'UNAVAILABLE_REGISTRATION_GATE','independently_validated':False}
            report['nearfield'] = {k:v for k,v in trace.items() if k!='rays'}
            report['nearfield']['uncorrected_observer_elevation_m'] = uncorrected['observer_elevation_m']
            report['samples'] = []
            for i,sample in enumerate(parent['samples']):
                row = {'timestamp':sample['timestamp']}
                for j,body in enumerate(('sun','earth')):
                    ray = trace['rays'][2*i+j]
                    # Rebase the source topocentric vector for the changed height,
                    # retaining the source body position and north/east axes.
                    delta = trace['observer_elevation_m']-parent['site']['terrain_elevation_m']
                    distance = sample[body]['distance_km']*1000
                    old_angle = np.radians(sample[body]['elevation_deg'])
                    angle = float(np.degrees(np.arctan2(distance*np.sin(old_angle)-delta,distance*np.cos(old_angle))))
                    row[body] = {**ray,'target_elevation_deg':angle,
                                 'local_status':classify_local(ray,angle),
                                 'uncorrected_local_horizon_deg':uncorrected['rays'][2*i+j]['sampled_max_elevation_deg']}
                    if scales:
                        row[body]['fused'] = fuse_rays(ray,scales[0][2*i+j],scales[1][2*i+j],angle)
                report['samples'].append(row)
            report['nearfield']['source_spacing_is_not_accuracy'] = True
        destination = out/f"{site['id']}.json"
        write_json(report,destination)
        entries.append({'site_id':site['id'],'parent_sha256':site['sha256'],
                        'url':f"/data/local-terrain/{site['id']}.json",'sha256':digest(destination)})
        print(site['name'],report['status'],flush=True)
    write_json({'schema_version':'1.0.0','sites':entries},out/'index.json')


if __name__=='__main__':
    main()
