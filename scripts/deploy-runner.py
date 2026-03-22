#!/usr/bin/env python3
"""scripts/deploy-runner.py — Deploy nexads to GitHub Actions runner accounts.

Usage:
  python scripts/deploy-runner.py init        # First time: create repos, push workflow, trigger
  python scripts/deploy-runner.py redeploy    # Re-trigger workflows on existing repos
  python scripts/deploy-runner.py update      # Re-push workflow and trigger
  python scripts/deploy-runner.py status      # Check running workflow status
  python scripts/deploy-runner.py stop        # Cancel all running workflows
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import shutil

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
REPO_NAME = "nexads-runner"
WORKFLOW_FILENAME = "run-nexads.yml"
SOURCE_REPO = "https://github.com/ourcaldo/nexads-main.git"
WORKFLOW_SOURCE = os.path.join(REPO_ROOT, ".github", "workflows", "run-nexads.yml")


def read_tokens():
    """Read account tokens from tokens.txt."""
    tokens_path = os.path.join(REPO_ROOT, "tokens.txt")
    if not os.path.exists(tokens_path):
        print(f"Error: {tokens_path} not found")
        sys.exit(1)

    tokens = []
    with open(tokens_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, token = line.split(":", 1)
                tokens.append({"name": name.strip(), "token": token.strip()})
            else:
                tokens.append({"name": None, "token": line.strip()})
    return tokens


def api_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def get_username(token):
    """Get GitHub username from PAT."""
    r = requests.get("https://api.github.com/user", headers=api_headers(token))
    r.raise_for_status()
    return r.json()["login"]


def repo_exists(token, owner, repo):
    """Check if a repo exists."""
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=api_headers(token),
    )
    return r.status_code == 200


def create_repo(token, repo_name):
    """Create a public repo under the authenticated user."""
    r = requests.post(
        "https://api.github.com/user/repos",
        headers=api_headers(token),
        json={"name": repo_name, "private": False, "auto_init": False},
    )
    if r.status_code == 422:
        return None
    r.raise_for_status()
    return r.json()


def push_workflow(token, owner, repo_name):
    """Push only the workflow YAML to the runner repo."""
    tmpdir = tempfile.mkdtemp(prefix="nexads-deploy-")
    try:
        dest = os.path.join(tmpdir, "repo")
        os.makedirs(os.path.join(dest, ".github", "workflows"), exist_ok=True)

        # Copy only the workflow file
        shutil.copy2(WORKFLOW_SOURCE, os.path.join(dest, ".github", "workflows", WORKFLOW_FILENAME))

        remote_url = f"https://x-access-token:{token}@github.com/{owner}/{repo_name}.git"

        cmds = [
            ["git", "init"],
            ["git", "checkout", "-b", "main"],
            ["git", "config", "user.email", "deploy@nexads.local"],
            ["git", "config", "user.name", "nexads-deploy"],
            ["git", "add", "-A"],
            ["git", "commit", "-m", "Deploy workflow"],
            ["git", "remote", "add", "origin", remote_url],
            ["git", "push", "-u", "origin", "main", "--force"],
        ]

        for cmd in cmds:
            result = subprocess.run(cmd, cwd=dest, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  Error running {' '.join(cmd[:3])}...: {result.stderr.strip()}")
                return False

        print(f"  Pushed workflow to {owner}/{repo_name}")
        return True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def trigger_workflow(token, owner, repo_name, num_workers=20, run_minutes=180):
    """Trigger the workflow via dispatch."""
    r = requests.post(
        f"https://api.github.com/repos/{owner}/{repo_name}/actions/workflows/{WORKFLOW_FILENAME}/dispatches",
        headers=api_headers(token),
        json={
            "ref": "main",
            "inputs": {
                "num_workers": str(num_workers),
                "run_minutes": str(run_minutes),
            },
        },
    )
    if r.status_code == 204:
        print(f"  Triggered: {num_workers} worker(s) for {run_minutes}min")
        return True
    else:
        print(f"  Failed to trigger: {r.status_code} {r.text}")
        return False


def get_running_workflows(token, owner, repo_name):
    """Get list of in-progress workflow runs."""
    r = requests.get(
        f"https://api.github.com/repos/{owner}/{repo_name}/actions/runs",
        headers=api_headers(token),
        params={"status": "in_progress", "per_page": 10},
    )
    r.raise_for_status()
    return r.json().get("workflow_runs", [])


def cancel_workflow(token, owner, repo_name, run_id):
    """Cancel a workflow run."""
    r = requests.post(
        f"https://api.github.com/repos/{owner}/{repo_name}/actions/runs/{run_id}/cancel",
        headers=api_headers(token),
    )
    return r.status_code == 202


# --- COMMANDS ---

def cmd_init(args, tokens):
    """First-time setup: create repos, push workflow, trigger."""
    for t in tokens:
        owner = get_username(t["token"])
        label = t["name"] or owner
        print(f"\n[{label}] ({owner})")

        if not repo_exists(t["token"], owner, REPO_NAME):
            create_repo(t["token"], REPO_NAME)
            print(f"  Created repo: {owner}/{REPO_NAME}")
        else:
            print(f"  Repo exists: {owner}/{REPO_NAME}")

        if push_workflow(t["token"], owner, REPO_NAME):
            trigger_workflow(t["token"], owner, REPO_NAME, args.workers, args.minutes)


def cmd_redeploy(args, tokens):
    """Stop running workflows, then re-trigger."""
    for t in tokens:
        owner = get_username(t["token"])
        label = t["name"] or owner
        print(f"\n[{label}] ({owner})")

        runs = get_running_workflows(t["token"], owner, REPO_NAME)
        for run in runs:
            cancel_workflow(t["token"], owner, REPO_NAME, run["id"])
            print(f"  Cancelled run #{run['id']}")

        trigger_workflow(t["token"], owner, REPO_NAME, args.workers, args.minutes)


def cmd_update(args, tokens):
    """Re-push workflow and trigger."""
    for t in tokens:
        owner = get_username(t["token"])
        label = t["name"] or owner
        print(f"\n[{label}] ({owner})")
        if push_workflow(t["token"], owner, REPO_NAME):
            trigger_workflow(t["token"], owner, REPO_NAME, args.workers, args.minutes)


def cmd_status(args, tokens):
    """Check status of running workflows."""
    for t in tokens:
        owner = get_username(t["token"])
        label = t["name"] or owner
        print(f"\n[{label}] ({owner})")

        runs = get_running_workflows(t["token"], owner, REPO_NAME)
        if runs:
            for run in runs:
                print(f"  Run #{run['id']}: {run['status']} — {run['name']} (started {run['created_at']})")
        else:
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{REPO_NAME}/actions/runs",
                headers=api_headers(t["token"]),
                params={"per_page": 3},
            )
            if r.status_code == 200:
                recent = r.json().get("workflow_runs", [])
                if recent:
                    for run in recent:
                        print(f"  Run #{run['id']}: {run['status']}/{run['conclusion']} — {run['name']}")
                else:
                    print("  No workflow runs found")
            else:
                print("  No active runs")


def cmd_stop(args, tokens):
    """Cancel all running workflows."""
    for t in tokens:
        owner = get_username(t["token"])
        label = t["name"] or owner
        print(f"\n[{label}] ({owner})")

        runs = get_running_workflows(t["token"], owner, REPO_NAME)
        if runs:
            for run in runs:
                if cancel_workflow(t["token"], owner, REPO_NAME, run["id"]):
                    print(f"  Cancelled run #{run['id']}")
                else:
                    print(f"  Failed to cancel run #{run['id']}")
        else:
            print("  No active runs to cancel")


def main():
    parser = argparse.ArgumentParser(description="Deploy nexads to GitHub runner accounts")
    sub = parser.add_subparsers(dest="command", required=True)

    commands = {
        "init": "Create repos, push workflow, and start",
        "redeploy": "Re-trigger workflows on existing repos",
        "update": "Re-push workflow and trigger",
        "status": "Check status of running workflows",
        "stop": "Cancel all running workflows",
    }

    for name, help_text in commands.items():
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-w", "--workers", type=int, default=20,
                       help="Number of parallel runner VMs per account (default: 20)")
        p.add_argument("-m", "--minutes", type=int, default=180,
                       help="Run duration in minutes (default: 180)")

    args = parser.parse_args()
    tokens = read_tokens()

    if not tokens:
        print("No tokens found in tokens.txt")
        sys.exit(1)

    print(f"Found {len(tokens)} account(s)")

    cmd_map = {
        "init": cmd_init,
        "redeploy": cmd_redeploy,
        "update": cmd_update,
        "status": cmd_status,
        "stop": cmd_stop,
    }
    cmd_map[args.command](args, tokens)


if __name__ == "__main__":
    main()
