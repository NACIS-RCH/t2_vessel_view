import argparse
import os

parser = argparse.ArgumentParser(description='A tool for generating Vessel Maps using T2-weighted MRI', 
            epilog='Version 1, Bonnie Alexander 2023')

parser.add_argument('-d', 
            metavar='mri_directory', 
            type=str, 
            action='store', 
            help='The path to the directory where the input MRI images are', 
            required=False, 
            dest='mri_dir')

parser.add_argument('-o', 
            metavar='output directory', 
            type=str, 
            action='store', 
            help='Optional. The directory to save the Vessel Map outputs to. Otherwise it will be saved to the MRI directory.', 
            dest='output_dir')
            
parser.add_argument('-i', 
            metavar='Main image T1 or similar', 
            type=str, 
            action='store', 
            help='Required T1 or similar main image that other images will be registered to.',
            required=False,
            dest='t1')

parser.add_argument('-f', 
            metavar='flair', 
            type=str, 
            action='store', 
            help='Optional 3D FLAIR or similar bright 3D image such as Mag.This will usually substantially help with segmentation of the brain parenchyma (FLAIR) and intracranial structures including venous sinuses (Mag). Also needed if you want to run the flair watershed segmentation option.',
            dest='flair')

parser.add_argument('-c', 
            metavar='t2_coronal', 
            type=str, 
            action='store', 
            help='2D coronal T2-weighted MRI image',
            dest='t2_cor')

parser.add_argument('-s', 
            metavar='t2_sagittal', 
            type=str, 
            action='store', 
            help='2D sagittal T2-weighted MRI image. Can include single hemisphere acquisitions.',
            dest='t2_sag')

# Optional separate sagittal acquisitions per hemisphere (advanced use)
parser.add_argument('--t2_sag_left', 
            metavar='t2_sagittal_left', 
            type=str, 
            action='store', 
            help='Left-hemisphere sagittal T2 (unilateral acquisition). If provided with --t2_sag_right, both will be processed.',
            dest='t2_sag_left')

parser.add_argument('--t2_sag_right', 
            metavar='t2_sagittal_right', 
            type=str, 
            action='store', 
            help='Right-hemisphere sagittal T2 (unilateral acquisition). If provided with --t2_sag_left, both will be processed.',
            dest='t2_sag_right')

parser.add_argument('-t', 
            metavar='t2_transverse', 
            type=str, 
            action='store', 
            help='2D transverse T2-weighted MRI image.',
            dest='t2_tra')
            
parser.add_argument('-p', 
            metavar='t2_3d', 
            type=str, 
            action='store', 
            help='3D T2-weighted MRI image such as t2 space.',
            dest='t2_3d')

parser.add_argument('-m', 
            metavar='user_mask', 
            type=str, 
            action='store', 
            help='User-provided brain mask to use if automatically generated mask is suboptimal.',
            dest='user_mask')

parser.add_argument('-n', 
            metavar='user_mask_structural', 
            type=str, 
            action='store', 
            help='Structural image that the user-provided mask was based on - i.e., has the same image dimensions as the mask. Needed for registration of mask to other images.',
            dest='user_mask_structural')

parser.add_argument('--use-hull-mask',
            action='store_true',
            help='Use convex hull mask to include sagittal sinus (may affect cortical surface morphology)',
            dest='use_hull_mask')

parser.add_argument('--auto-mask-method',
            metavar='auto_mask_method',
            type=str,
            choices=['bet', 'watershed'],
            action='store',
            help='Automatic mask method: "bet" (default) or "watershed" (FLAIR-based scalping).',
            default='bet',
            dest='auto_mask_method')

# Optional MRIcroGL overlays (registered to T1; rendered directly in MRIcroGL)
parser.add_argument('--overlay1-path',
            metavar='overlay1_path',
            type=str,
            action='store',
            help='Optional path to first overlay image registered to T1 (e.g., PET_to_T1). If omitted, overlay rendering is skipped.',
            dest='overlay1_path')

