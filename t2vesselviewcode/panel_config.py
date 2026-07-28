"""Load and validate YAML panel configs (custom_overlay_trio)."""

import os
import shutil
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from . import overlay_colors

ALLOWED_ANGLES = (
    "left",
    "right",
    "anterior",
    "posterior",
    "superior",
    "inferior",
    "surg_left_lat",
    "surg_right_lat",
    "surg_left_ato",
    "surg_right_ato",
)
# YAML bases: t2 auto-picks sag/cor/tra/3d per angle (same rules as multimodal/QMM panels).
ALLOWED_BASES = ("t1", "t2", "flair")
# Concrete T2 planes used internally by the angle resolver (not YAML bases).
T2_PLANE_BASES = ("t2_sag", "t2_cor", "t2_tra", "t2_3d")
MIN_SLOTS = 2
MAX_SLOTS = 4

# Packaged example path (repo examples/ when editable install; also used as fallback text source).
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_EXAMPLE = os.path.abspath(
    os.path.join(_PACKAGE_DIR, "..", "examples", "custom_overlay_trio.yaml")
)


def example_config_path() -> str:
    """Return path to the shipped example YAML if present."""
    return _REPO_EXAMPLE


def write_example_config(destination: str) -> str:
    """Write a starter custom_overlay_trio YAML to destination; return absolute path."""
    dest = os.path.abspath(destination)
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    src = example_config_path()
    if os.path.isfile(src):
        shutil.copyfile(src, dest)
    else:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(_EMBEDDED_EXAMPLE)
    return dest


def opacity_to_mricrogl(opacity: Any, default: int = 35) -> int:
    """Parse YAML opacity as MRIcroGL integer 0–100."""
    if opacity is None:
        return int(default)
    try:
        val = float(opacity)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid opacity value: {opacity!r}") from e
    if not (0.0 <= val <= 100.0):
        raise ValueError(f"Opacity out of range (use 0–100, same as MRIcroGL): {opacity}")
    return int(round(val))


def preferred_t2_plane_for_angle(angle: str) -> str:
    """Return preferred T2 plane key for a viewing angle (package multimodal/QMM rules).

    left/right and surgical views → sagittal;
    anterior/posterior → coronal;
    superior/inferior → transverse.
    """
    key = str(angle).strip().lower()
    if key in (
        "left",
        "right",
        "surg_left_lat",
        "surg_right_lat",
        "surg_left_ato",
        "surg_right_ato",
    ):
        return "t2_sag"
    if key in ("anterior", "posterior"):
        return "t2_cor"
    if key in ("superior", "inferior"):
        return "t2_tra"
    raise ValueError(f"Unknown angle for T2 plane selection: {angle}")


def t2_fallback_planes_for_angle(angle: str) -> List[str]:
    """Ordered T2 plane candidates for an angle: preferred, then t2_3d, then left/right t2_tra."""
    preferred = preferred_t2_plane_for_angle(angle)
    ordered: List[str] = [preferred]
    if "t2_3d" not in ordered:
        ordered.append("t2_3d")
    key = str(angle).strip().lower()
    # Match quant_map_mm left/right tertiary fallback when sag and 3d are missing.
    if key in ("left", "right") and "t2_tra" not in ordered:
        ordered.append("t2_tra")
    return ordered


def resolve_t2_plane_for_angle(
    angle: str,
    available_planes: Sequence[str],
) -> str:
    """Pick the first available T2 plane for an angle from the fallback chain.

    Parameters
    ----------
    angle :
        Viewing angle label.
    available_planes :
        Plane keys that currently have eroded NIfTIs (e.g. ``t2_sag``, ``t2_3d``).

    Returns
    -------
    str
        Chosen plane key.

    Raises
    ------
    ValueError
        If no candidate plane is available.
    """
    available = {str(p).strip().lower() for p in available_planes}
    for plane in t2_fallback_planes_for_angle(angle):
        if plane in available:
            return plane
    raise ValueError(
        f"No T2 eroded data for angle '{angle}'. Tried: "
        f"{', '.join(t2_fallback_planes_for_angle(angle))}."
    )


