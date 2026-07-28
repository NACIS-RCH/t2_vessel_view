"""Load and validate YAML configuration for the custom overlay panel.

This module is intentionally independent of commandline, dir_structure, the
main pipeline, and rendering modules. Keeping it dependency-light prevents the
YAML feature from changing the package's existing CLI import order.
"""

import os
from typing import Any, Dict, List

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
ALLOWED_BASES = ("t1", "t2", "flair")
MIN_SLOTS = 2
MAX_SLOTS = 4

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
    "left": ("t2_sag", "t2_3d", "t2_tra"),
    "right": ("t2_sag", "t2_3d", "t2_tra"),
    "anterior": ("t2_cor", "t2_3d"),
    "posterior": ("t2_cor", "t2_3d"),
    "superior": ("t2_tra", "t2_3d"),
    "inferior": ("t2_tra", "t2_3d"),
    "surg_left_lat": ("t2_sag", "t2_3d"),
    "surg_right_lat": ("t2_sag", "t2_3d"),
    "surg_left_ato": ("t2_sag", "t2_3d"),
    "surg_right_ato": ("t2_sag", "t2_3d"),
}


def angle_rows(angles: List[str]) -> List[List[Any]]:
    """Return MRIcroGL camera/clip rows in requested order."""
    rows: List[List[Any]] = []
    for angle in angles:
        key = str(angle).strip().lower()
        if key not in ANGLE_SPECS:
            raise ValueError(f"Unknown angle: {angle}")
        rows.append(list(ANGLE_SPECS[key]))
    return rows


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


def load_custom_overlay_trio_config(path: str) -> Dict[str, Any]:
    """Load and validate a ``custom_overlay_trio`` YAML file.

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
            "Panel config must be a YAML mapping containing 'angles' and 'slots'."
        )

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

    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        raise ValueError("Panel config must include a 'slots' list.")
    if not MIN_SLOTS <= len(raw_slots) <= MAX_SLOTS:
        raise ValueError(
            f"Panel config must contain {MIN_SLOTS} to {MAX_SLOTS} slots "
            f"(got {len(raw_slots)})."
        )

    config_dir = os.path.dirname(config_path)
    slots: List[Dict[str, Any]] = []
    for slot_index, raw_slot in enumerate(raw_slots):
        if not isinstance(raw_slot, dict):
            raise ValueError(
                f"Slot {slot_index} must be a mapping with a 'base' and "
                "optional 'overlays'."
            )
        base = str(raw_slot.get("base", "")).strip().lower()
        if base not in ALLOWED_BASES:
            raise ValueError(
                f"Slot {slot_index} has unknown base '{raw_slot.get('base')}'. "
                f"Allowed: {', '.join(ALLOWED_BASES)}."
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
        slots.append(
            {
                "index": slot_index,
                "base": base,
                "label": label,
                "overlays": overlays,
            }
        )

    return {
        "path": config_path,
        "angles": angles,
        "slots": slots,
    }
