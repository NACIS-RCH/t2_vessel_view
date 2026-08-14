"""Load and validate YAML configuration for the custom overlay panel.

This module is intentionally independent of commandline, dir_structure, the
main pipeline, and rendering modules. Keeping it dependency-light prevents the
YAML feature from changing the package's existing CLI import order.
"""

import os
import math
import re
from typing import Any, Dict, List, Optional

import yaml

from . import overlay_colors
from . import extra_images


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
ALLOWED_BASES = ("t1", "t2", "flair")
MIN_SLOTS = 2
MAX_SLOTS = 4
ROW_NAMES = ("top", "bottom")
DEFAULT_SLICE_ERODE_DEPTH = 35
DEFAULT_CUSTOM_PPTX_NAME = "custom_overlay_panels"

# [label, brain azimuth, brain elevation, clip azimuth, clip elevation]
ANGLE_SPECS = {
    "left": ("left", 90, 0, 270, 0),
    "right": ("right", 270, 0, 90, 0),
    "anterior": ("anterior", 180, 0, 180, 0),
    "posterior": ("posterior", 0, -10, 0, -10),
    "superior": ("superior", 0, 90, 0, 90),
    "inferior": ("inferior", 180, -90, 0, -90),
    "surg_left_lat": ("surg_left_lat", 270, 180, 90, 180),
    "surg_right_lat": ("surg_right_lat", 90, 180, 270, 180),
    "surg_left_ato": ("surg_left_ato", 300, 175, 225, 0),
    "surg_right_ato": ("surg_right_ato", 60, 175, 125, 0),
}

T2_CANDIDATES_BY_ANGLE = {
    "left": ("t2_sag_left", "t2_sag_generic", "t2_3d", "t2_tra"),
    "right": ("t2_sag_right", "t2_sag_generic", "t2_3d", "t2_tra"),
    "anterior": ("t2_cor", "t2_3d"),
    "posterior": ("t2_cor", "t2_3d"),
    "superior": ("t2_tra", "t2_3d"),
    "inferior": ("t2_tra", "t2_3d"),
    "surg_left_lat": ("t2_sag_left", "t2_sag_generic", "t2_3d"),
    "surg_right_lat": ("t2_sag_right", "t2_sag_generic", "t2_3d"),
    "surg_left_ato": ("t2_sag_left", "t2_sag_generic", "t2_3d"),
    "surg_right_ato": ("t2_sag_right", "t2_sag_generic", "t2_3d"),
}

ANGLE_T2_FAMILY = {
    "left": "sag_left",
    "right": "sag_right",
    "anterior": "cor",
    "posterior": "cor",
    "superior": "tra",
    "inferior": "tra",
    "surg_left_lat": "sag_left",
    "surg_right_lat": "sag_right",
    "surg_left_ato": "sag_left",
    "surg_right_ato": "sag_right",
}
EXACT_ANGLE_TIE_TOLERANCE_DEGREES = 1e-9


def parse_slice_erode_depth(value: Any = None) -> Dict[str, Any]:
    """Validate a YAML slice depth and return integer plus padded prefix.

    The integer uses the existing erosion filename units: 35 maps to prefix
    ``035`` (3.5 mm). Quoted digit strings are accepted to make leading-zero
    intent explicit without relying on YAML's numeric parsing rules.
    """
    if value is None:
        depth = DEFAULT_SLICE_ERODE_DEPTH
    elif isinstance(value, bool):
        raise ValueError("slice_erode_depth must be a non-negative integer.")
    elif isinstance(value, int):
        depth = value
    elif isinstance(value, str) and value.strip().isdigit():
        depth = int(value.strip(), 10)
    else:
        raise ValueError(
            "slice_erode_depth must be a non-negative integer "
            "(for example, 35 for prefix 035)."
        )
    if depth < 0:
        raise ValueError("slice_erode_depth must be a non-negative integer.")
    return {
        "slice_erode_depth": depth,
        "slice_erode_prefix": f"{depth:03d}",
    }


