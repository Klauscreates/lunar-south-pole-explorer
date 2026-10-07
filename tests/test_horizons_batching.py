"""Large date ranges retain a gap-free grid and each upstream provenance record."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from science.config import SiteConfig, TimeRangeConfig
from science.ephemeris.horizons import HorizonsEphemerisProvider
from science.errors import EphemerisError


class BatchedFixture(HorizonsEphemerisProvider):
    corrupt = False

    def _get(self, target_id, target_name, site, terrain, period):
        step = timedelta(minutes=period.step_minutes)
        count = (period.end_utc-period.start_utc)//step+1
        if count > 9000:
            return super()._get(target_id,target_name,site,terrain,period)
        timestamps = [period.start_utc+i*step for i in range(count)]
        if self.corrupt:
            timestamps[-1] = timestamps[0]
        return [SimpleNamespace(timestamp=t) for t in timestamps], {
            'ephemeris_source':'DE441', 'raw_cache_file':period.start_utc.isoformat(),
            'sample_count':count,
        }


class HorizonsBatchTests(unittest.TestCase):
    def test_quarter_and_single_epoch_tail_have_no_gaps_or_duplicates(self):
        with TemporaryDirectory() as directory:
            provider = BatchedFixture(Path(directory))
            start = datetime(2026,10,1,tzinfo=timezone.utc)
            for count in (9000,9001,13249,18001):
                period = TimeRangeConfig(start,start+timedelta(minutes=10*(count-1)),10)
                rows, metadata = provider.get_sun_positions(SiteConfig(),0,period)
                self.assertEqual(len(rows),count)
                self.assertEqual([r.timestamp for r in rows],[start+timedelta(minutes=10*i) for i in range(count)])
                if count>9000:
                    self.assertEqual(sum(b['sample_count'] for b in metadata['batches']),count)
                    self.assertTrue(all(b['raw_cache_file'] for b in metadata['batches']))

    def test_corrupt_batch_is_rejected(self):
        with TemporaryDirectory() as directory:
            provider = BatchedFixture(Path(directory))
            provider.corrupt = True
            with self.assertRaisesRegex(EphemerisError,'incomplete or unordered'):
                provider.get_earth_positions(SiteConfig(),0,TimeRangeConfig(
                    datetime(2026,10,1,tzinfo=timezone.utc),datetime(2027,1,1,tzinfo=timezone.utc),10))