parser.add_argument('--overlay1-color',
            metavar='overlay1_color',
            type=str,
            action='store',
            help=(
                'Colour map for first overlay (used for both MRIcroGL and colorbar). '
                'Accepts exact CLUT names (e.g. 2green, 1red, jet, electric_blue, viridis) '
                'or unprefixed aliases for numbered maps (e.g. green, red, blue, hot). '
                'Default: jet.'
            ),
            dest='overlay1_color')

parser.add_argument('--overlay1-name',
            metavar='overlay1_name',
            type=str,
            action='store',
            help='Optional short label for first overlay used in stitched PNG text (for example: PET). Use no spaces.',
            default='Overlay1',
            dest='overlay1_name')

parser.add_argument('--overlay1-min',
            metavar='overlay1_min',
            type=float,
            action='store',
            help='Optional minimum window value for first overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay1_min')

parser.add_argument('--overlay1-max',
            metavar='overlay1_max',
            type=float,
            action='store',
            help='Optional maximum window value for first overlay. Strongly recommended to set explicitl.',
            dest='overlay1_max')

parser.add_argument('--overlay1-opacity',
            metavar='overlay1_opacity',
            type=int,
            action='store',
            help='Opacity for first overlay layer (0-100). If omitted, defaults to 35.',
            dest='overlay1_opacity')

parser.add_argument('--overlay2-path',
            metavar='overlay2_path',
            type=str,
            action='store',
            help='Optional path to second overlay image registered to T1.',
            dest='overlay2_path')

parser.add_argument('--overlay2-color',
            metavar='overlay2_color',
            type=str,
            action='store',
            help=(
                'Colour map for second overlay (MRIcroGL + colorbar). Same accepted names as '
                '--overlay1-color. Default: red/1red (or electric_blue for quant_map_mm_panel).'
            ),
            dest='overlay2_color')

parser.add_argument('--overlay2-name',
            metavar='overlay2_name',
            type=str,
            action='store',
            help='Optional short label for second overlay used in stitched PNG text (for example: CBF). Use no spaces.',
            default='Overlay2',
            dest='overlay2_name')

parser.add_argument('--overlay2-min',
            metavar='overlay2_min',
            type=float,
            action='store',
            help='Optional minimum window value for second overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay2_min')

parser.add_argument('--overlay2-max',
            metavar='overlay2_max',
            type=float,
            action='store',
            help='Optional maximum window value for second overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay2_max')

parser.add_argument('--overlay2-opacity',
            metavar='overlay2_opacity',
            type=int,
            action='store',
            help='Opacity for second overlay layer (0-100). If omitted, defaults to 35 (or 100 for quant_map_mm_panel preset).',
            dest='overlay2_opacity')

parser.add_argument('--overlay3-path',
            metavar='overlay3_path',
            type=str,
            action='store',
            help='Optional path to third overlay image registered to T1.',
            dest='overlay3_path')

parser.add_argument('--overlay3-color',
            metavar='overlay3_color',
            type=str,
            action='store',
            help=(
                'Colour map for third overlay (MRIcroGL + colorbar). Same accepted names as '
                '--overlay1-color. Default: hot/4hot.'
            ),
            dest='overlay3_color')

parser.add_argument('--overlay3-name',
            metavar='overlay3_name',
            type=str,
            action='store',
            help='Optional short label for third overlay used in stitched PNG text. Use no spaces.',
            default='Overlay3',
            dest='overlay3_name')

parser.add_argument('--overlay3-min',
            metavar='overlay3_min',
            type=float,
            action='store',
            help='Optional minimum window value for third overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay3_min')

parser.add_argument('--overlay3-max',
            metavar='overlay3_max',
            type=float,
            action='store',
            help='Optional maximum window value for third overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay3_max')

parser.add_argument('--overlay3-opacity',
            metavar='overlay3_opacity',
            type=int,
            action='store',
            help='Opacity for third overlay layer (0-100). If omitted, defaults to 35.',
            dest='overlay3_opacity')

