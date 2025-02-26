#!/usr/bin/env python3

import os
import re
from datetime import datetime
import requests
from pathlib import Path
from collections import defaultdict

# GitHub API configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
if not GITHUB_TOKEN:
    raise EnvironmentError("GITHUB_TOKEN environment variable is required")

GITHUB_API = "https://api.github.com"
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def get_pr_details(pr_number):
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

def process_cache_misses(input_file):
    """Process the cache misses log file and group by PR."""
    pr_cache_misses = defaultdict(list)
    current_entry = {}
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                if current_entry:
                    pr_info = current_entry.get('reference', '')
                    pr_cache_misses[pr_info].append(current_entry.copy())
                    current_entry = {}
                continue
                
            if line.startswith('Timestamp:'):
                current_entry['timestamp'] = line.split('Timestamp:', 1)[1].strip()
            elif line.startswith('Reference:'):
                current_entry['reference'] = line.split('Reference:', 1)[1].strip()
            elif line.startswith('File:'):
                current_entry['file'] = line.split('File:', 1)[1].strip()
    
    return pr_cache_misses

def main():
    input_file = "cache_misses_20250226_165653.log"
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    output_file = f"enriched_cache_misses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    pr_cache_misses = process_cache_misses(input_file)
    
    # Write enriched data to new log file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Enriched Cache Miss Analysis Report\n")
        f.write("=" * 60 + "\n\n")
        
        for pr_info, misses in pr_cache_misses.items():
            # Extract PR number if available
            pr_match = re.search(r'PR #(\d+)', pr_info)
            if pr_match:
                pr_number = pr_match.group(1)
                try:
                    pr_details = get_pr_details(pr_number)
                    
                    f.write(f"Pull Request: #{pr_number}\n")
                    f.write(f"Title: {pr_details['title']}\n")
                    f.write(f"Author: {pr_details['author']}\n")
                    f.write(f"State: {pr_details['state']}\n")
                    f.write(f"Created: {pr_details['created_at']}\n")
                except requests.RequestException as e:
                    f.write(f"Pull Request: {pr_info}\n")
                    f.write(f"Error fetching PR details: {str(e)}\n")
            else:
                f.write(f"Reference: {pr_info}\n")
            
            f.write(f"Number of cache misses: {len(misses)}\n")
            f.write("\nCache Miss Occurrences:\n")
            
            for miss in misses:
                f.write(f"  - {miss['timestamp']} in {miss['file']}\n")
            
            f.write("-" * 60 + "\n\n")
    
    print(f"Enriched analysis complete. Results written to: {output_file}")

if __name__ == "__main__":
    main() 