def group_angles_by_resolved_t2_plane(
    angles: Sequence[str],
    available_planes: Sequence[str],
) -> List[Tuple[str, List[str]]]:
    """Group angles by the resolved T2 plane, preserving first-seen plane order.

    Returns list of (plane_key, angles_for_that_plane).
    """
    groups: Dict[str, List[str]] = {}
    order: List[str] = []
    for ang in angles:
        plane = resolve_t2_plane_for_angle(ang, available_planes)
        if plane not in groups:
            groups[plane] = []
            order.append(plane)
        groups[plane].append(str(ang).strip().lower())
    return [(plane, groups[plane]) for plane in order]


def load_custom_overlay_trio_config(path: str) -> Dict[str, Any]:
    """Load and validate a custom_overlay_trio YAML config.

    Returns
    -------
    dict with keys:
      angles: list[str]
      slots: list[dict] each with base, label, overlays (MRIcroGL-ready specs)
    """
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Panel config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Panel config must be a YAML mapping with 'angles' and 'slots'.")

    angles = raw.get("angles")
    if not angles or not isinstance(angles, list):
        raise ValueError("Panel config must include a non-empty 'angles' list.")
    cleaned_angles: List[str] = []
    for ang in angles:
        key = str(ang).strip().lower()
        if key not in ALLOWED_ANGLES:
            raise ValueError(
                f"Unknown angle '{ang}'. Allowed: {', '.join(ALLOWED_ANGLES)}."
            )
        if key not in cleaned_angles:
            cleaned_angles.append(key)

    slots_raw = raw.get("slots")
    if not isinstance(slots_raw, list):
        raise ValueError("Panel config must include a 'slots' list.")
    if not (MIN_SLOTS <= len(slots_raw) <= MAX_SLOTS):
        raise ValueError(
            f"Panel config must have between {MIN_SLOTS} and {MAX_SLOTS} slots "
            f"(got {len(slots_raw)})."
        )

    slots: List[Dict[str, Any]] = []
    for idx, slot in enumerate(slots_raw):
        if not isinstance(slot, dict):
            raise ValueError(f"Slot {idx} must be a mapping with 'base' and 'overlays'.")
        base = str(slot.get("base", "")).strip().lower()
        if base not in ALLOWED_BASES:
            raise ValueError(
                f"Slot {idx} has unknown base '{slot.get('base')}'. "
                f"Allowed: {', '.join(ALLOWED_BASES)}. "
                "Use base: t2 to auto-select sag/cor/tra/3d per angle."
            )
        overlays_raw = slot.get("overlays") or []
        if not isinstance(overlays_raw, list) or not overlays_raw:
            raise ValueError(f"Slot {idx} ({base}) must include a non-empty 'overlays' list.")

        overlays: List[Dict[str, Any]] = []
        for oidx, ov in enumerate(overlays_raw):
            if not isinstance(ov, dict):
                raise ValueError(f"Slot {idx} overlay {oidx} must be a mapping.")
            ov_path = ov.get("path")
            if not ov_path:
                raise ValueError(f"Slot {idx} overlay {oidx} is missing 'path'.")
            ov_path = os.path.abspath(str(ov_path))
            if not os.path.isfile(ov_path):
                raise FileNotFoundError(
                    f"Slot {idx} ({base}) overlay not found: {ov_path}"
                )
            color_in = ov.get("color", "jet")
            color_val, _ok = overlay_colors.resolve_or_warn(
                color_in,
                overlay_label=f"slot{idx}:{base}/overlay{oidx}",
            )
            name_val = str(ov.get("name") or f"Overlay{oidx + 1}")
            if " " in name_val:
                raise ValueError(
                    f"Slot {idx} overlay name must not contain spaces: {name_val!r}"
                )
            opacity_val = opacity_to_mricrogl(ov.get("opacity", 35))
            min_val = ov.get("min")
            max_val = ov.get("max")
            spec: Dict[str, Any] = {
                "path": ov_path,
                "name": name_val,
                "color": str(color_val),
                "opacity": int(opacity_val),
            }
            if min_val is not None:
                spec["min"] = float(min_val)
            if max_val is not None:
                spec["max"] = float(max_val)
            overlays.append(spec)

        overlay_names = [o["name"] for o in overlays]
        label = f"{base.upper()} + " + " + ".join(overlay_names)
        slots.append(
            {
                "index": idx,
                "base": base,
                "label": label,
                "overlays": overlays,
            }
        )

    return {"angles": cleaned_angles, "slots": slots}


