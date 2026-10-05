"""Independent frame checks of the checked-in orbital visualization export."""
import json
from pathlib import Path
import numpy as np
import spiceypy as spice
from science.ephemeris.kernels import KernelRepository
from science.ephemeris.spice import _isolated_kernel_pool

ROOT=Path(__file__).resolve().parents[1]


def test_orbital_positions_and_attitude_match_inertial_spice_chain():
    data=json.loads((ROOT/'outputs/orbital-scene.json').read_text())
    kernels=KernelRepository(ROOT/'data/kernels',auto_download=False).resolve()
    with _isolated_kernel_pool(spice,kernels):
        for i in (0,144,504,1008):
            row=data['samples'][i]
            et=spice.str2et(row['utc'])
            rotation=spice.pxform(data['frame'],'J2000',et)
            for name in ('EARTH','SUN'):
                independent=spice.spkpos(name,et,'J2000','NONE','MOON')[0]
                assert np.allclose(rotation @ row[f'{name.lower()}_km'],independent,atol=1e-6,rtol=0)
            body=np.array(row['earth_fixed_to_scene']).reshape(3,3)
            assert np.allclose(rotation @ body,spice.pxform('IAU_EARTH','J2000',et),atol=1e-12,rtol=0)
