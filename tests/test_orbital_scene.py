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
        for i in (0,144,504,1008,4464,8784,13248):
            row=data['samples'][i]
            et=spice.str2et(row['utc'])
            rotation=spice.pxform(data['frame'],'J2000',et)
            for name in ('EARTH','SUN'):
                independent=spice.spkpos(name,et,'J2000','NONE','MOON')[0]
                # Scale by vector length: platform float differences reach ~1e-13
                # relative on the ~1.5e8 km Sun vector, beyond a fixed 1e-6 km.
                error=np.linalg.norm(rotation @ row[f'{name.lower()}_km']-independent)
                assert error<=1e-6+1e-12*np.linalg.norm(independent)
            body=np.array(row['earth_fixed_to_scene']).reshape(3,3)
            # Windows libm differs by up to ~5e-12; 1e-10 rad is still sub-mm at Earth's surface.
            assert np.allclose(rotation @ body,spice.pxform('IAU_EARTH','J2000',et),atol=1e-10,rtol=0)