parser.add_argument('--overlay4-path',
            metavar='overlay4_path',
            type=str,
            action='store',
            help='Optional path to fourth overlay image registered to T1.',
            dest='overlay4_path')

parser.add_argument('--overlay4-color',
            metavar='overlay4_color',
            type=str,
            action='store',
            help=(
                'Colour map for fourth overlay (MRIcroGL + colorbar). Same accepted names as '
                '--overlay1-color. Default: blue/3blue.'
            ),
            dest='overlay4_color')

parser.add_argument('--overlay4-name',
            metavar='overlay4_name',
            type=str,
            action='store',
            help='Optional short label for fourth overlay used in stitched PNG text. Use no spaces.',
            default='Overlay4',
            dest='overlay4_name')

parser.add_argument('--overlay4-min',
            metavar='overlay4_min',
            type=float,
            action='store',
            help='Optional minimum window value for fourth overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay4_min')

parser.add_argument('--overlay4-max',
            metavar='overlay4_max',
            type=float,
            action='store',
            help='Optional maximum window value for fourth overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay4_max')

parser.add_argument('--overlay4-opacity',
            metavar='overlay4_opacity',
            type=int,
            action='store',
            help='Opacity for fourth overlay layer (0-100). If omitted, defaults to 35.',
            dest='overlay4_opacity')

parser.add_argument('--panels',
            metavar='panel',
            type=str,
            nargs='*',
            choices=[
                't1_overview',
                't1_overlay_overview',
                't2_overview',
                'multimodal_overview',
                'multimodal_overview_other_angles',
                'quant_map_mm_panel',
                'custom_overlay_trio',
                'standard',
                'all',
            ],
            default=[],
            action='store',
            help=(
                'Display panels to generate after erosion (default: none). '
                'IDs: t1_overview, t1_overlay_overview, t2_overview, multimodal_overview, '
                'multimodal_overview_other_angles, quant_map_mm_panel, custom_overlay_trio. '
                'Aliases: standard (structural T1/T2/multimodal), all (excludes custom_overlay_trio). '
                'custom_overlay_trio requires --panel-config. '
                'Omit --panels on the main command for preprocess/erode only; '
                'use t2vv_render_existing --panels ... to generate displays later.'
            ),
            dest='panels')

parser.add_argument('--panel-config',
            metavar='panel_config',
            type=str,
            action='store',
            help=(
                'YAML config for --panels custom_overlay_trio '
                '(angles, slots with base + per-slot overlays). '
                'See examples/custom_overlay_trio.yaml.'
            ),
            dest='panel_config')

parser.add_argument('--write-panel-config-example',
            metavar='output_yaml',
            type=str,
            action='store',
            help=(
                'Write a starter custom_overlay_trio YAML to this path and exit. '
                'Does not require -d/-i.'
            ),
            dest='write_panel_config_example')

parser.add_argument('--panel-preset',
            metavar='panel_preset',
            type=str,
            choices=['quant_map_mm_panel'],
            action='store',
            help=(
                'Deprecated. Prefer --panels quant_map_mm_panel. '
                'Still accepted as an alias that requests the quant_map_mm_panel output.'
            ),
            dest='panel_preset')

parser.add_argument('--qmm-main-erode-depth',
            metavar='qmm_main_erode_depth',
            type=int,
            action='store',
            help='Main erosion depth for quant_map_mm_panel slices (integer, e.g., 30 for prefix 030). Default: 30.',
            default=30,
            dest='qmm_main_erode_depth')

parser.add_argument('--qmm-angles',
            metavar='qmm_angles',
            type=str,
            nargs='+',
            choices=['left', 'right', 'anterior', 'posterior', 'superior', 'inferior'],
            action='store',
            help='Optional list of angles for quant_map_mm_panel. If omitted, all six are used.',
            dest='qmm_angles')

parser.add_argument('--keep-debug-images',
            action='store_true',
            help=(
                'Keep preprocess (and other) intermediate/debug NIfTI files on disk. '
                'By default those step files are removed after finals are written, '
                'and pure debug writes via write_debug_image are skipped.'
            ),
            dest='keep_debug_images')

