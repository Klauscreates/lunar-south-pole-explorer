"""Opt-in, hardware-specific spacecraft self-occlusion geometry.

No spacecraft shape, landing attitude, antenna, or solar-cell location is
inferred. A caller must supply a checksum-pinned tessellated mesh and named
sensor samples. This is finite-sample ray geometry, not flight certification,
thermal analysis, RF gain, or a terrain-horizon calculation.

The body frame is right-handed: +X right, +Y forward, +Z up. At zero attitude
these axes align with local East, North, Up. Yaw is clockwise from North for
the body +Y axis; positive pitch raises the nose (+Y); positive roll lowers
the right side (+X). Column vectors transform body -> ENU by
Rz(-yaw) @ Rx(pitch) @ Ry(roll), in that order.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from science.errors import ConfigurationError


Vec3 = tuple[float, float, float]
MAX_MANIFEST_BYTES = 512_000
MAX_MESH_BYTES = 32_000_000
MAX_TRIANGLES = 100_000
MAX_VERTICES = 300_000
MAX_PANEL_SAMPLES = 1024
MAX_TOTAL_PANEL_SAMPLES = 4096
MAX_PANELS = 128
MAX_ANTENNAS = 128
MAX_COORDINATE_M = 1000.0
RAY_MIN_DISTANCE_M = 1e-9
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SHA_RE = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True, slots=True)
class PanelSamples:
    id: str
    area_m2: float
    normal_body: Vec3
    sample_points_m: tuple[Vec3, ...]
    sample_weights: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class AntennaPhaseCenter:
    id: str
    phase_center_m: Vec3


@dataclass(frozen=True, slots=True)
class _Triangle:
    a: Vec3
    edge1: Vec3
    edge2: Vec3
    minimum: Vec3
    maximum: Vec3
    centroid: Vec3
    obstruction_id: str


@dataclass(frozen=True, slots=True)
class _BVHNode:
    minimum: Vec3
    maximum: Vec3
    left: _BVHNode | None
    right: _BVHNode | None
    indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SpacecraftGeometry:
    model_id: str
    provenance: Mapping[str, str]
    manifest_sha256: str
    mesh_sha256: str
    mesh_format: str
    mesh_scale_to_m: float
    panels: tuple[PanelSamples, ...]
    antennas: tuple[AntennaPhaseCenter, ...]
    triangle_count: int
    _triangles: tuple[_Triangle, ...]
    _bvh: _BVHNode


@dataclass(slots=True)
class RaycastBudget:
    """Bound total BVH-node visits and triangle tests across a run."""

    max_work_units: int
    used_work_units: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_work_units, bool)
            or not isinstance(self.max_work_units, int)
            or self.max_work_units <= 0
            or self.used_work_units != 0
        ):
            raise ConfigurationError("RaycastBudget requires a positive integer cap")

    def charge(self) -> None:
        self.used_work_units += 1
        if self.used_work_units > self.max_work_units:
            raise ConfigurationError(
                "Spacecraft raycast work budget exceeded; reduce mesh or sensor sampling"
            )


def load_spacecraft_geometry(
    manifest_path: Path, *, allowed_root: Path | None = None
) -> SpacecraftGeometry:
    """Load a checksum-pinned OBJ or STL and an explicit sensor manifest.

