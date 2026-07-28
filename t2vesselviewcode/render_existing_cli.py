"""Helper CLI for rerendering from an existing T2VesselView output folder.

This script is intentionally a thin wrapper around the main pipeline. It finds
enough existing files to satisfy the normal command-line validation, builds the
real render-only command, prints that command for transparency, and then runs it.
"""

import argparse  # Builds the small user-facing CLI for this helper command.
import glob  # Searches folders using wildcard patterns such as "*.nii.gz".
import os  # Handles file paths and checks whether files/folders exist.
import shlex  # Prints the generated command with shell-safe quoting.
import subprocess  # Runs the generated main pipeline command.
import sys  # Gives access to this Python executable and process exit handling.


def _first_existing(patterns):
    """Return the first existing file matching any pattern."""
    # Try each search pattern in priority order, from most specific to broadest.
    for pattern in patterns:
        # glob expands wildcard patterns into matching filesystem paths.
        matches = sorted(glob.glob(pattern, recursive=True))
        # Walk through matches in stable alphabetical order.
        for match in matches:
            # Only return real files, not directories.
            if os.path.isfile(match):
                # Store absolute paths so the generated command works from any folder.
                return os.path.abspath(match)
    # Return None when no candidate file could be found.
    return None


def _has_any_flag(args, flags):
    """Return True if any option flag is already present in pass-through args."""
    # Pass-through args are the options this helper does not parse itself and
    # forwards to t2_vessel_view, such as --overlay1-path or --panel-preset.
    for arg in args:
        # Handles split form, for example: --panel-preset quant_map_mm_panel.
        if arg in flags:
            return True
        # Handles equals form, for example: --panel-preset=quant_map_mm_panel.
        if any(arg.startswith(f"{flag}=") for flag in flags if flag.startswith("--")):
            return True
    # No matching user-supplied flag was found.
    return False


def _uses_quant_map_panel(args):
    """Return True if pass-through args request the quant_map_mm_panel output."""
    # Check each argument and its index so we can read the following value when needed.
    for idx, arg in enumerate(args):
        # Handles split form: --panel-preset quant_map_mm_panel.
        if arg == "--panel-preset" and idx + 1 < len(args):
            return args[idx + 1] == "quant_map_mm_panel"
        # Handles equals form: --panel-preset=quant_map_mm_panel.
        if arg.startswith("--panel-preset="):
            return arg.split("=", 1)[1] == "quant_map_mm_panel"
        # Handles --panels ... quant_map_mm_panel (or --panels=quant_map_mm_panel).
        if arg == "--panels":
            # Collect following tokens until the next flag.
            j = idx + 1
            while j < len(args) and not str(args[j]).startswith("-"):
                if args[j] in ("quant_map_mm_panel", "all"):
                    return True
                j += 1
        if arg.startswith("--panels="):
            values = arg.split("=", 1)[1].split()
            if "quant_map_mm_panel" in values or "all" in values:
                return True
    # If no panel request matches, this is not quant-map-panel mode.
    return False


def _has_panels_flag(args):
    """Return True if pass-through args include --panels with at least one value."""
    for idx, arg in enumerate(args):
        if arg == "--panels":
            # At least one non-flag value must follow.
            if idx + 1 < len(args) and not str(args[idx + 1]).startswith("-"):
                return True
        if arg.startswith("--panels=") and arg.split("=", 1)[1].strip():
            return True
        # Deprecated alias still counts as requesting a panel.
        if arg == "--panel-preset" and idx + 1 < len(args):
            return True
        if arg.startswith("--panel-preset="):
            return True
    return False