def parse_custom_pptx_name(value: Any = None) -> str:
    """Validate a safe custom-panel PPTX basename and strip its extension."""
    if value is None:
        return DEFAULT_CUSTOM_PPTX_NAME
    name = str(value).strip()
    if name.lower().endswith(".pptx"):
        name = name[:-5].rstrip()
    if not name:
        raise ValueError("pptx_name must not be empty.")
    if name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(
            "pptx_name must be a filename only, not a path."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*", name):
        raise ValueError(
            "pptx_name may contain letters, numbers, spaces, underscores, "
            "hyphens, and periods."
        )
    return name


def angle_rows(angles: List[str]) -> List[List[Any]]:
    """Return MRIcroGL camera/clip rows in requested order."""
    rows: List[List[Any]] = []
    for angle in angles:
        key = str(angle).strip().lower()
        if key not in ANGLE_SPECS:
            raise ValueError(f"Unknown angle: {angle}")
        rows.append(list(ANGLE_SPECS[key]))
    return rows


def viewing_direction(azimuth, elevation) -> List[float]:
    """Convert MRIcroGL display angles to a spherical unit direction."""
    azimuth_radians = math.radians(float(azimuth))
    elevation_radians = math.radians(float(elevation))
    cos_elevation = math.cos(elevation_radians)
    return [
        cos_elevation * math.cos(azimuth_radians),
        cos_elevation * math.sin(azimuth_radians),
        math.sin(elevation_radians),
    ]


def angular_distance_degrees(first, second) -> float:
    """Return spherical angular distance between two unit directions."""
    dot = sum(a * b for a, b in zip(first, second))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def nearest_angle_families(brain_az, brain_el) -> Dict[str, Any]:
    """Return nearest existing T2 families for a new display direction."""
    custom_direction = viewing_direction(brain_az, brain_el)
    records = []
    for label, row in ANGLE_SPECS.items():
        direction = viewing_direction(row[1], row[2])
        records.append({
            "label": label,
            "family": ANGLE_T2_FAMILY[label],
            "distance": angular_distance_degrees(
                custom_direction,
                direction,
            ),
        })
    minimum = min(record["distance"] for record in records)
    tied_records = [
        record for record in records
        if abs(record["distance"] - minimum)
        <= EXACT_ANGLE_TIE_TOLERANCE_DEGREES
    ]
    families = []
    representatives = {}
    for record in tied_records:
        family = record["family"]
        if family not in representatives:
            families.append(family)
            representatives[family] = record["label"]
    return {
        "distance": minimum,
        "families": families,
        "representatives": representatives,
        "labels": [record["label"] for record in tied_records],
    }


def _first_available(candidates, available):
    """Return the first candidate present in an available-source set."""
    return next(
        (candidate for candidate in candidates if candidate in available),
        None,
    )


def infer_custom_angle_t2_source(
    brain_az,
    brain_el,
    available_sources: List[str],
) -> Dict[str, Any]:
    """Infer one T2 source using nearest direction and exact-tie rules."""
    available = {str(source).strip().lower() for source in available_sources}
    nearest = nearest_angle_families(brain_az, brain_el)
    families = list(nearest["families"])

    if len(families) == 1:
        representative = nearest["representatives"][families[0]]
        candidates = t2_candidates_for_angle(representative)
        source = _first_available(candidates, available)
        if source is None:
            raise ValueError(
                "No usable T2 source for nearest angle "
                f"'{representative}' (tried: {', '.join(candidates)})."
            )
        return {
            **nearest,
            "ambiguous": False,
            "source": source,
            "candidates": candidates,
        }

    if "t2_3d" in available:
        return {
            **nearest,
            "ambiguous": True,
            "source": "t2_3d",
            "candidates": ["t2_3d"],
        }

    family_set = set(families)
    # When both sides are equally close, neither unilateral sagittal source is
    # anatomically safe; generic sagittal is also skipped by user preference.
    both_sag_sides = {"sag_left", "sag_right"} <= family_set
    sagittal_candidates = []
    if not both_sag_sides:
        if "sag_left" in family_set:
            sagittal_candidates = ["t2_sag_left", "t2_sag_generic"]
        elif "sag_right" in family_set:
            sagittal_candidates = ["t2_sag_right", "t2_sag_generic"]
    sagittal_source = _first_available(sagittal_candidates, available)
    transverse_source = "t2_tra" if "t2_tra" in available else None
    coronal_source = "t2_cor" if "t2_cor" in available else None

    has_sag_family = bool(
        {"sag_left", "sag_right"} & family_set
    ) and not both_sag_sides
    has_tra_family = "tra" in family_set
    has_cor_family = "cor" in family_set

    ordered_sources = []
    if has_sag_family and has_tra_family and has_cor_family:
        ordered_sources = [
            sagittal_source,
            transverse_source,
            coronal_source,
        ]
    elif has_sag_family and has_tra_family:
        ordered_sources = [
            sagittal_source,
            transverse_source,
            coronal_source,
        ]
    elif has_tra_family and has_cor_family:
        ordered_sources = [coronal_source, transverse_source]
    elif has_sag_family and has_cor_family:
        ordered_sources = [sagittal_source, coronal_source]
    else:
        # This includes left/right sagittal ties where sagittal was disabled.
        ordered_sources = [transverse_source, coronal_source]

    source = next(
        (candidate for candidate in ordered_sources if candidate is not None),
        None,
    )
    if source is None:
        raise ValueError(
            "No usable T2 source for ambiguous custom angle; nearest "
            f"families: {', '.join(families)}."
        )
    return {
        **nearest,
        "ambiguous": True,
        "source": source,
        "candidates": [
            candidate for candidate in ordered_sources
            if candidate is not None
        ],
    }


def t2_candidates_for_angle(angle: str) -> List[str]:
    """Return ordered concrete T2 source keys for one view."""
    key = str(angle).strip().lower()
    if key not in T2_CANDIDATES_BY_ANGLE:
        raise ValueError(f"Unknown angle for T2 selection: {angle}")
    return list(T2_CANDIDATES_BY_ANGLE[key])


def resolve_t2_sources(
    angles: List[str],
    available_sources: List[str],
) -> Dict[str, str]:
    """Resolve every requested angle to an available concrete T2 source.

    Resolution is all-or-nothing: if one or more angles cannot resolve, this
    function raises before rendering so the custom panel is never partial.
    """
    available = {str(source).strip().lower() for source in available_sources}
    resolved: Dict[str, str] = {}
    missing_messages: List[str] = []
    for angle in angles:
        key = str(angle).strip().lower()
        candidates = t2_candidates_for_angle(key)
        chosen = next(
            (candidate for candidate in candidates if candidate in available),
            None,
        )
        if chosen is None:
            missing_messages.append(
                f"{key} (tried: {', '.join(candidates)})"
            )
        else:
            resolved[key] = chosen
    if missing_messages:
        raise ValueError(
            "No usable T2 eroded data for requested angle(s): "
            + "; ".join(missing_messages)
            + "."
        )
    return resolved


def group_angles_by_t2_source(
    angles: List[str],
    resolved_sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Group ordered angles by concrete T2 source, preserving first use."""
    grouped: Dict[str, List[str]] = {}
    source_order: List[str] = []
    for angle in angles:
        key = str(angle).strip().lower()
        source = resolved_sources[key]
        if source not in grouped:
            grouped[source] = []
            source_order.append(source)
        grouped[source].append(key)
    return [
        {"source": source, "angles": grouped[source]}
        for source in source_order
    ]


def _parse_opacity(value: Any, slot_index: int, overlay_index: int) -> int:
    """Return MRIcroGL opacity as an integer from 0 to 100."""
    if isinstance(value, bool):
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: opacity must be an "
            "integer from 0 to 100."
        )
    try:
        opacity_float = float(value)
        opacity = int(opacity_float)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: invalid opacity {value!r}."
        ) from exc
    if opacity_float != opacity or not 0 <= opacity <= 100:
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: opacity must be an "
            "integer from 0 to 100."
        )
    return opacity


def _resolve_overlay_path(raw_path: Any, config_dir: str) -> str:
    """Resolve an overlay path relative to the YAML file."""
    if raw_path is None or not str(raw_path).strip():
        raise ValueError("Overlay path must not be empty.")
    path = os.path.expanduser(str(raw_path).strip())
    if not os.path.isabs(path):
        path = os.path.join(config_dir, path)
    return os.path.abspath(path)


def _validate_window(
    minimum: Any,
    maximum: Any,
    slot_index: int,
    overlay_index: int,
) -> Dict[str, float]:
    """Validate optional paired min/max values and return normalized fields."""
    if (minimum is None) != (maximum is None):
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: min and max must be "
            "provided together, or both omitted for automatic estimation."
        )
    if minimum is None:
        return {}
    try:
        minimum_float = float(minimum)
        maximum_float = float(maximum)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: min and max must be numeric."
        ) from exc
    if maximum_float <= minimum_float:
        raise ValueError(
            f"Slot {slot_index} overlay {overlay_index}: max must be greater "
            f"than min (got min={minimum_float}, max={maximum_float})."
        )
    return {"min": minimum_float, "max": maximum_float}


def _normalize_slot_layout(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize legacy one-row or explicit top/bottom YAML slot layout."""
    has_slots = "slots" in raw
    has_rows = "rows" in raw
    if has_slots == has_rows:
        raise ValueError(
            "Panel config must include exactly one of 'slots' (one row) "
            "or 'rows' (top and bottom)."
        )

    entries: List[Dict[str, Any]] = []
    if has_slots:
        raw_slots = raw.get("slots")
        if not isinstance(raw_slots, list):
            raise ValueError("Panel config 'slots' must be a list.")
        if not MIN_SLOTS <= len(raw_slots) <= MAX_SLOTS:
            raise ValueError(
                f"One-row panel config must contain {MIN_SLOTS} to "
                f"{MAX_SLOTS} slots (got {len(raw_slots)})."
            )
        for column, raw_slot in enumerate(raw_slots):
            entries.append({
                "row": "top",
                "column": column,
                "raw_slot": raw_slot,
            })
        return entries

    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, dict):
        raise ValueError("Panel config 'rows' must be a top/bottom mapping.")
    row_keys = set(raw_rows)
    missing = [name for name in ROW_NAMES if name not in row_keys]
    unknown = sorted(row_keys - set(ROW_NAMES))
    if missing or unknown:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        raise ValueError(
            "Panel config rows must contain exactly 'top' and 'bottom' "
            f"({'; '.join(details)})."
        )
    for row_name in ROW_NAMES:
        raw_slots = raw_rows[row_name]
        if not isinstance(raw_slots, list):
            raise ValueError(f"Panel row '{row_name}' must be a list.")
        if not 1 <= len(raw_slots) <= MAX_SLOTS:
            raise ValueError(
                f"Panel row '{row_name}' must contain 1 to {MAX_SLOTS} "
                f"slots (got {len(raw_slots)})."
            )
        for column, raw_slot in enumerate(raw_slots):
            entries.append({
                "row": row_name,
                "column": column,
                "raw_slot": raw_slot,
            })
    return entries


def load_custom_overlay_panels_config(
    path: str,
    extra_base_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Load and validate a ``custom_overlay_panels`` YAML file.

    Relative overlay paths are resolved relative to the YAML file. Returned
    angles and slots preserve user order; duplicate angle labels are removed.
    Overlay images are assumed to already be aligned with their structural base.
    """
    if not path:
        raise ValueError("A panel config path is required.")
    config_path = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Panel config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    if not isinstance(raw, dict):
        raise ValueError(
            "Panel config must be a YAML mapping containing 'angles' and "
            "either 'slots' or 'rows'."
        )

    slice_depth = parse_slice_erode_depth(raw.get("slice_erode_depth"))
    pptx_name = parse_custom_pptx_name(raw.get("pptx_name"))
    normalized_extra_bases = []
    for name in extra_base_names or []:
        normalized = str(name).strip().lower()
        if (
            extra_images.EXTRA_NAME_PATTERN.fullmatch(normalized)
            and normalized not in extra_images.RESERVED_EXTRA_NAMES
            and normalized not in normalized_extra_bases
        ):
            normalized_extra_bases.append(normalized)
    allowed_bases = tuple(ALLOWED_BASES) + tuple(normalized_extra_bases)

    raw_angles = raw.get("angles")
    if not isinstance(raw_angles, list) or not raw_angles:
        raise ValueError("Panel config must include a non-empty 'angles' list.")
    angles: List[str] = []
    for raw_angle in raw_angles:
        angle = str(raw_angle).strip().lower()
        if angle not in ALLOWED_ANGLES:
            raise ValueError(
                f"Unknown angle '{raw_angle}'. Allowed: {', '.join(ALLOWED_ANGLES)}."
            )
        if angle not in angles:
            angles.append(angle)

    layout_entries = _normalize_slot_layout(raw)

    config_dir = os.path.dirname(config_path)
    slots: List[Dict[str, Any]] = []
    rows: Dict[str, List[Dict[str, Any]]] = {
        "top": [],
        "bottom": [],
    }
    for slot_index, layout_entry in enumerate(layout_entries):
        raw_slot = layout_entry["raw_slot"]
        row_name = layout_entry["row"]
        column = layout_entry["column"]
        if not isinstance(raw_slot, dict):
            raise ValueError(
                f"Slot {slot_index} must be a mapping with a 'base' and "
                "optional 'overlays'."
            )
        base = str(raw_slot.get("base", "")).strip().lower()
        if base not in allowed_bases:
            raise ValueError(
                f"Slot {slot_index} has unknown base '{raw_slot.get('base')}'. "
                f"Allowed: {', '.join(allowed_bases)}."
            )

        raw_overlays = raw_slot.get("overlays", [])
        # YAML parses both an omitted key and an empty ``overlays:`` value as
        # no overlays. A structural-only slot remains a valid panel column.
        if raw_overlays is None:
            raw_overlays = []
        if not isinstance(raw_overlays, list):
            raise ValueError(
                f"Slot {slot_index} ({base}) overlays must be a list when provided."
            )

        overlays: List[Dict[str, Any]] = []
        for overlay_index, raw_overlay in enumerate(raw_overlays):
            if not isinstance(raw_overlay, dict):
                raise ValueError(
                    f"Slot {slot_index} overlay {overlay_index} must be a mapping."
                )
            overlay_path = _resolve_overlay_path(
                raw_overlay.get("path"),
                config_dir,
            )
            if not os.path.isfile(overlay_path):
                raise FileNotFoundError(
                    f"Slot {slot_index} ({base}) overlay not found: {overlay_path}"
                )

            name = str(
                raw_overlay.get("name") or f"Overlay{overlay_index + 1}"
            ).strip()
            if not name or any(character.isspace() for character in name):
                raise ValueError(
                    f"Slot {slot_index} overlay {overlay_index}: name must not "
                    f"contain spaces ({name!r})."
                )

            color, _recognized = overlay_colors.resolve_or_warn(
                raw_overlay.get("color", "jet"),
                overlay_label=f"slot{slot_index}:{base}/overlay{overlay_index}",
            )
            overlay: Dict[str, Any] = {
                "path": overlay_path,
                "name": name,
                "color": str(color),
                "opacity": _parse_opacity(
                    raw_overlay.get("opacity", 35),
                    slot_index,
                    overlay_index,
                ),
            }
            overlay.update(
                _validate_window(
                    raw_overlay.get("min"),
                    raw_overlay.get("max"),
                    slot_index,
                    overlay_index,
                )
            )
            overlays.append(overlay)

        overlay_names = [overlay["name"] for overlay in overlays]
        label = base.upper()
        if overlay_names:
            label += " + " + " + ".join(overlay_names)
        slot = {
            "index": slot_index,
            "row": row_name,
            "column": column,
            "base": base,
            "label": label,
            "overlays": overlays,
        }
        slots.append(slot)
        rows[row_name].append(slot)

    return {
        "path": config_path,
        **slice_depth,
        "pptx_name": pptx_name,
        "angles": angles,
        "slots": slots,
        "rows": rows,
    }
