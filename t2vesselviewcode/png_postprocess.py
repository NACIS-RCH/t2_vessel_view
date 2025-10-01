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

    return left_expanded, top_expanded, width_expanded, height_expanded


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


def annotate_modality_center_bottom(path_in: str, path_out: str, modality_text: str) -> None:
    """Annotate a PNG with a modality label centered at the bottom edge.

    - Uses a relative font size (~4.5% of height, min 14 px).
    - Centers text horizontally and places it just above the bottom margin.
    - Draws with an outline for visibility on dark/light backgrounds.
    """
    img = PILImage.open(path_in).convert('RGB')
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_size = max(14, int(h * 0.045))
    try:
        font = ImageFont.truetype("Arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Measure text to center precisely
    try:
        bbox = draw.textbbox((0, 0), modality_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = draw.textsize(modality_text, font=font)

    margin = max(8, int(h * 0.02))
    x = max(0, (w - text_w) // 2)
    y = max(0, h - margin - text_h)
    _draw_text_with_outline(draw, (x, y), modality_text, font=font)
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
    elif angle_lower == 'left':
        # Only L on left; place lower (bottom-biased)
        _draw_text_with_outline(draw, (left_x, y_bottom), 'L', font=font)
    elif angle_lower == 'right':
        # Only R on right; place lower (bottom-biased)
        _draw_text_with_outline(draw, (right_x, y_bottom), 'R', font=font)
    else:
        # Fallback: default L/R at mid-bottom as a safe choice
        _draw_text_with_outline(draw, (left_x, y_bottom), 'L', font=font)
        _draw_text_with_outline(draw, (right_x, y_bottom), 'R', font=font)

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
    height_inside = Inches(22 - 0.6)

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
            # Always add modality label for T1
            annotate_modality_center_bottom(out, out, 'T1')
            ann_paths.append(out)
        cropped_lists.append(sorted(ann_paths))

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

        # Enforce equal file counts across selected dirs
        counts = [len(pngs) for _, pngs in valid_dirs]
        if any(c != counts[0] for c in counts):
            print(f"[WARNING] Skipping angle '{angle}': unequal PNG counts across inputs")
            continue

        # Crop and annotate per directory
        cropped_lists = []
        for d, pngs in valid_dirs:
            dims = get_crop_dimensions(pngs, background_rgb, threshold)
            cropped = crop_image_series(pngs, d, dims)
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
        n = len(cropped_lists[0])
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

    # If nothing usable, return early
    if not resolved_dirs:
        print("[WARNING] T2 overview preset skipped: no T2 renders found")
        return

    # Gather PNG lists in the canonical angles order, skip missing
    angle_order = [a for a in angles if a in resolved_dirs]
    dir_pngs = [_list_pngs(resolved_dirs[a]) for a in angle_order]
    if not all(dir_pngs) or not all(len(p) == len(dir_pngs[0]) for p in dir_pngs):
        print("[WARNING] T2 overview preset: angle folders missing or file counts unequal; will fallback to single-row if needed")

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

    # Build two-row layout if we have all six required angles; else fallback to one-row
    angle_to_list = {ang: lst for ang, lst in zip(angle_order, cropped_lists)}
    required_top = ['left', 'right']
    required_bottom = ['superior', 'inferior', 'anterior', 'posterior']
    have_all = all(a in angle_to_list for a in required_top + required_bottom)
    n = len(cropped_lists[0]) if cropped_lists else 0

    if have_all:
        top_lists = [angle_to_list['left'], angle_to_list['right']]
        bottom_lists = [angle_to_list['superior'], angle_to_list['inferior'], angle_to_list['anterior'], angle_to_list['posterior']]
        concat_two_rows(n, top_lists, bottom_lists, out_panel_dir)
    else:
        print("[WARNING] Missing one or more angles for two-row T2 overview; falling back to single-row stitching")
        concat_one_row(n, cropped_lists, out_panel_dir)

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

        counts = [len(pngs) for _, pngs in valid_dirs]
        if any(c != counts[0] for c in counts):
            print(f"[WARNING] Skipping angle '{angle}': unequal PNG counts across inputs")
            continue

        cropped_lists = []
        for d, pngs in valid_dirs:
            dims = get_crop_dimensions(pngs, background_rgb, threshold)
            cropped = crop_image_series(pngs, d, dims)
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
        n = len(cropped_lists[0])
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