parser.add_argument('--export-overlay-dicom',
            action='store_true',
            help='Also export the T1 overlay overview stitched PNG panels as a local DICOM Secondary Capture folder. Requires at least one overlay path.',
            dest='export_overlay_dicom')

parser.add_argument('--render-existing-erosions',
            action='store_true',
            help='Skip preprocessing/masking and render from existing eroded NIfTI files in --render-source-dir.',
            dest='render_existing_erosions')

parser.add_argument('--render-source-dir',
            metavar='render_source_dir',
            type=str,
            action='store',
            help='Existing T2VesselView output folder to use for render-only mode; outputs are written back into this folder.',
            dest='render_source_dir')

parser.add_argument('--dicom-patient-id',
            metavar='dicom_patient_id',
            type=str,
            action='store',
            help='Optional PatientID override for generated DICOM Secondary Capture files. If omitted, PatientID is copied from --dicom-metadata-source.',
            dest='dicom_patient_id')

parser.add_argument('--dicom-metadata-source',
            metavar='dicom_metadata_source',
            type=str,
            action='store',
            help='DICOM file or folder to copy PatientName, PatientID, and StudyDate from for generated overlay DICOM output.',
            dest='dicom_metadata_source')

#parser.add_argument('-e', type=str, action='store', nargs=argparse.REMAINDER, help='One or more extra images. This has to be the last option specified, i.e., cant put the output directory after this.', required=True, dest='files')

## add flags for save masks or not

# Parsed CLI namespace; set by parse_and_validate(). Remains None until then so
# importing this module never requires argv or triggers circular path setup.
args = None


