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
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# GitHub API configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    raise EnvironmentError("GITHUB_TOKEN environment variable is required")

GITHUB_API = "https://api.github.com"
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# Cache key patterns to track
CACHE_KEY_PATTERNS = [
    r'macOS-lfs-',
    r'ubuntu-lfs',
    r'tardis-regression'
]

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
    latest_run_timestamp: str = ""  # Added field for latest run timestamp

def is_relevant_cache_key(key: str) -> bool:
    """Check if the cache key matches any of our patterns."""
    if not key:
        return False
    return any(pattern in key for pattern in CACHE_KEY_PATTERNS)

def extract_cache_info(content: str) -> List[tuple[str, Optional[str]]]:
    """Extract cache event type and key from content.
    Returns a list of tuples (event_type, key).
    Only returns one event per file - first hit or miss found."""
    
    # Look for cache hits first
    hit_patterns = [
        'Cache found and can be restored from key: tardis-regression-full-data',
        'Cache restored from key: macOS-lfs-',
        'Cache restored from key: Linux-lfs-',
        'Cache restored from key: tardis-regression-full-data-'
    ]
    
    # Look for cache misses
    miss_patterns = [
        'Cache not found for input keys: macOS-lfs-',
        'Cache not found for input keys: Linux-lfs-',
        'Cache not found for input keys: tardis-regression-full-data-'
    ]
    
    # Check for hits first
    for pattern in hit_patterns:
        if pattern in content:
            # Extract the key - everything after the colon
            key = pattern.split(': ')[1]
            return [('hit', key)]
    
    # If no hits found, check for misses
    for pattern in miss_patterns:
        if pattern in content:
            # Extract the key - everything after the colon
            key = pattern.split(': ')[1]
            return [('miss', key)]
    
    return []  # No hits or misses found

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

def extract_pr_info(content: str) -> Optional[str]:
    """Extract pull request number from workflow content."""
    pr_pattern = r"Job defined at: tardis-sn/tardis/\.github/workflows/tests\.yml@refs/pull/(\d+)/merge"
    match = re.search(pr_pattern, content)
    return match.group(1) if match else None

def analyze_workflow_run(run_dir: str) -> List[CacheEvent]:
    """Analyze a single workflow run directory for cache events, only looking at root-level txt files."""
    cache_events = []
    
    # Get run timestamp from directory name
    run_name = os.path.basename(run_dir)
    timestamp_match = re.search(r'run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', run_name)
    timestamp = timestamp_match.group(1) if timestamp_match else "Unknown"
    
    # Only look at files in the root directory
    for file in os.listdir(run_dir):
        file_path = os.path.join(run_dir, file)
        
        # Skip if it's a directory or not a .txt file
        if os.path.isdir(file_path) or not file.endswith('.txt'):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Get all cache events from the file
                events = extract_cache_info(content)
                for event_type, key in events:
                    cache_events.append(CacheEvent(
                        timestamp=timestamp,
                        event_type=event_type,
                        file=file,
                        relative_path=file,  # Since we're only looking at root files, the relative path is just the filename
                        cache_key=key
                    ))
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
    
    return cache_events

def group_by_pr(workflow_logs_dir: str) -> Dict[str, PRDetails]:
    """Process all workflow runs and group cache events by PR."""
    pr_details = {}
    
    # Find all run directories
    run_dirs = glob.glob(str(Path(workflow_logs_dir) / "run_*"))
    
    for run_dir in run_dirs:
        cache_events = analyze_workflow_run(run_dir)
        
        # Get run timestamp from directory name
        run_name = os.path.basename(run_dir)
        timestamp_match = re.search(r'run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', run_name)
        run_timestamp = timestamp_match.group(1) if timestamp_match else "Unknown"
        
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
                        cache_events=[],
                        latest_run_timestamp=run_timestamp
                    )
                except requests.RequestException as e:
                    print(f"Error fetching PR #{pr_number} details: {e}")
                    continue
            else:
                # Update latest_run_timestamp if this run is more recent
                if run_timestamp > pr_details[pr_number].latest_run_timestamp:
                    pr_details[pr_number].latest_run_timestamp = run_timestamp
            
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

