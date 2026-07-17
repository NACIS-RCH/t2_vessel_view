import os
import argparse
import numpy as np
import pandas as pd
import nibabel as nb
import nibabel.freesurfer.mghformat as fsmgh
import gzip
import sys
import shutil
import re
import SimpleITK as sitk
import nipype.interfaces.fsl as fsl
import ants
import glob

# Check if we're in test mode
TEST_MODE = os.environ.get('T2VV_TEST_MODE') == '1'

# Import package modules using relative imports
from . import dir_structure
from . import logger
from . import input_validation
from . import commandline
from . import preprocess
from . import utils
from . import masking
from . import volume_rendering
from . import png_postprocess


def run_dependency_preflight():
    """Check required external tools and templates before processing starts."""
    if TEST_MODE:
        print("[INFO] Test mode enabled: skipping external dependency preflight checks.")
        return True

    errors = []

    print("Running dependency preflight checks...")

    # MRIcroGL executable
    try:
        mricrogl_path = volume_rendering.resolve_mricrogl_executable(
            os.environ.get("T2VV_MRICROGL_PATH", "")
        )
        print(f"[OK] MRIcroGL found: {mricrogl_path}")
    except Exception as e:
        errors.append(
            "MRIcroGL not found. Install MRIcroGL or set T2VV_MRICROGL_PATH. "
            "Try this command to locate it: "
            "`command -v MRIcroGL || command -v mricrogl || command -v MRIcroGL_QT`. "
            f"Details: {e}"
        )

    # MRIcroGL template used by current rendering calls
    try:
        template_path = volume_rendering.resolve_mricrogl_template_path(
            "mricrogl_T1_renders.py"
        )
        print(f"[OK] MRIcroGL render template found: {template_path}")
    except Exception as e:
        errors.append(
            "MRIcroGL render template not found. Ensure display script templates are installed "
            "or set T2VV_MRICROGL_TEMPLATE_DIR. "
            f"Details: {e}"
        )

    # FSL commands needed by this pipeline
    if getattr(commandline.args, "render_existing_erosions", False):
        print("[INFO] Render-existing mode enabled: skipping FSL dependency checks.")
    else:
        bet_path = shutil.which("bet")
        robustfov_path = shutil.which("robustfov")

        if bet_path:
            print(f"[OK] FSL BET found: {bet_path}")
        else:
            errors.append(
                "FSL BET command not found ('bet'). Install FSL and ensure it is on PATH."
            )

        if robustfov_path:
            print(f"[OK] FSL RobustFOV found: {robustfov_path}")
        else:
            errors.append(
                "FSL RobustFOV command not found ('robustfov'). Install FSL and ensure it is on PATH."
            )

    if errors:
        print("[ERROR] Checks for external software dependencies (programs FSL and MRIcroGL) could not find all of the software needed to run this package:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("Dependency preflight checks passed.")
    return True

OVERLAY_CLI_COUNT = 4


def _iter_overlay_cli_indices():
    """Yield supported numbered overlay indices."""
    return range(1, OVERLAY_CLI_COUNT + 1)


def _has_any_cli_overlay():
    """Return True when any numbered overlay path was provided."""
    return any(getattr(commandline.args, f"overlay{idx}_path", None) for idx in _iter_overlay_cli_indices())


def _build_cli_overlay_specs(panel_preset=None):
    """Build MRIcroGL overlay specs from numbered CLI arguments.

    Overlays are loaded directly in MRIcroGL (not preprocessed/masked by this pipeline).
    If window min/max are omitted, robust defaults are estimated from the overlay image.
    """
    overlays = []
    overlay_names = []
    default_colors = {
        1: "jet",
        2: "red",
        3: "hot",
        4: "blue",
    }
    for idx in _iter_overlay_cli_indices():
        path_val = getattr(commandline.args, f"overlay{idx}_path", None)
        if not path_val:
            continue

        if not os.path.exists(path_val):
            raise FileNotFoundError(f"Overlay {idx} not found: {path_val}")

        # Preset-specific defaults (only when value was not provided on CLI)
        default_color = default_colors.get(idx, "jet")
        default_opacity = 35
        if panel_preset == "quant_map_mm_panel" and idx == 2:
            default_color = "electric_blue"
            default_opacity = 100

        raw_color = getattr(commandline.args, f"overlay{idx}_color", None)
        color_val = raw_color if raw_color else default_color
        name_val = getattr(commandline.args, f"overlay{idx}_name", f"Overlay{idx}")
        min_val = getattr(commandline.args, f"overlay{idx}_min", None)
        max_val = getattr(commandline.args, f"overlay{idx}_max", None)
        raw_opacity = getattr(commandline.args, f"overlay{idx}_opacity", None)
        opacity_val = int(raw_opacity) if raw_opacity is not None else int(default_opacity)

        if min_val is None or max_val is None:
            auto_min, auto_max = volume_rendering.compute_series_window(
                [path_val],
                low_pct=1.0,
                high_pct=99.0
            )
            min_val = auto_min
            max_val = auto_max
            print(
                f"[WARNING] Overlay {idx} window min/max were not provided. "
                f"Auto-estimated values are min={min_val}, max={max_val}. "
                "it is strongly recommended to provide explicit "
                f"--overlay{idx}-min and --overlay{idx}-max."
            )

        overlays.append({
            "path": os.path.abspath(path_val),
            "name": str(name_val),
            "color": str(color_val),
            "min": float(min_val),
            "max": float(max_val),
            "opacity": int(opacity_val)
        })
        overlay_names.append(str(name_val))
    return overlays, overlay_names


def _select_qmm_eroded_subset(nifti_paths, main_depth_int):
    """Select erosion files around main depth."""
    if not nifti_paths:
        return []
    main_depth_int = int(main_depth_int)
    target_depths = []
    if main_depth_int >= 20:
        target_depths.append(main_depth_int - 20)
    if main_depth_int >= 15:
        target_depths.append(main_depth_int - 15)
    target_depths.extend([
        main_depth_int - 10,
        main_depth_int - 5,
        main_depth_int,
        main_depth_int + 5,
        main_depth_int + 10,
        main_depth_int + 15,
    ])
    target_prefixes = {f"{d:03d}" for d in target_depths if d >= 0}
    selected = []
    for p in sorted(nifti_paths, key=os.path.basename):
        bn = os.path.basename(p)
        m = re.match(r"^(\d+)_eroded", bn)
        if m and m.group(1).zfill(3) in target_prefixes:
            selected.append(p)
    return selected


def _iter_chunks(items, chunk_size):
    """Yield consecutive chunks from a list."""
    if chunk_size <= 0:
        yield items
        return
    for start_idx in range(0, len(items), chunk_size):
        yield items[start_idx:start_idx + chunk_size]


def _collect_eroded_files(directory, pattern):
    """Return sorted eroded NIfTI files from a render source directory."""
    return sorted(glob.glob(os.path.join(directory, pattern)), key=os.path.basename)


def _validate_render_existing_inputs(panel_preset):
    """Validate that render-only mode has the existing eroded files it needs."""
    eroded_sets = {
        "T1": _collect_eroded_files(dir_structure.eroded_nifti_t1_dir, "*eroded*t1*nii.gz"),
        "FLAIR": _collect_eroded_files(dir_structure.eroded_nifti_flair_dir, "*eroded*flair*nii.gz"),
        "T2 sagittal": _collect_eroded_files(dir_structure.eroded_nifti_t2_sag_dir, "*eroded*t2_sag*nii.gz"),
        "T2 coronal": _collect_eroded_files(dir_structure.eroded_nifti_t2_cor_dir, "*eroded*t2_cor*nii.gz"),
        "T2 transverse": _collect_eroded_files(dir_structure.eroded_nifti_t2_tra_dir, "*eroded*t2_tra*nii.gz"),
        "T2 3D": _collect_eroded_files(dir_structure.eroded_nifti_t2_3d_dir, "*eroded*t2_3d*nii.gz"),
    }
    any_eroded = any(eroded_sets.values())
    if not any_eroded:
        raise ValueError(
            "No eroded NIfTI files were found under the render source folder. "
            "Expected files under Eroded_nifti/T1, FLAIR, or T2_* subfolders."
        )

    has_overlay = _has_any_cli_overlay()
    if has_overlay and not eroded_sets["T1"]:
        raise ValueError("Render-only T1 overlay output requires existing T1 eroded files.")

    if panel_preset == "quant_map_mm_panel":
        if not eroded_sets["T1"]:
            raise ValueError("quant_map_mm_panel render-only mode requires existing T1 eroded files.")
        if not eroded_sets["FLAIR"]:
            raise ValueError("quant_map_mm_panel render-only mode requires existing FLAIR eroded files.")
        requested_qmm_angles = getattr(commandline.args, "qmm_angles", None) or [
            "left", "right", "anterior", "posterior", "superior", "inferior"
        ]
        needs_sag = any(ang in requested_qmm_angles for ang in ("left", "right"))
        needs_cor = any(ang in requested_qmm_angles for ang in ("anterior", "posterior"))
        needs_tra = any(ang in requested_qmm_angles for ang in ("superior", "inferior"))
        has_t2_3d = bool(eroded_sets["T2 3D"])
        if needs_sag and not (eroded_sets["T2 sagittal"] or has_t2_3d or eroded_sets["T2 transverse"]):
            raise ValueError(
                "quant_map_mm_panel left/right angles require T2 sagittal, "
                "fallback T2 3D, or fallback T2 transverse eroded files."
            )
        if needs_cor and not (eroded_sets["T2 coronal"] or has_t2_3d):
            raise ValueError("quant_map_mm_panel anterior/posterior angles require T2 coronal or fallback T2 3D eroded files.")
        if needs_tra and not (eroded_sets["T2 transverse"] or has_t2_3d):
            raise ValueError("quant_map_mm_panel superior/inferior angles require T2 transverse or fallback T2 3D eroded files.")


def _run_render_outputs(panel_preset):
    """Run volume rendering and PNG/PPTX/DICOM post-processing from existing eroded files."""
    mricrogl_exec = volume_rendering.resolve_mricrogl_executable(
        os.environ.get('T2VV_MRICROGL_PATH', "")
    )
    overlay_specs, overlay_names = _build_cli_overlay_specs(panel_preset=panel_preset)
    qmm_only_outputs_mode = panel_preset == "quant_map_mm_panel"

    t1_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_t1_dir, '*eroded*t1*nii.gz')
    t2_sag_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_t2_sag_dir, '*eroded*t2_sag*nii.gz')
    t2_cor_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_t2_cor_dir, '*eroded*t2_cor*nii.gz')
    t2_tra_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_t2_tra_dir, '*eroded*t2_tra*nii.gz')
    t2_3d_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_t2_3d_dir, '*eroded*t2_3d*nii.gz')
    flair_eroded_files = _collect_eroded_files(dir_structure.eroded_nifti_flair_dir, '*eroded*flair*nii.gz')

    if t1_eroded_files:
        t1_window = volume_rendering.compute_series_window(t1_eroded_files, low_pct=2.0, high_pct=90.0)
        t1_window = volume_rendering.refine_window_vmax_by_saturation_circles(
            t1_eroded_files,
            t1_window,
            radius_mm=1.5,
            bright_threshold=250,
            max_valid_circle_locations=4,
            representative_slices=5,
            max_images_to_check=3,
            vmax_growth_factor=1.10,
            max_iterations=8
        )
        if not qmm_only_outputs_mode:
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                t1_eroded_files,
                dir_structure.renders_t1_dir,
                angles=[[90, 0, 'left'], [270, 0, 'right'], [180, 0, 'anterior'], [0, 0, 'posterior'], [0, 90, 'superior'], [180, -90, 'inferior'],
                        [270, 180, 'surg_left_lat'], [90, 180, 'surg_right_lat'], [300, 175, 'surg_left_ato'], [60, 175, 'surg_right_ato']],
                window=t1_window,
                image_size=(1200, 1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_renders.py",
                camera_distance='auto'
            )
            try:
                png_postprocess.run_preset_t1_overview_per_depth(
                    add_orientation_labels=True,
                    background_rgb=[0, 0, 0],
                    threshold=2,
                    pptx_name="T1_overview"
                )
            except Exception as e:
                print(f"[WARNING] PNG post-processing (T1 overview) skipped: {e}")

        if overlay_specs:
            try:
                t1_overview_overlay_specs = overlay_specs
                t1_overview_overlay_names = overlay_names
                export_overlay_dicom = bool(getattr(commandline.args, "export_overlay_dicom", False))
                dicom_metadata = {}
                if export_overlay_dicom:
                    dicom_metadata = input_validation.extract_dicom_metadata(
                        commandline.args.dicom_metadata_source
                    )
                    dicom_patient_id_override = getattr(commandline.args, "dicom_patient_id", None)
                    if dicom_patient_id_override:
                        dicom_metadata["patient_id"] = dicom_patient_id_override
                overlay_label = " + ".join(t1_overview_overlay_names)
                overlay_colorbar_spec = t1_overview_overlay_specs
                overlay_angles = [[90, 0, 'left'], [270, 0, 'right'], [180, 0, 'anterior'], [0, 0, 'posterior'], [0, 90, 'superior'], [180, -90, 'inferior'],
                                  [270, 180, 'surg_left_lat'], [90, 180, 'surg_right_lat'], [300, 175, 'surg_left_ato'], [60, 175, 'surg_right_ato']]
                overlay_batches = list(_iter_chunks(t1_eroded_files, 5))
                for batch_idx, t1_eroded_batch in enumerate(overlay_batches, start=1):
                    print(
                        f"[INFO] Rendering T1 overlay batch {batch_idx}/{len(overlay_batches)} "
                        f"({len(t1_eroded_batch)} erosion level(s))."
                    )
                    volume_rendering.render_volume_and_save_pngs_mricrogl(
                        t1_eroded_batch,
                        dir_structure.renders_t1_overlay_dir,
                        angles=overlay_angles,
                        window=t1_window,
                        image_size=(1200, 1200),
                        mricrogl_path=mricrogl_exec,
                        template_filename="mricrogl_T1_renders.py",
                        camera_distance='auto',
                        overlays=t1_overview_overlay_specs
                    )
                png_postprocess.run_preset_t1_overview_per_depth(
                    add_orientation_labels=True,
                    background_rgb=[0, 0, 0],
                    threshold=2,
                    pptx_name="T1_overlay_overview",
                    render_root_dir=dir_structure.renders_t1_overlay_dir,
                    modality_label="T1 + " + overlay_label,
                    export_dicom=export_overlay_dicom,
                    dicom_basename="T1_overlay_overview",
                    dicom_series_description="T1 erosion render + " + overlay_label + " overlay",
                    dicom_patient_id=dicom_metadata.get("patient_id"),
                    dicom_patient_name=dicom_metadata.get("patient_name"),
                    dicom_study_date=dicom_metadata.get("study_date"),
                    dicom_study_time=dicom_metadata.get("study_time"),
                    dicom_study_instance_uid=dicom_metadata.get("study_instance_uid"),
                    overlay_colorbar_spec=overlay_colorbar_spec
                )
            except Exception as e:
                print(f"[WARNING] T1 overlay rendering/post-processing skipped: {e}")

    if (not qmm_only_outputs_mode) and t2_sag_eroded_files:
        t2_sag_window = volume_rendering.compute_series_window(t2_sag_eroded_files, low_pct=0.3, high_pct=99.75)
        t2_sag_left_files = [p for p in t2_sag_eroded_files if 't2_sag_left' in os.path.basename(p).lower()]
        t2_sag_right_files = [p for p in t2_sag_eroded_files if 't2_sag_right' in os.path.basename(p).lower()]
        t2_sag_generic_files = [p for p in t2_sag_eroded_files if ('t2_sag_left' not in os.path.basename(p).lower() and 't2_sag_right' not in os.path.basename(p).lower())]
        for files_for_angle, angles in [
            (t2_sag_left_files or t2_sag_generic_files or t2_sag_right_files, [[90, 0, 'left'], [270, 180, 'surg_left_lat'], [300, 175, 'surg_left_ato']]),
            (t2_sag_right_files or t2_sag_generic_files or t2_sag_left_files, [[270, 0, 'right'], [90, 180, 'surg_right_lat'], [60, 175, 'surg_right_ato']]),
        ]:
            if files_for_angle:
                volume_rendering.render_volume_and_save_pngs_mricrogl(
                    files_for_angle,
                    os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
                    angles=angles,
                    window=t2_sag_window,
                    image_size=(1200, 1200),
                    mricrogl_path=mricrogl_exec,
                    template_filename="mricrogl_T1_renders.py",
                    camera_distance='auto'
                )

    render_specs = [
        (t2_cor_eroded_files, dir_structure.eroded_nifti_t2_cor_dir, 'T2_Cor_3D_renders', 0.3, 99.75),
        (t2_tra_eroded_files, dir_structure.eroded_nifti_t2_tra_dir, 'T2_Tra_3D_renders', 0.3, 99.75),
        (t2_3d_eroded_files, dir_structure.eroded_nifti_t2_3d_dir, 'T2_3D_3D_renders', 0.3, 99.75),
        (flair_eroded_files, dir_structure.eroded_nifti_flair_dir, 'FLAIR_3D_renders', 7.5, 99.99),
    ]
    standard_angles = [[90, 0, 'left'], [270, 0, 'right'], [180, 0, 'anterior'], [0, 0, 'posterior'], [0, 90, 'superior'], [180, -90, 'inferior'],
                       [270, 180, 'surg_left_lat'], [90, 180, 'surg_right_lat'], [300, 175, 'surg_left_ato'], [60, 175, 'surg_right_ato']]
    for eroded_files, _source_dir, render_folder, low_pct, high_pct in render_specs:
        if (not qmm_only_outputs_mode) and eroded_files:
            window = volume_rendering.compute_series_window(eroded_files, low_pct=low_pct, high_pct=high_pct)
            out_dir = os.path.join(dir_structure.renders_dir, render_folder)
            if render_folder.startswith("T2_"):
                out_dir = os.path.join(dir_structure.renders_t2_dir, render_folder)
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                eroded_files,
                out_dir,
                angles=standard_angles,
                window=window,
                image_size=(1200, 1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_renders.py",
                camera_distance='auto'
            )

    if panel_preset == "quant_map_mm_panel":
        try:
            if len(overlay_specs) < 2:
                raise ValueError("quant_map_mm_panel requires two overlays (--overlay1-path and --overlay2-path).")
            if not flair_eroded_files:
                raise ValueError("quant_map_mm_panel requires FLAIR inputs and eroded FLAIR outputs.")
            qmm_t1_overlays = overlay_specs
            qmm_non_t1_overlays = overlay_specs[:1]
            main_depth_int = int(getattr(commandline.args, "qmm_main_erode_depth", 30))
            main_prefix = f"{main_depth_int:03d}"
            t1_subset = _select_qmm_eroded_subset(t1_eroded_files, main_depth_int)
            flair_subset = _select_qmm_eroded_subset(flair_eroded_files, main_depth_int)
            t2_sag_subset = _select_qmm_eroded_subset(t2_sag_eroded_files, main_depth_int)
            t2_cor_subset = _select_qmm_eroded_subset(t2_cor_eroded_files, main_depth_int)
            t2_tra_subset = _select_qmm_eroded_subset(t2_tra_eroded_files, main_depth_int)
            t2_3d_subset = _select_qmm_eroded_subset(t2_3d_eroded_files, main_depth_int)
            if not t1_subset:
                raise ValueError("quant_map_mm_panel: no matching T1 eroded subset found around requested main depth.")
            if not flair_subset:
                raise ValueError("quant_map_mm_panel: no matching FLAIR eroded subset found around requested main depth.")
            print(
                f"[INFO] Running quant_map_mm_panel preset with main erosion depth {main_depth_int} "
                f"(prefix {main_prefix})."
            )
            t1_win = volume_rendering.compute_series_window(t1_subset, low_pct=2.0, high_pct=90.0)
            t1_win = volume_rendering.refine_window_vmax_by_saturation_circles(
                t1_subset,
                t1_win,
                radius_mm=1.5,
                bright_threshold=250,
                max_valid_circle_locations=4,
                representative_slices=5,
                max_images_to_check=3,
                vmax_growth_factor=1.10,
                max_iterations=8
            )
            flair_win = volume_rendering.compute_series_window(flair_subset, low_pct=7.5, high_pct=99.99)
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                t1_subset,
                os.path.join(dir_structure.renders_qmm_raw_dir, "T1"),
                overlays=qmm_t1_overlays,
                window=t1_win,
                main_erode_prefix=main_prefix,
                mricrogl_path=mricrogl_exec
            )
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                flair_subset,
                os.path.join(dir_structure.renders_qmm_raw_dir, "FLAIR"),
                overlays=qmm_non_t1_overlays,
                window=flair_win,
                main_erode_prefix=main_prefix,
                mricrogl_path=mricrogl_exec
            )
            for subset, label in [
                (t2_sag_subset, "T2_sag"),
                (t2_cor_subset, "T2_cor"),
                (t2_tra_subset, "T2_tra"),
                (t2_3d_subset, "T2_3d"),
            ]:
                if subset:
                    t2_win = volume_rendering.compute_series_window(subset, low_pct=0.3, high_pct=99.75)
                    volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                        subset,
                        os.path.join(dir_structure.renders_qmm_raw_dir, label),
                        overlays=qmm_non_t1_overlays,
                        window=t2_win,
                        main_erode_prefix=main_prefix,
                        mricrogl_path=mricrogl_exec
                    )
            requested_qmm_angles = getattr(commandline.args, "qmm_angles", None) or [
                "left", "right", "anterior", "posterior", "superior", "inferior"
            ]
            angle_to_t2_source = {}
            if t2_sag_subset:
                angle_to_t2_source["left"] = "T2_sag"
                angle_to_t2_source["right"] = "T2_sag"
            if t2_cor_subset:
                angle_to_t2_source["anterior"] = "T2_cor"
                angle_to_t2_source["posterior"] = "T2_cor"
            if t2_tra_subset:
                angle_to_t2_source["superior"] = "T2_tra"
                angle_to_t2_source["inferior"] = "T2_tra"
            for ang in requested_qmm_angles:
                if ang not in angle_to_t2_source and t2_3d_subset:
                    angle_to_t2_source[ang] = "T2_3d"
            for ang in ("left", "right"):
                if ang in requested_qmm_angles and ang not in angle_to_t2_source and t2_tra_subset:
                    angle_to_t2_source[ang] = "T2_tra"
            png_postprocess.run_preset_quant_map_mm_panel(
                raw_root=dir_structure.renders_qmm_raw_dir,
                angle_to_t2_source=angle_to_t2_source,
                qmm_angles=requested_qmm_angles,
                overlay_names=overlay_names,
                add_orientation_labels=True,
                background_rgb=[0, 0, 0],
                threshold=2,
                pptx_name="quant_map_mm_panel_overview"
            )
        except Exception as e:
            print(f"[WARNING] quant_map_mm_panel preset skipped: {e}")

    has_additional_modalities = any([
        bool(commandline.args.flair),
        bool(commandline.args.t2_sag),
        bool(getattr(commandline.args, 't2_sag_left', None)),
        bool(getattr(commandline.args, 't2_sag_right', None)),
        bool(commandline.args.t2_cor),
        bool(commandline.args.t2_tra),
        bool(commandline.args.t2_3d),
    ])
    if (not qmm_only_outputs_mode) and has_additional_modalities:
        try:
            png_postprocess.run_preset_multimodal_by_angle_per_depth(
                angles=['superior', 'inferior', 'left', 'right', 'anterior', 'posterior'],
                add_orientation_labels=True,
                background_rgb=[0, 0, 0],
                threshold=2,
                pptx_name="Multimodal_overview"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (multimodal by angle) skipped: {e}")
    elif not qmm_only_outputs_mode:
        print("[INFO] Skipping multimodal overview preset: no FLAIR/T2 inputs were provided.")

    if not qmm_only_outputs_mode:
        try:
            png_postprocess.run_preset_t2_overview_per_depth(
                add_orientation_labels=True,
                background_rgb=[0, 0, 0],
                threshold=2,
                pptx_name="T2_overview"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (T2 overview) skipped: {e}")

    if (not qmm_only_outputs_mode) and has_additional_modalities:
        try:
            png_postprocess.run_preset_multimodal_other_angles_per_depth(
                angles=['surg_left_lat', 'surg_right_lat', 'surg_left_ato', 'surg_right_ato'],
                add_orientation_labels=True,
                background_rgb=[0, 0, 0],
                threshold=2,
                pptx_name="multimodal_overview_other_angles"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (multimodal other angles) skipped: {e}")
    elif not qmm_only_outputs_mode:
        print("[INFO] Skipping multimodal surgical preset: no FLAIR/T2 inputs were provided.")

    return 0


def main():
    if not run_dependency_preflight():
        sys.exit(1)

    auto_method = getattr(commandline.args, "auto_mask_method", "bet")
    panel_preset = getattr(commandline.args, "panel_preset", None)
    render_existing_erosions = bool(getattr(commandline.args, "render_existing_erosions", False))

    # User-friendly rule: FLAIR is optional for BET, required for watershed.
    if auto_method == "watershed" and not commandline.args.flair:
        print(
            "[ERROR] You selected --auto-mask-method watershed, but no FLAIR image was provided with -f. "
            "Please provide a FLAIR image or rerun with --auto-mask-method bet."
        )
        sys.exit(1)
    if auto_method == "bet" and not commandline.args.flair:
        print(
            "[INFO] No FLAIR image provided. Continuing with BET automatic mask generation using the T1 image."
        )

    # Validate input files before processing
    print("Validating input files...")
    is_valid, errors = input_validation.validate_input_files(
        commandline.args.t1, 
        commandline.args.mri_dir,
        {
            't2_sag': commandline.args.t2_sag,
            't2_cor': commandline.args.t2_cor,
            't2_tra': commandline.args.t2_tra,
            'flair': commandline.args.flair,
            'user_mask': commandline.args.user_mask,
            'user_mask_structural': commandline.args.user_mask_structural,
            'overlay1': getattr(commandline.args, 'overlay1_path', None),
            'overlay2': getattr(commandline.args, 'overlay2_path', None),
            'overlay3': getattr(commandline.args, 'overlay3_path', None),
            'overlay4': getattr(commandline.args, 'overlay4_path', None)
        }
    )

    if not is_valid:
        print("Input validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    else:
        print("All input files validated successfully!")

    if render_existing_erosions:
        dir_structure.use_existing_t2vesselview_dir(commandline.args.render_source_dir)
        print(
            "[INFO] Render-existing mode: skipping preprocessing, masking, and erosion generation. "
            f"Reading and writing outputs under: {dir_structure.main_t2vv_dir}"
        )

    # Create directory structure
    dir_structure.create_directories()

    if render_existing_erosions:
        try:
            _validate_render_existing_inputs(panel_preset)
        except Exception as e:
            print(f"[ERROR] Render-existing validation failed: {e}")
            sys.exit(1)
        return _run_render_outputs(panel_preset)


    ## reorient inputs to standard orientation 
    reoriented_main_image_path = preprocess.convert_and_reorient(commandline.args.t1, "t1")
    reoriented_flair_path = None
    if commandline.args.flair:
        reoriented_flair_path = preprocess.convert_and_reorient(commandline.args.flair, "flair")

    # Support one or two sagittal T2 acquisitions (generic, left, right)
    reoriented_t2_sag_paths = []
    if commandline.args.t2_sag:
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag, "t2_sag")
        )
    if getattr(commandline.args, 't2_sag_left', None):
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag_left, "t2_sag_left")
        )
    if getattr(commandline.args, 't2_sag_right', None):
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag_right, "t2_sag_right")
        )

    reoriented_t2_cor_path = None
    if commandline.args.t2_cor:
        reoriented_t2_cor_path = preprocess.convert_and_reorient(commandline.args.t2_cor, "t2_cor")

    reoriented_t2_tra_path = None
    if commandline.args.t2_tra:
        reoriented_t2_tra_path = preprocess.convert_and_reorient(commandline.args.t2_tra, "t2_tra")

    reoriented_t2_3d_path = None
    if commandline.args.t2_3d:
        reoriented_t2_3d_path = preprocess.convert_and_reorient(commandline.args.t2_3d, "t2_3d")

    ## preprocess t1    
    preprocessed_main_image, preprocessed_main_image_path = preprocess.preprocess_main_image(reoriented_main_image_path)

    ## preprocess flair and register to preprocessed t1
    preprocessed_flair = None
    preprocessed_flair_img = None
    if reoriented_flair_path:
        preprocessed_flair, preprocessed_flair_img = preprocess.preprocess_n4_reg(reoriented_flair_path, "flair", preprocessed_main_image_path)

    ## preprocess t2 images
    preprocessed_t2_sag_paths = []
    preprocessed_t2_sag_imgs = []
    for reor_path in reoriented_t2_sag_paths:
        # Use the imagetype string embedded in the filename tag to keep outputs distinct
        # If reor_path name contains 't2_sag_left' or 't2_sag_right', preserve it; else default to 't2_sag'
        tag = 't2_sag_left' if 't2_sag_left' in os.path.basename(reor_path) else (
              't2_sag_right' if 't2_sag_right' in os.path.basename(reor_path) else 't2_sag')
        pp_path, pp_img = preprocess.preprocess_n4_reg(reor_path, tag, preprocessed_main_image_path)
        preprocessed_t2_sag_paths.append(pp_path)
        preprocessed_t2_sag_imgs.append(pp_img)

    preprocessed_t2_cor_path = None
    preprocessed_t2_cor_img = None
    if reoriented_t2_cor_path:
        preprocessed_t2_cor_path, preprocessed_t2_cor_img = preprocess.preprocess_n4_reg(reoriented_t2_cor_path, "t2_cor", preprocessed_main_image_path)

    preprocessed_t2_tra_path = None
    preprocessed_t2_tra_img = None
    if reoriented_t2_tra_path:
        preprocessed_t2_tra_path, preprocessed_t2_tra_img = preprocess.preprocess_n4_reg(reoriented_t2_tra_path, "t2_tra", preprocessed_main_image_path)

    preprocessed_t2_3d_path = None
    preprocessed_t2_3d_img = None
    if reoriented_t2_3d_path:
        preprocessed_t2_3d_path, preprocessed_t2_3d_img = preprocess.preprocess_n4_reg(reoriented_t2_3d_path, "t2_3d", preprocessed_main_image_path)

    ## postprocess t2 images
    # Keep (image, tag) pairs so tags propagate to eroded filenames
    postprocessed_t2_sag_items = []
    for pp_path in preprocessed_t2_sag_paths:
        tag = 't2_sag_left' if 't2_sag_left' in os.path.basename(pp_path) else (
              't2_sag_right' if 't2_sag_right' in os.path.basename(pp_path) else 't2_sag')
        img_obj = preprocess.postprocess_t2(pp_path, tag)
        postprocessed_t2_sag_items.append((img_obj, tag))

    postprocessed_t2_tra_image = None
    if preprocessed_t2_tra_path:
        postprocessed_t2_tra_image = preprocess.postprocess_t2(preprocessed_t2_tra_path, "t2_tra")

    postprocessed_t2_cor_image = None
    if preprocessed_t2_cor_path:
        postprocessed_t2_cor_image = preprocess.postprocess_t2(preprocessed_t2_cor_path, "t2_cor")

    postprocessed_t2_3d_image = None
    if preprocessed_t2_3d_path:
        postprocessed_t2_3d_image = preprocess.postprocess_t2(preprocessed_t2_3d_path, "t2_3d")

    ## generate automatic mask for QA (and for processing if no user mask is supplied)
    mask_source_path = preprocessed_flair or preprocessed_main_image_path
    auto_mask_path = ""
    auto_mask_exists = False
    auto_qa_filename = f"QA_mask_overlay_auto_mask_{auto_method}.png"

    try:
        if auto_method == "watershed":
            if not preprocessed_flair:
                raise ValueError("Watershed mask method requires a preprocessed FLAIR image.")
            auto_mask_path = masking.generate_mask_watershed(preprocessed_flair)
        else:
            auto_mask_path = masking.generate_mask(mask_source_path)
        auto_mask_exists = os.path.exists(auto_mask_path)
    except Exception as e:
        if commandline.args.user_mask:
            print(f"[WARNING] Automatic mask generation ({auto_method}) failed: {e}")
            auto_mask_exists = False
        else:
            print(f"[ERROR] Automatic mask generation ({auto_method}) failed: {e}")
            sys.exit(1)

    if not commandline.args.user_mask:
        print(
            "[INFO] No user-provided mask was supplied. This is the default. "
            f"The automatically generated {auto_method} mask will be used for processing. "
            "If manual correction of the mask is needed, or if you have a better mask than the pipeline generates, rerun the pipeline and input your preferred mask  with --user_mask."
        )
        if not auto_mask_exists:
            print(
                f"[ERROR] {auto_method} mask generation failed: no automatic mask file was found. "
                "You could try providing a user-generated mask with --user_mask and rerun."
            )
            sys.exit(1)
        mask_to_input = auto_mask_path
        try:
            auto_mask_img_for_qa = sitk.ReadImage(auto_mask_path)
        except Exception as e:
            print(f"[ERROR] Could not read generated {auto_method} mask for processing: {e}")
            sys.exit(1)
        utils.save_qa_mask_overlay(
            main_image=preprocessed_main_image,
            mask_image=auto_mask_img_for_qa,
            filename=auto_qa_filename
        )
    else:
        if not os.path.exists(commandline.args.user_mask):
            raise FileNotFoundError(f"User-provided mask not found: {commandline.args.user_mask}")
        if not commandline.args.user_mask_structural:
            print(
                "[ERROR] The structural image that the mask was made with, must be supplied when inputting a mask. This is so the structural image can be used for checking against and possibly registration to, the main input image. If you made the mask with the main input image, please just specify the main input image again with -n/--user_mask_structural "
                "when using -m/--user_mask."
            )
            sys.exit(1)
        if not os.path.exists(commandline.args.user_mask_structural):
            raise FileNotFoundError(
                f"User mask structural image not found: {commandline.args.user_mask_structural}"
            )
        print(
            "[INFO] User-provided mask detected. "
            "The user mask will be affine registered to the preprocessed T1 using the structural image supplied with -n. "
            f"An automatic {auto_method} mask will also be generated for QA comparison."
        )
        try:
            mask_to_input = preprocess.register_user_mask_to_preprocessed_t1(
                user_mask_path=commandline.args.user_mask,
                user_mask_structural_path=commandline.args.user_mask_structural,
                preprocessed_main_image_path=preprocessed_main_image_path
            )
        except Exception as e:
            print(f"[ERROR] User mask registration failed: {e}")
            sys.exit(1)

        if auto_mask_exists:
            try:
                auto_mask_img_for_qa = sitk.ReadImage(auto_mask_path)
                utils.save_qa_mask_overlay(
                    main_image=preprocessed_main_image,
                    mask_image=auto_mask_img_for_qa,
                    filename=auto_qa_filename
                )
            except Exception as e:
                print(f"[WARNING] Could not generate QA overlay for automatic {auto_method} mask: {e}")
        else:
            print(f"[WARNING] Automatic {auto_method} mask was not created. Continuing with user-provided mask only.")

        user_mask_img_for_qa = sitk.ReadImage(mask_to_input)
        utils.save_qa_mask_overlay(
            main_image=preprocessed_main_image,
            mask_image=user_mask_img_for_qa,
            filename="QA_mask_overlay_user_mask.png"
        )
    
    ## process mask
    sdt_all_plus_2 = masking.main_mask_operations(mask_to_input)

    ## erode mask
    eroded_masks_dict, zero_padded_erode_depths_list = masking.mask_erosions(sdt_all_plus_2)

    ## erode nifti
    if eroded_masks_dict and zero_padded_erode_depths_list:
        if preprocessed_main_image:
            res_t1 = masking.multiply_masks_by_images(preprocessed_main_image, "t1", dir_structure.eroded_nifti_t1_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        # Handle one or more sagittal T2s with explicit tags
        for t2s_img, tag in postprocessed_t2_sag_items:
            _ = masking.multiply_masks_by_images(t2s_img, tag, dir_structure.eroded_nifti_t2_sag_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_cor_image:
            res_t2_cor = masking.multiply_masks_by_images(postprocessed_t2_cor_image, "t2_cor", dir_structure.eroded_nifti_t2_cor_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_tra_image:
            res_t2_tra = masking.multiply_masks_by_images(postprocessed_t2_tra_image, "t2_tra", dir_structure.eroded_nifti_t2_tra_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if preprocessed_flair_img:
            res_flair = masking.multiply_masks_by_images(preprocessed_flair_img, "flair", dir_structure.eroded_nifti_flair_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_3d_image:
            res_t2_3d = masking.multiply_masks_by_images(postprocessed_t2_3d_image, "t2_3d", dir_structure.eroded_nifti_t2_3d_dir, zero_padded_erode_depths_list, eroded_masks_dict)

    # --- Volume rendering and PNG output ---
    # Resolve MRIcroGL executable across macOS/Linux (env var, PATH, common locations)
    mricrogl_exec = volume_rendering.resolve_mricrogl_executable(
        os.environ.get('T2VV_MRICROGL_PATH', "")
    )
    overlay_specs, overlay_names = _build_cli_overlay_specs(panel_preset=panel_preset)
    qmm_only_outputs_mode = panel_preset == "quant_map_mm_panel"
    # T1
    t1_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_t1_dir, '*eroded*t1*nii.gz')),
        key=os.path.basename
    )
    if t1_eroded_files:
        # Compute a robust window from the series (use 2nd/80th percentiles for T1)
        t1_window = volume_rendering.compute_series_window(t1_eroded_files, low_pct=2.0, high_pct=90.0)
        # Refine T1 vmax so broad saturated tissue regions are limited while thin bright vessels can still clip.
        t1_window = volume_rendering.refine_window_vmax_by_saturation_circles(
            t1_eroded_files,
            t1_window,
            radius_mm=1.5,
            bright_threshold=250,
            max_valid_circle_locations=4,
            representative_slices=5,
            max_images_to_check=3,
            vmax_growth_factor=1.10,
            max_iterations=8
        )
        if not qmm_only_outputs_mode:
            # volume_rendering.render_volume_and_save_pngs_pyvista(
            #     t1_eroded_files,
            #     dir_structure.renders_t1_dir
            # )
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                t1_eroded_files,
                dir_structure.renders_t1_dir,
                angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                        [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
                window=t1_window,
                image_size=(1200,1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_renders.py",
                camera_distance='auto'
            )
            # Post-process: crop, L/R annotate, stitch, and export PPTX for T1 overview
            try:
                png_postprocess.run_preset_t1_overview_per_depth(
                    add_orientation_labels=True,
                    background_rgb=[0,0,0],
                    threshold=2,
                    pptx_name="T1_overview"
                )
            except Exception as e:
                print(f"[WARNING] PNG post-processing (T1 overview) skipped: {e}")
        # Optional T1 + overlay rendering (only if at least one overlay was provided)
        if overlay_specs:
            try:
                # T1 overlay overview keeps all active overlays. In quant_map_mm_panel,
                # the T2/FLAIR-specific panels below still use overlay1 only.
                t1_overview_overlay_specs = overlay_specs
                t1_overview_overlay_names = overlay_names
                export_overlay_dicom = bool(getattr(commandline.args, "export_overlay_dicom", False))
                dicom_metadata = {}
                if export_overlay_dicom:
                    dicom_metadata = input_validation.extract_dicom_metadata(
                        commandline.args.dicom_metadata_source
                    )
                    dicom_patient_id_override = getattr(commandline.args, "dicom_patient_id", None)
                    if dicom_patient_id_override:
                        dicom_metadata["patient_id"] = dicom_patient_id_override
                overlay_label = " + ".join(t1_overview_overlay_names)
                overlay_colorbar_spec = t1_overview_overlay_specs
                overlay_angles = [[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                                  [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']]
                overlay_render_batch_size = 5
                overlay_batches = list(_iter_chunks(t1_eroded_files, overlay_render_batch_size))
                for batch_idx, t1_eroded_batch in enumerate(overlay_batches, start=1):
                    print(
                        f"[INFO] Rendering T1 overlay batch {batch_idx}/{len(overlay_batches)} "
                        f"({len(t1_eroded_batch)} erosion level(s))."
                    )
                    volume_rendering.render_volume_and_save_pngs_mricrogl(
                        t1_eroded_batch,
                        dir_structure.renders_t1_overlay_dir,
                        angles=overlay_angles,
                        window=t1_window,
                        image_size=(1200,1200),
                        mricrogl_path=mricrogl_exec,
                        template_filename="mricrogl_T1_renders.py",
                        camera_distance='auto',
                        overlays=t1_overview_overlay_specs
                    )
                png_postprocess.run_preset_t1_overview_per_depth(
                    add_orientation_labels=True,
                    background_rgb=[0,0,0],
                    threshold=2,
                    pptx_name="T1_overlay_overview",
                    render_root_dir=dir_structure.renders_t1_overlay_dir,
                    modality_label="T1 + " + overlay_label,
                    export_dicom=export_overlay_dicom,
                    dicom_basename="T1_overlay_overview",
                    dicom_series_description="T1 erosion render + " + overlay_label + " overlay",
                    dicom_patient_id=dicom_metadata.get("patient_id"),
                    dicom_patient_name=dicom_metadata.get("patient_name"),
                    dicom_study_date=dicom_metadata.get("study_date"),
                    dicom_study_time=dicom_metadata.get("study_time"),
                    dicom_study_instance_uid=dicom_metadata.get("study_instance_uid"),
                    overlay_colorbar_spec=overlay_colorbar_spec
                )
            except Exception as e:
                print(f"[WARNING] T1 overlay rendering/post-processing skipped: {e}")
    # T2 Sagittal
    t2_sag_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_t2_sag_dir, '*eroded*t2_sag*nii.gz')),
        key=os.path.basename
    )
    if (not qmm_only_outputs_mode) and t2_sag_eroded_files:
        t2_sag_window = volume_rendering.compute_series_window(t2_sag_eroded_files, low_pct=0.3, high_pct=99.75)
        # Split into left/right/generic lists by filename tag
        t2_sag_left_files = [p for p in t2_sag_eroded_files if 't2_sag_left' in os.path.basename(p).lower()]
        t2_sag_right_files = [p for p in t2_sag_eroded_files if 't2_sag_right' in os.path.basename(p).lower()]
        t2_sag_generic_files = [p for p in t2_sag_eroded_files if ('t2_sag_left' not in os.path.basename(p).lower() and 't2_sag_right' not in os.path.basename(p).lower())]

        # Define angle subsets
        left_angles = [[90,0,'left'], [270,180,'surg_left_lat'], [300,175,'surg_left_ato']]
        right_angles = [[270,0,'right'], [90,180,'surg_right_lat'], [60,175,'surg_right_ato']]

        # Choose file lists per subset with sensible fallbacks
        files_for_left = t2_sag_left_files or t2_sag_generic_files or t2_sag_right_files
        files_for_right = t2_sag_right_files or t2_sag_generic_files or t2_sag_left_files

        # Render left subset if any files available
        if files_for_left:
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                files_for_left,
                os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
                angles=left_angles,
                window=t2_sag_window,
                image_size=(1200,1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_renders.py",
                camera_distance='auto'
            )
        # Render right subset if any files available
        if files_for_right:
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                files_for_right,
                os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
                angles=right_angles,
                window=t2_sag_window,
                image_size=(1200,1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_renders.py",
                camera_distance='auto'
            )
    # T2 Coronal
    t2_cor_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_t2_cor_dir, '*eroded*t2_cor*nii.gz')),
        key=os.path.basename
    )
    if (not qmm_only_outputs_mode) and t2_cor_eroded_files:
        t2_cor_window = volume_rendering.compute_series_window(t2_cor_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_cor_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_cor_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_cor_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_renders.py",
            camera_distance='auto'
        )
    # T2 Transverse
    t2_tra_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_t2_tra_dir, '*eroded*t2_tra*nii.gz')),
        key=os.path.basename
    )
    if (not qmm_only_outputs_mode) and t2_tra_eroded_files:
        t2_tra_window = volume_rendering.compute_series_window(t2_tra_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_tra_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_tra_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_tra_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_renders.py",
            camera_distance='auto'
        )
    # T2 3D
    t2_3d_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_t2_3d_dir, '*eroded*t2_3d*nii.gz')),
        key=os.path.basename
    )
    if (not qmm_only_outputs_mode) and t2_3d_eroded_files:
        t2_3d_window = volume_rendering.compute_series_window(t2_3d_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_3d_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_3d_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_3d_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_renders.py",
            camera_distance='auto'
        )
    # FLAIR
    flair_eroded_files = sorted(
        glob.glob(os.path.join(dir_structure.eroded_nifti_flair_dir, '*eroded*flair*nii.gz')),
        key=os.path.basename
    )
    if (not qmm_only_outputs_mode) and flair_eroded_files:
        flair_window = volume_rendering.compute_series_window(flair_eroded_files, low_pct=7.5, high_pct=99.99)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     flair_eroded_files,
        #     os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            flair_eroded_files,
            os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=flair_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_renders.py",
            camera_distance='auto'
        )

    # --- Advanced preset: quant_map_mm_panel (keeps normal outputs as well) ---
    if panel_preset == "quant_map_mm_panel":
        try:
            if len(overlay_specs) < 2:
                raise ValueError("quant_map_mm_panel requires two overlays (--overlay1-path and --overlay2-path).")
            if not flair_eroded_files:
                raise ValueError("quant_map_mm_panel requires FLAIR inputs and eroded FLAIR outputs.")
            # Preset-specific overlay behavior:
            # - T1 panels keep all active overlays in CLI order.
            # - Non-T1 panels (FLAIR/T2) use only the first overlay.
            qmm_t1_overlays = overlay_specs
            qmm_non_t1_overlays = overlay_specs[:1]

            main_depth_int = int(getattr(commandline.args, "qmm_main_erode_depth", 30))
            main_prefix = f"{main_depth_int:03d}"

            t1_subset = _select_qmm_eroded_subset(t1_eroded_files, main_depth_int)
            flair_subset = _select_qmm_eroded_subset(flair_eroded_files, main_depth_int)
            t2_sag_subset = _select_qmm_eroded_subset(t2_sag_eroded_files, main_depth_int)
            t2_cor_subset = _select_qmm_eroded_subset(t2_cor_eroded_files, main_depth_int)
            t2_tra_subset = _select_qmm_eroded_subset(t2_tra_eroded_files, main_depth_int)
            t2_3d_subset = _select_qmm_eroded_subset(t2_3d_eroded_files, main_depth_int)

            if not t1_subset:
                raise ValueError("quant_map_mm_panel: no matching T1 eroded subset found around requested main depth.")
            if not flair_subset:
                raise ValueError("quant_map_mm_panel: no matching FLAIR eroded subset found around requested main depth.")

            print(
                f"[INFO] Running quant_map_mm_panel preset with main erosion depth {main_depth_int} "
                f"(prefix {main_prefix})."
            )

            # Render raw slices/snapshots for required modality buckets.
            t1_win = volume_rendering.compute_series_window(t1_subset, low_pct=2.0, high_pct=90.0)
            t1_win = volume_rendering.refine_window_vmax_by_saturation_circles(
                t1_subset,
                t1_win,
                radius_mm=1.5,
                bright_threshold=250,
                max_valid_circle_locations=4,
                representative_slices=5,
                max_images_to_check=3,
                vmax_growth_factor=1.10,
                max_iterations=8
            )
            flair_win = volume_rendering.compute_series_window(flair_subset, low_pct=7.5, high_pct=99.99)
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                t1_subset,
                os.path.join(dir_structure.renders_qmm_raw_dir, "T1"),
                overlays=qmm_t1_overlays,
                window=t1_win,
                main_erode_prefix=main_prefix,
                mricrogl_path=mricrogl_exec
            )
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                flair_subset,
                os.path.join(dir_structure.renders_qmm_raw_dir, "FLAIR"),
                overlays=qmm_non_t1_overlays,
                window=flair_win,
                main_erode_prefix=main_prefix,
                mricrogl_path=mricrogl_exec
            )

            # Optional T2 sources; we render any available source used by angle mapping.
            if t2_sag_subset:
                t2_sag_win = volume_rendering.compute_series_window(t2_sag_subset, low_pct=0.3, high_pct=99.75)
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    t2_sag_subset,
                    os.path.join(dir_structure.renders_qmm_raw_dir, "T2_sag"),
                    overlays=qmm_non_t1_overlays,
                    window=t2_sag_win,
                    main_erode_prefix=main_prefix,
                    mricrogl_path=mricrogl_exec
                )
            if t2_cor_subset:
                t2_cor_win = volume_rendering.compute_series_window(t2_cor_subset, low_pct=0.3, high_pct=99.75)
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    t2_cor_subset,
                    os.path.join(dir_structure.renders_qmm_raw_dir, "T2_cor"),
                    overlays=qmm_non_t1_overlays,
                    window=t2_cor_win,
                    main_erode_prefix=main_prefix,
                    mricrogl_path=mricrogl_exec
                )
            if t2_tra_subset:
                t2_tra_win = volume_rendering.compute_series_window(t2_tra_subset, low_pct=0.3, high_pct=99.75)
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    t2_tra_subset,
                    os.path.join(dir_structure.renders_qmm_raw_dir, "T2_tra"),
                    overlays=qmm_non_t1_overlays,
                    window=t2_tra_win,
                    main_erode_prefix=main_prefix,
                    mricrogl_path=mricrogl_exec
                )
            if t2_3d_subset:
                t2_3d_win = volume_rendering.compute_series_window(t2_3d_subset, low_pct=0.3, high_pct=99.75)
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    t2_3d_subset,
                    os.path.join(dir_structure.renders_qmm_raw_dir, "T2_3d"),
                    overlays=qmm_non_t1_overlays,
                    window=t2_3d_win,
                    main_erode_prefix=main_prefix,
                    mricrogl_path=mricrogl_exec
                )

            # Angle-specific T2 source selection (prefer 2D in-plane acquisitions).
            requested_qmm_angles = getattr(commandline.args, "qmm_angles", None) or [
                "left", "right", "anterior", "posterior", "superior", "inferior"
            ]
            angle_to_t2_source = {}
            if t2_sag_subset:
                angle_to_t2_source["left"] = "T2_sag"
                angle_to_t2_source["right"] = "T2_sag"
            if t2_cor_subset:
                angle_to_t2_source["anterior"] = "T2_cor"
                angle_to_t2_source["posterior"] = "T2_cor"
            if t2_tra_subset:
                angle_to_t2_source["superior"] = "T2_tra"
                angle_to_t2_source["inferior"] = "T2_tra"
            # Fallback to 3D T2 for any unresolved angle.
            for ang in requested_qmm_angles:
                if ang not in angle_to_t2_source and t2_3d_subset:
                    angle_to_t2_source[ang] = "T2_3d"
            # If left/right still have no sagittal or 3D T2 source, use transverse T2.
            for ang in ("left", "right"):
                if ang in requested_qmm_angles and ang not in angle_to_t2_source and t2_tra_subset:
                    angle_to_t2_source[ang] = "T2_tra"

            png_postprocess.run_preset_quant_map_mm_panel(
                raw_root=dir_structure.renders_qmm_raw_dir,
                angle_to_t2_source=angle_to_t2_source,
                qmm_angles=requested_qmm_angles,
                overlay_names=overlay_names,
                add_orientation_labels=True,
                background_rgb=[0, 0, 0],
                threshold=2,
                pptx_name="quant_map_mm_panel_overview"
            )
        except Exception as e:
            print(f"[WARNING] quant_map_mm_panel preset skipped: {e}")

    # --- Multimodal presets only when at least one non-T1 modality was provided ---
    has_additional_modalities = any([
        bool(commandline.args.flair),
        bool(commandline.args.t2_sag),
        bool(getattr(commandline.args, 't2_sag_left', None)),
        bool(getattr(commandline.args, 't2_sag_right', None)),
        bool(commandline.args.t2_cor),
        bool(commandline.args.t2_tra),
        bool(commandline.args.t2_3d),
    ])

    # --- Multimodal by-angle preset (one combined PPTX) ---
    if (not qmm_only_outputs_mode) and has_additional_modalities:
        try:
            png_postprocess.run_preset_multimodal_by_angle_per_depth(
                angles=['superior','inferior','left','right','anterior','posterior'],
                add_orientation_labels=True,
                background_rgb=[0,0,0],
                threshold=2,
                pptx_name="Multimodal_overview"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (multimodal by angle) skipped: {e}")
    elif not qmm_only_outputs_mode:
        print("[INFO] Skipping multimodal overview preset: no FLAIR/T2 inputs were provided.")

    # --- T2-only overview (two-row if complete, else single-row) ---
    if not qmm_only_outputs_mode:
        try:
            png_postprocess.run_preset_t2_overview_per_depth(
                add_orientation_labels=True,
                background_rgb=[0,0,0],
                threshold=2,
                pptx_name="T2_overview"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (T2 overview) skipped: {e}")

    # --- Multimodal surgical angles ---
    if (not qmm_only_outputs_mode) and has_additional_modalities:
        try:
            png_postprocess.run_preset_multimodal_other_angles_per_depth(
                angles=['surg_left_lat','surg_right_lat','surg_left_ato','surg_right_ato'],
                add_orientation_labels=True,
                background_rgb=[0,0,0],
                threshold=2,
                pptx_name="multimodal_overview_other_angles"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (multimodal other angles) skipped: {e}")
    elif not qmm_only_outputs_mode:
        print("[INFO] Skipping multimodal surgical preset: no FLAIR/T2 inputs were provided.")

    return 0

if __name__ == "__main__":
    sys.exit(main())

