#!/usr/bin/env python3

import os
import re
from datetime import datetime
import requests
import glob
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

# GitHub API configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    raise EnvironmentError("GITHUB_TOKEN environment variable is required")

GITHUB_API = "https://api.github.com"
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

@dataclass
class CacheEvent:
    timestamp: str
    event_type: str  # 'hit' or 'miss'
    file: str
    relative_path: str
    cache_key: Optional[str] = None

@dataclass
class PRDetails:
    number: str
    title: str
    author: str
    state: str
    created_at: str
    cache_events: List[CacheEvent]

def get_pr_details(pr_number: str) -> Dict:
    """Fetch PR details from GitHub API."""
    url = f"{GITHUB_API}/repos/tardis-sn/tardis/pulls/{pr_number}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 404:
        return {
            'title': 'PR not found',
            'author': 'Unknown',
            'state': 'unknown',
            'created_at': 'unknown'
        }
    
    response.raise_for_status()
    pr_data = response.json()
    
    return {
        'title': pr_data['title'],
        'author': pr_data['user']['login'],
        'state': pr_data['state'],
        'created_at': pr_data['created_at']
    }

def extract_cache_key(content: str) -> Optional[str]:
    """Extract cache key from content."""
    # For cache hits
    hit_match = re.search(r'Cache found and can be restored from key: (.+?)(?:\n|$)', content)
    if hit_match:
        return hit_match.group(1)
    
    # For cache misses
    miss_match = re.search(r'Cache not found for input keys: (.+?)(?:\n|$)', content)
    if miss_match:
        return miss_match.group(1)
    
    return None

def analyze_workflow_run(run_dir: str) -> List[CacheEvent]:
    """Analyze a single workflow run directory for cache events."""
    cache_events = []
    
    # Get run timestamp from directory name
    run_name = os.path.basename(run_dir)
    timestamp_match = re.search(r'run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', run_name)
    timestamp = timestamp_match.group(1) if timestamp_match else "Unknown"
    
    # Recursively walk through all files in the run directory
    for root, _, files in os.walk(run_dir):
        for file in files:
            if not file.endswith('.txt'):
                continue
                
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Check for cache hits
                    if "Cache found and can be restored from key:" in content:
                        cache_events.append(CacheEvent(
                            timestamp=timestamp,
                            event_type='hit',
                            file=file,
                            relative_path=os.path.relpath(file_path, run_dir),
                            cache_key=extract_cache_key(content)
                        ))
                    
                    # Check for cache misses
                    if "Cache not found for input keys:" in content:
                        cache_events.append(CacheEvent(
                            timestamp=timestamp,
                            event_type='miss',
                            file=file,
                            relative_path=os.path.relpath(file_path, run_dir),
                            cache_key=extract_cache_key(content)
                        ))
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
    
    return cache_events

def extract_pr_info(content: str) -> Optional[str]:
    """Extract pull request number from workflow content."""
    pr_pattern = r"Job defined at: tardis-sn/tardis/\.github/workflows/tests\.yml@refs/pull/(\d+)/merge"
    match = re.search(pr_pattern, content)
    return match.group(1) if match else None

def group_by_pr(workflow_logs_dir: str) -> Dict[str, PRDetails]:
    """Process all workflow runs and group cache events by PR."""
    pr_details = {}
    
    # Find all run directories
    run_dirs = glob.glob(str(Path(workflow_logs_dir) / "run_*"))
    
    for run_dir in run_dirs:
        cache_events = analyze_workflow_run(run_dir)
        
        # Try to find PR number in any of the files
        pr_number = None
        for root, _, files in os.walk(run_dir):
            for file in files:
                if not file.endswith('.txt'):
                    continue
                    
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                        pr_number = extract_pr_info(content)
                        if pr_number:
                            break
                except Exception:
                    continue
            if pr_number:
                break
        
        if pr_number:
            if pr_number not in pr_details:
                try:
                    details = get_pr_details(pr_number)
                    pr_details[pr_number] = PRDetails(
                        number=pr_number,
                        title=details['title'],
                        author=details['author'],
                        state=details['state'],
                        created_at=details['created_at'],
                        cache_events=[]
                    )
                except requests.RequestException as e:
                    print(f"Error fetching PR #{pr_number} details: {e}")
                    continue
            
            pr_details[pr_number].cache_events.extend(cache_events)
    
    return pr_details

def write_report(pr_details: Dict[str, PRDetails], output_file: str):
    """Write the analysis report to a file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Cache History Analysis Report\n")
        f.write("=" * 80 + "\n\n")
        
        for pr_number, details in sorted(pr_details.items()):
            f.write(f"Pull Request: #{pr_number}\n")
            f.write(f"Title: {details.title}\n")
            f.write(f"Author: {details.author}\n")
            f.write(f"State: {details.state}\n")
            f.write(f"Created: {details.created_at}\n\n")
            
            # Calculate statistics
            total_events = len(details.cache_events)
            hits = sum(1 for e in details.cache_events if e.event_type == 'hit')
            misses = sum(1 for e in details.cache_events if e.event_type == 'miss')
            hit_rate = (hits / total_events * 100) if total_events > 0 else 0
            
            f.write(f"Cache Statistics:\n")
            f.write(f"  Total Events: {total_events}\n")
            f.write(f"  Cache Hits: {hits}\n")
            f.write(f"  Cache Misses: {misses}\n")
            f.write(f"  Hit Rate: {hit_rate:.1f}%\n\n")
            
            f.write("Cache Events (chronological order):\n")
            for event in sorted(details.cache_events, key=lambda x: x.timestamp):
                event_type = "HIT" if event.event_type == 'hit' else "MISS"
                f.write(f"  [{event.timestamp}] {event_type}: {event.relative_path}\n")
                if event.cache_key:
                    f.write(f"    Key: {event.cache_key}\n")
            
            f.write("-" * 80 + "\n\n")

def main():
    workflow_logs_dir = "workflow_logs/tests"
    output_file = f"cache_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    print("Analyzing workflow runs...")
    pr_details = group_by_pr(workflow_logs_dir)
    
    print("Writing report...")
    write_report(pr_details, output_file)
    
    print(f"Analysis complete. Found data for {len(pr_details)} PRs.")
    print(f"Results written to: {output_file}")

if __name__ == "__main__":
    main() 