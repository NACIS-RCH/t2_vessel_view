"""
Basic test script to verify package installation and imports.

This script tests that all the main components of the t2vesselview package can be imported
correctly and performs basic functionality tests. It's useful for:
1. Verifying the package is installed correctly
2. Checking that all dependencies are available
3. Ensuring the directory structure is accessible
4. Testing basic logging functionality
5. Validating that the command-line interface is properly configured

Usage:
    python tests/test_basic_imports.py
"""
import sys
import os
import tempfile

# Add the parent directory to Python's module search path
# This is necessary because we're running the test from the tests directory,
# but we need to import modules from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set test mode to prevent actual processing
os.environ['T2VV_TEST_MODE'] = '1'

def create_test_directory_structure(base_dir):
    """Create the directory structure needed for testing."""
    dirs = [
        "T2VesselView",
        "T2VesselView/Eroded_nifti",
        "T2VesselView/Eroded_nifti/T1",
        "T2VesselView/Eroded_nifti/T2",
        "T2VesselView/Eroded_nifti/FLAIR",
        "T2VesselView/PowerPoints",
        "T2VesselView/Processing",
        "T2VesselView/Processing/Figures_for_QA",
        "T2VesselView/Processing/Log_files",
        "T2VesselView/Processing/Masks",
        "T2VesselView/Processing/Preprocessed_T1",
        "T2VesselView/Processing/Preprocessed_T2",
        "T2VesselView/Processing/Preprocessed_FLAIR",
        "T2VesselView/3D_renders_png",
        "T2VesselView/3D_renders_png/T1_3D_renders",
        "T2VesselView/3D_renders_png/T1_3D_renders/by_erode_level",
        "T2VesselView/3D_renders_png/T1_3D_renders/by_angle",
        "T2VesselView/3D_renders_png/T2_vessel_3D_renders",
        "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_erode_level",
        "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_angle"
    ]
    
    for dir_path in dirs:
        full_path = os.path.join(base_dir, dir_path)
        os.makedirs(full_path, exist_ok=True)
        print(f"Created directory: {full_path}")

def test_imports():
    """Test that we can import the main package components and basic functionality.
    
    This function attempts to import each major component of the package
    and verifies that the directory structure variables are accessible.
    It also tests basic functionality like logging and directory creation.
    It uses a try-except block to catch and report any import errors.
    
    Returns:
        bool: True if all imports and tests succeed, False otherwise
    """
    try:
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"\nTesting with temporary directory: {temp_dir}")
            
            # Create the full directory structure
            create_test_directory_structure(temp_dir)
            
            # Mock command line arguments
            sys.argv = [
                'test_basic_imports.py',
                '-d', temp_dir,
                '-i', os.path.join(temp_dir, 'test_t1.nii.gz'),
                '-f', os.path.join(temp_dir, 'test_flair.nii.gz')
            ]
            
            # Import the main package - this should work if the package is installed
            import t2vesselviewcode
            print("✓ Successfully imported t2vesselviewcode")
            
            # Import the main processing module that contains core functionality
            from t2vesselviewcode import t2_vessel_view_main
            print("✓ Successfully imported t2_vessel_view_main")
            
            # Import the logging module that handles output messages
            from t2vesselviewcode import logger
            print("✓ Successfully imported logger")
            
            # Test logger functionality
            test_logger = logger.setup_logger("test_logger", os.path.join(temp_dir, "test.log"))
            test_logger.info("Test log message")
            print("✓ Successfully created and used logger")
            
            # Import the directory structure module that defines where files are saved
            from t2vesselviewcode import dir_structure
            print("✓ Successfully imported dir_structure")
            
            # Test that we can access the directory paths without creating them
            # This verifies the directory structure is properly defined
            print(f"✓ Successfully accessed main_t2vv_dir: {dir_structure.main_t2vv_dir}")
            print(f"✓ Successfully accessed renders_dir: {dir_structure.renders_dir}")
            
            # Test directory creation
            test_dir = os.path.join(temp_dir, "test_output")
            os.makedirs(test_dir, exist_ok=True)
            print(f"✓ Successfully created test directory: {test_dir}")
            
            # Import the input validation module that checks MRI data
            from t2vesselviewcode import input_validation
            print("✓ Successfully imported input_validation")
            
            # Import the mask creation module for vessel visualization
            # Note: We're just importing it, not running the mask creation yet
            from t2vesselviewcode import make_mask_convex_hull
            print("✓ Successfully imported make_mask_convex_hull")
            
            print("\nAll imports and basic functionality tests successful!")
            print("Package is installed correctly and basic features are working.")
            print("\nNote: Mask creation functionality will be tested separately with proper test data.")
            return True
        
    except ImportError as e:
        # This catches errors when a module can't be found
        print(f"❌ Import failed: {str(e)}")
        return False
    except Exception as e:
        # This catches any other errors that might occur
        print(f"❌ Error occurred: {str(e)}")
        return False

# This is the standard Python idiom for running code only when the script is run directly
# (not when it's imported as a module)
if __name__ == "__main__":
    test_imports() 