Both manifest and mesh must remain under ``allowed_root`` when provided; by
default the mesh must remain under the manifest's directory. File and mesh
complexity caps make malformed or hostile input fail closed before ray work.
    """
    try:
        manifest = Path(manifest_path).resolve(strict=True)
        root = Path(allowed_root).resolve(strict=True) if allowed_root else manifest.parent
    except OSError as exc:
        raise ConfigurationError(f"Spacecraft manifest/root cannot be resolved: {exc}") from exc
    _require_contained(manifest, root)
    manifest_bytes = _read_capped(manifest, MAX_MANIFEST_BYTES)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        data = json.loads(
            manifest_bytes,
            parse_constant=lambda constant: _reject_constant(constant),
            object_pairs_hook=_unique_object,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise ConfigurationError(f"Invalid spacecraft manifest JSON: {exc}") from exc
    _keys(data, {"schema_version", "model_id", "provenance", "mesh", "panels", "antennas"})
    if data["schema_version"] != "1.0.0":
        raise ConfigurationError("Unsupported spacecraft manifest schema_version")
    model_id = _identifier(data["model_id"], "model_id")
    provenance = _provenance(data["provenance"])

    mesh = data["mesh"]
    _keys(mesh, {"path", "sha256", "format", "units", "scale_to_m"})
    if mesh["units"] != "m":
        raise ConfigurationError("Mesh units must be explicit meters ('m')")
    scale = _positive_finite(mesh["scale_to_m"], "mesh.scale_to_m")
    mesh_format = mesh["format"]
    if mesh_format not in ("obj", "stl"):
        raise ConfigurationError("Mesh format must be 'obj' or 'stl'")
    expected_sha = mesh["sha256"]
    if not isinstance(expected_sha, str) or not _SHA_RE.fullmatch(expected_sha):
        raise ConfigurationError("Mesh sha256 must be a 64-character hex digest")
    mesh_path = _safe_relative_path(mesh["path"], manifest.parent, root)
    mesh_bytes = _read_capped(mesh_path, MAX_MESH_BYTES)
    actual_sha = hashlib.sha256(mesh_bytes).hexdigest()
    if actual_sha != expected_sha.lower():
        raise ConfigurationError("Spacecraft mesh SHA-256 does not match manifest")
    raw_triangles = (
        _parse_obj(mesh_bytes, scale) if mesh_format == "obj" else _parse_stl(mesh_bytes, scale)
    )
    triangles = tuple(_make_triangle(*item) for item in raw_triangles)
    if not triangles:
        raise ConfigurationError("Spacecraft mesh contains no triangles")
    panels = _parse_panels(data["panels"])
    if sum(len(panel.sample_points_m) for panel in panels) > MAX_TOTAL_PANEL_SAMPLES:
        raise ConfigurationError("Spacecraft panels exceed total sample cap")
    antennas = _parse_antennas(data["antennas"])
    if not panels and not antennas:
        raise ConfigurationError("At least one panel or antenna sensor is required")
    return SpacecraftGeometry(
        model_id=model_id,
        provenance=provenance,
        manifest_sha256=manifest_sha,
        mesh_sha256=actual_sha,
        mesh_format=mesh_format,
        mesh_scale_to_m=scale,
        panels=panels,
        antennas=antennas,
        triangle_count=len(triangles),
        _triangles=triangles,
        _bvh=_build_bvh(triangles, tuple(range(len(triangles)))),
    )


def evaluate_spacecraft_geometry(
    model: SpacecraftGeometry,
    *,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
    earth_azimuth_deg: float,
    earth_elevation_deg: float,
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    include_samples: bool = True,
    budget: RaycastBudget | None = None,
) -> dict[str, Any]:
    """Evaluate Sun self-shadow and Earth-center self-LOS in body coordinates.

    ``illuminated_sample_fraction`` includes panel back-face incidence, but
    excludes terrain, partial solar disk, thermal response, and electronics.
    ``effective_direct_area_m2`` is area × cosine × unoccluded fraction.
    The Earth result is a *center-ray* self-occlusion only, not an RF link.
    """
    if not isinstance(model, SpacecraftGeometry):
        raise ConfigurationError("A loaded SpacecraftGeometry is required")
    if not isinstance(include_samples, bool):
        raise ConfigurationError("include_samples must be boolean")
    if budget is not None and not isinstance(budget, RaycastBudget):
        raise ConfigurationError("budget must be a RaycastBudget")
    sun_enu = _enu_direction(sun_azimuth_deg, sun_elevation_deg, "Sun")
    earth_enu = _enu_direction(earth_azimuth_deg, earth_elevation_deg, "Earth")
    attitude = _body_to_enu(yaw_deg, pitch_deg, roll_deg)
    sun_body = _transpose_multiply(attitude, sun_enu)
    earth_body = _transpose_multiply(attitude, earth_enu)

    panels: list[dict[str, Any]] = []
    for panel in model.panels:
        cosine = min(1.0, max(0.0, _dot(panel.normal_body, sun_body)))
        if cosine < 1e-12:
            cosine = 0.0
        samples = [] if include_samples else None
        unoccluded_fraction = 0.0
        obstructions: set[str] = set()
        for point, weight in zip(panel.sample_points_m, panel.sample_weights):
            hit = _nearest_hit(model, point, sun_body, budget)
            clear = hit is None
            if clear:
                unoccluded_fraction += weight
            else:
                obstructions.add(hit[0])
            if samples is not None:
                samples.append(
                    {
                        "clear": clear,
                        "weight": weight,
                        "obstruction_id": None if clear else hit[0],
                        "hit_distance_m": None if clear else hit[1],
                    }
                )
        # Avoid a 1.0000000000000002 fraction from valid rounded weights.
        unoccluded_fraction = min(1.0, max(0.0, unoccluded_fraction))
        panel_result = {
                "id": panel.id,
                "ray_target": "SUN_CENTER",
                "area_m2": panel.area_m2,
                "sample_count": len(panel.sample_points_m),
                "normal_body": list(panel.normal_body),
                "incidence_cosine": cosine,
                "unoccluded_sample_fraction": unoccluded_fraction,
                "illuminated_sample_fraction": unoccluded_fraction if cosine > 0.0 else 0.0,
                "effective_direct_area_m2": panel.area_m2 * cosine * unoccluded_fraction,
                "obstruction_ids": sorted(obstructions),
            }
        if samples is not None:
            panel_result["samples"] = samples
        panels.append(panel_result)

    antennas: list[dict[str, Any]] = []
    for antenna in model.antennas:
        hit = _nearest_hit(model, antenna.phase_center_m, earth_body, budget)
        antennas.append(
            {
                "id": antenna.id,
                "ray_target": "EARTH_CENTER",
                "self_los_clear": hit is None,
                "obstruction_ids": [] if hit is None else [hit[0]],
                "hit_distance_m": None if hit is None else hit[1],
            }
        )
    return {
        "model_status": "CONFIGURED_UNVALIDATED",
        "model_id": model.model_id,
        "provenance": dict(model.provenance),
        "manifest_sha256": model.manifest_sha256,
        "mesh_sha256": model.mesh_sha256,
        "mesh_format": model.mesh_format,
        "mesh_scale_to_m": model.mesh_scale_to_m,
        "triangle_count": model.triangle_count,
        "attitude_deg": {"yaw": yaw_deg, "pitch": pitch_deg, "roll": roll_deg},
        "attitude_convention": "body_X_right_Y_forward_Z_up; Rz(-yaw) Rx(pitch) Ry(roll); ENU",
        "sun_center_direction_body": list(sun_body),
        "earth_center_direction_body": list(earth_body),
        "panel_sampling_scope": "finite weighted center-ray sample approximation; not continuous self-shadow or full solar disk",
        "antenna_scope": "Earth-center ray self-occlusion only; not Earth-disk clearance, terrain visibility, antenna gain, or RF link budget",
        "ray_min_distance_m": RAY_MIN_DISTANCE_M,
        "panels": panels,
        "antennas": antennas,
    }


def _reject_constant(constant: str) -> None:
    raise ValueError(f"Non-finite JSON constant {constant} is prohibited")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _keys(value: Any, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ConfigurationError(f"Expected exactly these fields: {sorted(expected)}")


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ConfigurationError(f"{field} must be a stable ASCII identifier")
    return value


def _provenance(value: Any) -> Mapping[str, str]:
    if not isinstance(value, dict) or not {"source", "revision", "spacecraft"} <= value.keys():
        raise ConfigurationError("provenance requires source, revision, spacecraft")
    if any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or not v.strip()
        or len(v) > 512
        for k, v in value.items()
    ):
        raise ConfigurationError("provenance entries must be nonempty short strings")
    return dict(value)


def _positive_finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field} must be a finite positive number")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ConfigurationError(f"{field} must be a finite positive number") from exc
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ConfigurationError(f"{field} must be a finite positive number")
    return numeric


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{field} must be finite")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ConfigurationError(f"{field} must be finite") from exc
    if not math.isfinite(numeric):
        raise ConfigurationError(f"{field} must be finite")
    return numeric


def _vec3(value: Any, field: str, *, coordinate: bool = True) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ConfigurationError(f"{field} must be a three-vector")
    vector = tuple(_finite(item, field) for item in value)
    if coordinate and any(abs(component) > MAX_COORDINATE_M for component in vector):
        raise ConfigurationError(f"{field} exceeds {MAX_COORDINATE_M:g} m coordinate cap")
    return vector  # type: ignore[return-value]


def _safe_relative_path(raw: Any, base: Path, root: Path) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw:
        raise ConfigurationError("mesh.path must be a relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ConfigurationError("mesh.path must not be absolute or traverse directories")
    try:
        resolved = (base / raw).resolve(strict=True)
    except OSError as exc:
        raise ConfigurationError(f"Spacecraft mesh cannot be resolved: {exc}") from exc
    _require_contained(resolved, root)
    return resolved


def _require_contained(path: Path, root: Path) -> None:
    if not path.is_relative_to(root):
        raise ConfigurationError(f"Spacecraft input escapes allowed root: {path}")
    if not path.is_file():
        raise ConfigurationError(f"Spacecraft input is not a regular file: {path}")


def _read_capped(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ConfigurationError(f"Spacecraft input exceeds {limit} byte cap: {path}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ConfigurationError(f"Spacecraft input exceeds {limit} byte cap: {path}")
    return data


def _parse_panels(value: Any) -> tuple[PanelSamples, ...]:
    if not isinstance(value, list) or len(value) > MAX_PANELS:
        raise ConfigurationError("panels must be an array within the panel cap")
    result: list[PanelSamples] = []
    ids: set[str] = set()
    for item in value:
        _keys(item, {"id", "area_m2", "normal_body", "sample_points_m", "sample_weights"})
        panel_id = _identifier(item["id"], "panel.id")
        if panel_id in ids:
            raise ConfigurationError(f"Duplicate panel id: {panel_id}")
        ids.add(panel_id)
        area = _positive_finite(item["area_m2"], f"panel {panel_id} area_m2")
        normal = _vec3(item["normal_body"], f"panel {panel_id} normal_body", coordinate=False)
        norm = _norm(normal)
        if not 1.0 - 1e-6 <= norm <= 1.0 + 1e-6:
            raise ConfigurationError(f"panel {panel_id} normal_body must be unit length")
        normal = tuple(component / norm for component in normal)
        points_raw = item["sample_points_m"]
        weights_raw = item["sample_weights"]
        if (
            not isinstance(points_raw, list)
            or not 1 <= len(points_raw) <= MAX_PANEL_SAMPLES
            or not isinstance(weights_raw, list)
            or len(weights_raw) != len(points_raw)
        ):
            raise ConfigurationError(f"panel {panel_id} requires matching finite sample points and weights")
        points = tuple(_vec3(point, f"panel {panel_id} sample point") for point in points_raw)
        weights = tuple(_positive_finite(weight, f"panel {panel_id} sample weight") for weight in weights_raw)
        total_weight = math.fsum(weights)
        if abs(total_weight - 1.0) > 1e-9:
            raise ConfigurationError(f"panel {panel_id} sample weights must sum to one")
        weights = tuple(weight / total_weight for weight in weights)
        result.append(PanelSamples(panel_id, area, normal, points, weights))
    return tuple(result)


def _parse_antennas(value: Any) -> tuple[AntennaPhaseCenter, ...]:
    if not isinstance(value, list) or len(value) > MAX_ANTENNAS:
        raise ConfigurationError("antennas must be an array within the antenna cap")
    result: list[AntennaPhaseCenter] = []
    ids: set[str] = set()
    for item in value:
        _keys(item, {"id", "phase_center_m"})
        antenna_id = _identifier(item["id"], "antenna.id")
        if antenna_id in ids:
            raise ConfigurationError(f"Duplicate antenna id: {antenna_id}")
        ids.add(antenna_id)
        result.append(AntennaPhaseCenter(antenna_id, _vec3(item["phase_center_m"], "antenna phase_center_m")))
    return tuple(result)


def _parse_obj(data: bytes, scale: float) -> Iterable[tuple[Vec3, Vec3, Vec3, str]]:
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigurationError("OBJ mesh must be UTF-8 text") from exc
    vertices: list[Vec3] = []
    triangles: list[tuple[Vec3, Vec3, Vec3, str]] = []
    component = "mesh"
    for line_number, raw in enumerate(lines, 1):
        parts = raw.split("#", 1)[0].split()
        if not parts:
            continue
        tag, *values = parts
        if tag == "v":
            if len(values) != 3:
                raise ConfigurationError(f"OBJ line {line_number}: only 3D vertices are supported")
            vertex = _vec3([_parse_float(value, f"OBJ line {line_number}") * scale for value in values], f"OBJ line {line_number}")
            vertices.append(vertex)
            if len(vertices) > MAX_VERTICES:
                raise ConfigurationError("OBJ exceeds vertex cap")
        elif tag in ("o", "g"):
            if values:
                component = _identifier("_".join(values), f"OBJ line {line_number} component")
        elif tag == "f":
            if len(values) != 3:
                raise ConfigurationError(f"OBJ line {line_number}: mesh must be tessellated triangles")
            face: list[Vec3] = []
            for token in values:
                index_token = token.split("/", 1)[0]
                try:
                    index = int(index_token)
                except ValueError as exc:
                    raise ConfigurationError(f"OBJ line {line_number}: malformed face index") from exc
                index = index - 1 if index > 0 else len(vertices) + index
                if index < 0 or index >= len(vertices):
                    raise ConfigurationError(f"OBJ line {line_number}: face index outside vertices")
                face.append(vertices[index])
            triangles.append((face[0], face[1], face[2], component))
            if len(triangles) > MAX_TRIANGLES:
                raise ConfigurationError("OBJ exceeds triangle cap")
        elif tag in ("vt", "vn", "s", "usemtl", "mtllib"):
            continue
        else:
            raise ConfigurationError(f"OBJ line {line_number}: unsupported directive {tag}")
    return triangles


def _parse_stl(data: bytes, scale: float) -> Iterable[tuple[Vec3, Vec3, Vec3, str]]:
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            if count > MAX_TRIANGLES:
                raise ConfigurationError("STL exceeds triangle cap")
            triangles = []
            for index in range(count):
                floats = struct.unpack_from("<12f", data, 84 + index * 50)
                vertices = tuple(
                    _vec3([value * scale for value in floats[start : start + 3]], "binary STL vertex")
                    for start in (3, 6, 9)
                )
                triangles.append((*vertices, "mesh"))
            return triangles
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ConfigurationError("STL is neither valid binary nor ASCII") from exc
    triangles: list[tuple[Vec3, Vec3, Vec3, str]] = []
    component = "mesh"
    facet: list[Vec3] | None = None
    for line_number, raw in enumerate(lines, 1):
        parts = raw.strip().split()
        if not parts:
            continue
        tag = parts[0].lower()
        if tag == "solid":
            if facet is not None:
                raise ConfigurationError(f"STL line {line_number}: nested solid")
            if len(parts) > 1:
                component = _identifier("_".join(parts[1:]), "STL solid name")
        elif tag == "facet":
            if facet is not None or len(parts) != 5 or parts[1].lower() != "normal":
                raise ConfigurationError(f"STL line {line_number}: malformed facet")
            for value in parts[2:]:
                _parse_float(value, f"STL line {line_number} normal")
            facet = []
        elif tag == "vertex":
            if facet is None or len(parts) != 4 or len(facet) >= 3:
                raise ConfigurationError(f"STL line {line_number}: malformed vertex")
            facet.append(_vec3([_parse_float(v, f"STL line {line_number}") * scale for v in parts[1:]], "ASCII STL vertex"))
        elif tag == "endfacet":
            if facet is None or len(facet) != 3:
                raise ConfigurationError(f"STL line {line_number}: incomplete facet")
            triangles.append((facet[0], facet[1], facet[2], component))
            if len(triangles) > MAX_TRIANGLES:
                raise ConfigurationError("STL exceeds triangle cap")
            facet = None
        elif tag in ("outer", "endloop", "endsolid"):
            continue
        else:
            raise ConfigurationError(f"STL line {line_number}: unsupported directive {tag}")
    if facet is not None:
        raise ConfigurationError("STL has an unfinished facet")
    return triangles


def _parse_float(value: str, field: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{field} has a nonnumeric coordinate") from exc
    return _finite(numeric, field)


def _make_triangle(a: Vec3, b: Vec3, c: Vec3, obstruction_id: str) -> _Triangle:
    edge1 = _subtract(b, a)
    edge2 = _subtract(c, a)
    if _norm(_cross(edge1, edge2)) <= 1e-18:
        raise ConfigurationError("Spacecraft mesh has a zero-area or near-degenerate triangle")
    return _Triangle(
        a, edge1, edge2,
        tuple(min(a[i], b[i], c[i]) for i in range(3)),
        tuple(max(a[i], b[i], c[i]) for i in range(3)),
        tuple((a[i] + b[i] + c[i]) / 3.0 for i in range(3)),
        obstruction_id,
    )


def _build_bvh(triangles: Sequence[_Triangle], indices: tuple[int, ...]) -> _BVHNode:
    minimum = tuple(min(triangles[i].minimum[axis] for i in indices) for axis in range(3))
    maximum = tuple(max(triangles[i].maximum[axis] for i in indices) for axis in range(3))
    if len(indices) <= 8:
        return _BVHNode(minimum, maximum, None, None, indices)
    spread = [max(triangles[i].centroid[axis] for i in indices) - min(triangles[i].centroid[axis] for i in indices) for axis in range(3)]
    axis = max(range(3), key=lambda candidate: spread[candidate])
    ordered = sorted(indices, key=lambda index: triangles[index].centroid[axis])
    mid = len(ordered) // 2
    return _BVHNode(
        minimum, maximum,
        _build_bvh(triangles, tuple(ordered[:mid])),
        _build_bvh(triangles, tuple(ordered[mid:])),
        (),
    )


def _nearest_hit(
    model: SpacecraftGeometry,
    origin: Vec3,
    direction: Vec3,
    budget: RaycastBudget | None = None,
) -> tuple[str, float] | None:
    nearest = math.inf
    obstruction: str | None = None
    stack = [model._bvh]
    while stack:
        if budget is not None:
            budget.charge()
        node = stack.pop()
        if not _ray_box_intersects(origin, direction, node.minimum, node.maximum, nearest):
            continue
        if node.indices:
            for index in node.indices:
                if budget is not None:
                    budget.charge()
                triangle = model._triangles[index]
                distance = _ray_triangle_distance(origin, direction, triangle)
                if distance is not None and distance < nearest:
                    nearest = distance
                    obstruction = triangle.obstruction_id
        else:
            if node.left is not None:
                stack.append(node.left)
            if node.right is not None:
                stack.append(node.right)
    return None if obstruction is None else (obstruction, nearest)


def _ray_box_intersects(origin: Vec3, direction: Vec3, minimum: Vec3, maximum: Vec3, nearest: float) -> bool:
    near = RAY_MIN_DISTANCE_M
    far = nearest
    for axis in range(3):
        if abs(direction[axis]) < 1e-15:
            if origin[axis] < minimum[axis] - 1e-12 or origin[axis] > maximum[axis] + 1e-12:
                return False
            continue
        t1 = (minimum[axis] - origin[axis]) / direction[axis]
        t2 = (maximum[axis] - origin[axis]) / direction[axis]
        near = max(near, min(t1, t2))
        far = min(far, max(t1, t2))
        if far < near:
            return False
    return True


def _ray_triangle_distance(origin: Vec3, direction: Vec3, triangle: _Triangle) -> float | None:
    cross = _cross(direction, triangle.edge2)
    determinant = _dot(triangle.edge1, cross)
    tolerance = 1e-14 * _norm(triangle.edge1) * _norm(triangle.edge2)
    if abs(determinant) <= tolerance:
        return None
    inverse = 1.0 / determinant
    displacement = _subtract(origin, triangle.a)
    u = _dot(displacement, cross) * inverse
    if u < -1e-12 or u > 1.0 + 1e-12:
        return None
    q = _cross(displacement, triangle.edge1)
    v = _dot(direction, q) * inverse
    if v < -1e-12 or u + v > 1.0 + 1e-12:
        return None
    distance = _dot(triangle.edge2, q) * inverse
    return distance if distance > RAY_MIN_DISTANCE_M else None


def _enu_direction(azimuth_deg: float, elevation_deg: float, label: str) -> Vec3:
    azimuth = _finite(azimuth_deg, f"{label} azimuth_deg")
    elevation = _finite(elevation_deg, f"{label} elevation_deg")
    if not -90.0 <= elevation <= 90.0:
        raise ConfigurationError(f"{label} elevation_deg must be in [-90, 90]")
    if not 0.0 <= azimuth <= 360.0:
        raise ConfigurationError(f"{label} azimuth_deg must be in [0, 360]")
    azimuth_rad, elevation_rad = math.radians(azimuth), math.radians(elevation)
    return (
        math.cos(elevation_rad) * math.sin(azimuth_rad),
        math.cos(elevation_rad) * math.cos(azimuth_rad),
        math.sin(elevation_rad),
    )


def _body_to_enu(yaw_deg: float, pitch_deg: float, roll_deg: float) -> tuple[Vec3, Vec3, Vec3]:
    yaw = _finite(yaw_deg, "yaw_deg")
    pitch = _finite(pitch_deg, "pitch_deg")
    roll = _finite(roll_deg, "roll_deg")
    if abs(yaw) > 360.0:
        raise ConfigurationError("Landing yaw must be within [-360, 360] degrees")
    if abs(pitch) > 90.0 or abs(roll) > 90.0:
        raise ConfigurationError("Landing pitch/roll must each be within [-90, 90] degrees")
    yaw, pitch, roll = map(math.radians, (-yaw, pitch, roll))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    # Rows of Rz(yaw) @ Rx(pitch) @ Ry(roll).
    return (
        (cy * cr - sy * sp * sr, -sy * cp, cy * sr + sy * sp * cr),
        (sy * cr + cy * sp * sr, cy * cp, sy * sr - cy * sp * cr),
        (-cp * sr, sp, cp * cr),
    )


def _transpose_multiply(matrix: tuple[Vec3, Vec3, Vec3], vector: Vec3) -> Vec3:
    return tuple(sum(matrix[row][column] * vector[row] for row in range(3)) for column in range(3))  # type: ignore[return-value]


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _subtract(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _norm(vector: Vec3) -> float:
    return math.sqrt(_dot(vector, vector))
