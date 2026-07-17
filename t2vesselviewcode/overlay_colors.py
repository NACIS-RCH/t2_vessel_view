"""Shared overlay colour-name aliases for MRIcroGL and postprocess colorbars.

CLI --overlayN-color values are resolved here once, then reused for:
1. gl.colorname(...) in MRIcroGL render templates
2. Bundled .clut colorbar legends in png_postprocess
"""

import os
from typing import Dict, List, Optional, Tuple

# Bundled CLUT directory (package data beside this module).
_LUT_DIR = os.path.join(os.path.dirname(__file__), "assets", "lut")

# Canonical MRIcroGL colour names and their bundled .clut filenames.
# Canonical names match the CLUT stems MRIcroGL expects (including integer prefixes).
CANONICAL_CLUT_FILES: Dict[str, str] = {
    # Integer-prefixed overlay colours (MRIcroGL menu order).
    "1red": "1red.clut",
    "2green": "2green.clut",
    "3blue": "3blue.clut",
    "4hot": "4hot.clut",
    "5winter": "5winter.clut",
    "6bluegrn": "6bluegrn.clut",
    "6warm": "6warm.clut",
    "7cool": "7cool.clut",
    "8redyell": "8redyell.clut",
    # Continuous / quantitative maps.
    "jet": "jet.clut",
    "electric_blue": "electric_blue.clut",
    "blue2red": "blue2red.clut",
    "viridis": "Viridis.clut",
    "plasma": "Plasma.clut",
    "inferno": "Inferno.clut",
    "magma": "magma.clut",
    "cividis": "cividis.clut",
    "turbo": "turbo.clut",
    "turbo86": "turbo86.clut",
    "mako": "mako.clut",
    "rocket": "rocket.clut",
    "copper": "copper.clut",
    "copper2": "copper2.clut",
    "bone": "bone.clut",
    "bronze": "bronze.clut",
    "gold": "gold.clut",
    "hotiron": "HOTIRON.clut",
    "cubehelix": "cubehelix.clut",
    "x_rain": "x_rain.clut",
    "linspecer": "linspecer.clut",
    # Medical / CT presets.
    "nih": "NIH.clut",
    "actc": "actc.clut",
    "ge_color": "GE_color.clut",
    "surface": "surface.clut",
    "ct_airways": "CT_Airways.clut",
    "ct_bones": "CT_Bones.clut",
    "ct_head": "CT_Head.clut",
    "ct_kidneys": "CT_Kidneys.clut",
    "ct_liver": "CT_Liver.clut",
    "ct_muscles": "CT_Muscles.clut",
    "ct_scalp": "CT_Scalp.clut",
    "ct_skull": "CT_Skull.clut",
    "ct_soft": "CT_Soft.clut",
    "ct_soft_tissue": "CT_Soft_Tissue.clut",
    "ct_surface": "CT_Surface.clut",
    "ct_vessels": "CT_Vessels.clut",
    "ct_w_contrast": "CT_w_Contrast.clut",
}

# Unprefixed CLI aliases for the integer-prefixed subset only.
# Example: CLI "green" resolves to canonical "2green".
UNPREFIXED_ALIASES: Dict[str, str] = {
    "red": "1red",
    "green": "2green",
    "blue": "3blue",
    "hot": "4hot",
    "winter": "5winter",
    "bluegrn": "6bluegrn",
    "warm": "6warm",
    "cool": "7cool",
    "redyell": "8redyell",
}

