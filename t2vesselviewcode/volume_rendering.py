import pyvista as pv
import nibabel as nib
import numpy as np
import os
import tempfile
import shutil
import subprocess
import signal
import re
import glob

from . import dir_structure


def _file_signature(path):
    """Return a lightweight signature used to detect a new/updated output."""
    try:
        stat_result = os.stat(path)
        return (stat_result.st_size, stat_result.st_mtime_ns)
    except OSError:
        return None


def _stop_process_group(process, grace_s=5):
    """Stop only the launched render job, including its wrapper/child processes."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()

    try:
        return process.communicate(timeout=grace_s)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        return process.communicate()


def _run_mricrogl_command(
    cmd,
    timeout_s,
    output_dir,
    expected_outputs=None,
    render_description="MRIcroGL render",
):
    """Run one MRIcroGL batch and report timeout completeness accurately."""
    expected_outputs = list(expected_outputs or [])
    before = {path: _file_signature(path) for path in expected_outputs}
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name == "posix"),
    )

    try:
        stdout, stderr = process.communicate(timeout=int(timeout_s))
    except subprocess.TimeoutExpired:
        stdout, stderr = _stop_process_group(process)
        after = {path: _file_signature(path) for path in expected_outputs}
        completed = [
            path
            for path in expected_outputs
            if after[path] is not None and after[path] != before[path]
        ]

        if expected_outputs and len(completed) == len(expected_outputs):
            print(
                f"[WARNING] {render_description} timed out after "
                f"{int(timeout_s)}s during shutdown, but all "
                f"{len(expected_outputs)} expected screenshots were created."
            )
            return stdout, stderr

        if expected_outputs:
            missing = [path for path in expected_outputs if path not in completed]
            missing_preview = "\n".join(
                f"  - {os.path.relpath(path, output_dir)}"
                for path in missing[:10]
            )
            if len(missing) > 10:
                missing_preview += f"\n  - ... and {len(missing) - 10} more"
            completeness = (
                f"{len(completed)} of {len(expected_outputs)} expected "
                "screenshots were created or updated."
            )
            missing_text = f"\nMissing or unchanged outputs:\n{missing_preview}"
        else:
            completeness = "The requested output batch was not confirmed complete."
            missing_text = ""

        raise RuntimeError(
            f"{render_description} timed out after {int(timeout_s)}s. "
            f"{completeness} Partial outputs remain in: {output_dir}"
            f"{missing_text}"
        )

    if process.returncode != 0:
        raise RuntimeError(
            f"MRIcroGL failed (code {process.returncode}). "
            f"stderr: {stderr}\nstdout: {stdout}"
        )
    return stdout, stderr


def resolve_mricrogl_executable(user_path=None):
    """Resolve MRIcroGL executable path across macOS/Linux with clear fallback order."""
    candidates = []

    if user_path:
        candidates.append(user_path)

    env_path = os.environ.get("T2VV_MRICROGL_PATH", "").strip()
    if env_path:
        candidates.append(env_path)

    for name in ("MRIcroGL", "mricrogl", "MRIcroGL_QT"):
        which_path = shutil.which(name)
        if which_path:
            candidates.append(which_path)

    # Known common install paths on macOS and Linux
    candidates.extend([
        "/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",  # macOS app bundle
        "/usr/local/bin/MRIcroGL",
        "/usr/bin/MRIcroGL",
        "/opt/MRIcroGL/MRIcroGL",
    ])

    # Keep order but deduplicate
    seen = set()
    ordered = []
    for c in candidates:
        if c and c not in seen:
            ordered.append(c)
            seen.add(c)

    for c in ordered:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    raise FileNotFoundError(
        "Could not locate MRIcroGL executable. "
        "Set T2VV_MRICROGL_PATH or install MRIcroGL on PATH. "
        f"Tried: {ordered}"
    )


def resolve_mricrogl_template_path(template_filename):
    """Resolve MRIcroGL template path in package or legacy repo locations."""
    custom_templates_dir = os.environ.get("T2VV_MRICROGL_TEMPLATE_DIR", "").strip()
    package_templates_dir = os.path.join(os.path.dirname(__file__), "display_scripts", "templates")
    legacy_templates_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "display_scripts", "templates")
    )

    candidate_dirs = [custom_templates_dir, package_templates_dir, legacy_templates_dir]
    tried = []
    for d in candidate_dirs:
        if not d:
            continue
        p = os.path.join(d, template_filename)
        tried.append(p)
        if os.path.exists(p):
            return p

    raise FileNotFoundError(
        "MRIcroGL template not found. "
        f"Template name: {template_filename}. Tried: {tried}"
    )


def _ensure_ras(img):
    ax = nib.aff2axcodes(img.affine)
    if ax != ('R', 'A', 'S'):
        img = nib.as_closest_canonical(img)
        ax2 = nib.aff2axcodes(img.affine)
        if ax2 != ('R', 'A', 'S'):
            raise ValueError(f"Non-RAS after canonicalization: pre={ax}, post={ax2}")
    return img

def _set_mricrogl_label_orient_off():
    """Attempt to set LabelOrient=0 in MRIcroGL.ini on macOS to hide orientation labels/cube.

    This edits '~/Library/Application Support/MRIcroGL/MRIcroGL.ini' if it exists,
    creating a backup alongside it as '.bak'. Safe no-op if path not found.
    """
    ini_path = os.path.expanduser('~/Library/Application Support/MRIcroGL/MRIcroGL.ini')
    try:
        if not os.path.exists(ini_path):
            return
        # Backup
        try:
            shutil.copyfile(ini_path, ini_path + '.bak')
        except Exception:
            pass
        with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('LabelOrient='):
                new_lines.append('LabelOrient=0\n')
                found = True
            else:
                new_lines.append(line)
        if not found:
            # Append setting at end
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines[-1] = new_lines[-1] + '\n'
            new_lines.append('LabelOrient=0\n')
        with open(ini_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    except Exception:
        # Silent failure; prefer not to block rendering
        pass

def _configure_mricrogl_ini_preferences():
    """Update MRIcroGL.ini for reproducible screenshots on macOS.

    - Disable orientation cube/labels: LabelOrient=0
    - Disable Retina upscaling: RetinaDisplay=0
    - Ensure no bitmap tiling upscaling: BitmapZoom=1
    - Clear previous file references: PrevFilename1..10= and PrevBackgroundImage=

    Safe no-op if the INI file is not found. Creates a .bak backup when possible.
    """
    ini_path = os.path.expanduser('~/Library/Application Support/MRIcroGL/MRIcroGL.ini')
    try:
        if not os.path.exists(ini_path):
            return
        # Backup existing INI
        try:
            shutil.copyfile(ini_path, ini_path + '.bak')
        except Exception:
            pass

        with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        keys_to_set = {
            'LabelOrient': '0',
            'RetinaDisplay': '0',
            'BitmapZoom': '1',
            'PrevBackgroundImage': ''
        }
        # Add PrevFilename1..10
        for i in range(1, 11):
            keys_to_set[f'PrevFilename{i}'] = ''

        found_keys = {k: False for k in keys_to_set}
        new_lines = []
        for line in lines:
            stripped = line.strip()
            replaced = False
            for k, v in keys_to_set.items():
                if stripped.startswith(f'{k}='):
                    new_lines.append(f'{k}={v}\n')
                    found_keys[k] = True
                    replaced = True
                    break
            if not replaced:
                new_lines.append(line)

        # Append any missing keys
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] = new_lines[-1] + '\n'
        for k, v in keys_to_set.items():
            if not found_keys[k]:
                new_lines.append(f'{k}={v}\n')

        with open(ini_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    except Exception:
        # Non-fatal; continue without blocking rendering
        pass

# Tuned camera distance (persists across calls within this run only)
_TUNED_CAMERA_DISTANCE = None
# Detected empty hemisphere for T2 sagittal per series tag
# Dict[tag -> 'left' | 'right' | None]
_T2_SAG_EMPTY_SIDE_BY_TAG = {}

def _select_least_eroded_file(nifti_paths):
    """Pick the least-eroded file: the one whose basename starts with the smallest number.

    Falls back to the first path if no numeric prefix is found.
    """
    def key_fn(p):
        b = os.path.basename(p)
        m = re.match(r"^(\d+)_", b)
        return int(m.group(1)) if m else 9999999
    try:
        return sorted(nifti_paths, key=key_fn)[0]
    except Exception:
        return nifti_paths[0]

def _collect_trial_pngs(root):
    """Collect all PNGs in by_angle subfolders from a trial render root."""
    return sorted(glob.glob(os.path.join(root, 'by_angle', '*', '*.png')))

def _measure_edges_with_vips(png_path, threshold=2, background=[0, 0, 0]):
    """Return edge margins in pixels and fractions using pyvips.find_trim.

    Returns: (left_px, right_px, top_px, bottom_px, left_frac, right_frac, top_frac, bottom_frac)
    """
    import pyvips
    img = pyvips.Image.new_from_file(png_path)
    left, top, bw, bh = img.find_trim(threshold=threshold, background=background)
    right = img.width - left - bw
    bottom = img.height - top - bh
    lw = img.width if img.width else 1
    lh = img.height if img.height else 1
    return (
        left, right, top, bottom,
        left / lw, right / lw, top / lh, bottom / lh
    )

def _evaluate_camera_distance_once(nifti_path, angles, image_size, mricrogl_path, template_filename, camera_distance):
    """Render a trial at the given camera distance and evaluate conditions.

    Returns: (too_close, too_far)
    - too_close: any edge == 0 px for any angle image
    - too_far: every edge on every image has > 20% background fraction
    """
    # Use a temp output dir so we don't pollute real outputs
    trial_dir = tempfile.mkdtemp(prefix='t2vv_cam_trial_')
    try:
        # Compute a window from the single image for reasonable contrast
        window = compute_series_window([nifti_path])
        # Reuse main renderer to produce PNGs for all angles
        render_volume_and_save_pngs_mricrogl(
            [nifti_path], trial_dir, angles=angles, window=window,
            image_size=image_size, mricrogl_path=mricrogl_path,
            template_filename=template_filename, camera_distance=camera_distance
        )
        pngs = _collect_trial_pngs(trial_dir)
        if not pngs:
            # If nothing rendered, treat as too_close to nudge outward safely
            return True, False

        # Evaluate margins across all PNGs a;erofijse;rogtijbsrh
        any_zero_edge = False
        all_edges_gt_20 = True
        for p in pngs:
            l, r, t, b, lf, rf, tf, bf = _measure_edges_with_vips(p)
            if l == 0 or r == 0 or t == 0 or b == 0:
                any_zero_edge = True
            if not (lf > 0.20 and rf > 0.20 and tf > 0.20 and bf > 0.20):
                all_edges_gt_20 = False
        return any_zero_edge, all_edges_gt_20
    finally:
        try:
            shutil.rmtree(trial_dir)
        except Exception:
            pass

def _maybe_mask_empty_hemisphere_for_t2_sag(img):
    """Deprecated heuristic (kept for fallback). Prefer _apply_detected_t2_sag_half_mask."""
    return None

def _detect_t2_sag_empty_side_for_tag(tag: str):
    """Detect empty hemisphere for a given sagittal T2 series tag ('t2_sag', 't2_sag_left', 't2_sag_right').

    Returns 'left', 'right', or None. Caches per tag in _T2_SAG_EMPTY_SIDE_BY_TAG.
    Criteria: count non-zero voxels per hemisphere in RAS; if one side <10% of the other → empty.
    """
    if tag in _T2_SAG_EMPTY_SIDE_BY_TAG:
        return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]

    base = dir_structure.processed_t2_sag_dir
    # Prefer exact registered filename for the tag
    candidates = [
        os.path.join(base, f'registered_{tag}.nii.gz'),
        os.path.join(base, f'registered_{tag}.nii'),
    ]
    # Fallback globs containing the tag
    candidates += sorted(glob.glob(os.path.join(base, f'registered_*{tag}*.nii*')))
    candidates += sorted(glob.glob(os.path.join(base, f'*{tag}*.nii*')))

    reg_path = next((c for c in candidates if os.path.isfile(c)), None)
    if reg_path is None:
        _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = None
        return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]

    try:
        img = nib.load(reg_path)
        img = _ensure_ras(img)
        data = img.get_fdata(dtype=np.float32)
        if data.ndim != 3:
            _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = None
            return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]
        x = data.shape[0]
        mid = x // 2
        left = data[:mid, :, :]
        right = data[mid:, :, :]
        left_nz = int(np.count_nonzero(left > 0.0))
        right_nz = int(np.count_nonzero(right > 0.0))
        if left_nz == 0 and right_nz == 0:
            _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = None
            return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]
        if left_nz < 0.1 * max(right_nz, 1):
            _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = 'left'
        elif right_nz < 0.1 * max(left_nz, 1):
            _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = 'right'
        else:
            _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = None
        return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]
    except Exception:
        _T2_SAG_EMPTY_SIDE_BY_TAG[tag] = None
        return _T2_SAG_EMPTY_SIDE_BY_TAG[tag]

def _apply_detected_t2_sag_half_mask(img: nib.Nifti1Image, tag: str) -> nib.Nifti1Image:
    """Apply the detected empty-side half mask (if any) for a given tag and return a new image."""
    side = _detect_t2_sag_empty_side_for_tag(tag)
    if side is None:
        return img
    ras_img = _ensure_ras(img)
    data = ras_img.get_fdata(dtype=np.float32)
    if data.ndim != 3:
        return img
    x = data.shape[0]
    mid = x // 2
    masked = data.copy()
    if side == 'left':
        masked[:mid, :, :] = 0.0
    elif side == 'right':
        masked[mid:, :, :] = 0.0
    return nib.Nifti1Image(masked, ras_img.affine, header=ras_img.header)

def tune_camera_distance(nifti_paths, angles, image_size, mricrogl_path, template_filename, start=0.6, dmin=0.2, dmax=1.8):
    """Find a suitable camera distance using bracketing + binary search.

    Criteria:
    - too_close(d): any image has any edge with 0 background pixels
    - too_far(d): all images have all four edges > 20% background fraction

    Returns the smallest acceptable distance that avoids cropping (prefers larger brain).
    Caches the result for the module lifetime.
    """
    global _TUNED_CAMERA_DISTANCE
    if _TUNED_CAMERA_DISTANCE is not None:
        return _TUNED_CAMERA_DISTANCE

    if not nifti_paths:
        _TUNED_CAMERA_DISTANCE = start
        return _TUNED_CAMERA_DISTANCE

    test_img = _select_least_eroded_file(nifti_paths)

    # Evaluate at start
    s = max(dmin, min(dmax, float(start)))
    tc, tf = _evaluate_camera_distance_once(test_img, angles, image_size, mricrogl_path, template_filename, s)
    if not tc and not tf:
        _TUNED_CAMERA_DISTANCE = s
        return _TUNED_CAMERA_DISTANCE

    lo = None  # last too_close distance
    hi = None  # first not too_close (or compact) distance

    d = s
    if tc:
        # Grow multiplicatively until not too_close or reach max
        while True:
            lo = d
            nd = min(dmax, d * 1.5)
            if nd == d:
                break
            d = nd
            tc2, tf2 = _evaluate_camera_distance_once(test_img, angles, image_size, mricrogl_path, template_filename, d)
            if not tc2:
                hi = d
                tf = tf2
                break
        if hi is None:
            # Even at max still too close; accept max to avoid crop as much as possible
            _TUNED_CAMERA_DISTANCE = dmax
            return _TUNED_CAMERA_DISTANCE
    else:
        # too_far at start: shrink until not too_far
        while True:
            nd = max(dmin, d / 1.5)
            if nd == d:
                break
            d = nd
            tc2, tf2 = _evaluate_camera_distance_once(test_img, angles, image_size, mricrogl_path, template_filename, d)
            if not tf2:
                hi = d
                tc = tc2
                break
            # Optionally record lo if we hit too_close while shrinking
            if tc2:
                lo = d
                break
        if hi is None:
            # Could not find a non-too-far spot; keep start
            _TUNED_CAMERA_DISTANCE = s
            return _TUNED_CAMERA_DISTANCE

    # If we have lo (too_close) and hi (not too_close), run binary to ~0.1 precision
    if lo is not None and hi is not None:
        best = None
        while (hi - lo) > 0.1:
            mid = (lo + hi) / 2.0
            tc_m, tf_m = _evaluate_camera_distance_once(test_img, angles, image_size, mricrogl_path, template_filename, mid)
            if tc_m:
                lo = mid
            elif tf_m:
                hi = mid
            else:
                best = mid
                # Bias toward closest acceptable distance
                hi = mid
        _TUNED_CAMERA_DISTANCE = (best if best is not None else hi)
        return _TUNED_CAMERA_DISTANCE

    # Fallbacks when only one side was found
    if hi is not None:
        _TUNED_CAMERA_DISTANCE = hi
        return _TUNED_CAMERA_DISTANCE
    _TUNED_CAMERA_DISTANCE = s
    return _TUNED_CAMERA_DISTANCE

def compute_series_window(
    nifti_paths,
    low_pct: float = 10.0,
    high_pct: float = 90.0,
    ignore_zeros: bool = True,
    max_samples: int = 2000000
):
    """Compute a robust intensity window from a list of NIfTI files.

    Strategy (fast and stable for MVP):
    - Use up to the first 3 volumes in the series.
    - For each, sample up to `max_samples` voxels to compute per-image percentiles.
    - Optionally ignore zeros (masked background) for percentiles.
    - Return the median of the per-image low/high percentiles (10th/90th by default), cast to int.

    Falls back to (0, 1000) if any error occurs.
    """
    try:
        # If nothing to analyze, fall back to a sensible default window
        if not nifti_paths:
            return (0, 1000)
        per_lows = []  # collect per-image lower percentile
        per_highs = []  # collect per-image upper percentile
        # Analyze at most the first three images for speed and stability
        for p in nifti_paths[:3]:
            img = nib.load(p)  # load image header + data
            data = img.get_fdata(dtype=np.float32)  # get data as float32 for uniformity
            flat = data.ravel()  # flatten to 1D for simple percentile computation
            if ignore_zeros:
                flat = flat[flat != 0]  # drop masked background voxels
            if flat.size == 0:
                continue  # skip images with no foreground
            if flat.size > max_samples:
                # Subsample without replacement to bound time/memory for huge volumes
                idx = np.random.choice(flat.size, size=max_samples, replace=False)
                flat = flat[idx]
            # Compute requested low/high percentiles for this image
            per_lows.append(np.percentile(flat, low_pct))
            per_highs.append(np.percentile(flat, high_pct))
        # If nothing usable was gathered, return default
        if not per_lows or not per_highs:
            return (0, 1000)
        # Aggregate by median to reduce sensitivity to outliers across images
        low = float(np.median(per_lows))
        high = float(np.median(per_highs))
        # Validate numbers are sane and ordered
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            return (0, 1000)
        # Pad window by 5% of span to avoid clipping subtle structures
        span = high - low
        low_adj = max(0.0, low - 0.05 * span)  # avoid negative lower bound
        high_adj = high + 0.05 * span
        # Return integer bounds expected by MRIcroGL scripting
        return (int(low_adj), int(high_adj))
    except Exception:
        # On any error, fall back to default window to keep pipeline moving
        return (0, 1000)


def _make_disk_structure(radius_px):
    """Return a 2D boolean disk structuring element for morphology checks."""
    r = int(max(1, radius_px))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= (r * r)


def _render_slice_to_uint8(slice_2d, vmin, vmax):
    """Render a 2D slice with linear clip->rescale to uint8 [0, 255]."""
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return np.zeros(slice_2d.shape, dtype=np.uint8)
    clipped = np.clip(slice_2d, vmin, vmax)
    scaled = (clipped - vmin) / (vmax - vmin)
    return np.clip(np.round(scaled * 255.0), 0, 255).astype(np.uint8)


def _representative_slice_views(data, spacing, n_slices=5):
    """Yield representative 2D views: mostly axial plus central coronal/sagittal."""
    sx, sy, sz = spacing
    nx, ny, nz = data.shape
    views = []

    # Axial slices: spread through middle 60% of z-range.
    axial_count = max(1, min(int(n_slices), 3))
    if nz <= 1:
        axial_indices = [0]
    else:
        z0 = max(0, int(round(0.2 * (nz - 1))))
        z1 = max(z0, int(round(0.8 * (nz - 1))))
        if axial_count == 1:
            axial_indices = [int(round(0.5 * (nz - 1)))]
        else:
            axial_indices = np.linspace(z0, z1, axial_count).astype(int).tolist()
    for z in axial_indices:
        views.append((data[:, :, int(z)], float(sx), float(sy)))

    # Add one central coronal and one central sagittal when requested.
    if n_slices >= 4:
        y = ny // 2
        views.append((data[:, int(y), :], float(sx), float(sz)))
    if n_slices >= 5:
        x = nx // 2
        views.append((data[int(x), :, :], float(sy), float(sz)))

    return views[:max(1, int(n_slices))]


def _count_valid_circle_locations(bright_mask, radius_px):
    """Count centers where a full disk of radius_px fits inside bright_mask."""
    try:
        from scipy.ndimage import binary_erosion
    except Exception:
        # Safe fallback: if scipy morphology is unavailable, disable this check.
        return 0
    if bright_mask.size == 0 or not np.any(bright_mask):
        return 0
    structure = _make_disk_structure(radius_px)
    fitted = binary_erosion(bright_mask.astype(bool), structure=structure, border_value=0)
    return int(np.count_nonzero(fitted))


def refine_window_vmax_by_saturation_circles(
    nifti_paths,
    initial_window,
    radius_mm=1.5,
    bright_threshold=250,
    max_valid_circle_locations=4,
    representative_slices=5,
    max_images_to_check=3,
    vmax_growth_factor=1.10,
    max_iterations=8,
):
    """Increase vmax until broad saturated regions are limited by a disk-fit test.

    Heuristic:
    - Render representative 2D slices with linear clip->rescale to uint8.
    - Threshold near-white pixels (>= bright_threshold).
    - Convert radius_mm to pixels using in-plane spacing.
    - Count where a full disk can fit inside bright regions.
    - If any slice has more than max_valid_circle_locations, increase vmax and retry.
    """
    try:
        if not nifti_paths:
            return initial_window

        vmin = float(initial_window[0])
        vmax = float(initial_window[1])
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            return (0, 1000)

        files_to_check = sorted(nifti_paths, key=os.path.basename)[:max(1, int(max_images_to_check))]

        for iteration in range(max(1, int(max_iterations)) + 1):
            failed = False
            worst_count = 0

            for p in files_to_check:
                img = _ensure_ras(nib.load(p))
                data = img.get_fdata(dtype=np.float32)
                if data.ndim != 3:
                    continue
                spacing = img.header.get_zooms()[:3]
                if len(spacing) < 3:
                    spacing = (1.0, 1.0, 1.0)

                for sl, sp_a, sp_b in _representative_slice_views(
                    data,
                    spacing,
                    n_slices=representative_slices
                ):
                    rendered = _render_slice_to_uint8(sl, vmin, vmax)
                    bright_mask = rendered >= int(bright_threshold)
                    inplane_mm = max(1e-6, 0.5 * (float(sp_a) + float(sp_b)))
                    radius_px = int(np.ceil(float(radius_mm) / inplane_mm))
                    valid_locations = _count_valid_circle_locations(bright_mask, radius_px)
                    worst_count = max(worst_count, valid_locations)
                    if valid_locations > int(max_valid_circle_locations):
                        failed = True
                        break
                if failed:
                    break

            if not failed:
                print(
                    f"[INFO] Saturation circle check passed at iter={iteration}: "
                    f"window=({int(vmin)}, {int(vmax)}), max_valid_circle_locations={worst_count}"
                )
                return (int(vmin), int(vmax))

            span = max(1.0, vmax - vmin)
            vmax = vmin + span * float(vmax_growth_factor)
            print(
                f"[INFO] Saturation circle check failed at iter={iteration}: "
                f"increasing vmax to {int(vmax)}"
            )

        print(
            "[WARNING] Saturation circle refinement hit iteration limit; "
            f"using last window=({int(vmin)}, {int(vmax)})."
        )
        return (int(vmin), int(vmax))
    except Exception as e:
        print(f"[WARNING] Saturation circle refinement skipped due to error: {e}")
        return initial_window

def render_volume_and_save_pngs_mricrogl(
    nifti_paths,
    output_dir,
    angles=None,
    window=(0, 1000),
    image_size=(1200, 1200),
    mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
    template_filename="mricrogl_T1_renders.py",
    camera_distance=0.6,
    overlays=None
):
    """
    Render volumes using MRIcroGL by generating a temporary gl script from a template.

    This does not modify stored outputs. It creates temporary uncompressed .nii copies
    for MRIcroGL to read reliably, runs MRIcroGL with the generated script, saves PNGs
    to output_dir, and cleans up temps.

    Parameters
    ----------
    nifti_paths : list[str]
        Absolute paths to input NIfTI files to render.
    output_dir : str
        Absolute output directory for PNG screenshots.
    angles : list[[azimuth, elevation, label]]
        Camera angles; defaults to six standard views if None.
    window : (float, float)
        Intensity window (min, max).
    image_size : (int, int)
        PNG size in pixels (width, height).
    mricrogl_path : str
        Path to the MRIcroGL executable.
    template_filename : str
        Template script filename located under display_scripts/templates/ within the package.
    camera_distance : float
        Camera distance to use (>0 applies; smaller is closer). Set <=0 to skip.
    overlays : list[dict] | None
        Optional list of overlay specifications loaded directly by MRIcroGL.
        Each item can include: path, color, min, max, opacity.
    """
    if angles is None:
        angles = [
            [90, 0, 'left'],
            [270, 0, 'right'],
            [180, 0, 'anterior'],
            [0, 0, 'posterior'],
            [0, 90, 'superior'],
            [180, -90, 'inferior'],
        ]

    # Enforce deterministic render order (least eroded first).
    # Erosion files are zero-padded (e.g., 005_, 010_), so alphabetical works.
    try:
        nifti_paths = sorted(nifti_paths, key=os.path.basename)
    except Exception:
        pass

    os.makedirs(output_dir, exist_ok=True)

    # Resolve template path from package/legacy/custom locations
    template_path = resolve_mricrogl_template_path(template_filename)

    # Resolve executable robustly if caller provided default or empty path
    mricrogl_path = resolve_mricrogl_executable(mricrogl_path)

    # Auto-tune camera distance if requested
    if isinstance(camera_distance, str) and camera_distance.strip().lower() == 'auto':
        camera_distance = tune_camera_distance(
            nifti_paths=nifti_paths,
            angles=angles,
            image_size=image_size,
            mricrogl_path=mricrogl_path,
            template_filename=template_filename,
            start=0.6,
            dmin=0.2,
            dmax=1.8
        )

    # Create a temp workspace
    tmp_root = tempfile.mkdtemp(prefix='t2vv_mricrogl_')
    tmp_imgs = []
    try:
        # Create temporary uncompressed .nii copies for MRIcroGL
        for p in nifti_paths:
            if not os.path.isabs(p):
                raise ValueError(f"Input path must be absolute for MRIcroGL: {p}")
            img = nib.load(p)
            # Try masking empty hemisphere for sagittal T2 series (per series tag)
            base_name = os.path.basename(p).lower()
            if 't2_sag' in base_name:
                tag = 't2_sag_left' if 't2_sag_left' in base_name else (
                      't2_sag_right' if 't2_sag_right' in base_name else 't2_sag')
                img = _apply_detected_t2_sag_half_mask(img, tag)
            # Keep dtype as float32 to preserve intensity scaling; MRIcroGL handles .nii float32 fine
            data = _ensure_ras(img).get_fdata(dtype=np.float32)
            tmp_p = os.path.join(tmp_root, os.path.splitext(os.path.basename(p))[0] + '.nii')
            nib.Nifti1Image(data, img.affine, header=img.header).to_filename(tmp_p)
            tmp_imgs.append(tmp_p)

        # Fill the template placeholders
        with open(template_path, 'r') as f:
            tpl = f.read()

        # Build literal strings for placeholders
        # Ensure paths are properly quoted for MRIcroGL's interpreter
        img_list_literal = '[' + ', '.join([repr(s) for s in tmp_imgs]) + ']'
        angles_literal = '[' + ', '.join([f"[{a[0]}, {a[1]}, '{a[2]}']" for a in angles]) + ']'
        window_literal = f"[{int(window[0])}, {int(window[1])}]"
        view_literal = f"[{int(image_size[0])}, {int(image_size[1])}]"
        camera_literal = f"{float(camera_distance)}" if camera_distance and camera_distance > 0 else "-1"
        overlays_literal = repr(overlays if overlays is not None else [])

        script_text = tpl
        script_text = script_text.replace('__IMAGELIST__', img_list_literal)
        script_text = script_text.replace('__OUTPUT_DIR__', output_dir)
        script_text = script_text.replace('__ANGLES__', angles_literal)
        script_text = script_text.replace('__WINDOW__', window_literal)
        script_text = script_text.replace('__VIEW_SIZE__', view_literal)
        script_text = script_text.replace('__CAMERA_DISTANCE__', camera_literal)
        script_text = script_text.replace('__OVERLAYS__', overlays_literal)

        # Write temp script
        tmp_script = os.path.join(tmp_root, 'mricrogl_run.py')
        with open(tmp_script, 'w') as f:
            f.write(script_text)

        # Run MRIcroGL (ensure INI prefs are set for deterministic screenshots)
        _configure_mricrogl_ini_preferences()
        cmd = [mricrogl_path, '-s', tmp_script]
        expected_outputs = []
        for tmp_img in tmp_imgs:
            base = os.path.splitext(os.path.basename(tmp_img))[0]
            for azimuth, elevation, label in angles:
                expected_outputs.append(
                    os.path.join(
                        output_dir,
                        'by_angle',
                        str(label),
                        f"{label}-{azimuth}-{elevation}-{base}.png",
                    )
                )
        _run_mricrogl_command(
            cmd,
            timeout_s=120,
            output_dir=output_dir,
            expected_outputs=expected_outputs,
            render_description="MRIcroGL volume render",
        )

        print(f"[INFO] MRIcroGL renders saved under: {output_dir}")
    finally:
        # Cleanup temp files
        try:
            shutil.rmtree(tmp_root)
        except Exception:
            pass


def _normalize_slice_angle_rows(angles=None):
    """Return validated camera/clip rows, preserving legacy QMM defaults."""
    if angles is None:
        return [
            ["left", 90, 0, 270, 0],
            ["right", 270, 0, 90, 0],
            ["anterior", 180, 0, 180, 0],
            ["posterior", 0, -10, 0, -10],
            ["superior", 0, 90, 0, 90],
            ["inferior", 180, -90, 0, -90],
        ]
    rows = [list(row) for row in angles]
    if any(len(row) != 5 for row in rows):
        raise ValueError(
            "Each slice angle must contain "
            "[label, brain_az, brain_el, clip_az, clip_el]."
        )
    return rows


def render_quant_map_mm_panel_slices_mricrogl(
    nifti_paths,
    output_dir,
    overlays,
    window=(0, 1000),
    main_erode_prefix="030",
    mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
    template_filename="mricrogl_quant_map_mm_panel_slices.py",
    camera_distance=0.7,
    slice_z_start=5,
    slice_z_end=95,
    slice_h_divisor=100.0,
    sagittal_slice_end_fraction=0.52,
    angles=None,
    slice_all_depths=False,
    save_structural_outputs=True,
    save_overlay_outputs=True,
    timeout_s=600,
):
    """Render raw slice and erosion screenshots for QMM/custom workflows.

    The defaults preserve quant_map_mm_panel behavior: six cardinal views and
    slice sweeps only for ``main_erode_prefix``. Custom panels can supply
    camera/clip rows and select which structural/composite output families
    are written.
    """
    if not bool(save_structural_outputs) and not bool(save_overlay_outputs):
        raise ValueError(
            "At least one of save_structural_outputs or "
            "save_overlay_outputs must be True."
        )
    if not nifti_paths:
        return

    try:
        nifti_paths = sorted(nifti_paths, key=os.path.basename)
    except Exception:
        pass

    os.makedirs(output_dir, exist_ok=True)
    template_path = resolve_mricrogl_template_path(template_filename)
    mricrogl_path = resolve_mricrogl_executable(mricrogl_path)

    # [label, brain_az, brain_el, clip_az, clip_el]
    slice_angles = _normalize_slice_angle_rows(angles)

    tmp_root = tempfile.mkdtemp(prefix='t2vv_mricrogl_qmm_')
    tmp_imgs = []
    try:
        for p in nifti_paths:
            if not os.path.isabs(p):
                raise ValueError(f"Input path must be absolute for MRIcroGL: {p}")
            img = nib.load(p)
            data = _ensure_ras(img).get_fdata(dtype=np.float32)
            tmp_p = os.path.join(tmp_root, os.path.splitext(os.path.basename(p))[0] + '.nii')
            nib.Nifti1Image(data, img.affine, header=img.header).to_filename(tmp_p)
            tmp_imgs.append(tmp_p)

        with open(template_path, 'r') as f:
            tpl = f.read()

        img_list_literal = '[' + ', '.join([repr(s) for s in tmp_imgs]) + ']'
        window_literal = f"[{int(window[0])}, {int(window[1])}]"
        camera_literal = f"{float(camera_distance)}" if camera_distance and camera_distance > 0 else "-1"
        overlays_literal = repr(overlays if overlays is not None else [])
        slice_angles_literal = '[' + ', '.join(
            [f"['{a[0]}', {int(a[1])}, {int(a[2])}, {int(a[3])}, {int(a[4])}]" for a in slice_angles]
        ) + ']'

        script_text = tpl
        script_text = script_text.replace('__IMAGELIST__', img_list_literal)
        script_text = script_text.replace('__OUTPUT_DIR__', output_dir)
        script_text = script_text.replace('__WINDOW__', window_literal)
        script_text = script_text.replace('__CAMERA_DISTANCE__', camera_literal)
        script_text = script_text.replace('__OVERLAYS__', overlays_literal)
        script_text = script_text.replace('__MAIN_ERODE_PREFIX__', str(main_erode_prefix))
        script_text = script_text.replace('__SLICE_Z_START__', str(int(slice_z_start)))
        script_text = script_text.replace('__SLICE_Z_END__', str(int(slice_z_end)))
        script_text = script_text.replace('__SLICE_H_DIVISOR__', str(float(slice_h_divisor)))
        script_text = script_text.replace('__SAGITTAL_SLICE_END_FRACTION__', str(float(sagittal_slice_end_fraction)))
        script_text = script_text.replace('__SLICE_ALL_DEPTHS__', repr(bool(slice_all_depths)))
        script_text = script_text.replace(
            '__SAVE_STRUCTURAL_OUTPUTS__',
            repr(bool(save_structural_outputs)),
        )
        script_text = script_text.replace(
            '__SAVE_OVERLAY_OUTPUTS__',
            repr(bool(save_overlay_outputs)),
        )
        script_text = script_text.replace('__SLICE_ANGLES__', slice_angles_literal)

        tmp_script = os.path.join(tmp_root, 'mricrogl_qmm_slices.py')
        with open(tmp_script, 'w') as f:
            f.write(script_text)

        _configure_mricrogl_ini_preferences()
        cmd = [mricrogl_path, '-s', tmp_script]
        expected_outputs = []
        sagittal_labels = {
            "left",
            "right",
            "surg_left_lat",
            "surg_right_lat",
            "surg_left_ato",
            "surg_right_ato",
        }
        enabled_families = []
        if bool(save_structural_outputs):
            enabled_families.append("structural")
        if bool(save_overlay_outputs):
            enabled_families.append("overlay")

        for tmp_img in tmp_imgs:
            base = os.path.splitext(os.path.basename(tmp_img))[0]
            for label, _brain_az, _brain_el, _clip_az, _clip_el in slice_angles:
                for family in enabled_families:
                    expected_outputs.append(
                        os.path.join(
                            output_dir,
                            f"{label}_erosion_{family}",
                            f"{label}_erosion_{family}_{base}.png",
                        )
                    )

            should_save_slices = bool(slice_all_depths) or (
                bool(main_erode_prefix)
                and (str(main_erode_prefix) + "_eroded") in base
            )
            if should_save_slices:
                for label, _brain_az, _brain_el, _clip_az, _clip_el in slice_angles:
                    slice_end = int(slice_z_end)
                    if str(label).lower() in sagittal_labels:
                        slice_end = int(
                            round(
                                float(sagittal_slice_end_fraction)
                                * float(slice_h_divisor)
                            )
                        )
                    for z_value in range(int(slice_z_start), slice_end + 1):
                        for family in enabled_families:
                            expected_outputs.append(
                                os.path.join(
                                    output_dir,
                                    f"{label}_slices_{family}",
                                    f"{label}_slices_{family}-"
                                    f"{z_value:03d}-{base}.png",
                                )
                            )

        _run_mricrogl_command(
            cmd,
            timeout_s=timeout_s,
            output_dir=output_dir,
            expected_outputs=expected_outputs,
            render_description="MRIcroGL slice render",
        )

        print(f"[INFO] MRIcroGL quant_map_mm_panel raw screenshots saved under: {output_dir}")
    finally:
        try:
            shutil.rmtree(tmp_root)
        except Exception:
            pass

def render_volume_and_save_pngs_pyvista(
    nifti_paths,
    output_dir,
    angles=[('left', 90, 0), ('right', 270, 0), ('posterior', 0, 0), ('anterior', 180, 0), ('superior', 0, 90), ('inferior', 180, -90)],
    window=(0, 1000),
    image_size=(800, 800)
):
    """
    Render a list of NIfTI volumes using PyVista and save PNG screenshots from multiple angles.
    Parameters
    ----------
    nifti_paths : list of str
        List of paths to NIfTI files to render.
    output_dir : str
        Directory to save PNG screenshots (by angle subfolders will be created).
    angles : list of (str, float, float)
        List of (name, azimuth, elevation) tuples for camera angles.
    window : (float, float)
        Intensity window (min, max) for display.
    image_size : (int, int)
        Output PNG size in pixels.
    """
    for nifti_path in nifti_paths:
        # Load NIfTI
        img = nib.load(nifti_path)
        img = _ensure_ras(img)
        data = img.get_fdata()
        # Window/level
        vmin, vmax = window
        data = np.clip(data, vmin, vmax)
        data = (data - vmin) / (vmax - vmin)  # normalize to 0-1

        # Create PyVista UniformGrid
        grid = pv.ImageData()
        grid.dimensions = np.array(data.shape) + 1
        grid.origin = (0, 0, 0)
        grid.spacing = img.header.get_zooms()
        grid.cell_data["values"] = data.flatten(order="F")

        # Set up plotter (offscreen)
        plotter = pv.Plotter(off_screen=True, window_size=image_size)
        plotter.add_volume(
            grid,
            scalars='values',
            opacity='sigmoid',  # or 'linear', or a custom transfer function
            cmap='gray',
            shade=True,
            opacity_unit_distance=0.1,  # controls sharpness
            show_scalar_bar=False
        )

        # Output for each angle
        for name, azimuth, elevation in angles:
            plotter.camera_position = 'xy'  # reset to default
            plotter.camera.azimuth = azimuth
            plotter.camera.elevation = elevation
            plotter.camera.zoom(1.0)
            outdir = os.path.join(output_dir, 'by_angle', name)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, f"{name}-{azimuth}-{elevation}-{os.path.basename(nifti_path).split('.')[0]}.png")
            plotter.show(screenshot=outpath, auto_close=False)
        plotter.close()

def render_volume_and_save_pngs_vedo(
    nifti_paths,
    output_dir,
    angles=[('left', 90, 0), ('right', 270, 0), ('posterior', 0, 0), ('anterior', 180, 0), ('superior', 0, 90), ('inferior', 180, -90)],
    window=(0, 1000),
    image_size=(800, 800)
):
    """
    Render a list of NIfTI volumes using vedo and save PNG screenshots from multiple angles.
    Parameters
    ----------
    nifti_paths : list of str
        List of paths to NIfTI files to render.
    output_dir : str
        Directory to save PNG screenshots (by angle subfolders will be created).
    angles : list of (str, float, float)
        List of (name, azimuth, elevation) tuples for camera angles.
    window : (float, float)
        Intensity window (min, max) for display.
    image_size : (int, int)
        Output PNG size in pixels.
    """
    from vedo import Volume, Plotter
    import nibabel as nib
    import numpy as np
    import os

    for nifti_path in nifti_paths:
        img = nib.load(nifti_path)
        img = _ensure_ras(img)
        data = img.get_fdata()
        vmin, vmax = window
        data = np.clip(data, vmin, vmax)
        data = (data - vmin) / (vmax - vmin)  # normalize to 0-1

        vol = Volume(data)
        #vol.cmap('gray')
        #vol.alpha([0, 0, 1, 1])  # No transparency on main volume

        for name, azimuth, elevation in angles:
            plt = Plotter(offscreen=True, size=image_size, bg='black')
            plt.show(vol, resetcam=True)
            plt.camera.Azimuth(azimuth)
            plt.camera.Elevation(elevation)
            plt.camera.Zoom(1.0)
            outdir = os.path.join(output_dir, 'by_angle', name)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, f"{name}-{azimuth}-{elevation}-{os.path.basename(nifti_path).split('.')[0]}.png")
            plt.screenshot(outpath)
            plt.close() 