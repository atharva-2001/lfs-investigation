#!/usr/bin/env python3

import os
import re
from datetime import datetime
import glob
from pathlib import Path

def extract_pr_info(content):
    """Extract pull request information from workflow content."""
    pr_pattern = r"Job defined at: tardis-sn/tardis/\.github/workflows/tests\.yml@refs/pull/(\d+)/merge"
    match = re.search(pr_pattern, content)
    if match:
        return f"PR #{match.group(1)}"
    
    # If no PR found, check if it's a push to a branch
    branch_pattern = r"Job defined at: tardis-sn/tardis/\.github/workflows/tests\.yml@refs/heads/(\w+)"
    match = re.search(branch_pattern, content)
    if match:
        return f"Push to {match.group(1)}"
    
    return "No PR/branch information found"

def analyze_workflow_run(run_dir):
    """Analyze a single workflow run directory for cache misses."""
    cache_misses = []
    
    # Recursively walk through all files in the run directory
    for root, _, files in os.walk(run_dir):
        for file in files:
            if not file.endswith('.txt'):
                continue
                
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "Cache not found for input keys:" in content:
                        # Get run timestamp from directory name
                        run_name = os.path.basename(run_dir)
                        timestamp_match = re.search(r'run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', run_name)
                        timestamp = timestamp_match.group(1) if timestamp_match else "Unknown"
                        
                        # Find any PR information in the file
                        pr_info = extract_pr_info(content)
                        
                        cache_misses.append({
                            'timestamp': timestamp,
                            'pr_info': pr_info,
                            'file': file,
                            'relative_path': os.path.relpath(file_path, run_dir)
                        })
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
    
    return cache_misses

def main():
    workflow_logs_dir = Path("workflow_logs/tests")
    output_file = f"cache_misses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    all_cache_misses = []
    
    # Find all run directories
    run_dirs = glob.glob(str(workflow_logs_dir / "run_*"))
    
    for run_dir in run_dirs:
        cache_misses = analyze_workflow_run(run_dir)
        all_cache_misses.extend(cache_misses)
    
    # Sort by timestamp
    all_cache_misses.sort(key=lambda x: x['timestamp'])
    
    # Write results to log file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Cache Miss Analysis Report\n")
        f.write("=" * 50 + "\n\n")
        
        for miss in all_cache_misses:
            f.write(f"Timestamp: {miss['timestamp']}\n")
            f.write(f"Reference: {miss['pr_info']}\n")
            f.write(f"File: {miss['relative_path']}\n")
            f.write("-" * 50 + "\n\n")
            
    print(f"Analysis complete. Found {len(all_cache_misses)} cache misses.")
    print(f"Results written to: {output_file}")

if __name__ == "__main__":
    main() 