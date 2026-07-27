import os

## make directory structure

# Filled by configure_paths(args). Remains None until main (or a test) configures paths.
base_directory = None


def configure_paths(args):
    """Set base_directory and all T2VesselView path globals from CLI args.

    Safe to call more than once (idempotent). Does not import commandline;
    callers must pass the parsed args object explicitly.

    Parameters
    ----------
    args :
        Parsed CLI namespace with ``output_dir`` and/or ``mri_dir``.

    Returns
    -------
    bool
        True when paths were configured.
    """
    global base_directory
    if args is None:
        raise TypeError(
            "configure_paths(args) requires parsed CLI args; "
            "call commandline.parse_and_validate() first."
        )
    base_directory = args.output_dir or args.mri_dir
    if not base_directory:
        raise ValueError(
            "Cannot configure output paths: need -d/--mri_dir or -o/--output_dir."
        )
    _set_t2vv_root(os.path.join(base_directory, "T2VesselView"))
    return True


def _set_t2vv_root(t2vv_root):
    """Set all package output paths from a concrete T2VesselView-style root folder."""
    global main_t2vv_dir
    global eroded_nifti_dir
    global eroded_nifti_t1_dir
    global eroded_nifti_t2_tra_dir
    global eroded_nifti_t2_cor_dir
    global eroded_nifti_t2_sag_dir
    global eroded_nifti_t2_3d_dir
    global eroded_nifti_flair_dir
    global powerpoints_dir
    global dicom_dir
    global processing_dir
    global processing_figures_dir
    global processing_log_dir
    global processing_mask_dir
    global processed_t1_dir
    global processed_t2_dir
    global processed_flair_dir
    global processed_t2_tra_dir
    global processed_t2_cor_dir
    global processed_t2_sag_dir
    global processed_t2_3d_dir
    global renders_dir
    global renders_t1_dir
    global renders_t1_erode_dir
    global renders_t1_angle_dir
    global renders_t1_overlay_dir
    global renders_t1_overlay_erode_dir
    global renders_t1_overlay_angle_dir
    global renders_t2_dir
    global renders_t2_erode_dir
    global renders_t2_angle_dir
    global renders_qmm_dir
    global renders_qmm_raw_dir
    global renders_qmm_stitched_dir
    global renders_custom_trio_dir
    global renders_custom_trio_raw_dir
    global renders_custom_trio_stitched_dir
    global directory_structure

    main_t2vv_dir = os.path.abspath(t2vv_root)
    eroded_nifti_dir = os.path.join(main_t2vv_dir, "Eroded_nifti")
    eroded_nifti_t1_dir = os.path.join(eroded_nifti_dir, "T1")
    eroded_nifti_t2_tra_dir = os.path.join(eroded_nifti_dir, "T2_Tra")
    eroded_nifti_t2_cor_dir = os.path.join(eroded_nifti_dir, "T2_Cor")
    eroded_nifti_t2_sag_dir = os.path.join(eroded_nifti_dir, "T2_Sag")
    eroded_nifti_t2_3d_dir = os.path.join(eroded_nifti_dir, "T2_3D")
    eroded_nifti_flair_dir = os.path.join(eroded_nifti_dir, "FLAIR")
    powerpoints_dir = os.path.join(main_t2vv_dir, "PowerPoints")
    dicom_dir = os.path.join(main_t2vv_dir, "Dicom")
    processing_dir = os.path.join(main_t2vv_dir, "Processing")
    processing_figures_dir = os.path.join(processing_dir, "Figures_for_QA")
    processing_log_dir = os.path.join(processing_dir, "Log_files")
    processing_mask_dir = os.path.join(processing_dir, "Masks")
    processed_t1_dir = os.path.join(processing_dir, "Preprocessed_T1")
    processed_t2_dir = os.path.join(processing_dir, "Preprocessed_T2")
    processed_flair_dir = os.path.join(processing_dir, "Preprocessed_FLAIR")
    processed_t2_tra_dir = os.path.join(processing_dir, "Preprocessed_T2_Tra")
    processed_t2_cor_dir = os.path.join(processing_dir, "Preprocessed_T2_Cor")
    processed_t2_sag_dir = os.path.join(processing_dir, "Preprocessed_T2_Sag")
    processed_t2_3d_dir = os.path.join(processing_dir, "Preprocessed_T2_3D")
    renders_dir = os.path.join(main_t2vv_dir, "3D_renders_png")
    renders_t1_dir = os.path.join(renders_dir, "T1_3D_renders")
    renders_t1_erode_dir = os.path.join(renders_t1_dir, "by_erode_level")
    renders_t1_angle_dir = os.path.join(renders_t1_dir, "by_angle")
    renders_t1_overlay_dir = os.path.join(renders_dir, "T1_overlay_3D_renders")
    renders_t1_overlay_erode_dir = os.path.join(renders_t1_overlay_dir, "by_erode_level")
    renders_t1_overlay_angle_dir = os.path.join(renders_t1_overlay_dir, "by_angle")
    renders_t2_dir = os.path.join(renders_dir, "T2_vessel_3D_renders")
    renders_t2_erode_dir = os.path.join(renders_t2_dir, "by_erode_level")
    renders_t2_angle_dir = os.path.join(renders_t2_dir, "by_angle")
    renders_qmm_dir = os.path.join(renders_dir, "Quant_map_mm_panel")
    renders_qmm_raw_dir = os.path.join(renders_qmm_dir, "raw")
    renders_qmm_stitched_dir = os.path.join(renders_qmm_dir, "stitched")
    renders_custom_trio_dir = os.path.join(renders_dir, "Custom_overlay_trio")
    renders_custom_trio_raw_dir = os.path.join(renders_custom_trio_dir, "raw")
    renders_custom_trio_stitched_dir = os.path.join(renders_custom_trio_dir, "stitched")

    # Full path registry (for reference / tests). Create uses core + modality lists.
    directory_structure = [
        main_t2vv_dir,
        eroded_nifti_dir,
        eroded_nifti_t1_dir,
        eroded_nifti_t2_tra_dir,
        eroded_nifti_t2_cor_dir,
        eroded_nifti_t2_sag_dir,
        eroded_nifti_t2_3d_dir,
        eroded_nifti_flair_dir,
        powerpoints_dir,
        dicom_dir,
        processing_dir,
        processing_figures_dir,
        processing_log_dir,
        processing_mask_dir,
        processed_t1_dir,
        processed_t2_dir,
        processed_flair_dir,
        processed_t2_tra_dir,
        processed_t2_cor_dir,
        processed_t2_sag_dir,
        processed_t2_3d_dir,
        renders_dir,
        renders_t1_dir,
        renders_t1_erode_dir,
        renders_t1_angle_dir,
        renders_t1_overlay_dir,
        renders_t1_overlay_erode_dir,
        renders_t1_overlay_angle_dir,
        renders_t2_dir,
        renders_t2_erode_dir,
        renders_t2_angle_dir,
        renders_qmm_dir,
        renders_qmm_raw_dir,
        renders_qmm_stitched_dir
    ]


