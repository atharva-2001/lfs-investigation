#!/usr/bin/env python3

import os
from pathlib import Path
from datetime import datetime

def cleanup_workflow_logs(base_path="workflow_logs/tests"):
    """
    Delete empty directories in the workflow logs path and create a log of directory names.
    
    Args:
        base_path (str): Path to the workflow logs directory
    """
    base_dir = Path(base_path)
    if not base_dir.exists():
        print(f"Directory {base_path} does not exist!")
        return
        
    # Create a log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = base_dir.parent / f"directory_log_{timestamp}.txt"
    
    directories = []
    empty_dirs = []
    
    # Check all directories
    for item in base_dir.iterdir():
        if item.is_dir():
            directories.append(item.name)
            # Check if directory is empty
            if not any(item.iterdir()):
                empty_dirs.append(item.name)
                # Delete empty directory
                item.rmdir()
                print(f"Deleted empty directory: {item}")
    
    # Write to log file
    with open(log_file, 'w') as f:
        f.write("Workflow Log Directories\n")
        f.write("======================\n\n")
        f.write("Timestamp: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
        f.write("All directories:\n")
        for dir_name in sorted(directories):
            f.write(f"- {dir_name}\n")
        f.write("\nEmpty directories that were deleted:\n")
        for dir_name in sorted(empty_dirs):
            f.write(f"- {dir_name}\n")

if __name__ == "__main__":
    cleanup_workflow_logs() 