def create_visualization(pr_details: Dict[str, PRDetails], output_dir: str):
    """Create an interactive visualization of cache hits and misses."""
    # Prepare data for visualization
    data = []
    for pr_number, details in pr_details.items():
        hits = sum(1 for e in details.cache_events if e.event_type == 'hit')
        misses = sum(1 for e in details.cache_events if e.event_type == 'miss')
        
        # Convert timestamp format from "YYYY-MM-DD_HH-MM-SS" to "YYYY-MM-DD HH:MM:SS"
        if details.latest_run_timestamp and details.latest_run_timestamp != "Unknown":
            try:
                # Split into date and time parts
                date_str, time_str = details.latest_run_timestamp.split('_')
                # Replace hyphens with colons only in time part
                time_str = time_str.replace('-', ':')
                formatted_timestamp = f"{date_str} {time_str}"
                # Validate the timestamp format by trying to parse it
                pd.to_datetime(formatted_timestamp)
            except (ValueError, pd.errors.ParserError):
                # If any parsing error occurs, use a default timestamp
                print(f"Warning: Invalid timestamp format for PR #{pr_number}: {details.latest_run_timestamp}")
                formatted_timestamp = "1970-01-01 00:00:00"
        else:
            formatted_timestamp = "1970-01-01 00:00:00"  # Default timestamp for unknown dates
        
        data.append({
            'pr_number': f"#{pr_number}",
            'title': details.title,
            'author': details.author,
            'created_at': pd.to_datetime(details.created_at),
            'latest_run': pd.to_datetime(formatted_timestamp),
            'hits': hits,
            'misses': misses,
            'total_events': len(details.cache_events),
            'hit_rate': (hits / len(details.cache_events) * 100) if details.cache_events else 0
        })
    
    # Convert to DataFrame and sort by latest run timestamp
    df = pd.DataFrame(data)
    df = df.sort_values('latest_run')
    
    # Create the visualization
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        subplot_titles=("Cache Hits and Misses by Pull Request", "Cache Hit Rate (%)"),
        vertical_spacing=0.15
    )
    
    # Add traces for hits and misses
    fig.add_trace(
        go.Scatter(
            x=df['pr_number'],
            y=[1] * len(df),  # All points on same y-level
            mode='markers',
            name='Cache Hits',
            marker=dict(
                size=df['hits'] * 0.3,  # Scale the size for better visibility
                color='green',
                opacity=0.6,
                line=dict(width=1, color='darkgreen')
            ),
            text=[f"PR: {pr}<br>Title: {title}<br>Hits: {hits}<br>Author: {author}" 
                  for pr, title, hits, author in zip(df['pr_number'], df['title'], df['hits'], df['author'])],
            hoverinfo='text'
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['pr_number'],
            y=[0] * len(df),  # All points on same y-level
            mode='markers',
            name='Cache Misses',
            marker=dict(
                size=df['misses'] * 0.3,  # Scale the size for better visibility
                color='red',
                opacity=0.6,
                line=dict(width=1, color='darkred')
            ),
            text=[f"PR: {pr}<br>Title: {title}<br>Misses: {misses}<br>Author: {author}" 
                  for pr, title, misses, author in zip(df['pr_number'], df['title'], df['misses'], df['author'])],
            hoverinfo='text'
        ),
        row=1, col=1
    )
    
    # Add hit rate line chart
    fig.add_trace(
        go.Scatter(
            x=df['pr_number'],
            y=df['hit_rate'],
            mode='lines+markers',
            name='Hit Rate',
            line=dict(color='blue', width=2),
            marker=dict(size=8),
            text=[f"PR: {pr}<br>Hit Rate: {rate:.1f}%" 
                  for pr, rate in zip(df['pr_number'], df['hit_rate'])],
            hoverinfo='text'
        ),
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        title="Cache Performance Analysis",
        showlegend=True,
        height=800,
        template='plotly_white',
        hovermode='x unified'
    )
    
    # Update y-axes
    fig.update_yaxes(
        title_text="Cache Events",
        showticklabels=False,
        range=[-0.5, 1.5],
        row=1, col=1
    )
    fig.update_yaxes(
        title_text="Hit Rate (%)",
        range=[0, 100],
        row=2, col=1
    )
    
    # Update x-axis
    fig.update_xaxes(
        title_text="Pull Requests",
        tickangle=45,
        row=1, col=1
    )
    fig.update_xaxes(
        title_text="Pull Requests",
        tickangle=45,
        row=2, col=1
    )
    
    # Save the visualization
    output_file = os.path.join(output_dir, f"cache_visualization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    fig.write_html(output_file)
    print(f"Visualization saved to: {output_file}")

def main():
    workflow_logs_dir = "workflow_logs/tests"
    output_dir = "."
    log_file = f"cache_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    print("Analyzing workflow runs...")
    pr_details = group_by_pr(workflow_logs_dir)
    
    print("Writing report...")
    write_report(pr_details, os.path.join(output_dir, log_file))
    
    print("Creating visualization...")
    create_visualization(pr_details, output_dir)
    
    print(f"Analysis complete. Found data for {len(pr_details)} PRs.")

if __name__ == "__main__":
    main() 