def base_to_eroded_dir(base: str, dir_structure_module) -> str:
    """Map a concrete modality key to its Eroded_nifti directory.

    ``base`` must be ``t1``, ``flair``, or a concrete T2 plane (``t2_sag``, …).
    Use ``resolve_t2_plane_for_angle`` / ``group_angles_by_resolved_t2_plane`` for YAML ``t2``.
    """
    mapping = {
        "t1": dir_structure_module.eroded_nifti_t1_dir,
        "t2_cor": dir_structure_module.eroded_nifti_t2_cor_dir,
        "t2_tra": dir_structure_module.eroded_nifti_t2_tra_dir,
        "t2_sag": dir_structure_module.eroded_nifti_t2_sag_dir,
        "t2_3d": dir_structure_module.eroded_nifti_t2_3d_dir,
        "flair": dir_structure_module.eroded_nifti_flair_dir,
    }
    if base == "t2":
        raise ValueError(
            "base 't2' is angle-dependent; resolve a concrete plane with "
            "resolve_t2_plane_for_angle / group_angles_by_resolved_t2_plane."
        )
    if base not in mapping:
        raise ValueError(f"Unknown base: {base}")
    return mapping[base]


def base_to_glob_pattern(base: str) -> str:
    """Return glob pattern for eroded NIfTIs for a concrete modality key."""
    patterns = {
        "t1": "*eroded*t1*nii.gz",
        "t2_cor": "*eroded*t2_cor*nii.gz",
        "t2_tra": "*eroded*t2_tra*nii.gz",
        "t2_sag": "*eroded*t2_sag*nii.gz",
        "t2_3d": "*eroded*t2_3d*nii.gz",
        "flair": "*eroded*flair*nii.gz",
    }
    if base == "t2":
        raise ValueError(
            "base 't2' is angle-dependent; use a concrete plane key for globs."
        )
    if base not in patterns:
        raise ValueError(f"Unknown base: {base}")
    return patterns[base]


_EMBEDDED_EXAMPLE = """# Custom overlay trio panel config for t2_vessel_view.
#
# Edit paths, then:
#   t2vv_render_existing --source-dir /path/to/T2VesselView \\
#     --panels custom_overlay_trio --panel-config ./my_trio.yaml
#
# Angles: left, right, anterior, posterior, superior, inferior,
#   surg_left_lat, surg_right_lat, surg_left_ato, surg_right_ato
# Bases: t1, t2, flair
#   t2 auto-selects plane per angle (sag L/R/surg, cor A/P, tra S/I; fallback t2_3d).

angles:
  - superior
  - left

slots:
  - base: t1
    overlays:
      - path: /data/pet.nii.gz
        color: jet
        name: PET
        opacity: 60

  - base: t2
    overlays:
      - path: /data/fmri.nii.gz
        color: hot
        name: fMRI
        opacity: 50
      - path: /data/tract1.nii.gz
        color: green
        name: TractA
        opacity: 80

  - base: flair
    overlays:
      - path: /data/overlay_a.nii.gz
        color: electric_blue
        name: OverlayA
        opacity: 50
"""
