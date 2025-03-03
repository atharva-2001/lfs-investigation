#!/usr/bin/env python3

import os
import requests
import datetime
from pathlib import Path
from datetime import datetime, timedelta
import zipfile
import io

def download_workflow_logs(token, owner="tardis-sn", repo="tardis", workflow_file="tests.yml", months=1):
    """
    Download logs for all runs of a specific GitHub Actions workflow from the last N months.
    
    Args:
        token (str): GitHub Personal Access Token
        owner (str): Repository owner
        repo (str): Repository name
        workflow_file (str): Name of the workflow file
        months (int): Number of months to look back
    """
    # Calculate the date threshold (3 months ago)
    three_months_ago = datetime.now() - timedelta(days=30 * months)
    
    # Create base directory for logs
    base_dir = Path("workflow_logs") / workflow_file.replace(".yml", "")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    # GitHub API headers
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}"
    }
    
    # Get workflow ID first
    workflows_url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows"
    workflows = requests.get(workflows_url, headers=headers).json()
    workflow_id = None
    
    for workflow in workflows.get("workflows", []):
        if workflow["path"].endswith(workflow_file):
            workflow_id = workflow["id"]
            break
    
    if not workflow_id:
        raise ValueError(f"Could not find workflow: {workflow_file}")
    
    # Get all workflow runs
    runs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
    page = 1
    per_page = 100
    
    print(f"Downloading workflow logs from {three_months_ago.strftime('%Y-%m-%d')} to now...")
    
    while True:
        params = {
            "page": page,
            "per_page": per_page,
            "created": f">{three_months_ago.strftime('%Y-%m-%d')}"
        }
        response = requests.get(runs_url, headers=headers, params=params)
        runs = response.json()
        
        if not runs.get("workflow_runs"):
            break
            
        for run in runs["workflow_runs"]:
            run_id = run["id"]
            run_date = datetime.strptime(
                run["created_at"], "%Y-%m-%dT%H:%M:%SZ"
            )
            
            # Skip if the run is older than three months
            if run_date < three_months_ago:
                continue
                
            run_date_str = run_date.strftime("%Y-%m-%d_%H-%M-%S")
            run_status = run["conclusion"] or "running"
            
            # Create directory for this run
            run_dir = base_dir / f"run_{run_date_str}_{run_status}"
            run_dir.mkdir(exist_ok=True)
            
            # Download logs
            logs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
            logs_response = requests.get(logs_url, headers=headers, allow_redirects=True)
            
            if logs_response.status_code == 200:
                # Extract zip content directly from memory
                with zipfile.ZipFile(io.BytesIO(logs_response.content)) as zip_ref:
                    # Extract all files from the zip
                    zip_ref.extractall(run_dir)
                    
                    # List all extracted files for user feedback
                    extracted_files = [f.filename for f in zip_ref.filelist]
                    print(f"Downloaded and extracted logs for run {run_id} ({run_date_str}) to {run_dir}")
                    # print(f"  Extracted files: {', '.join(extracted_files)}")
            else:
                print(f"Failed to download logs for run {run_id}: {logs_response.status_code}")
        
        if len(runs["workflow_runs"]) < per_page:
            break
        page += 1

if __name__ == "__main__":
    # Get GitHub token from environment variable
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("Please set the GITHUB_TOKEN environment variable")
    
    download_workflow_logs(token) 