def use_existing_t2vesselview_dir(existing_root):
    """Use an existing T2VesselView-style folder for render-only input and output."""
    _set_t2vv_root(existing_root)


def core_directories():
    """Directories always created for a run (modality/panel trees are on demand)."""
    return [
        main_t2vv_dir,
        processing_dir,
        processing_figures_dir,
        processing_log_dir,
        processing_mask_dir,
        processed_t1_dir,
        eroded_nifti_dir,
        eroded_nifti_t1_dir,
        renders_dir,
    ]


def modality_directories_for_args(args):
    """Return preprocess/erode folders for modalities present on the CLI.

    Panel/render/DICOM/PowerPoint trees are not created here; writers call
    makedirs when those outputs are actually produced (including later
    t2vv_render_existing runs).
    """
    dirs = []
    if getattr(args, "flair", None):
        dirs.extend([processed_flair_dir, eroded_nifti_flair_dir])
    if getattr(args, "t2_cor", None):
        dirs.extend([processed_t2_cor_dir, eroded_nifti_t2_cor_dir])
    if getattr(args, "t2_tra", None):
        dirs.extend([processed_t2_tra_dir, eroded_nifti_t2_tra_dir])
    if (
        getattr(args, "t2_sag", None)
        or getattr(args, "t2_sag_left", None)
        or getattr(args, "t2_sag_right", None)
    ):
        dirs.extend([processed_t2_sag_dir, eroded_nifti_t2_sag_dir])
    if getattr(args, "t2_3d", None):
        dirs.extend([processed_t2_3d_dir, eroded_nifti_t2_3d_dir])
    return dirs


def create_directories(args):
    """Create core dirs plus folders for modalities present in args.

    Path globals must already exist via configure_paths / _set_t2vv_root;
    only mkdir is selective. Writers must still use os.makedirs(..., exist_ok=True)
    before writing so later add-on modality or render_existing steps can create
    missing folders.
    """
    if args is None:
        raise TypeError("create_directories(args) requires parsed CLI args.")
    to_create = list(core_directories()) + list(modality_directories_for_args(args))
    # Preserve order while dropping duplicates.
    seen = set()
    for directory in to_create:
        if directory in seen:
            continue
        seen.add(directory)
        os.makedirs(directory, exist_ok=True)


def prune_empty_directories(root=None):
    """Remove empty directories under the T2VesselView root (bottom-up).

    Never deletes the root itself. Safe after erosion-only or render runs:
    only empties are removed; folders with outputs are kept.
    """
    if root is None:
        root = main_t2vv_dir
    if not root or not os.path.isdir(root):
        return 0

    abs_root = os.path.abspath(root)
    removed = 0
    # Bottom-up so child empties are cleared before parents are reconsidered.
    for dirpath, dirnames, filenames in os.walk(abs_root, topdown=False):
        abs_dir = os.path.abspath(dirpath)
        if abs_dir == abs_root:
            continue
        # Re-check liveliness: walk snapshot may be stale after child removals.
        try:
            entries = os.listdir(abs_dir)
        except OSError:
            continue
        if entries:
            continue
        try:
            os.rmdir(abs_dir)
            removed += 1
        except OSError as e:
            print(f"[WARNING] Could not remove empty directory {abs_dir}: {e}")

    if removed:
        print(f"[INFO] Removed {removed} empty director{'y' if removed == 1 else 'ies'} under {abs_root}.")
    return removed
