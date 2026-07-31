"""Parse and locate named extra T1-like structural images."""

import argparse
import glob
import os
import re
from typing import Dict, List


EXTRA_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
RESERVED_EXTRA_NAMES = {
    "t1",
    "t2",
    "flair",
    "t2_sag",
    "t2_sag_left",
    "t2_sag_right",
    "t2_cor",
    "t2_tra",
    "t2_3d",
}


def parse_extra_image_spec(value: str) -> Dict[str, str]:
    """Parse one ``NAME=PATH`` CLI value into a normalized record."""
    raw_value = str(value or "").strip()
    if "=" not in raw_value:
        raise argparse.ArgumentTypeError(
            "--extra-image must use NAME=PATH, for example "
            "--extra-image t1_gd=/data/T1_Gd.nii.gz."
        )
    raw_name, raw_path = raw_value.split("=", 1)
    name = raw_name.strip().lower()
    if not EXTRA_NAME_PATTERN.fullmatch(name):
        raise argparse.ArgumentTypeError(
            "Extra image NAME must start with a letter and contain only "
            "letters, numbers, underscores, or hyphens."
        )
    if name in RESERVED_EXTRA_NAMES:
        raise argparse.ArgumentTypeError(
            f"Extra image name '{name}' is reserved by a built-in modality."
        )
    path_text = raw_path.strip()
    if not path_text:
        raise argparse.ArgumentTypeError(
            f"Extra image '{name}' is missing its input path."
        )
    path = os.path.abspath(os.path.expanduser(path_text))
    if not os.path.exists(path):
        raise argparse.ArgumentTypeError(
            f"Extra image '{name}' was not found: {path}"
        )
    return {"name": name, "path": path}


def validate_extra_image_specs(specs: List[Dict[str, str]]) -> None:
    """Reject duplicate normalized names in an ordered extra-image list."""
    seen = set()
    duplicates = []
    for spec in specs or []:
        name = spec["name"]
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise ValueError(
            "Duplicate --extra-image name(s): " + ", ".join(duplicates)
        )


def processed_extra_root(processing_dir: str) -> str:
    """Return the root folder for preprocessed named extras."""
    return os.path.join(processing_dir, "Preprocessed_Extra")


def processed_extra_dir(processing_dir: str, name: str) -> str:
    """Return one named extra's preprocessing folder."""
    return os.path.join(processed_extra_root(processing_dir), name)


def eroded_extra_root(eroded_nifti_dir: str) -> str:
    """Return the root folder for eroded named extras."""
    return os.path.join(eroded_nifti_dir, "Extra")


def eroded_extra_dir(eroded_nifti_dir: str, name: str) -> str:
    """Return one named extra's eroded-NIfTI folder."""
    return os.path.join(eroded_extra_root(eroded_nifti_dir), name)


def discover_eroded_extras(eroded_nifti_dir: str) -> Dict[str, List[str]]:
    """Discover valid named extra folders and their eroded NIfTI files."""
    root = eroded_extra_root(eroded_nifti_dir)
    discovered: Dict[str, List[str]] = {}
    if not os.path.isdir(root):
        return discovered
    for entry in sorted(os.scandir(root), key=lambda item: item.name.lower()):
        name = entry.name.strip().lower()
        if not entry.is_dir() or not EXTRA_NAME_PATTERN.fullmatch(name):
            continue
        if name in RESERVED_EXTRA_NAMES:
            continue
        paths = sorted(
            path
            for path in glob.glob(os.path.join(entry.path, "*eroded*nii*"))
            if os.path.isfile(path)
        )
        if paths:
            discovered[name] = paths
    return discovered
