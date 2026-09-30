"""Pinned NAIF kernel acquisition, integrity verification, and provenance.

The kernel lock file is the trust boundary for offline ephemeris calculations.
Files are accepted only when both their byte size and SHA-256 match the lock.
Missing files may be downloaded from the HTTPS NAIF origin, streamed into a
same-directory temporary file, verified, and atomically installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from science.errors import EphemerisError

DEFAULT_MANIFEST_PATH = Path(__file__).with_name("kernels.lock.json")
NAIF_DOWNLOAD_HOST = "naif.jpl.nasa.gov"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROCESS_DOWNLOAD_LOCK = threading.RLock()


class KernelError(EphemerisError):
    """Base failure for a pinned SPICE kernel set."""


class KernelManifestError(KernelError):
    """The tracked kernel lock file is invalid or unsafe."""


class KernelMissingError(KernelError):
    """A required pinned kernel is not present locally."""


class KernelIntegrityError(KernelError):
    """A local or downloaded kernel does not match its pinned digest."""


class KernelDownloadError(KernelError):
    """A required kernel could not be securely downloaded."""


@dataclass(frozen=True)
class KernelSpec:
    """Immutable lock-file record for one NAIF kernel."""

    filename: str
    kind: str
    role: str
    url: str
    size_bytes: int
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> KernelSpec:
        try:
            spec = cls(
                filename=str(value["filename"]),
                kind=str(value["kind"]),
                role=str(value["role"]),
                url=str(value["url"]),
                size_bytes=int(value["size_bytes"]),
                sha256=str(value["sha256"]).lower(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise KernelManifestError(
                f"Malformed kernel manifest entry: {value!r}"
            ) from exc
        spec.validate()
        return spec

    def validate(self) -> None:
        if not self.filename or self.filename != Path(self.filename).name:
            raise KernelManifestError(
                f"Kernel filename must be a basename: {self.filename!r}"
            )
        if any(separator in self.filename for separator in ("/", "\\")):
            raise KernelManifestError(
                f"Kernel filename contains a path separator: {self.filename!r}"
            )
        if not self.kind.strip() or not self.role.strip():
            raise KernelManifestError(
                f"Kernel kind and role are required for {self.filename}"
            )
        if self.size_bytes <= 0:
            raise KernelManifestError(
                f"Kernel size must be positive for {self.filename}"
            )
        if not _SHA256_RE.fullmatch(self.sha256):
            raise KernelManifestError(
                f"Invalid SHA-256 for {self.filename}: {self.sha256!r}"
            )
        parsed = urllib.parse.urlparse(self.url)
        if not _is_trusted_naif_https_location(parsed):
            raise KernelManifestError(
                f"Kernel URL must use the trusted NAIF HTTPS origin: {self.url!r}"
            )
        if Path(parsed.path).name != self.filename:
            raise KernelManifestError(
                f"Kernel URL basename does not match {self.filename}: {self.url!r}"
            )


@dataclass(frozen=True)
class KernelManifest:
    """Validated collection of mutually compatible kernel specifications."""

    path: Path
    sha256: str
    manifest_id: str
    source_authority: str
    reference_frame_name: str
    reference_frame_id: int
    reference_frame_center_id: int
    binary_pck_frame_id: int
    kernels: tuple[KernelSpec, ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_MANIFEST_PATH) -> KernelManifest:
        manifest_path = Path(path).resolve()
        try:
            payload = manifest_path.read_bytes()
            raw = json.loads(payload)
        except OSError as exc:
            raise KernelManifestError(
                f"Kernel manifest cannot be read: {manifest_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise KernelManifestError(
                f"Kernel manifest is not valid JSON: {manifest_path}"
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise KernelManifestError(
                f"Unsupported kernel manifest schema in {manifest_path}"
            )
        try:
            frame = raw["reference_frame"]
            entries = raw["kernels"]
            if not isinstance(frame, dict) or not isinstance(entries, list):
                raise TypeError
            kernels = tuple(KernelSpec.from_mapping(entry) for entry in entries)
            manifest = cls(
                path=manifest_path,
                sha256=hashlib.sha256(payload).hexdigest(),
                manifest_id=str(raw["manifest_id"]),
                source_authority=str(raw["source_authority"]),
                reference_frame_name=str(frame["name"]),
                reference_frame_id=int(frame["naif_id"]),
                reference_frame_center_id=int(frame["center_id"]),
                binary_pck_frame_id=int(raw["binary_pck_frame_id"]),
                kernels=kernels,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise KernelManifestError(
                f"Kernel manifest metadata is incomplete: {manifest_path}"
            ) from exc
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not self.manifest_id.strip() or not self.source_authority.strip():
            raise KernelManifestError("Kernel manifest identity is empty")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise KernelManifestError("Kernel manifest SHA-256 is invalid")
        if not self.reference_frame_name.strip():
            raise KernelManifestError("Reference-frame name is empty")
        if self.reference_frame_center_id != 301:
            raise KernelManifestError(
                "The lunar reference frame must be centered on NAIF body 301"
            )
        if not self.kernels:
            raise KernelManifestError("Kernel manifest contains no kernels")
        for spec in self.kernels:
            spec.validate()
        names = [spec.filename for spec in self.kernels]
        if len(names) != len(set(names)):
            raise KernelManifestError("Kernel manifest contains duplicate filenames")
        required_kinds = {"LSK", "PCK-TEXT", "PCK-BINARY", "FK", "SPK"}
        kind_counts = {
            kind: sum(spec.kind == kind for spec in self.kernels)
            for kind in {spec.kind for spec in self.kernels} | required_kinds
        }
        if set(kind_counts) != required_kinds or any(
            count != 1 for count in kind_counts.values()
        ):
            raise KernelManifestError(
                "Kernel manifest must contain exactly one of each required "
                f"kind; found {kind_counts}"
            )

    def spec_by_kind(self, kind: str) -> KernelSpec:
        matches = [spec for spec in self.kernels if spec.kind == kind]
        if len(matches) != 1:
            raise KernelManifestError(
                f"Expected exactly one {kind} kernel, found {len(matches)}"
            )
        return matches[0]


@dataclass(frozen=True)
class VerifiedKernel:
    """A local kernel proven byte-for-byte identical to the lock file."""

    spec: KernelSpec
    path: Path

    def as_provenance(self) -> dict[str, Any]:
        return {
            "filename": self.spec.filename,
            "kind": self.spec.kind,
            "role": self.spec.role,
            "source_url": self.spec.url,
            "local_path": str(self.path.resolve()),
            "size_bytes": self.spec.size_bytes,
            "sha256": self.spec.sha256,
        }


UrlOpener = Callable[..., Any]


class KernelRepository:
    """Resolve a locked kernel set without accepting unverified bytes."""

    def __init__(
        self,
        directory: Path,
        *,
        manifest: KernelManifest | None = None,
        auto_download: bool = True,
        timeout_seconds: float = 60.0,
        lock_timeout_seconds: float = 120.0,
        opener: UrlOpener | None = None,
    ) -> None:
        if timeout_seconds <= 0.0 or lock_timeout_seconds <= 0.0:
            raise ValueError("Kernel timeouts must be positive")
        self.directory = Path(directory).resolve()
        self.manifest = manifest or KernelManifest.load()
        self.manifest.validate()
        self.auto_download = auto_download
        self.timeout_seconds = timeout_seconds
        self.lock_timeout_seconds = lock_timeout_seconds
        self._opener = opener or urllib.request.urlopen

    def resolve(self) -> tuple[VerifiedKernel, ...]:
        """Return the complete verified set, downloading only missing files."""
        return self._resolve(allow_download=self.auto_download)

    def verify(self) -> tuple[VerifiedKernel, ...]:
        """Verify all files without allowing network access."""
        return self._resolve(allow_download=False)

    def _resolve(self, *, allow_download: bool) -> tuple[VerifiedKernel, ...]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with _exclusive_download_lock(
            self.directory / ".kernel-download.lock",
            self.lock_timeout_seconds,
        ):
            resolved = tuple(
                self._resolve_one(spec, allow_download=allow_download)
                for spec in self.manifest.kernels
            )
        return resolved

    def _resolve_one(
        self,
        spec: KernelSpec,
        *,
        allow_download: bool,
    ) -> VerifiedKernel:
        path = self.directory / spec.filename
        if path.is_symlink():
            raise KernelIntegrityError(f"Refusing symbolic-link kernel path: {path}")
        if path.exists():
            self._verify_path(path, spec)
            return VerifiedKernel(spec=spec, path=path)
        if not allow_download:
            raise KernelMissingError(
                f"Required kernel is missing: {path}. Run "
                f"`python -m science.ephemeris.kernels {self.directory}` "
                "to download the locked set."
            )
        self._download_atomic(path, spec)
        self._verify_path(path, spec)
        return VerifiedKernel(spec=spec, path=path)

    @staticmethod
    def _verify_path(path: Path, spec: KernelSpec) -> None:
        try:
            stat = path.stat()
        except OSError as exc:
            raise KernelIntegrityError(f"Cannot stat kernel: {path}") from exc
        if not path.is_file():
            raise KernelIntegrityError(f"Kernel path is not a regular file: {path}")
        if stat.st_size != spec.size_bytes:
            raise KernelIntegrityError(
                f"Kernel size mismatch for {path.name}: expected "
                f"{spec.size_bytes}, found {stat.st_size}"
            )
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != spec.sha256:
            raise KernelIntegrityError(
                f"Kernel SHA-256 mismatch for {path.name}: expected "
                f"{spec.sha256}, found {actual_sha256}"
            )

    def _download_atomic(self, destination: Path, spec: KernelSpec) -> None:
        request = urllib.request.Request(
            spec.url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": "LunarMissionPlanner/0.1 pinned-naif-kernels",
            },
        )
        temporary_path: Path | None = None
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                final_location = urllib.parse.urlparse(final_url)
                if not _is_trusted_naif_https_location(final_location):
                    raise KernelDownloadError(
                        "Refusing kernel redirect away from the trusted NAIF "
                        f"HTTPS origin: {final_url}"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError as exc:
                        raise KernelDownloadError(
                            f"Invalid Content-Length for {spec.filename}: "
                            f"{content_length!r}"
                        ) from exc
                    if declared_size != spec.size_bytes:
                        raise KernelIntegrityError(
                            f"NAIF Content-Length changed for {spec.filename}: "
                            f"expected {spec.size_bytes}, received {declared_size}"
                        )

                digest = hashlib.sha256()
                byte_count = 0
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{spec.filename}.",
                    suffix=".part",
                    dir=self.directory,
                    delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        byte_count += len(chunk)
                        if byte_count > spec.size_bytes:
                            raise KernelIntegrityError(
                                f"Download exceeded locked size for {spec.filename}"
                            )
                        digest.update(chunk)
                        temporary.write(chunk)
                    temporary.flush()
                    os.fsync(temporary.fileno())

                if byte_count != spec.size_bytes:
                    raise KernelIntegrityError(
                        f"Downloaded size mismatch for {spec.filename}: expected "
                        f"{spec.size_bytes}, received {byte_count}"
                    )
                actual_sha256 = digest.hexdigest()
                if actual_sha256 != spec.sha256:
                    raise KernelIntegrityError(
                        f"Downloaded SHA-256 mismatch for {spec.filename}: expected "
                        f"{spec.sha256}, received {actual_sha256}"
                    )
                os.chmod(temporary_path, 0o644)
                os.replace(temporary_path, destination)
                temporary_path = None
                _fsync_directory(self.directory)
        except (KernelError, KeyboardInterrupt):
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KernelDownloadError(
                f"Failed to download pinned NAIF kernel {spec.filename}: {exc}"
            ) from exc
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_trusted_naif_https_location(
    location: urllib.parse.ParseResult,
) -> bool:
    try:
        port = location.port
    except ValueError:
        return False
    return (
        location.scheme == "https"
        and location.hostname == NAIF_DOWNLOAD_HOST
        and port in (None, 443)
        and location.username is None
        and location.password is None
    )


def _fsync_directory(path: Path) -> None:
    """Best-effort durability for the atomic rename."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


@contextmanager
def _exclusive_download_lock(path: Path, timeout_seconds: float) -> Iterator[None]:
    """Serialize downloads across processes on POSIX and threads elsewhere."""
    with _PROCESS_DOWNLOAD_LOCK:
        try:
            import fcntl  # POSIX only
        except ImportError:
            yield
            return

        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise KernelDownloadError(
                            f"Timed out waiting for kernel download lock: {path}"
                        ) from exc
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _provenance_document(
    manifest: KernelManifest,
    kernels: Sequence[VerifiedKernel],
) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_path": str(manifest.path),
        "manifest_sha256": manifest.sha256,
        "source_authority": manifest.source_authority,
        "reference_frame": manifest.reference_frame_name,
        "kernels": [kernel.as_provenance() for kernel in kernels],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download and SHA-256 verify the locked NASA/JPL NAIF kernels."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default="data/kernels",
        type=Path,
        help="kernel cache directory (default: data/kernels)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="fail if a kernel is missing instead of downloading it",
    )
    args = parser.parse_args(argv)
    repository = KernelRepository(
        args.directory,
        auto_download=not args.verify_only,
    )
    kernels = repository.resolve()
    print(
        json.dumps(
            _provenance_document(repository.manifest, kernels),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