def _discover_inputs(source_dir):
    """Find validation filler images from an existing T2VesselView output folder."""
    # Existing preprocessed files live under the prior run's Processing folder.
    processing_dir = os.path.join(source_dir, "Processing")
    # Existing renderable eroded files live under the prior run's Eroded_nifti folder.
    eroded_dir = os.path.join(source_dir, "Eroded_nifti")
    # These files are only used to satisfy the main CLI's required inputs in
    # render-only mode; the actual rendering reads from Eroded_nifti.
    return {
        # Prefer the final preprocessed T1, fall back to any main-looking T1,
        # then fall back to an eroded T1 if that is all the folder contains.
        "t1": _first_existing([
            os.path.join(processing_dir, "Preprocessed_T1", "Preprocessed_main_image.nii.gz"),
            os.path.join(processing_dir, "Preprocessed_T1", "*main*.nii*"),
            os.path.join(eroded_dir, "T1", "*eroded*t1*nii*"),
        ]),
        # FLAIR is needed as a validation filler for quant_map_mm_panel.
        "flair": _first_existing([
            os.path.join(processing_dir, "Preprocessed_FLAIR", "Preprocessed_flair.nii.gz"),
            os.path.join(processing_dir, "**", "Preprocessed_flair*.nii*"),
            os.path.join(eroded_dir, "FLAIR", "*eroded*flair*nii*"),
        ]),
        # Sagittal T2 is preferred for quant panel left/right views.
        "t2_sag": _first_existing([
            os.path.join(processing_dir, "Preprocessed_T2_Sag", "Preprocessed_t2_sag.nii.gz"),
            os.path.join(processing_dir, "**", "Preprocessed_t2_sag*.nii*"),
            os.path.join(eroded_dir, "T2_Sag", "*eroded*t2_sag*nii*"),
        ]),
        # Coronal T2 can support anterior/posterior quant panel views.
        "t2_cor": _first_existing([
            os.path.join(processing_dir, "Preprocessed_T2_Cor", "Preprocessed_t2_cor.nii.gz"),
            os.path.join(processing_dir, "**", "Preprocessed_t2_cor*.nii*"),
            os.path.join(eroded_dir, "T2_Cor", "*eroded*t2_cor*nii*"),
        ]),
        # Transverse T2 can support superior/inferior quant panel views.
        "t2_tra": _first_existing([
            os.path.join(processing_dir, "Preprocessed_T2_Tra", "Preprocessed_t2_tra.nii.gz"),
            os.path.join(processing_dir, "**", "Preprocessed_t2_tra*.nii*"),
            os.path.join(eroded_dir, "T2_Tra", "*eroded*t2_tra*nii*"),
        ]),
        # 3D T2 is a useful fallback when plane-specific T2 inputs are not present.
        "t2_3d": _first_existing([
            os.path.join(processing_dir, "Preprocessed_T2_3D", "Preprocessed_t2_3d.nii.gz"),
            os.path.join(processing_dir, "**", "Preprocessed_t2_3d*.nii*"),
            os.path.join(eroded_dir, "T2_3D", "*eroded*t2_3d*nii*"),
        ]),
    }


def _build_command(source_dir, passthrough_args):
    """Build the underlying render-only pipeline command."""
    # Normalize the source folder path so it is unambiguous in the printed command.
    source_dir = os.path.abspath(source_dir)
    # Look inside the source folder for preprocessed or eroded images we can reuse.
    discovered = _discover_inputs(source_dir)
    # The main CLI still requires -i, even though render-only mode will not preprocess it.
    if not discovered["t1"]:
        raise FileNotFoundError(
            "Could not find a T1 filler image in the source folder. Expected "
            "Processing/Preprocessed_T1/Preprocessed_main_image.nii.gz or an eroded T1 file."
        )

    # Build the base command as a list of arguments. Keeping it as a list avoids
    # shell quoting problems when paths contain spaces.
    cmd = [
        # Use the same Python interpreter that launched this helper.
        sys.executable,
        # Run the main pipeline module directly.
        "-m",
        "t2vesselviewcode.t2_vessel_view_main",
        # The main CLI still requires -d; parent of source_dir is the case folder.
        "-d",
        os.path.dirname(source_dir),
        # Fill required -i using the discovered T1-like file.
        "-i",
        discovered["t1"],
        # Tell the main pipeline to skip preprocessing/masking/erosions.
        "--render-existing-erosions",
        # Tell the main pipeline which existing T2VesselView-style folder to use.
        "--render-source-dir",
        source_dir,
    ]

    # Quant panel mode currently requires FLAIR and one T2 argument at CLI level,
    # so the helper auto-adds those if the user did not specify them manually.
    quant_map_panel = _uses_quant_map_panel(passthrough_args)
    # Add -f automatically for quant_map_mm_panel unless the user supplied it.
    if quant_map_panel and not _has_any_flag(passthrough_args, {"-f"}):
        if not discovered["flair"]:
            raise FileNotFoundError(
                "quant_map_mm_panel requires a FLAIR filler image, but none was found in the source folder."
            )
        cmd.extend(["-f", discovered["flair"]])

    # Add one T2 input automatically for quant_map_mm_panel unless the user supplied
    # any T2 option manually.
    if quant_map_panel and not _has_any_flag(
        passthrough_args,
        {"-s", "--t2_sag_left", "--t2_sag_right", "-c", "-t", "-p"}
    ):
        # Prefer sagittal because it is best for left/right views.
        if discovered["t2_sag"]:
            cmd.extend(["-s", discovered["t2_sag"]])
        # Fall back to coronal if no sagittal filler exists.
        elif discovered["t2_cor"]:
            cmd.extend(["-c", discovered["t2_cor"]])
        # Fall back to transverse if no sagittal/coronal filler exists.
        elif discovered["t2_tra"]:
            cmd.extend(["-t", discovered["t2_tra"]])
        # Fall back to 3D T2 if it is the only available T2-like file.
        elif discovered["t2_3d"]:
            cmd.extend(["-p", discovered["t2_3d"]])
        else:
            raise FileNotFoundError(
                "quant_map_mm_panel requires at least one T2 filler image, but none was found in the source folder."
            )

    # Add everything else the user passed to this helper, such as overlays,
    # DICOM export, qmm options, or window min/max values.
    cmd.extend(passthrough_args)
    # Return the list form so subprocess.run can execute it safely without shell=True.
    return cmd


