#!/usr/bin/env python3
"""
run_translate.py — Bridge script: reads sync_result.json, runs translations.

Usage:
    python run_translate.py sync_result.json repo_dir [--incremental]

This script:
  1. Reads the sync result (from sync_upstream.py)
  2. For each changed/new notebook, copies upstream version and translates
  3. In incremental mode, compares cell-by-cell and only re-translates changed cells
"""

import json
import os
import sys
import shutil
import argparse
from pathlib import Path

# Import translation engine
sys.path.insert(0, os.path.dirname(__file__))
from translate_notebook import (
    OpenAI, API_KEY, BASE_URL, MODEL,
    translate_file,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sync_result", help="Path to sync_result.json")
    parser.add_argument("repo_dir", default=".", help="Repository root directory")
    parser.add_argument("--incremental", "-i", action="store_true", help="Incremental translation")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--base-url", help="Override base URL")
    parser.add_argument("--api-key", help="Override API key")
    args = parser.parse_args()

    global API_KEY, BASE_URL, MODEL
    if args.api_key:
        API_KEY = args.api_key
    if args.base_url:
        BASE_URL = args.base_url
    if args.model:
        MODEL = args.model

    if not API_KEY:
        print("Error: OPENAI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    # Load sync result
    with open(args.sync_result) as f:
        sync = json.load(f)

    if not sync.get("has_changes"):
        print("✅ No changes to translate")
        return

    repo_dir = os.path.abspath(args.repo_dir)
    staging_dir = sync.get("staging_dir", os.path.join(repo_dir, ".upstream-staging"))

    changed = sync.get("changed_files", [])
    new = sync.get("new_files", [])
    deleted = sync.get("deleted_files", [])
    all_files = changed + new

    if not all_files:
        print("✅ No notebooks to translate")
        return

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    print(f"🤖 Model: {MODEL} @ {BASE_URL}")
    print(f"📋 Processing {len(changed)} changed + {len(new)} new notebooks\n")

    translated_count = 0
    failed = []

    for filepath in all_files:
        upstream_file = os.path.join(staging_dir, filepath)
        output_file = os.path.join(repo_dir, filepath)

        if not os.path.exists(upstream_file):
            print(f"⚠ Staging file missing: {filepath}")
            continue

        try:
            if args.incremental:
                # Use existing translated file for cell-level comparison
                translate_file(client, upstream_file, output_file, incremental=True)
            else:
                translate_file(client, upstream_file, output_file, incremental=False)
            translated_count += 1
        except Exception as e:
            print(f"  ✗ Error translating {filepath}: {e}")
            failed.append(filepath)

    # Handle deleted files
    for filepath in deleted:
        output_file = os.path.join(repo_dir, filepath)
        if os.path.exists(output_file):
            print(f"  🗑 Removing deleted file: {filepath}")
            os.remove(output_file)

    print(f"\n{'='*50}")
    print(f"✅ Translated: {translated_count}/{len(all_files)}")
    if failed:
        print(f"✗ Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
