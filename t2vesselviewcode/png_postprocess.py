"""
PNG post-processing utilities for cropping, annotating, stitching, and PPTX export.

Provenance: This module ports the behavior of the legacy `screenshot_stitcher.py`
(used clinically) into package functions so the pipeline can call them directly.

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
from typing import List, Tuple

import pyvips
from PIL import Image as PILImage, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Inches

from . import dir_structure


def _ensure_dir(path: str) -> None:
    """Create directory if missing (no error if it already exists)."""
    os.makedirs(path, exist_ok=True)


def _extract_depth_from_basename(basename: str) -> str:
    """Extract leading zero-padded erosion depth from a filename.

    Example: '030_eroded_t1_something.png' -> '030'. Used to sort slides.
    Returns '000' if not found (safe default).
    """
    m = re.match(r"^(\d+)_", basename)
    return m.group(1) if m else "000"


def _list_pngs(directory: str) -> List[str]:
    """List all PNGs in a directory, sorted alphabetically."""
    return sorted(glob.glob(os.path.join(directory, '*.png')))


def get_crop_dimensions(images: List[str], background_colour: List[int], threshold: int = 2) -> Tuple[int, int, int, int]:
    """Compute a single crop box for an image series using least background across all.

    Uses pyvips.find_trim(threshold, background) like the legacy script:
    - Chooses the first image with non-zero brain width as the sample.
    - Measures left/top/width/height on the sample, converts to right/bottom margins.
    - Iterates all images, always keeping the most conservative crop (least margins).

    Returns: (left, top, width, height) suitable for pyvips.crop.
    """
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
    return left_crop, top_crop, width_crop, height_crop


def crop_image_series(images: List[str], output_directory: str, dimensions: Tuple[int, int, int, int]) -> List[str]:
    """Crop each image in a series to the provided dimensions; write to 0_cropped_series.

    Returns a sorted list of output file paths.
    """
    outpath = os.path.join(output_directory, '0_cropped_series')
    _ensure_dir(outpath)
    left, top, width, height = dimensions
    out_files = []
    for path in images:
        img = pyvips.Image.new_from_file(path)
        try:
            img = img.crop(left, top, width, height)  # fast region extraction
        except pyvips.error.Error:
            # Skip problematic file but keep processing others
            continue
        out_name = os.path.join(outpath, f"cropped_{os.path.basename(path)}")
        img.write_to_file(out_name)
        out_files.append(out_name)
    return sorted(out_files)


def _draw_text_with_outline(draw: ImageDraw.Draw, xy: Tuple[int, int], text: str, fill=(255, 255, 255), outline=(0, 0, 0), font=None):
    """Draw text with a simple 8-direction outline for legibility on any background."""
    x, y = xy
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]:
        draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


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
    try:
        font = ImageFont.truetype("Arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

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
    - left:      L on left only
    - right:     R on right only
    """
    img = PILImage.open(path_in).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_size = max(16, int(h * 0.05))
    try:
        font = ImageFont.truetype("Arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    margin = max(8, int(w * 0.02))
    left_pos = (margin, h // 2 - font_size // 2)
    right_pos = (w - margin - font_size // 2, h // 2 - font_size // 2)

    angle_lower = (angle or '').lower()
    if angle_lower in ('superior', 'posterior'):
        # Default: L left, R right
        _draw_text_with_outline(draw, left_pos, 'L', font=font)
        _draw_text_with_outline(draw, right_pos, 'R', font=font)
    elif angle_lower in ('inferior', 'anterior'):
        # Swap: R left, L right
        _draw_text_with_outline(draw, left_pos, 'R', font=font)
        _draw_text_with_outline(draw, right_pos, 'L', font=font)
    elif angle_lower == 'left':
        # Only L on left
        _draw_text_with_outline(draw, left_pos, 'L', font=font)
    elif angle_lower == 'right':
        # Only R on right
        _draw_text_with_outline(draw, right_pos, 'R', font=font)
    else:
        # Fallback: default L left, R right
        _draw_text_with_outline(draw, left_pos, 'L', font=font)
        _draw_text_with_outline(draw, right_pos, 'R', font=font)

    img.save(path_out)


def concat_one_row(n: int, top_lists: List[List[str]], output_location: str) -> None:
    """Concatenate n columns (2–4 images per row) into one wide row per depth."""
    _ensure_dir(output_location)
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


def concat_two_rows(n: int, top_lists: List[List[str]], bottom_lists: List[List[str]], output_location: str) -> None:
    """Concatenate two rows (top and bottom) into a panel per depth."""
    _ensure_dir(output_location)
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
    height_inside = Inches(38 - 0.6)

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


def run_preset_t1_overview_per_depth(add_orientation_labels: bool = True, background_rgb: List[int] = [0, 0, 0], threshold: int = 2, pptx_name: str = "T1_overview") -> None:
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
    angle_dirs = [os.path.join(dir_structure.renders_t1_dir, 'by_angle', a) for a in angles]

    # Ensure directories exist and have PNGs; enforce equal counts across angles
    dir_pngs = [_list_pngs(d) for d in angle_dirs]
    if not all(dir_pngs) or not all(len(p) == len(dir_pngs[0]) for p in dir_pngs):
        print("[WARNING] T1 overview preset skipped: angle folders missing or file counts unequal")
        return

    # Crop per angle folder and optionally annotate L/R, preserving order per depth
    cropped_lists = []
    for paths, adir in zip(dir_pngs, angle_dirs):
        dims = get_crop_dimensions(paths, background_rgb, threshold)
        cropped = crop_image_series(paths, adir, dims)
        if add_orientation_labels:
            annotated_dir = os.path.join(adir, '1_cropped_annotated')
            _ensure_dir(annotated_dir)
            ann_paths = []
            for p in cropped:
                out = os.path.join(annotated_dir, os.path.basename(p))
                annotate_by_angle_on_png(p, out, adir.split('/')[-1]) # Pass the angle folder name
                ann_paths.append(out)
            cropped_lists.append(sorted(ann_paths))
        else:
            cropped_lists.append(cropped)

    # Map angle -> list for two-row layout
    angle_to_list = {ang: lst for ang, lst in zip(angles, cropped_lists)}

    # Output directory for stitched panels
    out_panel_dir = os.path.join(dir_structure.renders_t1_dir, 'stitched_overview')
    _ensure_dir(out_panel_dir)

    # Build two-row layout if all required angles present; else fallback to one-row
    required_top = ['left', 'right']
    required_bottom = ['superior', 'inferior', 'anterior', 'posterior']
    have_all = all(a in angle_to_list for a in required_top + required_bottom)

    n = len(cropped_lists[0])

    if have_all:
        top_lists = [angle_to_list['left'], angle_to_list['right']]
        bottom_lists = [angle_to_list['superior'], angle_to_list['inferior'], angle_to_list['anterior'], angle_to_list['posterior']]
        concat_two_rows(n, top_lists, bottom_lists, out_panel_dir)
    else:
        # Safe fallback if any angle is missing: keep a single-row panel in the original order
        print("[WARNING] Missing one or more angles for two-row T1 overview; falling back to single-row stitching")
        concat_one_row(n, cropped_lists, out_panel_dir)

    # Export PPTX with one slide per stitched panel
    export_pptx_from_folder(out_panel_dir, pptx_name) 