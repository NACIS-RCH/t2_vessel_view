"""
Logging module for T2 vessel visualization pipeline.
Provides consistent logging and progress tracking throughout the pipeline.
This module helps track what's happening during image processing and makes debugging easier.
"""

# Import required Python modules
import logging  # Python's built-in logging system
import os  # For operating system operations
from datetime import datetime  # For creating timestamps
from pathlib import Path  # Modern way to handle file paths (better than os.path)

def setup_logger(output_dir: str = None) -> logging.Logger:
    """
    Set up and configure the logger for the pipeline.
    
    Args:
        output_dir (str, optional): Directory to save log files. If None, logs only to console.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create a new logger instance with a specific name
    # This name helps identify where the log messages are coming from
    logger = logging.getLogger('t2vesselview')
    
    # Set the minimum level of messages to be logged
    # INFO level means we'll see all messages except debug messages
    logger.setLevel(logging.INFO)
    
    # Create two different formats for logging:
    # 1. Console format: Short timestamp (HH:MM:SS) for quick reading
    # 2. File format: Full timestamp (YYYY-MM-DD HH:MM:SS) for detailed records
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',  # Format: time - level - message
        datefmt='%H:%M:%S'  # Short time format for console
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'  # Full date and time format for files
    )
    
    # Set up console output (what you see in the terminal)
    console_handler = logging.StreamHandler()  # Creates a handler for console output
    console_handler.setFormatter(console_formatter)  # Apply the short format
    logger.addHandler(console_handler)  # Add this handler to our logger
    
    # Set up file output (if an output directory is specified)
    if output_dir:
        # Convert string path to Path object and create directory if it doesn't exist
        # parents=True: create parent directories if needed
        # exist_ok=True: don't raise error if directory already exists
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create a unique log file name using current timestamp
        # Format: pipeline_YYYYMMDD_HHMMSS.log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = output_path / f'pipeline_{timestamp}.log'
        
        # Set up file output handler
        file_handler = logging.FileHandler(log_file)  # Creates a handler for file output
        file_handler.setFormatter(file_formatter)  # Apply the detailed format
        logger.addHandler(file_handler)  # Add this handler to our logger
    
    return logger

def log_progress(logger: logging.Logger, message: str, level: str = 'info') -> None:
    """
    Log a progress message with consistent formatting.
    This function adds visual indicators to make different types of messages easily distinguishable.
    
    Args:
        logger (logging.Logger): Logger instance to use
        message (str): The message to log
        level (str): Type of message ('info', 'warning', 'error', 'debug')
    """
    # Convert level to lowercase to make it case-insensitive
    level = level.lower()
    
    # Add different symbols based on message type:
    # → for normal info messages
    # ⚠ for warnings
    # ✗ for errors
    # ⚙ for debug messages
    if level == 'info':
        logger.info(f"→ {message}")  # Normal progress message
    elif level == 'warning':
        logger.warning(f"⚠ {message}")  # Something to be careful about
    elif level == 'error':
        logger.error(f"✗ {message}")  # Something went wrong
    elif level == 'debug':
        logger.debug(f"⚙ {message}")  # Technical details for debugging
    else:
        logger.info(f"→ {message}")  # Default to info if level not recognized

def log_step(logger: logging.Logger, step_name: str) -> None:
    """
    Log the start of a pipeline step with clear visual separation.
    This makes it easy to see where each major processing step begins in the logs.
    
    Args:
        logger (logging.Logger): Logger instance to use
        step_name (str): Name of the pipeline step (e.g., "Image Loading", "Skull Stripping")
    """
    # Create a visual separator line
    logger.info("=" * 50)  # Print 50 equals signs
    
    # Log the step name
    logger.info(f"Starting: {step_name}")
    
    # Create another separator line
    logger.info("=" * 50) 