import unittest
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin
from pyproj import CRS

from science.terrain.nearfield import (LocalGrid, classify_local, coregistration_diagnostic,
                                     read_local_grid, roughness, trace_local, apply_registration, fuse_rays)

CRS_MOON = CRS.from_proj4('+proj=stere +lat_0=-90 +lon_0=0 +R=1737400 +units=m')


class NearfieldTests(unittest.TestCase):
    def grid(self, qualified=True):
        return LocalGrid(np.zeros((200,200)),from_origin(-100,100,1,1),CRS_MOON,1,qualified)

    def test_five_meter_obstruction_blocks_low_target(self):
        grid = self.grid()
        grid.values[78:83,98:103] = 5
        ray = trace_local(grid,0,-90,2,[0],radius_m=50)['rays'][0]
        self.assertTrue(ray['complete'])
        self.assertGreater(ray['sampled_max_elevation_deg'],7)
        self.assertEqual(classify_local(ray,2),'BLOCKED')
        self.assertEqual(classify_local(ray,20),'CLEAR_SAMPLED_LOCAL_DOMAIN')

    def test_nodata_does_not_become_clear(self):
        grid = self.grid()
        grid.values[70:72,:] = np.nan
        ray = trace_local(grid,0,-90,2,[0],radius_m=50)['rays'][0]
        self.assertFalse(ray['complete'])
        self.assertEqual(classify_local(ray,80),'UNKNOWN')

    def test_unqualified_sfs_never_classifies_clear(self):
        ray = trace_local(self.grid(False),0,-90,2,[0],radius_m=50)['rays'][0]
        self.assertEqual(ray['valid_fraction'],1)
        self.assertEqual(classify_local(ray,20),'UNKNOWN')

    def test_plane_roughness_and_missing_support(self):
        grid = self.grid()
        rows,cols = np.indices(grid.values.shape)
        grid.values = cols*.1 + rows*.2
        result = roughness(grid,0,0,10)
        self.assertLess(result['detrended_rms_m'],1e-12)
        self.assertAlmostEqual(result['plane_slope_deg'],np.degrees(np.arctan(np.sqrt(.05))))
        grid.values[99,99] = np.nan
        self.assertNotIn('detrended_rms_m',roughness(grid,0,0,10))

    def test_observer_in_gap_rejected(self):
        grid=self.grid()
        grid.values[99:101,99:101]=np.nan
        with self.assertRaisesRegex(Exception,'Observer'):
            trace_local(grid,0,-90,2,[0],radius_m=50)

    def test_coregistration_recovers_known_translation(self):
        rows,cols=np.indices((800,800))
        x,y=-800+(cols+.5)*2,800-(rows+.5)*2
        def shape(x,y):
            return 20*np.sin(x/70)+30*np.cos(y/90)+.0001*x*y
        transform=from_origin(-800,800,2,2)
        ref=LocalGrid(shape(x,y),transform,CRS_MOON,2,True)
        moving=LocalGrid(shape(x-4,y+6)+3,transform,CRS_MOON,2,True)
        result=coregistration_diagnostic(ref,moving,0,0)
        np.testing.assert_allclose(result['translation_m'],[4,-6,-3],atol=.02)
        self.assertFalse(result['applied'])
        self.assertFalse(result['independent_accuracy_validation'])
        corrected,applied=apply_registration(moving,result)
        self.assertTrue(applied['applied'])
        np.testing.assert_allclose(corrected.sample(np.array([0,10]),np.array([0,20])),
                                   ref.sample(np.array([0,10]),np.array([0,20])),atol=.01)
        np.testing.assert_array_equal(moving.values,shape(x-4,y+6)+3)

    def test_registration_gate_rejects_unqualified_or_bad_fit(self):
        valid={'status':'REVIEW_REQUIRED','fit_at_bound':False,'translation_m':[1,2,3],
               'holdout_count':100,'jacobian_condition':10,
               'holdout_before':{'rmse_m':2,'nmad_m':1},'holdout_after':{'rmse_m':1,'nmad_m':.5}}
        for change in ({'fit_at_bound':True},{'translation_m':[float('nan'),0,0]},
                       {'jacobian_condition':None},{'holdout_count':50},
                       {'holdout_after':{'rmse_m':1.9,'nmad_m':.5}}):
            _,result=apply_registration(self.grid(),{**valid,**change})
            self.assertFalse(result['applied'])
        _,result=apply_registration(self.grid(False),valid)
        self.assertFalse(result['applied'])

    def test_fusion_never_fills_unknown_nearfield(self):
        near={'complete':False,'sampled_max_elevation_deg':1,'obstruction_distance_m':20}
        distant={'complete':True,'sampled_max_elevation_deg':2,'obstruction_distance_m':5000}
        self.assertEqual(fuse_rays(near,distant,distant,10)['status'],'UNKNOWN')
        self.assertEqual(fuse_rays(near,distant,distant,1)['status'],'BLOCKED')
        near['complete']=True
        self.assertEqual(fuse_rays(near,distant,distant,10)['status'],'CLEAR_SAMPLED_MULTISCALE_DOMAIN')

    def test_native_confidence_codes_are_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            dem,conf=Path(tmp)/'dem.tif',Path(tmp)/'conf.tif'
            profile=dict(driver='GTiff',width=100,height=100,count=1,crs=CRS_MOON,
                         transform=from_origin(-50,50,1,1))
            with rasterio.open(dem,'w',dtype='float32',nodata=-9999,**profile) as dst:
                dst.write(np.zeros((100,100),dtype='float32'),1)
            values=np.full((100,100),14,dtype='uint8')
            values[49:51,49:51]=4
            with rasterio.open(conf,'w',dtype='uint8',nodata=0,**profile) as dst:
                dst.write(values,1)
            grid=read_local_grid(dem,0,-90,radius_m=40,confidence_path=conf)
            self.assertTrue(grid.quality_qualified)
            self.assertTrue(np.isnan(grid.sample(0,0)))
            self.assertEqual(grid.resolution_m,1)

    def test_export_lineage_and_fail_closed_haworth(self):
        root=Path(__file__).resolve().parents[1]
        sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        index=json.loads((root/'outputs/local-terrain/index.json').read_text())
        parents=json.loads((root/'outputs/simulation-index.json').read_text())
        self.assertEqual({s['site_id'] for s in index['sites']},{s['id'] for s in parents['sites']})
        for entry in index['sites']:
            path=root/'outputs/local-terrain'/f"{entry['site_id']}.json"
            self.assertEqual(sha(path),entry['sha256'])
            report=json.loads(path.read_text())
            self.assertFalse(report['landing_safety_certified'])
            self.assertFalse(report['operational_visibility_changed'])
            self.assertEqual(report['manifest_sha256'],sha(root/'data/nac-products.json'))
            for name,value in report['implementation_sha256'].items():
                self.assertEqual(sha(root/name),value)
            parent=next(s for s in parents['sites'] if s['id']==entry['site_id'])
            self.assertEqual(report['parent_sha256'],parent['sha256'])
            if report['status']=='NATIVE_RESOLUTION_DIAGNOSTIC':
                self.assertEqual(len(report['samples']),1009)
                self.assertEqual(report['coregistration']['applied'],entry['site_id']=='connecting-ridge')
                self.assertFalse(report['fusion']['independently_validated'])
                for row in report['samples']:
                    for body in ('sun','earth'):
                        ray=row[body]
                        self.assertEqual(ray['local_status'],classify_local(ray,ray['target_elevation_deg']))
                        if entry['site_id']=='haworth':
                            self.assertEqual(ray['local_status'],'UNKNOWN')
                            self.assertNotIn('fused',ray)
                        else:
                            self.assertIn('fused',ray)
                            if ray['fused']['status']=='CLEAR_SAMPLED_MULTISCALE_DOMAIN':
                                self.assertTrue(ray['fused']['complete'])
                if entry['site_id']=='connecting-ridge':
                    self.assertTrue(any(row['sun']['sampled_max_elevation_deg'] != row['sun']['uncorrected_local_horizon_deg']
                                        for row in report['samples']))


if __name__=='__main__':
    unittest.main()