def parse_and_validate(argv=None):
    """Parse CLI arguments, validate them, and store on ``commandline.args``.

    Must be called explicitly from the main entrypoint (not at import time) so
    other modules can import ``commandline`` safely before paths are configured.

    Parameters
    ----------
    argv :
        Optional argument list (defaults to ``sys.argv[1:]`` via argparse).

    Returns
    -------
    argparse.Namespace
        The validated args object (also available as ``commandline.args``).
    """
    global args
    args = parser.parse_args(argv)

    # Early exit: write starter YAML without requiring -d/-i or other pipeline args.
    if getattr(args, "write_panel_config_example", None):
        import sys
        from . import panel_config as _panel_config
        out_path = _panel_config.write_example_config(args.write_panel_config_example)
        print(f"[INFO] Wrote example panel config: {out_path}")
        print(
            "[INFO] Edit overlay paths, then run with "
            "--panels custom_overlay_trio --panel-config <that file>."
        )
        sys.exit(0)

    if not args.mri_dir:
        parser.error('the following arguments are required: -d')
    if not args.t1:
        parser.error('the following arguments are required: -i')

    if args.user_mask and not args.user_mask_structural:
        parser.error('-m/--user_mask requires -n/--user_mask_structural.')

    # Basic CLI validation for overlay parameters
    for overlay_idx in range(1, 5):
        path_val = getattr(args, f'overlay{overlay_idx}_path', None)
        name_val = getattr(args, f'overlay{overlay_idx}_name', f'Overlay{overlay_idx}')
        min_val = getattr(args, f'overlay{overlay_idx}_min', None)
        max_val = getattr(args, f'overlay{overlay_idx}_max', None)
        opacity_val = getattr(args, f'overlay{overlay_idx}_opacity', 35)

        if opacity_val is not None and not (0 <= int(opacity_val) <= 100):
            parser.error(f'--overlay{overlay_idx}-opacity must be between 0 and 100.')

        # If user provided one bound, require both so intent is explicit.
        if path_val and ((min_val is None) ^ (max_val is None)):
            parser.error(
                f'--overlay{overlay_idx}-min and --overlay{overlay_idx}-max must be provided together, '
                f'or both omitted for automatic estimation.'
            )

        if path_val and min_val is not None and max_val is not None and float(max_val) <= float(min_val):
            parser.error(f'--overlay{overlay_idx}-max must be greater than --overlay{overlay_idx}-min.')

        if path_val and name_val and any(ch.isspace() for ch in str(name_val)):
            parser.error(f'--overlay{overlay_idx}-name please specify a name without spaces.')

    # Resolve requested display panels (aliases + deprecated --panel-preset).
    # Import here so argparse setup above stays free of package-side effects.
    from . import panel_registry as _panel_registry

    try:
        _resolved_panels = _panel_registry.resolve_requested_panels(
            getattr(args, "panels", None),
            panel_preset=getattr(args, "panel_preset", None),
        )
    except ValueError as e:
        parser.error(str(e))

    args.resolved_panels = _resolved_panels

    if getattr(args, "panel_preset", None) == "quant_map_mm_panel":
        print(
            "[WARNING] --panel-preset is deprecated; prefer "
            "'--panels quant_map_mm_panel'."
        )

    # Validation for quant_map_mm_panel when that panel was requested
    if "quant_map_mm_panel" in args.resolved_panels:
        if not args.flair:
            parser.error('--panels quant_map_mm_panel requires a FLAIR input via -f.')
        if not args.overlay1_path or not args.overlay2_path:
            parser.error(
                '--panels quant_map_mm_panel requires both --overlay1-path and --overlay2-path.'
            )
        has_any_t2 = any([
            bool(args.t2_3d),
            bool(args.t2_sag),
            bool(args.t2_sag_left),
            bool(args.t2_sag_right),
            bool(args.t2_cor),
            bool(args.t2_tra),
        ])
        if not has_any_t2:
            parser.error(
                '--panels quant_map_mm_panel requires at least one T2 input '
                '(3D T2 or one/more T2 planes).'
            )
        if int(args.qmm_main_erode_depth) < 0:
            parser.error('--qmm-main-erode-depth must be >= 0.')
        if args.qmm_angles:
            # Preserve user order while removing accidental duplicates.
            args.qmm_angles = list(dict.fromkeys(args.qmm_angles))

    if "t1_overlay_overview" in args.resolved_panels:
        if not any(getattr(args, f'overlay{idx}_path', None) for idx in range(1, 5)):
            parser.error(
                '--panels t1_overlay_overview requires at least one overlay path '
                '(--overlay1-path through --overlay4-path).'
            )

    if "custom_overlay_trio" in args.resolved_panels:
        if not getattr(args, "panel_config", None):
            parser.error(
                '--panels custom_overlay_trio requires --panel-config PATH.yaml '
                '(see examples/custom_overlay_trio.yaml or --write-panel-config-example).'
            )
        if not os.path.isfile(args.panel_config):
            parser.error(f'--panel-config not found: {args.panel_config}')

    if args.export_overlay_dicom and "t1_overlay_overview" not in args.resolved_panels:
        parser.error(
            '--export-overlay-dicom requires --panels t1_overlay_overview '
            '(and at least one overlay path).'
        )

    if args.export_overlay_dicom and not any(getattr(args, f'overlay{idx}_path', None) for idx in range(1, 5)):
        parser.error('--export-overlay-dicom requires at least one overlay path (--overlay1-path through --overlay4-path).')

    if args.export_overlay_dicom:
        if not args.dicom_metadata_source:
            parser.error('--export-overlay-dicom requires --dicom-metadata-source, please provide a DICOM file or folder.')
        if not os.path.exists(args.dicom_metadata_source):
            parser.error(f'--dicom-metadata-source not found: {args.dicom_metadata_source}')

    if args.render_existing_erosions:
        if not args.render_source_dir:
            parser.error('--render-existing-erosions requires --render-source-dir.')
        if not os.path.isdir(args.render_source_dir):
            parser.error(f'--render-source-dir not found or is not a folder: {args.render_source_dir}')
        if not args.resolved_panels:
            parser.error(
                'Render-existing mode requires --panels (for example: '
                '--panels standard  or  --panels t1_overlay_overview).'
            )

    return args