def main(argv=None):
    # Define the small CLI for this helper. All unknown arguments are forwarded
    # to the main t2_vessel_view command.
    parser = argparse.ArgumentParser(
        description=(
            "Rerender T2VesselView display panels from an existing output folder. "
            "Requires --panels (for example: --panels standard)."
        ),
        epilog=(
            "Examples:\n"
            "  t2vv_render_existing --source-dir /out --panels standard\n"
            "  t2vv_render_existing --source-dir /out --panels t1_overlay_overview "
            "--overlay1-path PET.nii.gz --overlay1-color green\n"
            "  t2vv_render_existing --source-dir /out --panels quant_map_mm_panel "
            "--overlay1-path CBF.nii.gz --overlay2-path ATT.nii.gz\n"
            "  t2vv_render_existing --source-dir /out "
            "--panels custom_overlay_trio --panel-config ./custom_panel.yaml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # The user must point to the exact existing output folder to avoid guessing
    # among multiple renamed runs.
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Existing T2VesselView-style folder containing Eroded_nifti and Processing subfolders.",
    )
    # Dry run is useful for checking exactly what will be executed.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated render-only command without running it.",
    )
    # parse_known_args keeps helper-specific flags in args and leaves all other
    # options in passthrough_args for the main pipeline.
    args, passthrough_args = parser.parse_known_args(argv)

    # Fail early if the requested existing output folder is not present.
    if not os.path.isdir(args.source_dir):
        parser.error(f"--source-dir not found or is not a folder: {args.source_dir}")

    if not _has_panels_flag(passthrough_args):
        parser.error(
            "t2vv_render_existing requires --panels "
            "(for example: --panels standard  or  --panels t1_overlay_overview)."
        )

    # Build the real main-pipeline command, converting helper errors into tidy
    # command-line parser errors.
    try:
        cmd = _build_command(args.source_dir, passthrough_args)
    except Exception as e:
        parser.error(str(e))

    print("[INFO] Generated render-only command:")
    # shlex.join turns the argument list into a copy/pasteable shell command.
    # For example, a path with spaces becomes quoted correctly:
    # /path/with spaces/file.nii.gz -> '/path/with spaces/file.nii.gz'
    print(shlex.join(cmd))
    # In dry-run mode, stop after showing the command.
    if args.dry_run:
        print("[INFO] Dry run requested; command was not executed.")
        return 0

    print("[INFO] Running generated command now.")
    # Run the argument list directly. This is safer than shell=True because each
    # list item stays one argument, even if paths contain spaces.
    completed = subprocess.run(cmd)
    # Propagate the main pipeline's success/failure code back to the terminal.
    return int(completed.returncode)


if __name__ == "__main__":
    # Allows this file to be run directly with python render_existing_cli.py.
    sys.exit(main())
