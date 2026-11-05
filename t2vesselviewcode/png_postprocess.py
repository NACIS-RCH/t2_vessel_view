"""
PNG post-processing utilities for cropping, annotating, stitching, and PPTX export.

Provenance: This module ports the behavior of the legacy `screenshot_stitcher.py`
into package functions so the pipeline can call them directly.

Design goals (MVP):
- Preserve EXACT cropping behavior using pyvips.find_trim (threshold/background).
- Add simple L/R overlays after crop (white with black outline).
- Stitch images into one/two-row panels per erosion depth.
- Always export a PPTX with one slide per stitched panel.

Downstream: more presets (multimodal per angle), richer labels (S/I/A/P), DPI tuning.
"""

import os
import glob
import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

import nibabel as nib
import numpy as np
import pydicom
import pyvips
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageChops, ImageStat
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
from pptx import Presentation
from pptx.util import Inches

from . import dir_structure
from . import overlay_colors

# Hard-coded tolerance for consecutive stitched PNG dedupe.
# Unit is mean absolute RGB difference per channel on [0, 255].
# Lower means stricter (0.0 = exact-match only).
CONSECUTIVE_DEDUPE_MEAN_ABS_DIFF_THRESHOLD = 0.35

# Backwards-compatible alias kept for any external imports; prefer overlay_colors.
CLUT_NAME_TO_FILE = {
    key: filename
    for key, filename in overlay_colors.CANONICAL_CLUT_FILES.items()
}
CLUT_NAME_TO_FILE.update({
    alias: overlay_colors.CANONICAL_CLUT_FILES[canonical]
    for alias, canonical in overlay_colors.UNPREFIXED_ALIASES.items()
})


def _ensure_dir(path: str) -> None:
    """Create directory if missing (no error if it already exists)."""
    os.makedirs(path, exist_ok=True)


def _extract_depth_from_basename(basename: str) -> str:
    """Extract erosion depth from a filename using '<depth>_eroded'.

    Example: 'right-270-0-030_eroded_t1.png' -> '030'. Used to sort slides.
    Returns '000' if not found (safe default).
    """
    m = re.search(r"(\d+)_eroded", basename)
    return m.group(1) if m else "000"


def _list_pngs(directory: str) -> List[str]:
    """List all PNGs in a directory, sorted alphabetically."""
    return sorted(glob.glob(os.path.join(directory, '*.png')))


def _extract_erode_prefix_or_none(basename: str) -> Optional[str]:
    """Extract zero-padded erosion prefix from '<prefix>_eroded' in filename.

    Returns None when the filename does not contain an erosion prefix and should
    be excluded from prefix-based stitching logic.
    """
    m = re.search(r"(\d+)_eroded", basename)
    if not m:
        return None
    return str(m.group(1)).zfill(3)


def _build_prefix_map(paths: List[str]) -> Dict[str, str]:
    """Build mapping: erosion prefix -> file path (eligible files only)."""
    out: Dict[str, str] = {}
    for p in sorted(paths):
        prefix = _extract_erode_prefix_or_none(os.path.basename(p))
        if prefix is None:
            continue
        # Keep first deterministic entry if duplicates exist for a prefix.
        if prefix not in out:
            out[prefix] = p
    return out


def _common_prefixes_across_maps(prefix_maps: List[Dict[str, str]]) -> List[str]:
    """Return numerically sorted erosion prefixes common to all maps."""
    if not prefix_maps:
        return []
    common: Set[str] = set(prefix_maps[0].keys())
    for mp in prefix_maps[1:]:
        common &= set(mp.keys())
    return sorted(common, key=lambda x: int(x))


def _log_skipped_prefixes(context: str, all_prefixes: Set[str], common_prefixes: List[str]) -> None:
    """Print an info line showing skipped erosion prefixes for transparency."""
    skipped = sorted(set(all_prefixes) - set(common_prefixes), key=lambda x: int(x))
    if skipped:
        print(f"[INFO] {context}: skipped erosion prefixes missing in one or more required folders: {', '.join(skipped)}")


def get_crop_dimensions(images: List[str], background_colour: List[int], threshold: int = 2, padding_px: int = 6) -> Tuple[int, int, int, int]:
    """Compute a single crop box for an image series using least background across all.

    Uses pyvips.find_trim(threshold, background) like the legacy script:
    - Chooses the first image with non-zero brain width as the sample.
    - Measures left/top/width/height on the sample, converts to right/bottom margins.
    - Iterates all images, always keeping the most conservative crop (least margins).
    - Finally, expands the crop by a small padding (in pixels) to retain a thin
      rim of background so stitched images do not touch and labels have space.

    Returns: (left, top, width, height) suitable for pyvips.crop.
    """
    print(f"[INFO] Finding crop trim across {len(images)} PNG(s)...")
    # Find the first usable sample (non-empty brain extent). If none, use the first file.
    sample = None
    for path in images:
        img = pyvips.Image.new_from_file(path)  # lazy read of file metadata
        brain_width = img.find_trim(threshold=threshold, background=background_colour)[2]
        if brain_width != 0:
            sample = img
            break
    if sample is None:
        sample = pyvips.Image.new_from_file(images[0])

    # Baseline crop from the sample
    left, top, brain_width, brain_height = sample.find_trim(threshold=threshold, background=background_colour)
    right = sample.width - left - brain_width
    bottom = sample.height - top - brain_height

    # Initialize the conservative crop margins we will tighten
    left_crop, top_crop = left, top
    right_margin, bottom_margin = right, bottom

    # Walk all images to choose least background (tightest margins without clipping)
    for entry in images:
        img = pyvips.Image.new_from_file(entry)
        if img.width != sample.width or img.height != sample.height:
            raise ValueError(f"All images must share identical dimensions; {entry} differs")
        i_left, i_top, i_w, i_h = img.find_trim(threshold=threshold, background=background_colour)
        # If brain is missing (i_w == 0), treat right/bottom margins as left/top respectively
        i_right = sample.width - i_left - i_w if i_w != 0 else i_left
        i_bottom = sample.height - i_top - i_h if i_h != 0 else i_top

        # Keep the smallest margins found so far
        left_crop = i_left if i_left < left_crop else left_crop
        top_crop = i_top if i_top < top_crop else top_crop
        right_margin = i_right if i_right < right_margin else right_margin
        bottom_margin = i_bottom if i_bottom < bottom_margin else bottom_margin

    # Convert margins back to final crop width/height
    width_crop = sample.width - left_crop - right_margin
    height_crop = sample.height - top_crop - bottom_margin

    # Expand the crop rectangle by padding while clamping to image bounds
    pad = max(0, int(padding_px))
    left_expanded = max(0, left_crop - pad)
    top_expanded = max(0, top_crop - pad)
    width_expanded = min(sample.width - left_expanded, width_crop + pad * 2)
    height_expanded = min(sample.height - top_expanded, height_crop + pad * 2)

    print("[INFO] Crop trim complete.")
    return left_expanded, top_expanded, width_expanded, height_expanded


def crop_image_series(images: List[str], output_directory: str, dimensions: Tuple[int, int, int, int]) -> List[str]:
    """Crop each image in a series to the provided dimensions; write to 0_cropped_series.

    Returns a sorted list of output file paths.
    """
    outpath = os.path.join(output_directory, '0_cropped_series')
    _ensure_dir(outpath)
    left, top, width, height = dimensions
    print(f"[INFO] Writing {len(images)} cropped PNG(s) to {outpath}...")
    out_files = []
    for idx, path in enumerate(images, start=1):
        img = pyvips.Image.new_from_file(path)
        try:
            img = img.crop(left, top, width, height)  # fast region extraction
        except pyvips.error.Error:
            # Skip problematic file but keep processing others
            continue
        out_name = os.path.join(outpath, f"cropped_{os.path.basename(path)}")
        img.write_to_file(out_name)
        out_files.append(out_name)
        if len(images) >= 10 and idx % 10 == 0:
            print(f"[INFO] Cropped {idx}/{len(images)} PNG(s)...")
    print(f"[INFO] Wrote {len(out_files)} cropped PNG(s).")
    return sorted(out_files)


def _draw_text_with_outline(draw: ImageDraw.Draw, xy: Tuple[int, int], text: str, fill=(255, 255, 255), outline=(0, 0, 0), font=None):
    """Draw text with a simple 8-direction outline for legibility on any background."""
    x, y = xy
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]:
        draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _load_annotation_font(font_size: int):
    """Load a scalable annotation font with cross-platform fallbacks.

    Preference order keeps current macOS behavior (Arial first), while adding
    common Linux fonts to avoid tiny bitmap fallback text.
    """
    candidates = [
        "Arial.ttf",                # Common on macOS/Windows
        "DejaVuSans.ttf",           # Common on Linux
        "LiberationSans-Regular.ttf",
    ]
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, font_size)
        except Exception:
            continue
    return ImageFont.load_default()


def _format_colorbar_value(value) -> str:
    """Format a colorbar endpoint without commas or scientific notation."""
    try:
        val = float(value)
    except Exception:
        # If the value is not numeric, keep it as text rather than failing.
        return str(value)
    # Use fixed decimal formatting so labels never show as 1e+04 or 1,000.
    text = f"{val:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _resolve_bundled_clut_path(color_name: str) -> Optional[str]:
    """Return the bundled MRIcroGL CLUT path for a requested color name."""
    # Shared resolver so colorbars use the same aliases as MRIcroGL overlays
    # (e.g. green and 2green both map to 2green.clut).
    return overlay_colors.resolve_clut_path(color_name)


