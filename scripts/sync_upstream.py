#!/usr/bin/env python3
"""
sync_upstream.py — Detect upstream changes and prepare translation work.

Workflow:
  1. Fetch upstream repo
  2. Compare current tracked commit with latest upstream
  3. Find changed .ipynb files
  4. Copy changed files to a staging area
  5. Output a summary of what needs translation

Used by GitHub Action to decide whether to run translation and what to translate.

Output (JSON to stdout):
  {
    "has_changes": true/false,
    "upstream_commit": "abc123",
    "previous_commit": "def456",
    "changed_files": ["ch02/ch02_main.ipynb", ...],
    "new_files": ["ch09/ch09_main.ipynb", ...],
    "deleted_files": [...]
  }
"""

import json
import os
import sys
import subprocess
import argparse
from pathlib import Path


def load_dotenv():
    """Load .env file from project root if present."""
    for parent in [Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]:
        env_file = parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip(), value.strip()
                        if key and key not in os.environ:
                            os.environ[key] = value
            return


load_dotenv()

UPSTREAM_REPO = "https://github.com/rasbt/reasoning-from-scratch.git"
UPSTREAM_BRANCH = "main"
COMMIT_FILE = ".upstream-commit"


def run(cmd: str, cwd: str = None) -> tuple[int, str]:
    """Run a shell command, return (exit_code, stdout)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout.strip()


def ensure_upstream_remote(repo_dir: str):
    """Add or update the upstream remote."""
    code, remotes = run("git remote", cwd=repo_dir)
    if "upstream" not in remotes:
        run(f"git remote add upstream {UPSTREAM_REPO}", cwd=repo_dir)
    else:
        # Update URL in case it changed
        run(f"git remote set-url upstream {UPSTREAM_REPO}", cwd=repo_dir)


def get_tracked_commit(repo_dir: str) -> str | None:
    """Read the last synced upstream commit hash."""
    commit_file = os.path.join(repo_dir, COMMIT_FILE)
    if os.path.exists(commit_file):
        with open(commit_file) as f:
            return f.read().strip()
    return None


def save_tracked_commit(repo_dir: str, commit_hash: str):
    """Save the current upstream commit hash."""
    commit_file = os.path.join(repo_dir, COMMIT_FILE)
    with open(commit_file, "w") as f:
        f.write(commit_hash + "\n")


def get_latest_upstream_commit(repo_dir: str) -> str:
    """Get the latest commit hash on upstream/main."""
    run("git fetch upstream", cwd=repo_dir)
    code, sha = run(f"git rev-parse upstream/{UPSTREAM_BRANCH}", cwd=repo_dir)
    if code != 0:
        print(f"Error: cannot resolve upstream/{UPSTREAM_BRANCH}", file=sys.stderr)
        sys.exit(1)
    return sha


def get_changed_notebooks(repo_dir: str, old_commit: str, new_commit: str) -> dict:
    """Get lists of changed/new/deleted .ipynb files between two commits."""
    result = {"changed": [], "new": [], "deleted": []}

    # --diff-filter: A=added, M=modified, D=deleted
    code, diff_output = run(
        f"git diff --name-only --diff-filter=AMRD {old_commit} {new_commit} -- '*.ipynb'",
        cwd=repo_dir,
    )
    if not diff_output:
        return result

    for filepath in diff_output.split("\n"):
        filepath = filepath.strip()
        if not filepath.endswith(".ipynb"):
            continue

        # Check if file is new (added) or modified
        code_old, _ = run(
            f"git cat-file -e {old_commit}:{filepath}", cwd=repo_dir
        )
        code_new, _ = run(
            f"git cat-file -e {new_commit}:{filepath}", cwd=repo_dir
        )

        if code_old == 0 and code_new == 0:
            result["changed"].append(filepath)
        elif code_old != 0 and code_new == 0:
            result["new"].append(filepath)
        elif code_old == 0 and code_new != 0:
            result["deleted"].append(filepath)
        else:
            result["changed"].append(filepath)

    return result


def checkout_upstream_files(repo_dir: str, commit: str, files: list[str]):
    """Checkout specific files from the upstream commit to a staging area."""
    staging = os.path.join(repo_dir, ".upstream-staging")
    os.makedirs(staging, exist_ok=True)

    for filepath in files:
        code, content = run(
            f"git show {commit}:{filepath}", cwd=repo_dir
        )
        if code == 0:
            out_path = os.path.join(staging, filepath)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Sync upstream changes")
    parser.add_argument("--repo-dir", default=".", help="Local repo directory")
    parser.add_argument("--force", action="store_true", help="Force full re-sync")
    parser.add_argument("--init", action="store_true", help="Initialize: track latest commit without translating")
    args = parser.parse_args()

    repo_dir = os.path.abspath(args.repo_dir)

    # Ensure upstream remote exists
    ensure_upstream_remote(repo_dir)

    # Get latest upstream commit
    latest = get_latest_upstream_commit(repo_dir)
    print(f"📡 Latest upstream: {latest[:12]}", file=sys.stderr)

    # Get previously tracked commit
    tracked = get_tracked_commit(repo_dir)

    if args.init:
        # Just save the current commit, no translation needed
        save_tracked_commit(repo_dir, latest)
        print(json.dumps({
            "has_changes": False,
            "upstream_commit": latest,
            "previous_commit": None,
            "changed_files": [],
            "new_files": [],
            "deleted_files": [],
            "action": "initialized",
        }))
        return

    if args.force or not tracked:
        # Full translation: treat everything as changed
        print("🔄 Full sync (no previous commit or --force)", file=sys.stderr)
        code, ls_output = run(
            f"git ls-tree -r --name-only upstream/{UPSTREAM_BRANCH} -- '*.ipynb'",
            cwd=repo_dir,
        )
        all_notebooks = [f for f in ls_output.split("\n") if f.strip().endswith(".ipynb")]
        changed_info = {"changed": all_notebooks, "new": [], "deleted": []}
    else:
        if tracked == latest:
            print("✅ Already up to date", file=sys.stderr)
            print(json.dumps({
                "has_changes": False,
                "upstream_commit": latest,
                "previous_commit": tracked,
                "changed_files": [],
                "new_files": [],
                "deleted_files": [],
            }))
            return

        changed_info = get_changed_notebooks(repo_dir, tracked, latest)

    all_changes = changed_info["changed"] + changed_info["new"]

    if not all_changes and not changed_info["deleted"]:
        print("✅ No notebook changes", file=sys.stderr)
        save_tracked_commit(repo_dir, latest)
        print(json.dumps({
            "has_changes": False,
            "upstream_commit": latest,
            "previous_commit": tracked,
            "changed_files": [],
            "new_files": [],
            "deleted_files": [],
        }))
        return

    # Checkout changed/new files from upstream to staging area
    if all_changes:
        checkout_upstream_files(repo_dir, latest, all_changes)

    staging = os.path.join(repo_dir, ".upstream-staging")

    print(f"📋 Changes detected:", file=sys.stderr)
    for f in changed_info["changed"]:
        print(f"  M {f}", file=sys.stderr)
    for f in changed_info["new"]:
        print(f"  A {f}", file=sys.stderr)
    for f in changed_info["deleted"]:
        print(f"  D {f}", file=sys.stderr)

    # Output JSON for the GitHub Action to consume
    print(json.dumps({
        "has_changes": True,
        "upstream_commit": latest,
        "previous_commit": tracked,
        "changed_files": changed_info["changed"],
        "new_files": changed_info["new"],
        "deleted_files": changed_info["deleted"],
        "staging_dir": staging,
        "total_notebooks": len(all_changes),
    }))


if __name__ == "__main__":
    main()