# Names that should be passed to gl.colorname with non-lowercase spelling
# (matching the bundled CLUT stem / MRIcroGL menu label).
_CANONICAL_DISPLAY_NAMES: Dict[str, str] = {
    "viridis": "Viridis",
    "plasma": "Plasma",
    "inferno": "Inferno",
    "hotiron": "HOTIRON",
    "nih": "NIH",
    "ge_color": "GE_color",
    "ct_airways": "CT_Airways",
    "ct_bones": "CT_Bones",
    "ct_head": "CT_Head",
    "ct_kidneys": "CT_Kidneys",
    "ct_liver": "CT_Liver",
    "ct_muscles": "CT_Muscles",
    "ct_scalp": "CT_Scalp",
    "ct_skull": "CT_Skull",
    "ct_soft": "CT_Soft",
    "ct_soft_tissue": "CT_Soft_Tissue",
    "ct_surface": "CT_Surface",
    "ct_vessels": "CT_Vessels",
    "ct_w_contrast": "CT_w_Contrast",
}


def normalize_color_key(color_name: str) -> str:
    """Normalise a CLI colour string for dictionary lookup."""
    # Allow common typing variations: spaces/hyphens become underscores.
    key = str(color_name or "").strip().lower()
    return key.replace(" ", "_").replace("-", "_")


def resolve_overlay_color(color_name: str) -> Optional[str]:
    """Resolve a CLI colour name to the canonical MRIcroGL colorname.

    Accepts:
    - Exact CLUT / MRIcroGL names (including integer-prefixed names like 2green)
    - Unprefixed aliases for the numbered subset (green -> 2green)

    Returns None when the name is not recognised.
    """
    key = normalize_color_key(color_name)
    if not key:
        return None

    # Unprefixed aliases first so "red" maps to "1red", not a missing bare name.
    if key in UNPREFIXED_ALIASES:
        key = UNPREFIXED_ALIASES[key]

    if key not in CANONICAL_CLUT_FILES:
        return None

    # Prefer the display spelling MRIcroGL expects when it differs from the key.
    return _CANONICAL_DISPLAY_NAMES.get(key, key)


def resolve_clut_path(color_name: str) -> Optional[str]:
    """Return the bundled .clut path for a CLI or canonical colour name."""
    canonical = resolve_overlay_color(color_name)
    if canonical is None:
        return None
    # Look up the file using the normalised canonical key.
    file_key = normalize_color_key(canonical)
    # Display names like Viridis still map via lowercase key.
    if file_key not in CANONICAL_CLUT_FILES:
        # Reverse-map display name back to file key if needed.
        for key, display in _CANONICAL_DISPLAY_NAMES.items():
            if display == canonical:
                file_key = key
                break
    clut_filename = CANONICAL_CLUT_FILES.get(file_key)
    if not clut_filename:
        return None
    clut_path = os.path.join(_LUT_DIR, clut_filename)
    return clut_path if os.path.exists(clut_path) else None


def accepted_color_names() -> List[str]:
    """Return sorted accepted CLI colour names (canonical + unprefixed aliases)."""
    names = set(CANONICAL_CLUT_FILES.keys()) | set(UNPREFIXED_ALIASES.keys())
    return sorted(names)


def format_accepted_colors_help(max_examples: int = 12) -> str:
    """Short help snippet listing representative accepted colour names."""
    examples = [
        "1red", "red", "2green", "green", "3blue", "blue",
        "4hot", "hot", "jet", "electric_blue", "viridis", "plasma",
    ]
    shown = [name for name in examples if name in set(accepted_color_names())]
    shown = shown[:max_examples]
    return (
        "Accepted names include exact MRIcroGL CLUT names "
        f"(e.g. {', '.join(shown)}) and unprefixed aliases for numbered maps "
        "(e.g. green -> 2green)."
    )


def resolve_or_warn(color_name: str, overlay_label: str = "overlay") -> Tuple[str, bool]:
    """Resolve a colour name; fall back to jet and report whether it was unknown.

    Returns (canonical_name, was_recognized).
    """
    canonical = resolve_overlay_color(color_name)
    if canonical is not None:
        return canonical, True
    # Keep a safe default so rendering can continue, but warn the caller.
    print(
        f"[WARNING] Unrecognised {overlay_label} colour '{color_name}'. "
        "Falling back to 'jet'. "
        f"{format_accepted_colors_help()}"
    )
    return "jet", False