def _parse_mricrogl_clut(clut_path: str) -> List[Tuple[int, Tuple[int, int, int]]]:
    """Parse MRIcroGL .clut nodes as intensity/RGB pairs."""
    # MRIcroGL CLUTs store the intensity positions and RGB colours in separate
    # sections, so collect them by node index and combine them after reading.
    # For example, nodeintensity2 and nodergba2 describe the same point in the
    # colour ramp: where it sits and what colour it should be.
    intensities = {}
    rgba_values = {}
    with open(clut_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            # Ignore section headers, blank lines, and descriptive colour labels.
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key.startswith("nodeintensity"):
                try:
                    # Example: nodeintensity2=128 gives the 0-255 position.
                    # These values usually come from the [BYT] section.
                    idx = int(key.replace("nodeintensity", ""))
                    intensities[idx] = int(float(value))
                except Exception:
                    continue
            elif key.startswith("nodergba"):
                try:
                    # Example: nodergba2=127|255|127|64; only RGB is needed.
                    # These values usually come from the [RGBA255] section.
                    # The fourth value is alpha/transparency, which is useful for
                    # MRIcroGL rendering but not for this solid PNG legend.
                    idx = int(key.replace("nodergba", ""))
                    parts = [int(float(part)) for part in value.split("|")[:3]]
                    if len(parts) == 3:
                        # Clamp values to valid 8-bit RGB in case a CLUT is odd.
                        rgba_values[idx] = tuple(max(0, min(255, part)) for part in parts)
                except Exception:
                    continue

    # Combine matching intensity/RGB nodes, sorted from low to high intensity.
    nodes = []
    for idx, intensity in intensities.items():
        if idx in rgba_values:
            nodes.append((max(0, min(255, intensity)), rgba_values[idx]))
    nodes = sorted(nodes, key=lambda item: item[0])
    if len(nodes) < 2:
        # A gradient needs at least two points; otherwise interpolation is not possible.
        raise ValueError(f"CLUT must contain at least two valid nodes: {clut_path}")
    return nodes


def _interpolate_clut_rgb(nodes: List[Tuple[int, Tuple[int, int, int]]], intensity: float) -> Tuple[int, int, int]:
    """Interpolate RGB from CLUT nodes at a 0-255 intensity position."""
    # Keep the requested intensity inside the standard MRIcroGL 0-255 CLUT range.
    pos = max(0.0, min(255.0, float(intensity)))
    if pos <= nodes[0][0]:
        return nodes[0][1]
    if pos >= nodes[-1][0]:
        return nodes[-1][1]

    # Find the two CLUT nodes surrounding this position and linearly blend RGB.
    for idx in range(len(nodes) - 1):
        lo_i, lo_rgb = nodes[idx]
        hi_i, hi_rgb = nodes[idx + 1]
        if lo_i <= pos <= hi_i:
            # frac is 0.0 at the lower node and 1.0 at the upper node.
            denom = max(1.0, float(hi_i - lo_i))
            frac = (pos - lo_i) / denom
            return tuple(
                int(round(lo_rgb[channel] + frac * (hi_rgb[channel] - lo_rgb[channel])))
                for channel in range(3)
            )
    return nodes[-1][1]


@lru_cache(maxsize=64)
def _is_binary_overlay_cached(
    absolute_path: str,
    modified_ns: int,
    file_size: int,
) -> bool:
    """Inspect one immutable file version for exact visible 0/1 values."""
    del modified_ns, file_size  # Included in the cache key for invalidation.
    try:
        data = np.asanyarray(nib.load(absolute_path).dataobj)
        if data.size == 0:
            return False
        finite_mask = np.isfinite(data)
        if not np.any(finite_mask):
            return False
        values = data[finite_mask]
        return bool(
            np.any(values == 1)
            and np.all((values == 0) | (values == 1))
        )
    except Exception:
        return False


def _is_binary_overlay(path: str) -> bool:
    """Return True for an existing NIfTI whose finite values are exactly 0/1."""
    try:
        absolute_path = os.path.abspath(os.path.expanduser(str(path)))
        stat = os.stat(absolute_path)
        return _is_binary_overlay_cached(
            absolute_path,
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except Exception:
        return False


def _value_to_clut_intensity(value, window_min, window_max) -> float:
    """Map one overlay value through its min/max window to CLUT position."""
    try:
        value_float = float(value)
        minimum = float(window_min)
        maximum = float(window_max)
    except (TypeError, ValueError):
        return 255.0
    if not all(np.isfinite(item) for item in (value_float, minimum, maximum)):
        return 255.0
    if maximum <= minimum:
        return 255.0
    position = 255.0 * (value_float - minimum) / (maximum - minimum)
    return max(0.0, min(255.0, position))


def _make_binary_clut_swatch_image(
    color_name: str,
    width: int,
    height: int,
    window_min,
    window_max,
) -> Optional[PILImage.Image]:
    """Create a solid swatch matching binary foreground value 1."""
    clut_path = _resolve_bundled_clut_path(color_name)
    if not clut_path:
        return None
    nodes = _parse_mricrogl_clut(clut_path)
    position = _value_to_clut_intensity(1, window_min, window_max)
    rgb = _interpolate_clut_rgb(nodes, position)
    return PILImage.new("RGB", (width, height), rgb)


def _make_clut_colorbar_image(color_name: str, width: int, height: int) -> Optional[PILImage.Image]:
    """Create a vertical colorbar from a bundled MRIcroGL .clut file."""
    # Missing CLUTs are handled by the caller with a clear warning.
    clut_path = _resolve_bundled_clut_path(color_name)
    if not clut_path:
        return None

    # Parse the MRIcroGL colour ramp and draw it into a small Pillow image.
    nodes = _parse_mricrogl_clut(clut_path)
    bar = PILImage.new("RGB", (width, height))
    denom = max(1, height - 1)
    for y in range(height):
        # Top of the bar should represent the maximum value, bottom the minimum.
        # Convert this image row into the equivalent 0-255 CLUT intensity.
        intensity = 255.0 * (1.0 - (y / denom))
        rgb = _interpolate_clut_rgb(nodes, intensity)
        # Fill this whole row with the same colour to create a vertical gradient.
        for x in range(width):
            bar.putpixel((x, y), rgb)
    return bar


def _normalize_overlay_colorbar_specs(overlay_specs) -> List[Dict]:
    """Return overlay colorbar specs as a clean list of dictionaries."""
    if not overlay_specs:
        return []
    if isinstance(overlay_specs, dict):
        overlay_specs = [overlay_specs]
    return [spec for spec in overlay_specs if isinstance(spec, dict)]


def _deduplicate_overlay_colorbar_specs(overlay_specs) -> List[Dict]:
    """Remove exact duplicate legends while preserving their first-seen order."""
    unique_specs = []
    seen = set()
    for spec in _normalize_overlay_colorbar_specs(overlay_specs):
        key = (
            str(spec.get("path", "")),
            str(spec.get("name", "")),
            str(spec.get("color", "")),
            spec.get("min"),
            spec.get("max"),
            spec.get("opacity"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_specs.append(spec)
    return unique_specs


def _measure_text(draw: ImageDraw.Draw, text: str, font) -> Tuple[int, int]:
    """Measure text dimensions with Pillow version fallbacks."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return draw.textsize(text, font=font)


def _layout_colorbar_name(
    draw: ImageDraw.Draw,
    overlay_name: str,
    font,
    max_width: int,
    line_gap: int,
    max_characters: int = 17,
) -> Dict:
    """Lay out a colorbar name on one or two measured, centered lines."""
    display_name = " ".join(str(overlay_name).replace("_", " ").split())
    full_size = _measure_text(draw, display_name, font)
    if len(display_name) <= int(max_characters):
        return {
            "lines": [display_name],
            "line_sizes": [full_size],
            "width": full_size[0],
            "height": full_size[1],
        }

    words = display_name.split()
    candidates = []
    for split_index in range(1, len(words)):
        lines = (
            " ".join(words[:split_index]),
            " ".join(words[split_index:]),
        )
        sizes = [_measure_text(draw, line, font) for line in lines]
        widths = [size[0] for size in sizes]
        candidates.append(
            (
                max(widths),
                abs(widths[0] - widths[1]),
                lines,
                sizes,
            )
        )
    fitting = [
        candidate for candidate in candidates
        if (
            candidate[0] <= max_width
            and all(
                len(line) <= int(max_characters)
                for line in candidate[2]
            )
        )
    ]
    if fitting:
        best = min(fitting, key=lambda candidate: (candidate[0], candidate[1]))
        return {
            "lines": list(best[2]),
            "line_sizes": best[3],
            "width": best[0],
            "height": sum(size[1] for size in best[3]) + line_gap,
        }

    # If no word-boundary split fits, permit one visibly hyphenated word break.
    hyphenated_candidates = []
    for split_index in range(1, len(display_name)):
        left = display_name[:split_index].rstrip()
        right = display_name[split_index:].lstrip()
        if not left or not right:
            continue
        breaks_word = (
            not display_name[split_index - 1].isspace()
            and not display_name[split_index].isspace()
        )
        first_line = left + ("-" if breaks_word else "")
        lines = (first_line, right)
        sizes = [_measure_text(draw, line, font) for line in lines]
        widths = [size[0] for size in sizes]
        hyphenated_candidates.append(
            (
                max(widths),
                abs(widths[0] - widths[1]),
                lines,
                sizes,
            )
        )
    fitting_hyphenated = [
        candidate for candidate in hyphenated_candidates
        if (
            candidate[0] <= max_width
            and all(
                len(line) <= int(max_characters)
                for line in candidate[2]
            )
        )
    ]
    pool = fitting_hyphenated or hyphenated_candidates or candidates
    best = min(pool, key=lambda candidate: (candidate[0], candidate[1]))
    return {
        "lines": list(best[2]),
        "line_sizes": best[3],
        "width": best[0],
        "height": sum(size[1] for size in best[3]) + line_gap,
    }


def annotate_overlay_colorbars_on_png(path_in: str, path_out: str, overlay_specs) -> None:
    """Add compact stacked overlay colorbar legends to a stitched PNG.

    overlay_specs can be one dictionary or a list of dictionaries from the overlay
    CLI values, for example:
    {"name": "PET", "color": "jet", "min": 2000, "max": 23000}.
    This function edits one final stitched panel image, not the individual
    MRIcroGL view screenshots.
    """
    overlay_specs = _normalize_overlay_colorbar_specs(overlay_specs)
    if not overlay_specs:
        return

    # Open the stitched panel as RGB so drawing and pasted colours are predictable.
    img = PILImage.open(path_in).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Use a slightly smaller legend when several overlays are present.
    multiple_overlays = len(overlay_specs) > 1
    font_size = max(12, int(h * (0.020 if multiple_overlays else 0.023)))
    value_font_size = max(10, int(h * (0.015 if multiple_overlays else 0.018)))
    name_font = _load_annotation_font(font_size)
    value_font = _load_annotation_font(value_font_size)

    margin = max(12, int(min(w, h) * 0.02))
    gap = max(4, int(min(w, h) * 0.008))
    entry_gap = max(8, int(min(w, h) * 0.012))
    name_to_bar_gap = gap + 3
    name_line_gap = max(2, int(font_size * 0.18))
    name_max_width = min(
        max(80, int(w * 0.28)),
        max(1, w - (2 * margin)),
    )
    bar_width = max(12, int(w * 0.012))
    bar_height = max(28, int(h * (0.055 if multiple_overlays else 0.08)))

    entries = []
    global_value_width = 0
    global_block_width = 0
    for overlay_idx, overlay_spec in enumerate(overlay_specs, start=1):
        color_name = str(overlay_spec.get("color", "")).lower()
        overlay_name = str(overlay_spec.get("name", f"Overlay{overlay_idx}"))
        is_binary = _is_binary_overlay(overlay_spec.get("path", ""))
        min_text = (
            "" if is_binary
            else _format_colorbar_value(overlay_spec.get("min", ""))
        )
        max_text = (
            "" if is_binary
            else _format_colorbar_value(overlay_spec.get("max", ""))
        )

        # If the renderer used a colour we did not bundle, skip only that legend.
        if not _resolve_bundled_clut_path(color_name):
            print(
                f"[WARNING] Overlay colorbar skipped for {os.path.basename(path_in)}: "
                f"no bundled MRIcroGL CLUT found for '{color_name}'."
            )
            continue

        try:
            entry_bar_height = bar_width if is_binary else bar_height
            if is_binary:
                colorbar = _make_binary_clut_swatch_image(
                    color_name,
                    bar_width,
                    entry_bar_height,
                    overlay_spec.get("min"),
                    overlay_spec.get("max"),
                )
            else:
                colorbar = _make_clut_colorbar_image(
                    color_name,
                    bar_width,
                    bar_height,
                )
        except Exception as e:
            print(
                f"[WARNING] Overlay colorbar skipped for {os.path.basename(path_in)}: "
                f"could not parse CLUT for '{color_name}': {e}"
            )
            continue
        if colorbar is None:
            continue

        # Measure text so each stacked legend entry can align consistently.
        name_layout = _layout_colorbar_name(
            draw,
            overlay_name,
            name_font,
            name_max_width,
            name_line_gap,
        )
        name_w = name_layout["width"]
        name_h = name_layout["height"]
        if is_binary:
            max_w = max_h = min_w = min_h = 0
            value_width = 0
        else:
            max_w, max_h = _measure_text(draw, max_text, value_font)
            min_w, min_h = _measure_text(draw, min_text, value_font)
            value_width = max(max_w, min_w)
        entry_width = max(name_w, value_width + gap + bar_width)
        global_value_width = max(global_value_width, value_width)
        global_block_width = max(global_block_width, entry_width)
        entries.append({
            "colorbar": colorbar,
            "name_lines": name_layout["lines"],
            "name_line_sizes": name_layout["line_sizes"],
            "min": min_text,
            "max": max_text,
            "name_w": name_w,
            "name_h": name_h,
            "max_h": max_h,
            "min_h": min_h,
            "is_binary": is_binary,
            "bar_height": entry_bar_height,
        })

    if not entries:
        return

    block_x = max(margin, w - margin - global_block_width)
    current_y = margin
    for entry_idx, entry in enumerate(entries):
        name_y = current_y
        bar_x = block_x + global_value_width + gap
        bar_y = name_y + entry["name_h"] + name_to_bar_gap

        img.paste(entry["colorbar"], (bar_x, bar_y))
        draw.rectangle(
            [
                bar_x - 1,
                bar_y - 1,
                bar_x + bar_width,
                bar_y + entry["bar_height"],
            ],
            outline=(255, 255, 255),
            width=1
        )

        # Draw all text with a black outline so it remains readable over image content.
        current_name_y = name_y
        for line, (line_width, line_height) in zip(
            entry["name_lines"],
            entry["name_line_sizes"],
        ):
            name_x = block_x + max(
                0,
                (global_block_width - line_width) // 2,
            )
            _draw_text_with_outline(
                draw,
                (name_x, current_name_y),
                line,
                font=name_font,
            )
            current_name_y += line_height + name_line_gap
        if not entry["is_binary"]:
            _draw_text_with_outline(
                draw,
                (block_x, bar_y - entry["max_h"] // 2),
                entry["max"],
                font=value_font,
            )
            _draw_text_with_outline(
                draw,
                (
                    block_x,
                    bar_y + entry["bar_height"] - entry["min_h"] // 2,
                ),
                entry["min"],
                font=value_font,
            )
        current_y = (
            bar_y
            + entry["bar_height"]
            + (entry_gap if entry_idx < len(entries) - 1 else 0)
        )

    img.save(path_out)


def annotate_overlay_colorbar_on_png(path_in: str, path_out: str, overlay_spec: Dict) -> None:
    """Add one overlay colorbar legend to a stitched PNG."""
    annotate_overlay_colorbars_on_png(path_in, path_out, overlay_spec)


def annotate_overlay_colorbar_series(folder: str, overlay_spec) -> None:
    """Annotate each stitched concat PNG in a folder with overlay colorbars."""
    if not overlay_spec:
        return
    # These concat_*.png files are the final stitched panels that become PPTX slides.
    for path in sorted(glob.glob(os.path.join(folder, 'concat_*.png'))):
        annotate_overlay_colorbars_on_png(path, path, overlay_spec)


def annotate_overlay_colorbars_on_series(
    paths: List[str],
    overlay_specs,
) -> List[str]:
    """Apply one image/slot's deduplicated colorbars to each prepared PNG."""
    unique_specs = _deduplicate_overlay_colorbar_specs(overlay_specs)
    if not unique_specs:
        return paths
    for path in paths:
        annotate_overlay_colorbars_on_png(path, path, unique_specs)
    return paths


def _layout_modality_label(
    draw: ImageDraw.Draw,
    modality_text: str,
    image_width: int,
    image_height: int,
    margin: int,
) -> Dict:
    """Choose one/two label lines and the largest font that fits the image.

    Long custom labels wrap only between `` + `` components, keeping modality
    and overlay names intact. Underscores are converted to spaces for display.
    """
    components = [
        component.strip().replace("_", " ")
        for component in str(modality_text).split(" + ")
    ]
    display_text = " + ".join(components)
    available_width = max(1, int(image_width) - (2 * int(margin)))
    initial_size = max(12, int(image_height * 0.03))
    minimum_size = max(8, int(image_height * 0.02))

    # If the current one-line label fits, preserve the existing appearance.
    initial_font = _load_annotation_font(initial_size)
    initial_dimensions = _measure_text(draw, display_text, initial_font)
    if initial_dimensions[0] <= available_width:
        return {
            "lines": [display_text],
            "font": initial_font,
            "font_size": initial_size,
            "line_sizes": [initial_dimensions],
            "available_width": available_width,
        }

    # Build every legal two-line split and select by measured pixel width.
    split_candidates = [
        (
            " + ".join(components[:split_index]),
            "+ " + " + ".join(components[split_index:]),
        )
        for split_index in range(1, len(components))
    ]

    for font_size in range(initial_size, minimum_size - 1, -1):
        font = _load_annotation_font(font_size)
        if split_candidates:
            measured_candidates = []
            for lines in split_candidates:
                sizes = [_measure_text(draw, line, font) for line in lines]
                widths = [size[0] for size in sizes]
                measured_candidates.append(
                    (
                        max(widths),
                        abs(widths[0] - widths[1]),
                        lines,
                        sizes,
                    )
                )
            best = min(
                measured_candidates,
                key=lambda candidate: (candidate[0], candidate[1]),
            )
            if best[0] <= available_width:
                return {
                    "lines": list(best[2]),
                    "font": font,
                    "font_size": font_size,
                    "line_sizes": best[3],
                    "available_width": available_width,
                }
        else:
            dimensions = _measure_text(draw, display_text, font)
            if dimensions[0] <= available_width:
                return {
                    "lines": [display_text],
                    "font": font,
                    "font_size": font_size,
                    "line_sizes": [dimensions],
                    "available_width": available_width,
                }

    # Pathological single-component names may still exceed the readable lower
    # bound. Return the best lower-bound layout without adding a third line.
    font = _load_annotation_font(minimum_size)
    if split_candidates:
        measured_candidates = []
        for lines in split_candidates:
            sizes = [_measure_text(draw, line, font) for line in lines]
            widths = [size[0] for size in sizes]
            measured_candidates.append(
                (
                    max(widths),
                    abs(widths[0] - widths[1]),
                    lines,
                    sizes,
                )
            )
        best = min(
            measured_candidates,
            key=lambda candidate: (candidate[0], candidate[1]),
        )
        lines = list(best[2])
        line_sizes = best[3]
    else:
        lines = [display_text]
        line_sizes = [_measure_text(draw, display_text, font)]
    return {
        "lines": lines,
        "font": font,
        "font_size": minimum_size,
        "line_sizes": line_sizes,
        "available_width": available_width,
    }


def annotate_modality_center_bottom(path_in: str, path_out: str, modality_text: str) -> None:
    """Annotate a PNG with a modality label centered at the bottom edge.

    - Keeps short labels at the existing ~4.5%-of-height font size.
    - Wraps long component lists onto at most two centered lines.
    - Shrinks only as needed to fit the individual panel column.
    - Displays underscores as spaces without changing stored overlay names.
    - Draws with an outline for visibility on dark/light backgrounds.
    """
    img = PILImage.open(path_in).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size

    margin = max(8, int(h * 0.02))
    layout = _layout_modality_label(draw, modality_text, w, h, margin)
    line_gap = max(2, int(layout["font_size"] * 0.2))
    total_height = sum(size[1] for size in layout["line_sizes"])
    if len(layout["lines"]) > 1:
        total_height += line_gap * (len(layout["lines"]) - 1)
    current_y = max(0, h - margin - total_height)

    for line, (text_width, text_height) in zip(
        layout["lines"],
        layout["line_sizes"],
    ):
        x = max(0, (w - text_width) // 2)
        _draw_text_with_outline(
            draw,
            (x, current_y),
            line,
            font=layout["font"],
        )
        current_y += text_height + line_gap
    img.save(path_out)


def annotate_lr_on_png(path_in: str, path_out: str) -> None:
    """Add 'L' at the left edge and 'R' at the right edge (mid-height) of a PNG.

    - Uses a relative font size based on image height.
    - Falls back to a default font if Arial is unavailable.
    """
    img = PILImage.open(path_in).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Heuristic font size ~5% of image height (min 16 px)
    font_size = max(16, int(h * 0.05))
    font = _load_annotation_font(font_size)

    # Place labels near left and right edges with a small margin
    margin = max(8, int(w * 0.02))
    _draw_text_with_outline(draw, (margin, h // 2 - font_size // 2), 'L', font=font)
    _draw_text_with_outline(draw, (w - margin - font_size // 2, h // 2 - font_size // 2), 'R', font=font)
    img.save(path_out)


def annotate_by_angle_on_png(path_in: str, path_out: str, angle: str) -> None:
    """Annotate a PNG with orientation letters based on the viewing angle.

    Rules (as specified):
    - superior:  L on left,  R on right
    - inferior:  R on left,  L on right (swap)
    - anterior:  R on left,  L on right (swap)
    - posterior: L on left,  R on right
    - left, surg_left_lat, surg_left_ato: L on left only
    - right, surg_right_lat, surg_right_ato: R on right only
    - unknown: no orientation annotation
    """
    img = PILImage.open(path_in).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_size = max(16, int(h * 0.05))
    font = _load_annotation_font(font_size)

    margin = max(8, int(w * 0.02))

    # Compute vertical target positions:
    # - top-biased (about 1/3 from top)
    # - bottom-biased (about 2/3 from top)
    top_target_y = int(h * 0.33)
    bottom_target_y = int(h * 0.66)

    # Clamp targets within margins to avoid clipping
    y_top = max(margin, min(top_target_y, h - margin - font_size))
    y_bottom = max(margin, min(bottom_target_y, h - margin - font_size))

    # Horizontal anchoring near edges
    left_x = margin
    right_x = w - margin - font_size // 2

    angle_lower = (angle or '').lower()

    if angle_lower in ('superior', 'posterior'):
        # Default orientation; place labels higher (top-biased)
        _draw_text_with_outline(draw, (left_x, y_top), 'L', font=font)
        _draw_text_with_outline(draw, (right_x, y_top), 'R', font=font)
    elif angle_lower in ('inferior', 'anterior'):
        # Swap L/R; place labels higher (top-biased)
        _draw_text_with_outline(draw, (left_x, y_top), 'R', font=font)
        _draw_text_with_outline(draw, (right_x, y_top), 'L', font=font)
    elif angle_lower in ('left', 'surg_left_lat', 'surg_left_ato'):
        # Left sagittal family: only L on left, lower (bottom-biased).
        _draw_text_with_outline(draw, (left_x, y_bottom), 'L', font=font)
    elif angle_lower in ('right', 'surg_right_lat', 'surg_right_ato'):
        # Right sagittal family: only R on right, lower (bottom-biased).
        _draw_text_with_outline(draw, (right_x, y_bottom), 'R', font=font)
    else:
        # Unknown anatomy/view: omit labels rather than risk misinformation.
        pass

    img.save(path_out)


def concat_one_row(n: int, top_lists: List[List[str]], output_location: str) -> None:
    """Concatenate n columns (2–4 images per row) into one wide row per depth."""
    _ensure_dir(output_location)
    print(f"[INFO] Stitching {n} panel(s) into {output_location}...")
    for idx in range(n):
        # Collect each column image at this depth
        paths = [plist[idx] for plist in top_lists]
        images = [PILImage.open(p) for p in paths]

        # Layout: hard-concatenate along width
        widths, heights = zip(*(im.size for im in images))
        total_width = sum(widths)
        max_height = max(heights)
        new_im = PILImage.new('RGB', (total_width, max_height))

        x = 0
        for im in images:
            new_im.paste(im, (x, 0))
            x += im.size[0]
        new_im.save(os.path.join(output_location, f'concat_{idx:03}.png'))
    print(f"[INFO] Stitched {n} panel(s).")


def concat_two_rows(n: int, top_lists: List[List[str]], bottom_lists: List[List[str]], output_location: str) -> None:
    """Concatenate two rows (top and bottom) into a panel per depth."""
    _ensure_dir(output_location)
    print(f"[INFO] Stitching {n} panel(s) into {output_location}...")
    for idx in range(n):
        # Gather top row images and compute dimensions
        top_paths = [plist[idx] for plist in top_lists]
        bot_paths = [plist[idx] for plist in bottom_lists]
        top_images = [PILImage.open(p) for p in top_paths]
        bot_images = [PILImage.open(p) for p in bot_paths]

        top_widths, top_heights = zip(*(im.size for im in top_images))
        bot_widths, bot_heights = zip(*(im.size for im in bot_images))
        total_width = max(sum(top_widths), sum(bot_widths))
        top_h = max(top_heights)
        bot_h = max(bot_heights)

        new_im = PILImage.new('RGB', (total_width, top_h + bot_h))

        # Paste top row
        x = 0
        for im in top_images:
            new_im.paste(im, (x, 0))
            x += im.size[0]
        # Paste bottom row
        x = 0
        for im in bot_images:
            new_im.paste(im, (x, top_h))
            x += im.size[0]

        new_im.save(os.path.join(output_location, f'concat_{idx:03}.png'))
    print(f"[INFO] Stitched {n} panel(s).")


def export_pptx_from_folder(folder: str, pptx_basename: str) -> None:
    """Export all concat_*.png in a folder to a PPTX (one slide per image).
    Saves a single copy into the global PowerPoints directory only.
    """
    prs = Presentation()
    # Use a large 16:9-ish slide with black background to match your previous output
    prs.slide_width = Inches(38)
    prs.slide_height = Inches(22)
    from_left = Inches(0.3)
    from_top = Inches(0.3)
    width_inside = Inches(38 - 0.6)
    height_inside = Inches(22 - 0.6)

    def _are_consecutive_pngs_same_or_near_same(path_a: str, path_b: str) -> bool:
        """Return True when two PNGs are identical or within tiny tolerance."""
        try:
            with PILImage.open(path_a) as a_im, PILImage.open(path_b) as b_im:
                a_rgb = a_im.convert('RGB')
                b_rgb = b_im.convert('RGB')
                if a_rgb.size != b_rgb.size:
                    return False
                # Fast exact check first.
                if a_rgb.tobytes() == b_rgb.tobytes():
                    return True
                # Tiny-tolerance check for near-identical consecutive frames.
                diff = ImageChops.difference(a_rgb, b_rgb)
                mean_per_channel = ImageStat.Stat(diff).mean
                mean_abs_diff = sum(mean_per_channel) / float(len(mean_per_channel))
                return mean_abs_diff <= float(CONSECUTIVE_DEDUPE_MEAN_ABS_DIFF_THRESHOLD)
        except Exception:
            return False

    def _dedupe_consecutive_concat_pngs(target_folder: str) -> int:
        """Delete consecutive duplicate/near-duplicate concat_*.png files."""
        paths = sorted(glob.glob(os.path.join(target_folder, 'concat_*.png')))
        if len(paths) < 2:
            return 0

        removed = 0
        prev_kept: Optional[str] = None
        for p in paths:
            if prev_kept is not None and _are_consecutive_pngs_same_or_near_same(prev_kept, p):
                try:
                    os.remove(p)
                    removed += 1
                    continue
                except Exception:
                    pass
            prev_kept = p
        return removed

    removed_count = _dedupe_consecutive_concat_pngs(folder)
    if removed_count > 0:
        print(
            f"[INFO] Removed {removed_count} consecutive duplicate stitched PNG(s) "
            f"before PPTX export for '{pptx_basename}'."
        )

    images = sorted(glob.glob(os.path.join(folder, 'concat_*.png')))
    for path in images:
        # New slide with black background
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        fill = slide.background.fill
        fill.solid()
        from pptx.dml.color import RGBColor
        fill.fore_color.rgb = RGBColor(0, 0, 0)

        # Fit image into slide while preserving aspect ratio
        with PILImage.open(path) as im:
            w, h = im.size
        image_ratio = w / h
        slide_ratio = 38 / 22
        if image_ratio > slide_ratio:
            slide.shapes.add_picture(path, from_left, from_top, width=width_inside)
        else:
            slide.shapes.add_picture(path, from_left, from_top, height=height_inside)

    # Save a single copy in the global PowerPoints directory
    _ensure_dir(dir_structure.powerpoints_dir)
    out_global = os.path.join(dir_structure.powerpoints_dir, f"{pptx_basename}.pptx")
    prs.save(out_global)
    print(f"[INFO] Saved PPTX to: {out_global}")


def export_png_series_to_dicom_folder(
    folder: str,
    dicom_basename: str,
    series_description: str,
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    study_date: Optional[str] = None,
    study_time: Optional[str] = None,
    study_instance_uid: Optional[str] = None,
    output_root: Optional[str] = None
) -> List[str]:
    """Export stitched PNG panels as a DICOM series.

    The exported files are derived screenshots, not source MR/PET slices. The
    DICOM metadata therefore avoids anatomical geometry and stores the overlay
    description in human-readable series fields.
    """
    png_paths = sorted(glob.glob(os.path.join(folder, 'concat_*.png')))
    if not png_paths:
        print(f"[WARNING] DICOM export skipped: no concat_*.png files found in {folder}")
        return []

    root = output_root or dir_structure.dicom_dir
    output_dir = os.path.join(root, dicom_basename)
    _ensure_dir(output_dir)

    now = datetime.now()
    study_uid = study_instance_uid or generate_uid()
    series_uid = generate_uid()
    saved_paths = []

    for instance_number, png_path in enumerate(png_paths, start=1):
        with PILImage.open(png_path) as img:
            rgb_img = img.convert('RGB')
            rows = int(rgb_img.height)
            cols = int(rgb_img.width)
            pixel_bytes = rgb_img.tobytes()

        sop_instance_uid = generate_uid()
        file_meta = FileMetaDataset()
        file_meta.FileMetaInformationVersion = b'\x00\x01'
        file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()

        out_path = os.path.join(output_dir, f"{instance_number:04d}.dcm")
        ds = FileDataset(out_path, {}, file_meta=file_meta, preamble=b'\0' * 128)
        ds.is_little_endian = True
        ds.is_implicit_VR = False

        ds.SOPClassUID = SecondaryCaptureImageStorage
        ds.SOPInstanceUID = sop_instance_uid
        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.Modality = "OT"
        ds.PatientID = patient_id or ""
        ds.PatientName = patient_name or ""
        ds.StudyDescription = ""
        ds.SeriesDescription = series_description
        ds.ImageComments = "Postprocessed T1 and coregistered overlay image, non-quantitative"
        ds.InstanceNumber = instance_number
        ds.ContentDate = now.strftime("%Y%m%d")
        ds.ContentTime = now.strftime("%H%M%S")
        ds.StudyDate = study_date or ""
        ds.StudyTime = study_time or ""
        ds.SeriesDate = ds.ContentDate
        ds.SeriesTime = ds.ContentTime
        ds.Manufacturer = ""
        ds.ConversionType = "WSD"

        ds.SamplesPerPixel = 3
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0
        ds.Rows = rows
        ds.Columns = cols
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = pixel_bytes

        pydicom.dcmwrite(out_path, ds, write_like_original=False)
        saved_paths.append(out_path)

    print(f"[INFO] Saved DICOM Secondary Capture series to: {output_dir}")
    return saved_paths


def run_preset_t1_overview_per_depth(
    add_orientation_labels: bool = True,
    background_rgb: List[int] = [0, 0, 0],
    threshold: int = 2,
    pptx_name: str = "T1_overview",
    render_root_dir: str = None,
    modality_label: str = "T1",
    export_dicom: bool = False,
    dicom_basename: Optional[str] = None,
    dicom_series_description: Optional[str] = None,
    dicom_patient_id: Optional[str] = None,
    dicom_patient_name: Optional[str] = None,
    dicom_study_date: Optional[str] = None,
    dicom_study_time: Optional[str] = None,
    dicom_study_instance_uid: Optional[str] = None,
    overlay_colorbar_spec: Optional[Dict] = None
) -> None:
    """Stitch T1 multi-angle panels per erosion depth and export PPTX.

    Workflow:
    - Collect angle folders: left/right/superior/inferior/anterior/posterior.
    - Ensure all have the same number of PNGs (one per depth).
    - Crop each folder using the legacy algorithm.
    - Optionally overlay L/R onto each cropped image.
    - Concatenate into TWO rows per depth:
      * Top row: left, right
      * Bottom row: superior, inferior, anterior, posterior
    - Export all panels to a PPTX (one slide per panel).
    """
    angles = ['left', 'right', 'superior', 'inferior', 'anterior', 'posterior']
    base_render_root = render_root_dir or dir_structure.renders_t1_dir
    angle_dirs = [os.path.join(base_render_root, 'by_angle', a) for a in angles]

    # Build erosion-prefix maps for each required angle and keep only shared prefixes.
    prefix_maps = []
    all_prefixes: Set[str] = set()
    for angle, d in zip(angles, angle_dirs):
        mp = _build_prefix_map(_list_pngs(d))
        if not mp:
            print(f"[WARNING] T1 overview preset skipped: no eligible '*_eroded*' PNGs found for angle '{angle}'")
            return
        prefix_maps.append(mp)
        all_prefixes.update(mp.keys())

    common_prefixes = _common_prefixes_across_maps(prefix_maps)
    if not common_prefixes:
        print("[WARNING] T1 overview preset skipped: no shared erosion prefixes across required angles")
        return
    _log_skipped_prefixes("T1 overview", all_prefixes, common_prefixes)
    dir_pngs = [[mp[pfx] for pfx in common_prefixes] for mp in prefix_maps]

    # Crop per angle folder and annotate overlays, preserving order per depth
    cropped_lists = []
    for paths, adir in zip(dir_pngs, angle_dirs):
        dims = get_crop_dimensions(paths, background_rgb, threshold)
        cropped = crop_image_series(paths, adir, dims)
        annotated_dir = os.path.join(adir, '1_cropped_annotated')
        _ensure_dir(annotated_dir)
        ann_paths = []
        for p in cropped:
            out = os.path.join(annotated_dir, os.path.basename(p))
            if add_orientation_labels:
                # First add angle-based L/R annotations
                annotate_by_angle_on_png(p, out, adir.split('/')[-1])
            else:
                # Copy cropped into annotated_dir if not adding L/R
                try:
                    from shutil import copyfile
                    copyfile(p, out)
                except Exception:
                    continue
            # Always add modality label
            annotate_modality_center_bottom(out, out, modality_label)
            ann_paths.append(out)
        cropped_lists.append(sorted(ann_paths))

    # Map angle -> list for two-row layout
    angle_to_list = {ang: lst for ang, lst in zip(angles, cropped_lists)}

    # Output directory for stitched panels
    out_panel_dir = os.path.join(base_render_root, 'stitched_overview')
    _ensure_dir(out_panel_dir)

    # Require all six angles (already enforced above) and stitch two rows.
    n = len(common_prefixes)
    top_lists = [angle_to_list['left'], angle_to_list['right']]
    bottom_lists = [angle_to_list['superior'], angle_to_list['inferior'], angle_to_list['anterior'], angle_to_list['posterior']]
    concat_two_rows(n, top_lists, bottom_lists, out_panel_dir)
    annotate_overlay_colorbar_series(out_panel_dir, overlay_colorbar_spec)

    # Export PPTX with one slide per stitched panel
    export_pptx_from_folder(out_panel_dir, pptx_name)
    if export_dicom:
        export_png_series_to_dicom_folder(
            out_panel_dir,
            dicom_basename or pptx_name,
            dicom_series_description or pptx_name,
            patient_id=dicom_patient_id,
            patient_name=dicom_patient_name,
            study_date=dicom_study_date,
            study_time=dicom_study_time,
            study_instance_uid=dicom_study_instance_uid
        )


def run_preset_multimodal_by_angle_per_depth(
    angles: List[str] = ['left','right','superior','inferior','anterior','posterior'],
    add_orientation_labels: bool = True,
    background_rgb: List[int] = [0, 0, 0],
    threshold: int = 2,
    pptx_name: str = "Multimodal_by_angle"
) -> None:
    """Stitch multimodal panels (T1, best T2 plane for angle, FLAIR) per depth into one PPTX.

    For each angle, we assemble a one-row panel with:
      - T1 by_angle/<angle>
      - T2 best acquisition for that angle:
          left/right -> T2_Sag_3D_renders
          anterior/posterior -> T2_Cor_3D_renders
          superior/inferior -> T2_Tra_3D_renders
        (if missing, we attempt T2_3D_3D_renders; if still missing, skip the angle)
      - FLAIR by_angle/<angle> (optional; skip if missing)

    We crop each input directory with the legacy algorithm, annotate L/R by angle,
    then stitch top row per depth. Slides are appended to a single PPTX in PowerPoints.
    """
    # Resolve base dirs
    t1_base = dir_structure.renders_t1_dir
    t2_base = dir_structure.renders_t2_dir
    flair_base = os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders')

    # Map angle -> best T2 plane folder name
    angle_to_t2_plane = {
        'left': 'T2_Sag_3D_renders',
        'right': 'T2_Sag_3D_renders',
        'anterior': 'T2_Cor_3D_renders',
        'posterior': 'T2_Cor_3D_renders',
        'superior': 'T2_Tra_3D_renders',
        'inferior': 'T2_Tra_3D_renders',
    }

    # Create a temporary folder to collect panels per angle then export
    panels_root = os.path.join(dir_structure.renders_dir, 'stitched_multimodal_by_angle')
    _ensure_dir(panels_root)

    # Collect all panel folders generated to feed PPTX
    per_angle_panel_folders = []

    for angle in angles:
        angle_dir_name = angle.lower()
        # Build input directories for this angle
        t1_dir = os.path.join(t1_base, 'by_angle', angle_dir_name)
        t2_plane = angle_to_t2_plane.get(angle_dir_name)
        t2_dir = os.path.join(t2_base, t2_plane, 'by_angle', angle_dir_name) if t2_plane else None
        flair_dir = os.path.join(flair_base, 'by_angle', angle_dir_name)

        # Fallback to T2_3D if plane-specific is missing
        if not (t2_dir and os.path.isdir(t2_dir) and _list_pngs(t2_dir)):
            t2_dir_alt = os.path.join(t2_base, 'T2_3D_3D_renders', 'by_angle', angle_dir_name)
            if os.path.isdir(t2_dir_alt) and _list_pngs(t2_dir_alt):
                t2_dir = t2_dir_alt

        # Check existence and PNG lists
        candidates = [(t1_dir, 't1'), (t2_dir, 't2'), (flair_dir, 'flair')]
        valid_dirs = []
        for d, label in candidates:
            if d and os.path.isdir(d):
                pngs = _list_pngs(d)
                if pngs:
                    valid_dirs.append((d, pngs))

        # Need at least T1 and one other to build a useful multimodal panel
        if len(valid_dirs) < 2:
            print(f"[WARNING] Skipping angle '{angle}': insufficient inputs")
            continue

        # Keep only erosion prefixes shared across all participating modalities.
        prefix_maps = []
        all_prefixes: Set[str] = set()
        for _, pngs in valid_dirs:
            mp = _build_prefix_map(pngs)
            if not mp:
                prefix_maps = []
                break
            prefix_maps.append(mp)
            all_prefixes.update(mp.keys())
        if not prefix_maps:
            print(f"[WARNING] Skipping angle '{angle}': no eligible '*_eroded*' PNGs")
            continue
        common_prefixes = _common_prefixes_across_maps(prefix_maps)
        if not common_prefixes:
            print(f"[WARNING] Skipping angle '{angle}': no shared erosion prefixes across participating modalities")
            continue
        _log_skipped_prefixes(f"Multimodal by-angle ({angle})", all_prefixes, common_prefixes)

        # Crop and annotate per directory
        cropped_lists = []
        for (d, pngs), prefix_map in zip(valid_dirs, prefix_maps):
            selected_pngs = [prefix_map[pfx] for pfx in common_prefixes]
            dims = get_crop_dimensions(selected_pngs, background_rgb, threshold)
            cropped = crop_image_series(selected_pngs, d, dims)
            annotated_dir = os.path.join(d, '1_cropped_annotated')
            _ensure_dir(annotated_dir)
            ann_paths = []
            for p in cropped:
                out = os.path.join(annotated_dir, os.path.basename(p))
                if add_orientation_labels:
                    annotate_by_angle_on_png(p, out, angle)
                else:
                    try:
                        from shutil import copyfile
                        copyfile(p, out)
                    except Exception:
                        continue
                # Determine modality text by directory identity
                if d == t1_dir:
                    modality_text = 'T1'
                elif d == flair_dir:
                    modality_text = 'FLAIR'
                else:
                    modality_text = 'T2 (inv)'
                annotate_modality_center_bottom(out, out, modality_text)
                ann_paths.append(out)
            cropped_lists.append(sorted(ann_paths))

        # Stitch a single-row panel for this angle
        out_panel_dir = os.path.join(panels_root, angle_dir_name)
        _ensure_dir(out_panel_dir)
        n = len(common_prefixes)
        concat_one_row(n, cropped_lists, out_panel_dir)
        per_angle_panel_folders.append(out_panel_dir)

    # Build one combined PPTX: append all angles' panels ordered by angles list
    # Create a temp folder to collect copies in desired order
    combined_folder = os.path.join(panels_root, '_combined_for_pptx')
    _ensure_dir(combined_folder)

    slide_idx = 0
    for angle in angles:
        angle_dir_name = angle.lower()
        pdir = os.path.join(panels_root, angle_dir_name)
        if not os.path.isdir(pdir):
            continue
        panel_paths = sorted(glob.glob(os.path.join(pdir, 'concat_*.png')))
        for p in panel_paths:
            # Copy into combined folder with sequential names to preserve order
            dst = os.path.join(combined_folder, f'concat_{slide_idx:03}.png')
            try:
                from shutil import copyfile
                copyfile(p, dst)
                slide_idx += 1
            except Exception:
                pass

    # Export single PPTX with all angles
    export_pptx_from_folder(combined_folder, pptx_basename=pptx_name) 


def run_preset_t2_overview_per_depth(
    add_orientation_labels: bool = True,
    background_rgb: List[int] = [0, 0, 0],
    threshold: int = 2,
    pptx_name: str = "T2_overview"
) -> None:
    """Stitch T2 multi-angle panels per erosion depth and export PPTX.

    Angle → plane mapping (best visual quality):
      - left/right      → T2_Sag_3D_renders
      - anterior/posterior → T2_Cor_3D_renders
      - superior/inferior  → T2_Tra_3D_renders

    Fallback per angle: T2_3D_3D_renders if the plane-specific folder is missing/empty.
    """
    angles = ['left', 'right', 'superior', 'inferior', 'anterior', 'posterior']
    angle_to_t2_plane = {
        'left': 'T2_Sag_3D_renders',
        'right': 'T2_Sag_3D_renders',
        'anterior': 'T2_Cor_3D_renders',
        'posterior': 'T2_Cor_3D_renders',
        'superior': 'T2_Tra_3D_renders',
        'inferior': 'T2_Tra_3D_renders',
    }

    t2_base = dir_structure.renders_t2_dir

    # Resolve a directory per angle (with fallback to T2_3D)
    resolved_dirs = {}
    for angle in angles:
        plane = angle_to_t2_plane.get(angle)
        primary = os.path.join(t2_base, plane, 'by_angle', angle) if plane else None
        chosen = None
        if primary and os.path.isdir(primary) and _list_pngs(primary):
            chosen = primary
        else:
            alt = os.path.join(t2_base, 'T2_3D_3D_renders', 'by_angle', angle)
            if os.path.isdir(alt) and _list_pngs(alt):
                chosen = alt
        if chosen:
            resolved_dirs[angle] = chosen

    # Require all six angles for T2 overview.
    missing_angles = [a for a in angles if a not in resolved_dirs]
    if missing_angles:
        print(f"[WARNING] T2 overview preset skipped: missing required angle folders: {', '.join(missing_angles)}")
        return

    # Build erosion-prefix maps for each required angle and keep only shared prefixes.
    angle_order = angles
    prefix_maps = []
    all_prefixes: Set[str] = set()
    for angle in angle_order:
        mp = _build_prefix_map(_list_pngs(resolved_dirs[angle]))
        if not mp:
            print(f"[WARNING] T2 overview preset skipped: no eligible '*_eroded*' PNGs for angle '{angle}'")
            return
        prefix_maps.append(mp)
        all_prefixes.update(mp.keys())
    common_prefixes = _common_prefixes_across_maps(prefix_maps)
    if not common_prefixes:
        print("[WARNING] T2 overview preset skipped: no shared erosion prefixes across required angles")
        return
    _log_skipped_prefixes("T2 overview", all_prefixes, common_prefixes)
    dir_pngs = [[mp[pfx] for pfx in common_prefixes] for mp in prefix_maps]

    # Crop and annotate per resolved angle folder
    cropped_lists = []
    for angle, paths in zip(angle_order, dir_pngs):
        dims = get_crop_dimensions(paths, background_rgb, threshold)
        cropped = crop_image_series(paths, resolved_dirs[angle], dims)
        annotated_dir = os.path.join(resolved_dirs[angle], '1_cropped_annotated')
        _ensure_dir(annotated_dir)
        ann_paths = []
        for p in cropped:
            out = os.path.join(annotated_dir, os.path.basename(p))
            if add_orientation_labels:
                annotate_by_angle_on_png(p, out, angle)
            else:
                try:
                    from shutil import copyfile
                    copyfile(p, out)
                except Exception:
                    continue
            annotate_modality_center_bottom(out, out, 'T2 (inv)')
            ann_paths.append(out)
        cropped_lists.append(sorted(ann_paths))

    # Output directory for stitched panels
    out_panel_dir = os.path.join(dir_structure.renders_t2_dir, 'stitched_overview')
    _ensure_dir(out_panel_dir)

    # Build two-row layout (all six required angles were enforced above).
    angle_to_list = {ang: lst for ang, lst in zip(angle_order, cropped_lists)}
    n = len(common_prefixes)
    top_lists = [angle_to_list['left'], angle_to_list['right']]
    bottom_lists = [angle_to_list['superior'], angle_to_list['inferior'], angle_to_list['anterior'], angle_to_list['posterior']]
    concat_two_rows(n, top_lists, bottom_lists, out_panel_dir)

    export_pptx_from_folder(out_panel_dir, pptx_name)


def run_preset_multimodal_other_angles_per_depth(
    angles: List[str] = ['surg_left_lat','surg_right_lat','surg_left_ato','surg_right_ato'],
    add_orientation_labels: bool = True,
    background_rgb: List[int] = [0, 0, 0],
    threshold: int = 2,
    pptx_name: str = "multimodal_overview_other_angles"
) -> None:
    """Stitch multimodal panels (T1, best T2 plane, FLAIR) at specified surgical views.

    T2 plane choice (initial): sagittal for all four views.
    Fallbacks mirror the main multimodal preset: if sagittal missing, try T2_3D.
    """
    t1_base = dir_structure.renders_t1_dir
    t2_base = dir_structure.renders_t2_dir
    flair_base = os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders')

    panels_root = os.path.join(dir_structure.renders_dir, 'stitched_multimodal_other_angles')
    _ensure_dir(panels_root)

    per_angle_panel_folders = []
    for angle in angles:
        angle_dir = angle.lower()
        t1_dir = os.path.join(t1_base, 'by_angle', angle_dir)
        # Prefer sagittal T2 for these views
        t2_dir = os.path.join(t2_base, 'T2_Sag_3D_renders', 'by_angle', angle_dir)
        if not (os.path.isdir(t2_dir) and _list_pngs(t2_dir)):
            t2_alt = os.path.join(t2_base, 'T2_3D_3D_renders', 'by_angle', angle_dir)
            if os.path.isdir(t2_alt) and _list_pngs(t2_alt):
                t2_dir = t2_alt
        flair_dir = os.path.join(flair_base, 'by_angle', angle_dir)

        candidates = [(t1_dir, 't1'), (t2_dir, 't2'), (flair_dir, 'flair')]
        valid_dirs = []
        for d, label in candidates:
            if d and os.path.isdir(d):
                pngs = _list_pngs(d)
                if pngs:
                    valid_dirs.append((d, pngs))
        if len(valid_dirs) < 2:
            print(f"[WARNING] Skipping angle '{angle}': insufficient inputs")
            continue

        # Keep only erosion prefixes shared across all participating modalities.
        prefix_maps = []
        all_prefixes: Set[str] = set()
        for _, pngs in valid_dirs:
            mp = _build_prefix_map(pngs)
            if not mp:
                prefix_maps = []
                break
            prefix_maps.append(mp)
            all_prefixes.update(mp.keys())
        if not prefix_maps:
            print(f"[WARNING] Skipping angle '{angle}': no eligible '*_eroded*' PNGs")
            continue
        common_prefixes = _common_prefixes_across_maps(prefix_maps)
        if not common_prefixes:
            print(f"[WARNING] Skipping angle '{angle}': no shared erosion prefixes across participating modalities")
            continue
        _log_skipped_prefixes(f"Multimodal surgical ({angle})", all_prefixes, common_prefixes)

        cropped_lists = []
        for (d, pngs), prefix_map in zip(valid_dirs, prefix_maps):
            selected_pngs = [prefix_map[pfx] for pfx in common_prefixes]
            dims = get_crop_dimensions(selected_pngs, background_rgb, threshold)
            cropped = crop_image_series(selected_pngs, d, dims)
            annotated_dir = os.path.join(d, '1_cropped_annotated')
            _ensure_dir(annotated_dir)
            ann_paths = []
            for p in cropped:
                out = os.path.join(annotated_dir, os.path.basename(p))
                if add_orientation_labels:
                    annotate_by_angle_on_png(p, out, angle)
                else:
                    try:
                        from shutil import copyfile
                        copyfile(p, out)
                    except Exception:
                        continue
                if d == t1_dir:
                    modality_text = 'T1'
                elif d == flair_dir:
                    modality_text = 'FLAIR'
                else:
                    modality_text = 'T2 (inv)'
                annotate_modality_center_bottom(out, out, modality_text)
                ann_paths.append(out)
            cropped_lists.append(sorted(ann_paths))

        out_panel_dir = os.path.join(panels_root, angle_dir)
        _ensure_dir(out_panel_dir)
        n = len(common_prefixes)
        concat_one_row(n, cropped_lists, out_panel_dir)
        per_angle_panel_folders.append(out_panel_dir)

    # Combine to a single PPTX in requested order
    combined_folder = os.path.join(panels_root, '_combined_for_pptx')
    _ensure_dir(combined_folder)
    slide_idx = 0
    for angle in angles:
        angle_dir = angle.lower()
        pdir = os.path.join(panels_root, angle_dir)
        if not os.path.isdir(pdir):
            continue
        panel_paths = sorted(glob.glob(os.path.join(pdir, 'concat_*.png')))
        for p in panel_paths:
            dst = os.path.join(combined_folder, f'concat_{slide_idx:03}.png')
            try:
                from shutil import copyfile
                copyfile(p, dst)
                slide_idx += 1
            except Exception:
                pass

    export_pptx_from_folder(combined_folder, pptx_basename=pptx_name)


def _build_slice_number_map(paths: List[str]) -> Dict[str, str]:
    """Build mapping: slice number key -> file path for '*-NNN-*' slice screenshots."""
    out: Dict[str, str] = {}
    for p in sorted(paths):
        bn = os.path.basename(p)
        m = re.search(r"-(\d{3})-", bn)
        if not m:
            continue
        key = m.group(1)
        if key not in out:
            out[key] = p
    return out


def _prepare_qmm_annotated_series(
    paths_by_key: Dict[str, str],
    ordered_keys: List[str],
    output_dir: str,
    angle: str,
    modality_label: str,
    add_orientation_labels: bool,
    background_rgb: List[int],
    threshold: int
) -> List[str]:
    """Create cropped+annotated PNG list ordered by keys for quant_map_mm_panel stitching."""
    _ensure_dir(output_dir)
    selected_paths = [paths_by_key.get(key) for key in ordered_keys if paths_by_key.get(key)]
    if not selected_paths:
        return []

    print(
        f"[INFO] Preparing annotated series for {modality_label} ({angle}) "
        f"with {len(selected_paths)} image(s)..."
    )
    # Keep qmm behavior aligned with other presets: crop first, then annotate.
    try:
        dims = get_crop_dimensions(selected_paths, background_rgb, threshold)
        source_paths = crop_image_series(selected_paths, output_dir, dims)
    except Exception:
        source_paths = selected_paths

    ann_paths = []
    for src in source_paths:
        dst = os.path.join(output_dir, os.path.basename(src))
        if add_orientation_labels:
            annotate_by_angle_on_png(src, dst, angle)
        else:
            try:
                from shutil import copyfile
                copyfile(src, dst)
            except Exception:
                continue
        annotate_modality_center_bottom(dst, dst, modality_label)
        ann_paths.append(dst)
    return ann_paths


def _qmm_t2_modality_label(t2_source: str) -> str:
    """Return a user-facing inverted-T2 label for one QMM source."""
    source_key = str(t2_source).strip().lower()
    labels = {
        "t2_sag": "T2 sag (inv)",
        "t2_sag_left": "T2 sag (inv)",
        "t2_sag_right": "T2 sag (inv)",
        "t2_sag_generic": "T2 sag (inv)",
        "t2_cor": "T2 cor (inv)",
        "t2_tra": "T2 tra (inv)",
        "t2_3d": "T2 3D (inv)",
    }
    return labels.get(source_key, "T2 (inv)")


def run_preset_quant_map_mm_panel(
    raw_root: str,
    angle_to_t2_source: Dict[str, str],
    qmm_angles: Optional[List[str]] = None,
    overlay_names: Optional[List[str]] = None,
    add_orientation_labels: bool = True,
    background_rgb: List[int] = [0, 0, 0],
    threshold: int = 2,
    pptx_name: str = "quant_map_mm_panel_overview",
    overlay_specs: Optional[List[Dict]] = None,
) -> None:
    """Build quant_map_mm_panel stitched PNGs and PPTX from raw screenshot folders.

    Expects raw_root folder structure:
      raw_root/T1/<angle>_slices_overlay
      raw_root/T1/<angle>_slices_structural
      raw_root/T1/<angle>_erosion_overlay
      raw_root/T1/<angle>_erosion_structural
      raw_root/<T2_source>/...
      raw_root/FLAIR/...
    where <T2_source> is one of: T2_sag, T2_cor, T2_tra, T2_3d.
    """
    angles = qmm_angles or ['left', 'right', 'anterior', 'posterior', 'superior', 'inferior']
    overlay1_name = (overlay_names[0] if overlay_names and len(overlay_names) >= 1 else "Overlay1")
    t1_overlay_names = overlay_names if overlay_names else [overlay1_name]
    t1_overlay_label = "T1 + " + " + ".join(t1_overlay_names)
    flair_overlay_label = f"FLAIR + {overlay1_name}"
    t1_colorbar_specs = _deduplicate_overlay_colorbar_specs(overlay_specs)
    non_t1_colorbar_specs = t1_colorbar_specs[:1]
    stitched_root = os.path.join(dir_structure.renders_qmm_stitched_dir, 'by_angle')
    _ensure_dir(stitched_root)
    combined_for_pptx = os.path.join(dir_structure.renders_qmm_stitched_dir, '_combined_for_pptx')
    _ensure_dir(combined_for_pptx)

    slide_idx = 0
    for angle in angles:
        t2_source = angle_to_t2_source.get(angle)
        if not t2_source:
            print(f"[WARNING] quant_map_mm_panel: skipping angle '{angle}' (no T2 source selected)")
            continue
        t2_structural_label = _qmm_t2_modality_label(t2_source)
        t2_overlay_label = f"{t2_structural_label} + {overlay1_name}"

        # Build six required directories for two-row (top overlay, bottom structural)
        t1_overlay_dir = os.path.join(raw_root, 'T1', f"{angle}_slices_overlay")
        t2_overlay_dir = os.path.join(raw_root, t2_source, f"{angle}_slices_overlay")
        flair_overlay_dir = os.path.join(raw_root, 'FLAIR', f"{angle}_slices_overlay")
        t1_struct_dir = os.path.join(raw_root, 'T1', f"{angle}_slices_structural")
        t2_struct_dir = os.path.join(raw_root, t2_source, f"{angle}_slices_structural")
        flair_struct_dir = os.path.join(raw_root, 'FLAIR', f"{angle}_slices_structural")

        # Also stitch erosion snapshots for the same angle.
        t1_overlay_erode_dir = os.path.join(raw_root, 'T1', f"{angle}_erosion_overlay")
        t2_overlay_erode_dir = os.path.join(raw_root, t2_source, f"{angle}_erosion_overlay")
        flair_overlay_erode_dir = os.path.join(raw_root, 'FLAIR', f"{angle}_erosion_overlay")
        t1_struct_erode_dir = os.path.join(raw_root, 'T1', f"{angle}_erosion_structural")
        t2_struct_erode_dir = os.path.join(raw_root, t2_source, f"{angle}_erosion_structural")
        flair_struct_erode_dir = os.path.join(raw_root, 'FLAIR', f"{angle}_erosion_structural")

        # -------------------- Slice sweep panels --------------------
        slice_dirs = [
            t1_overlay_dir, t2_overlay_dir, flair_overlay_dir,
            t1_struct_dir, t2_struct_dir, flair_struct_dir
        ]
        if not all(os.path.isdir(d) for d in slice_dirs):
            print(f"[WARNING] quant_map_mm_panel: skipping angle '{angle}' slices (missing one or more required dirs)")
        else:
            slice_maps = [_build_slice_number_map(_list_pngs(d)) for d in slice_dirs]
            if all(slice_maps):
                all_slice_keys: Set[str] = set()
                for mp in slice_maps:
                    all_slice_keys.update(mp.keys())
                common_slice_keys = _common_prefixes_across_maps(slice_maps)
                if common_slice_keys:
                    _log_skipped_prefixes(f"quant_map_mm_panel slices ({angle})", all_slice_keys, common_slice_keys)

                    annotated_root = os.path.join(stitched_root, angle, 'slices_annotated')
                    t1_ov_ann = _prepare_qmm_annotated_series(slice_maps[0], common_slice_keys, os.path.join(annotated_root, 't1_overlay'), angle, t1_overlay_label, add_orientation_labels, background_rgb, threshold)
                    t2_ov_ann = _prepare_qmm_annotated_series(slice_maps[1], common_slice_keys, os.path.join(annotated_root, 't2_overlay'), angle, t2_overlay_label, add_orientation_labels, background_rgb, threshold)
                    fl_ov_ann = _prepare_qmm_annotated_series(slice_maps[2], common_slice_keys, os.path.join(annotated_root, 'flair_overlay'), angle, flair_overlay_label, add_orientation_labels, background_rgb, threshold)
                    t1_st_ann = _prepare_qmm_annotated_series(slice_maps[3], common_slice_keys, os.path.join(annotated_root, 't1_struct'), angle, 'T1', add_orientation_labels, background_rgb, threshold)
                    t2_st_ann = _prepare_qmm_annotated_series(slice_maps[4], common_slice_keys, os.path.join(annotated_root, 't2_struct'), angle, t2_structural_label, add_orientation_labels, background_rgb, threshold)
                    fl_st_ann = _prepare_qmm_annotated_series(slice_maps[5], common_slice_keys, os.path.join(annotated_root, 'flair_struct'), angle, 'FLAIR', add_orientation_labels, background_rgb, threshold)

                    annotate_overlay_colorbars_on_series(
                        t1_ov_ann,
                        t1_colorbar_specs,
                    )
                    annotate_overlay_colorbars_on_series(
                        t2_ov_ann,
                        non_t1_colorbar_specs,
                    )
                    annotate_overlay_colorbars_on_series(
                        fl_ov_ann,
                        non_t1_colorbar_specs,
                    )

                    n = len(common_slice_keys)
                    out_angle_slices = os.path.join(stitched_root, angle, 'slices_stitched')
                    _ensure_dir(out_angle_slices)
                    concat_two_rows(
                        n,
                        top_lists=[t1_ov_ann, t2_ov_ann, fl_ov_ann],
                        bottom_lists=[t1_st_ann, t2_st_ann, fl_st_ann],
                        output_location=out_angle_slices
                    )

                else:
                    print(f"[WARNING] quant_map_mm_panel: no shared slice keys for angle '{angle}'")
            else:
                print(f"[WARNING] quant_map_mm_panel: no eligible slice PNGs for angle '{angle}'")

        # -------------------- Erosion snapshot panels --------------------
        erode_dirs = [
            t1_overlay_erode_dir, t2_overlay_erode_dir, flair_overlay_erode_dir,
            t1_struct_erode_dir, t2_struct_erode_dir, flair_struct_erode_dir
        ]
        if not all(os.path.isdir(d) for d in erode_dirs):
            print(f"[WARNING] quant_map_mm_panel: skipping angle '{angle}' erosions (missing one or more required dirs)")
            continue

        erode_maps = [_build_prefix_map(_list_pngs(d)) for d in erode_dirs]
        if not all(erode_maps):
            print(f"[WARNING] quant_map_mm_panel: no eligible erosion PNGs for angle '{angle}'")
            continue

        all_erode_keys: Set[str] = set()
        for mp in erode_maps:
            all_erode_keys.update(mp.keys())
        common_erode_keys = _common_prefixes_across_maps(erode_maps)
        if not common_erode_keys:
            print(f"[WARNING] quant_map_mm_panel: no shared erosion prefixes for angle '{angle}'")
            continue
        _log_skipped_prefixes(f"quant_map_mm_panel erosions ({angle})", all_erode_keys, common_erode_keys)

        erode_ann_root = os.path.join(stitched_root, angle, 'erosions_annotated')
        t1_ov_e_ann = _prepare_qmm_annotated_series(erode_maps[0], common_erode_keys, os.path.join(erode_ann_root, 't1_overlay'), angle, t1_overlay_label, add_orientation_labels, background_rgb, threshold)
        t2_ov_e_ann = _prepare_qmm_annotated_series(erode_maps[1], common_erode_keys, os.path.join(erode_ann_root, 't2_overlay'), angle, t2_overlay_label, add_orientation_labels, background_rgb, threshold)
        fl_ov_e_ann = _prepare_qmm_annotated_series(erode_maps[2], common_erode_keys, os.path.join(erode_ann_root, 'flair_overlay'), angle, flair_overlay_label, add_orientation_labels, background_rgb, threshold)
        t1_st_e_ann = _prepare_qmm_annotated_series(erode_maps[3], common_erode_keys, os.path.join(erode_ann_root, 't1_struct'), angle, 'T1', add_orientation_labels, background_rgb, threshold)
        t2_st_e_ann = _prepare_qmm_annotated_series(erode_maps[4], common_erode_keys, os.path.join(erode_ann_root, 't2_struct'), angle, t2_structural_label, add_orientation_labels, background_rgb, threshold)
        fl_st_e_ann = _prepare_qmm_annotated_series(erode_maps[5], common_erode_keys, os.path.join(erode_ann_root, 'flair_struct'), angle, 'FLAIR', add_orientation_labels, background_rgb, threshold)

        annotate_overlay_colorbars_on_series(
            t1_ov_e_ann,
            t1_colorbar_specs,
        )
        annotate_overlay_colorbars_on_series(
            t2_ov_e_ann,
            non_t1_colorbar_specs,
        )
        annotate_overlay_colorbars_on_series(
            fl_ov_e_ann,
            non_t1_colorbar_specs,
        )

        n_erode = len(common_erode_keys)
        out_angle_erosions = os.path.join(stitched_root, angle, 'erosions_stitched')
        _ensure_dir(out_angle_erosions)
        concat_two_rows(
            n_erode,
            top_lists=[t1_ov_e_ann, t2_ov_e_ann, fl_ov_e_ann],
            bottom_lists=[t1_st_e_ann, t2_st_e_ann, fl_st_e_ann],
            output_location=out_angle_erosions
        )

        # For each angle in the final PPTX sequence, place erosion panels first, then slices.
        for p in sorted(glob.glob(os.path.join(out_angle_erosions, 'concat_*.png'))):
            dst = os.path.join(combined_for_pptx, f'concat_{slide_idx:03}.png')
            try:
                from shutil import copyfile
                copyfile(p, dst)
                slide_idx += 1
            except Exception:
                pass

        out_angle_slices = os.path.join(stitched_root, angle, 'slices_stitched')
        for p in sorted(glob.glob(os.path.join(out_angle_slices, 'concat_*.png'))):
            dst = os.path.join(combined_for_pptx, f'concat_{slide_idx:03}.png')
            try:
                from shutil import copyfile
                copyfile(p, dst)
                slide_idx += 1
            except Exception:
                pass

    export_pptx_from_folder(combined_for_pptx, pptx_basename=pptx_name)


def _build_erode_and_slice_map(paths: List[str]) -> Dict[str, str]:
    """Map ``erosion depth:slice number`` to all-depth slice screenshots."""
    mapped: Dict[str, str] = {}
    for path in sorted(paths):
        basename = os.path.basename(path)
        slice_match = re.search(r"-(\d{3})-", basename)
        erode_match = re.search(r"(\d+)_eroded", basename)
        if not slice_match or not erode_match:
            continue
        key = (
            f"{str(erode_match.group(1)).zfill(3)}:"
            f"{str(slice_match.group(1)).zfill(3)}"
        )
        if key not in mapped:
            mapped[key] = path
    return mapped


def _sort_erode_and_slice_keys(keys: Set[str]) -> List[str]:
    """Sort composite ``erosion:slice`` keys numerically."""
    return sorted(
        keys,
        key=lambda key: tuple(int(part) for part in key.split(":", 1)),
    )


def _common_erode_and_slice_keys(
    slice_maps: List[Dict[str, str]],
) -> List[str]:
    """Return ordered all-depth slice keys shared across every slot."""
    if not slice_maps:
        return []
    common = set(slice_maps[0].keys())
    for slice_map in slice_maps[1:]:
        common &= set(slice_map.keys())
    return _sort_erode_and_slice_keys(common)


def _stitch_custom_slot_rows(
    n: int,
    slots: List[Dict],
    prepared_lists: List[List[str]],
    output_location: str,
) -> None:
    """Stitch normalized custom slots as one row or left-aligned two rows."""
    top_lists = [
        paths
        for slot, paths in zip(slots, prepared_lists)
        if slot.get("row", "top") == "top"
    ]
    bottom_lists = [
        paths
        for slot, paths in zip(slots, prepared_lists)
        if slot.get("row", "top") == "bottom"
    ]
    if not top_lists:
        raise ValueError("custom_overlay_panels requires at least one top-row slot.")
    if bottom_lists:
        concat_two_rows(
            n,
            top_lists=top_lists,
            bottom_lists=bottom_lists,
            output_location=output_location,
        )
    else:
        concat_one_row(n, top_lists, output_location)


def run_preset_custom_overlay_panels(
    raw_root: str,
    stitched_root: str,
    slots: List[Dict],
    angles: List[str],
    add_orientation_labels: bool = True,
    background_rgb: Optional[List[int]] = None,
    threshold: int = 2,
    pptx_name: str = "custom_overlay_panels",
) -> None:
    """Stitch custom overlay slots into one-row erosion and slice panels.

    For each angle, erosion panels are appended first, followed by all-depth
    slice panels. Only erosion/slice keys shared by every configured slot are
    stitched, ensuring columns always describe the same depth and clip position.
    """
    if background_rgb is None:
        background_rgb = [0, 0, 0]
    if not slots:
        raise ValueError("custom_overlay_panels requires at least one slot.")

    by_angle_root = os.path.join(stitched_root, "by_angle")
    combined_root = os.path.join(stitched_root, "_combined_for_pptx")
    _ensure_dir(by_angle_root)
    _ensure_dir(combined_root)

    slot_dirs = [
        os.path.join(
            raw_root,
            f"{int(slot['index']):02d}_{slot['base']}",
        )
        for slot in slots
    ]

    from shutil import copyfile

    slide_index = 0
    for angle in angles:
        angle_root = os.path.join(by_angle_root, angle)

        # Erosion snapshots: one screenshot per erosion depth and slot.
        erosion_dirs = [
            os.path.join(slot_dir, f"{angle}_erosion_overlay")
            for slot_dir in slot_dirs
        ]
        if all(os.path.isdir(path) for path in erosion_dirs):
            erosion_maps = [
                _build_prefix_map(_list_pngs(path))
                for path in erosion_dirs
            ]
            common_erosions = _common_prefixes_across_maps(erosion_maps)
            all_erosions: Set[str] = set()
            for erosion_map in erosion_maps:
                all_erosions.update(erosion_map.keys())
            _log_skipped_prefixes(
                f"custom_overlay_panels erosions ({angle})",
                all_erosions,
                common_erosions,
            )
            if common_erosions:
                annotated_lists = []
                for slot, erosion_map in zip(slots, erosion_maps):
                    prepared = _prepare_qmm_annotated_series(
                        erosion_map,
                        common_erosions,
                        os.path.join(
                            angle_root,
                            "erosions_annotated",
                            f"{int(slot['index']):02d}_{slot['base']}",
                        ),
                        angle,
                        slot.get("label", slot["base"]),
                        add_orientation_labels,
                        background_rgb,
                        threshold,
                    )
                    annotated_lists.append(
                        annotate_overlay_colorbars_on_series(
                            prepared,
                            slot.get("overlays"),
                        )
                    )
                erosion_output = os.path.join(
                    angle_root,
                    "erosions_stitched",
                )
                _stitch_custom_slot_rows(
                    len(common_erosions),
                    slots,
                    annotated_lists,
                    erosion_output,
                )
                for path in sorted(
                    glob.glob(os.path.join(erosion_output, "concat_*.png"))
                ):
                    copyfile(
                        path,
                        os.path.join(
                            combined_root,
                            f"concat_{slide_index:05d}.png",
                        ),
                    )
                    slide_index += 1
            else:
                print(
                    f"[WARNING] custom_overlay_panels: no shared erosion "
                    f"depths for angle '{angle}'."
                )
        else:
            print(
                f"[WARNING] custom_overlay_panels: missing erosion folder(s) "
                f"for angle '{angle}'."
            )

        # Slice sweeps: key by erosion depth and clip slice to avoid collisions.
        slice_dirs = [
            os.path.join(slot_dir, f"{angle}_slices_overlay")
            for slot_dir in slot_dirs
        ]
        if all(os.path.isdir(path) for path in slice_dirs):
            slice_maps = [
                _build_erode_and_slice_map(_list_pngs(path))
                for path in slice_dirs
            ]
            common_slices = _common_erode_and_slice_keys(slice_maps)
            all_slices: Set[str] = set()
            for slice_map in slice_maps:
                all_slices.update(slice_map.keys())
            skipped_slices = _sort_erode_and_slice_keys(
                all_slices - set(common_slices)
            )
            if skipped_slices:
                print(
                    f"[INFO] custom_overlay_panels slices ({angle}): skipped "
                    f"keys missing in one or more slots: "
                    f"{', '.join(skipped_slices)}"
                )
            if common_slices:
                annotated_lists = []
                for slot, slice_map in zip(slots, slice_maps):
                    prepared = _prepare_qmm_annotated_series(
                        slice_map,
                        common_slices,
                        os.path.join(
                            angle_root,
                            "slices_annotated",
                            f"{int(slot['index']):02d}_{slot['base']}",
                        ),
                        angle,
                        slot.get("label", slot["base"]),
                        add_orientation_labels,
                        background_rgb,
                        threshold,
                    )
                    annotated_lists.append(
                        annotate_overlay_colorbars_on_series(
                            prepared,
                            slot.get("overlays"),
                        )
                    )
                slice_output = os.path.join(angle_root, "slices_stitched")
                _stitch_custom_slot_rows(
                    len(common_slices),
                    slots,
                    annotated_lists,
                    slice_output,
                )
                for path in sorted(
                    glob.glob(os.path.join(slice_output, "concat_*.png"))
                ):
                    copyfile(
                        path,
                        os.path.join(
                            combined_root,
                            f"concat_{slide_index:05d}.png",
                        ),
                    )
                    slide_index += 1
            else:
                print(
                    f"[WARNING] custom_overlay_panels: no shared slice keys "
                    f"for angle '{angle}'."
                )
        else:
            print(
                f"[WARNING] custom_overlay_panels: missing slice folder(s) "
                f"for angle '{angle}'."
            )

    if slide_index == 0:
        raise ValueError(
            "custom_overlay_panels produced no stitched panels; check raw "
            "MRIcroGL output folders and shared erosion depths."
        )
    export_pptx_from_folder(combined_root, pptx_basename=pptx_name)