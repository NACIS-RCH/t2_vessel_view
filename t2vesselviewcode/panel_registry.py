"""Panel ID registry for opt-in display / PPTX outputs.

Users select panels with --panels. The main pipeline defaults to no panels
(preprocess/erode only). t2vv_render_existing requires at least one panel.
"""

from typing import Iterable, Optional, Set

# Concrete panel IDs that map 1:1 to existing postprocess presets.
PANEL_IDS = (
    "t1_overview",
    "t1_overlay_overview",
    "t2_overview",
    "multimodal_overview",
    "multimodal_overview_other_angles",
    "quant_map_mm_panel",
    "custom_overlay_trio",
)

# Alias expansions for convenience.
PANEL_ALIASES = {
    "standard": (
        "t1_overview",
        "t2_overview",
        "multimodal_overview",
        "multimodal_overview_other_angles",
    ),
    # custom_overlay_trio requires a user-supplied --panel-config.
    "all": tuple(
        panel_id for panel_id in PANEL_IDS
        if panel_id != "custom_overlay_trio"
    ),
}

# CLI choices include concrete IDs plus aliases.
PANEL_CLI_CHOICES = tuple(list(PANEL_IDS) + list(PANEL_ALIASES.keys()))


def resolve_requested_panels(
    panels_arg: Optional[Iterable[str]] = None,
    panel_preset: Optional[str] = None,
) -> Set[str]:
    """Expand --panels aliases and optional deprecated --panel-preset into a set.

    An empty/omitted --panels list means no display panels (preprocess only).
    """
    requested: Set[str] = set()
    for token in panels_arg or []:
        token = str(token).strip()
        if not token:
            continue
        if token in PANEL_ALIASES:
            requested.update(PANEL_ALIASES[token])
        elif token in PANEL_IDS:
            requested.add(token)
        else:
            raise ValueError(
                f"Unknown panel '{token}'. "
                f"Choose from: {', '.join(PANEL_CLI_CHOICES)}."
            )

    # Deprecated shim: --panel-preset quant_map_mm_panel adds that panel ID.
    if panel_preset == "quant_map_mm_panel":
        requested.add("quant_map_mm_panel")

    return requested


def raw_renders_needed(requested_panels: Set[str]) -> Set[str]:
    """Return which raw MRIcroGL render families are needed for the panels."""
    needed: Set[str] = set()
    if requested_panels & {"t1_overview", "multimodal_overview", "multimodal_overview_other_angles"}:
        needed.add("t1")
    if "t1_overlay_overview" in requested_panels:
        needed.add("t1_overlay")
    if requested_panels & {"t2_overview", "multimodal_overview", "multimodal_overview_other_angles"}:
        needed.add("t2_flair")
    if "quant_map_mm_panel" in requested_panels:
        needed.add("qmm")
    if "custom_overlay_trio" in requested_panels:
        needed.add("custom_trio")
    return needed


def format_panels_help() -> str:
    """Short help text for --panels."""
    return (
        "Display panels to generate (default: none — preprocess/erode only). "
        f"IDs: {', '.join(PANEL_IDS)}. "
        "Aliases: standard (T1/T2/multimodal structural), all "
        "(excludes custom_overlay_trio). "
        "Example: --panels standard   or   --panels t1_overlay_overview"
    )
