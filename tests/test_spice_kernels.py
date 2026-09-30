import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from science.ephemeris.kernels import (
    DEFAULT_MANIFEST_PATH,
    KernelDownloadError,
    KernelIntegrityError,
    KernelManifest,
    KernelMissingError,
    KernelRepository,
    KernelSpec,
)

KINDS = ("LSK", "PCK-TEXT", "PCK-BINARY", "FK", "SPK")


class _FakeResponse:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self._stream = io.BytesIO(payload)
        self._final_url = final_url
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self) -> str:
        return self._final_url

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _test_manifest() -> tuple[KernelManifest, dict[str, bytes]]:
    payloads = {
        f"test-{kind.lower()}.ker": f"locked test payload for {kind}".encode()
        for kind in KINDS
    }
    specs = tuple(
        KernelSpec(
            filename=filename,
            kind=kind,
            role=f"test {kind}",
            url=f"https://naif.jpl.nasa.gov/pub/naif/test/{filename}",
            size_bytes=len(payloads[filename]),
            sha256=hashlib.sha256(payloads[filename]).hexdigest(),
        )
        for kind, filename in zip(KINDS, payloads, strict=True)
    )
    manifest = KernelManifest(
        path=Path("test-kernels.lock.json"),
        sha256="0" * 64,
        manifest_id="unit-test",
        source_authority="NASA/JPL NAIF",
        reference_frame_name="MOON_ME_DE440_ME421",
        reference_frame_id=31009,
        reference_frame_center_id=301,
        binary_pck_frame_id=31008,
        kernels=specs,
    )
    manifest.validate()
    return manifest, payloads


def _write_all(directory: Path, payloads: dict[str, bytes]) -> None:
    for filename, payload in payloads.items():
        (directory / filename).write_bytes(payload)


class KernelManifestTests(unittest.TestCase):
    def test_tracked_manifest_locks_complete_de440_lunar_set(self):
        manifest = KernelManifest.load(DEFAULT_MANIFEST_PATH)

        self.assertEqual(manifest.reference_frame_name, "MOON_ME_DE440_ME421")
        self.assertEqual(manifest.reference_frame_id, 31009)
        self.assertEqual(manifest.reference_frame_center_id, 301)
        self.assertEqual(manifest.binary_pck_frame_id, 31008)
        self.assertEqual({spec.kind for spec in manifest.kernels}, set(KINDS))
        self.assertTrue(all(len(spec.sha256) == 64 for spec in manifest.kernels))
        self.assertTrue(
            all(
                spec.url.startswith("https://naif.jpl.nasa.gov/")
                for spec in manifest.kernels
            )
        )


class KernelRepositoryTests(unittest.TestCase):
    def test_verify_rejects_same_size_corruption_without_network(self):
        manifest, payloads = _test_manifest()
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            _write_all(directory, payloads)
            first = manifest.kernels[0]
            (directory / first.filename).write_bytes(b"x" * first.size_bytes)

            def unexpected_network(*args, **kwargs):
                raise AssertionError("verify() attempted network access")

            repository = KernelRepository(
                directory,
                manifest=manifest,
                auto_download=True,
                opener=unexpected_network,
            )
            with self.assertRaisesRegex(KernelIntegrityError, "SHA-256 mismatch"):
                repository.verify()

            self.assertTrue(repository.auto_download)

    def test_verify_reports_missing_kernel_without_network(self):
        manifest, _payloads = _test_manifest()
        with tempfile.TemporaryDirectory() as raw_directory:
            calls = []

            def unexpected_network(*args, **kwargs):
                calls.append((args, kwargs))
                raise AssertionError("verify() attempted network access")

            repository = KernelRepository(
                Path(raw_directory),
                manifest=manifest,
                opener=unexpected_network,
            )
            with self.assertRaises(KernelMissingError):
                repository.verify()
            self.assertEqual(calls, [])

    def test_resolve_atomically_installs_matching_download(self):
        manifest, payloads = _test_manifest()
        missing = manifest.kernels[0]
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            _write_all(directory, payloads)
            (directory / missing.filename).unlink()

            def opener(request, timeout):
                self.assertGreater(timeout, 0.0)
                return _FakeResponse(payloads[missing.filename], request.full_url)

            resolved = KernelRepository(
                directory,
                manifest=manifest,
                opener=opener,
            ).resolve()

            self.assertEqual(len(resolved), len(KINDS))
            self.assertEqual(
                (directory / missing.filename).read_bytes(),
                payloads[missing.filename],
            )
            self.assertEqual(list(directory.glob(".*.part")), [])

    def test_resolve_rejects_same_host_http_redirect(self):
        manifest, payloads = _test_manifest()
        missing = manifest.kernels[0]
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            _write_all(directory, payloads)
            destination = directory / missing.filename
            destination.unlink()

            def opener(_request, timeout):
                self.assertGreater(timeout, 0.0)
                downgraded = (
                    f"http://naif.jpl.nasa.gov/pub/naif/test/{missing.filename}"
                )
                return _FakeResponse(payloads[missing.filename], downgraded)

            repository = KernelRepository(
                directory,
                manifest=manifest,
                opener=opener,
            )
            with self.assertRaisesRegex(
                KernelDownloadError,
                "trusted NAIF HTTPS origin",
            ):
                repository.resolve()

            self.assertFalse(destination.exists())
            self.assertEqual(list(directory.glob(".*.part")), [])


if __name__ == "__main__":
    unittest.main()
