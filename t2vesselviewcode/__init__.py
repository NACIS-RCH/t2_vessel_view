"""
T2 vessel visualization package.
"""

# Core functionality imports
from . import logger
from . import dir_structure
from . import input_validation
from . import make_mask_convex_hull
from . import t2_vessel_view_main

# Command-line interface is imported only when needed
# This prevents argument parsing from being triggered on import
def get_commandline():
    """Get the commandline module when needed."""
    from . import commandline
    return commandline

__version__ = '0.1.0'
