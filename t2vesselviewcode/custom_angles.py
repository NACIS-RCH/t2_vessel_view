"""Parse brand-new display and slice-plane angle definitions from CLI."""

import math
import re
from typing import Dict, Iterable, List, Optional


ANGLE_LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
RESERVED_ANGLE_LABELS = {
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
}


def _parse_pair_record(
    record: Iterable[str],
    option_name: str,
) -> Dict[str, object]:
    """Parse one LABEL/AZ/EL record after argparse's nargs handling."""
    values = list(record)
    if len(values) != 3:
        raise ValueError(f"{option_name} requires LABEL AZIMUTH ELEVATION.")
    label = str(values[0]).strip().lower()
    if not ANGLE_LABEL_PATTERN.fullmatch(label):
        raise ValueError(
            f"{option_name} LABEL must start with a letter and contain only "
            "letters, numbers, underscores, or hyphens."
        )
    if label in RESERVED_ANGLE_LABELS:
        raise ValueError(
            f"{option_name} label '{label}' is an existing preset angle; "
            "CLI custom angles must use a brand-new label."
        )
    try:
        azimuth = float(values[1])
        elevation = float(values[2])
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{option_name} azimuth/elevation must be numeric."
        ) from error
    if not math.isfinite(azimuth) or not math.isfinite(elevation):
        raise ValueError(
            f"{option_name} azimuth/elevation must be finite."
        )
    return {
        "label": label,
        "azimuth": azimuth,
        "elevation": elevation,
    }


def build_custom_angle_specs(
    display_records: Optional[List[Iterable[str]]] = None,
    slice_records: Optional[List[Iterable[str]]] = None,
    require_slice_planes: bool = False,
) -> List[Dict[str, object]]:
    """Merge ordered display and optional slice records by brand-new label."""
    display_specs: List[Dict[str, object]] = []
    display_by_label = {}
    for record in display_records or []:
        parsed = _parse_pair_record(record, "--display-angle")
        label = parsed["label"]
        if label in display_by_label:
            raise ValueError(f"Duplicate --display-angle label: {label}")
        display_by_label[label] = parsed
        display_specs.append(parsed)

    slice_by_label = {}
    for record in slice_records or []:
        parsed = _parse_pair_record(record, "--slice-plane")
        label = parsed["label"]
        if label in slice_by_label:
            raise ValueError(f"Duplicate --slice-plane label: {label}")
        if label not in display_by_label:
            raise ValueError(
                f"--slice-plane label '{label}' has no matching "
                "--display-angle definition."
            )
        slice_by_label[label] = parsed

    custom_specs = []
    missing_slice_labels = []
    for display in display_specs:
        label = display["label"]
        slice_spec = slice_by_label.get(label)
        if require_slice_planes and slice_spec is None:
            missing_slice_labels.append(label)
        custom_specs.append({
            "label": label,
            "brain_az": display["azimuth"],
            "brain_el": display["elevation"],
            "clip_az": (
                slice_spec["azimuth"] if slice_spec is not None else None
            ),
            "clip_el": (
                slice_spec["elevation"] if slice_spec is not None else None
            ),
        })
    if missing_slice_labels:
        raise ValueError(
            "Custom slice-producing panels require --slice-plane for: "
            + ", ".join(missing_slice_labels)
        )
    return custom_specs


def display_rows(custom_specs) -> List[List[object]]:
    """Return [azimuth, elevation, label] rows for volume rendering."""
    return [
        [spec["brain_az"], spec["brain_el"], spec["label"]]
        for spec in custom_specs or []
    ]


def slice_rows(custom_specs) -> List[List[object]]:
    """Return five-value rows for slice rendering, requiring clip values."""
    rows = []
    for spec in custom_specs or []:
        if spec.get("clip_az") is None or spec.get("clip_el") is None:
            raise ValueError(
                f"Custom angle '{spec['label']}' has no slice plane."
            )
        rows.append([
            spec["label"],
            spec["brain_az"],
            spec["brain_el"],
            spec["clip_az"],
            spec["clip_el"],
        ])
    return rows
