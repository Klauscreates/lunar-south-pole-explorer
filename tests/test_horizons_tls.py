"""The live Horizons adapter must never relax HTTPS certificate validation."""

from __future__ import annotations

import json
import ssl
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from science.ephemeris.horizons import HorizonsEphemerisProvider


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def read(self):
        return json.dumps({"signature": {"source": "JPL"}}).encode("utf-8")


class HorizonsTLSTests(unittest.TestCase):
    def test_horizons_uses_a_verifying_ca_context(self):
        with TemporaryDirectory() as directory:
            provider = HorizonsEphemerisProvider(Path(directory))
            with patch(
                "science.ephemeris.horizons.urllib.request.urlopen",
                return_value=_Response(),
            ) as urlopen:
                provider._fetch({"format": "json"})
            context = urlopen.call_args.kwargs["context"]
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertGreater(len(context.get_ca_certs()), 0)


if __name__ == "__main__":
    unittest.main()
