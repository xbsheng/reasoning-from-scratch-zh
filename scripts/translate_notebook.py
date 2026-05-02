#!/usr/bin/env python3
"""
translate_notebook.py — Incremental notebook translator

Translates Markdown cells in .ipynb files using OpenAI-compatible API.
Supports incremental translation: only re-translates cells whose source changed.

Each translated cell stores metadata:
  cell.metadata._translation.hash  — hash of original English source
  cell.metadata._translation.model — model used
  cell.metadata._translation.date  — translation timestamp

Usage:
    # Full translate (single file)
    python translate_notebook.py input.ipynb output.ipynb

    # Incremental (re-translate only changed cells)
    python translate_notebook.py upstream.ipynb existing-zh.ipynb --incremental

    # Batch (whole directory)
    python translate_notebook.py upstream_dir/ zh_dir/ --incremental

Environment:
    OPENAI_API_KEY     API key (required)
    OPENAI_BASE_URL    API base URL (default: https://api.openai.com/v1)
    TRANSLATE_MODEL    Model name (default: gpt-4o-mini)
"""

import json
import os
import sys
import re
import time
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    sys.exit(1)


def load_dotenv():
    """Load .env file from project root if present."""
    # Walk up from this script to find .env
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

# ── Config ──────────────────────────────────────────────────────

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("TRANSLATE_MODEL", "gpt-4o-mini")
RATE_LIMIT_DELAY = float(os.environ.get("TRANSLATE_DELAY", "0.5"))
MAX_RETRIES = 3
CHUNK_SIZE = 80

# ── Prompt ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional technical translator. Translate English markdown to Simplified Chinese.

Rules:
1. Translate ALL English text to Chinese.
2. Do NOT translate: inline code (`...`), code blocks (```...```), LaTeX ($...$, $$...$$), URLs, file paths, variable/function/class names.
3. Keep well-known tech proper nouns in English: PyTorch, CUDA, GitHub, Hugging Face, etc.
4. For terms with common Chinese equivalents, use them: reinforcement learning → 强化学习, neural network → 神经网络.
5. For terms the Chinese AI community commonly uses in English, keep them: token, embedding, prompt, checkpoint, batch, epoch, etc.
6. For less common terms, use Chinese (English) on first occurrence, then just Chinese: 思维链 (Chain-of-Thought).
7. Keep ALL markdown formatting EXACTLY: headers, lists, bold, italic, links, tables, horizontal rules.
8. Preserve line breaks and paragraph structure.
9. Return ONLY the translated markdown. No explanations."""


# ── Helpers ─────────────────────────────────────────────────────

def cell_hash(source_lines: list[str]) -> str:
    """SHA256 of the cell source for change detection."""
    text = "".join(source_lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_cell_translation_meta(cell: dict) -> dict | None:
    """Get stored translation metadata from a cell."""
    meta = cell.get("metadata", {})
    return meta.get("_translation")


def set_cell_translation_meta(cell: dict, original_hash: str):
    """Store translation metadata in a cell."""
    if "metadata" not in cell:
        cell["metadata"] = {}
    cell["metadata"]["_translation"] = {
        "hash": original_hash,
        "model": MODEL,
        "date": datetime.now(timezone.utc).isoformat(),
    }


def should_skip(cell_source: list[str]) -> bool:
    text = "".join(cell_source).strip()
    if not text or len(text) < 5:
        return True
    return False


def is_code_only(cell_source: list[str]) -> bool:
    text = "".join(cell_source)
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    cleaned = re.sub(r'`[^`]+`', '', cleaned)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    return len(cleaned.strip()) < 10


def split_chunks(lines: list[str], size: int) -> list[list[str]]:
    if len(lines) <= size:
        return [lines]
    chunks, cur = [], []
    for line in lines:
        cur.append(line)
        if len(cur) >= size and line.strip() == "":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


# ── Translation ─────────────────────────────────────────────────

def translate_text(client: OpenAI, text: str) -> str:
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Translate:\n\n{text}"},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            result = resp.choices[0].message.content.strip()
            if result:
                return result
            print(f"  ⚠ Empty, retry {attempt+1}/{MAX_RETRIES}")
        except Exception as e:
            print(f"  ⚠ {e}, retry {attempt+1}/{MAX_RETRIES}")
        time.sleep(2 ** attempt)
    print("  ✗ Failed, keeping original")
    return text


def translate_cell_source(client: OpenAI, source: list[str]) -> list[str]:
    text = "".join(source)
    chunks = split_chunks(source, CHUNK_SIZE)
    if len(chunks) == 1:
        translated = translate_text(client, text)
        if source and source[-1].endswith("\n") and not translated.endswith("\n"):
            translated += "\n"
        return [translated]
    else:
        parts = []
        for i, chunk in enumerate(chunks):
            t = translate_text(client, "".join(chunk))
            parts.append(t)
            if i < len(chunks) - 1:
                parts.append("\n")
        return ["\n".join(parts) + "\n"]


# ── Notebook Processing ─────────────────────────────────────────

def process_notebook_full(client: OpenAI, nb: dict, save_fn=None) -> int:
    """Full translation of all markdown cells. Returns count of translated cells."""
    count = 0
    for i, cell in enumerate(nb.get("cells", [])):
        if cell["cell_type"] != "markdown":
            continue
        src = cell["source"]
        if should_skip(src) or is_code_only(src):
            continue
        preview = "".join(src)[:50].replace("\n", " ")
        print(f"  🔄 [{i+1}] {preview}...")
        original_h = cell_hash(src)
        cell["source"] = translate_cell_source(client, src)
        set_cell_translation_meta(cell, original_h)
        count += 1
        if save_fn:
            save_fn(nb)
        time.sleep(RATE_LIMIT_DELAY)
    return count


def process_notebook_incremental(client: OpenAI, upstream_nb: dict, existing_nb: dict | None, save_fn=None) -> tuple[int, int, int]:
    """
    Incremental translation. Compares upstream cells against existing translation.
    Returns (translated, reused, new) counts.
    """
    translated = reused = new = 0

    # Build lookup from existing translated notebook
    # Key: cell index, Value: (translated_source, translation_meta)
    existing_map = {}
    if existing_nb:
        for idx, cell in enumerate(existing_nb.get("cells", [])):
            meta = get_cell_translation_meta(cell)
            existing_map[idx] = (cell["source"], meta)

    for i, cell in enumerate(upstream_nb.get("cells", [])):
        if cell["cell_type"] != "markdown":
            continue

        src = cell["source"]
        current_h = cell_hash(src)

        if should_skip(src) or is_code_only(src):
            # Keep upstream source as-is (it's code or trivial)
            continue

        # Check if we have an existing translation for this cell position
        if i in existing_map:
            existing_src, existing_meta = existing_map[i]
            if existing_meta and existing_meta.get("hash") == current_h:
                # Source unchanged — reuse existing translation
                cell["source"] = existing_src
                cell["metadata"] = cell.get("metadata", {})
                cell["metadata"]["_translation"] = existing_meta
                reused += 1
                continue

        # Self-translation check: cell already has _translation metadata
        # (happens when input=output — the cell IS the translated version)
        self_meta = get_cell_translation_meta(cell)
        if self_meta and self_meta.get("model"):
            # Already translated, reuse as-is
            reused += 1
            continue

        # Need to translate (new cell or source changed)
        preview = "".join(src)[:50].replace("\n", " ")
        action = "🔄 NEW " if i not in existing_map else "🔄 CHG "
        print(f"  {action}[{i+1}] {preview}...")
        cell["source"] = translate_cell_source(client, src)
        set_cell_translation_meta(cell, current_h)
        translated += 1
        if save_fn:
            save_fn(upstream_nb)
        time.sleep(RATE_LIMIT_DELAY)

    return translated, reused, new


# ── Main Logic ──────────────────────────────────────────────────

def translate_file(client: OpenAI, input_path: str, output_path: str, incremental: bool = False):
    """Translate a single notebook file."""
    print(f"\n📄 {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        upstream_nb = json.load(f)

    existing_nb = None
    if incremental and os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            existing_nb = json.load(f)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def save_progress(nb):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, ensure_ascii=False, indent=1)

    if incremental and existing_nb:
        translated, reused, _ = process_notebook_incremental(client, upstream_nb, existing_nb, save_fn=save_progress)
        total = translated + reused
        print(f"  📊 {total} markdown cells: {reused} reused, {translated} translated")
    else:
        count = process_notebook_full(client, upstream_nb, save_fn=save_progress)
        print(f"  📊 {count} cells translated")

    # Final save
    save_progress(upstream_nb)
    print(f"  💾 → {output_path}")


def batch_translate(client: OpenAI, input_dir: str, output_dir: str, incremental: bool = False):
    """Translate all .ipynb files in a directory tree."""
    inp = Path(input_dir)
    notebooks = sorted(inp.rglob("*.ipynb"))
    # Exclude hidden dirs, staging, test artifacts, checkpoints
    exclude_names = {".ipynb_checkpoints", ".test-upstream", ".test-output",
                     ".upstream-staging", ".git", "__pycache__", "node_modules"}
    def is_excluded(p: Path) -> bool:
        parts = p.relative_to(inp).parts
        return any(part in exclude_names or part.startswith(".") for part in parts)
    notebooks = [n for n in notebooks if not is_excluded(n)]

    print(f"📚 Found {len(notebooks)} notebooks")

    total_translated = 0
    total_reused = 0

    for nb_path in notebooks:
        rel = nb_path.relative_to(inp)
        out_path = Path(output_dir) / rel
        translate_file(client, str(nb_path), str(out_path), incremental=incremental)

    print(f"\n✅ All done!")


def main():
    parser = argparse.ArgumentParser(description="Translate .ipynb notebooks (English → Chinese)")
    parser.add_argument("input", help="Input .ipynb file or directory")
    parser.add_argument("output", nargs="?", help="Output file or directory")
    parser.add_argument("--incremental", "-i", action="store_true",
                        help="Incremental mode: only re-translate changed cells")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--base-url", help="Override base URL")
    parser.add_argument("--api-key", help="Override API key")
    parser.add_argument("--delay", type=float, help="Rate limit delay (sec)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")

    args = parser.parse_args()

    global API_KEY, BASE_URL, MODEL, RATE_LIMIT_DELAY
    if args.api_key:
        API_KEY = args.api_key
    if args.base_url:
        BASE_URL = args.base_url
    if args.model:
        MODEL = args.model
    if args.delay is not None:
        RATE_LIMIT_DELAY = args.delay

    if not API_KEY:
        print("Error: OPENAI_API_KEY required")
        sys.exit(1)

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    print(f"🤖 Model: {MODEL} @ {BASE_URL}")

    input_path = Path(args.input)

    if input_path.is_dir():
        output_dir = args.output or str(input_path.parent / (input_path.name + "-zh"))
        if args.dry_run:
            inp = Path(str(input_path))
            exclude_names = {".ipynb_checkpoints", ".test-upstream", ".test-output",
                             ".upstream-staging", ".git", "__pycache__", "node_modules"}
            notebooks = sorted(inp.rglob("*.ipynb"))
            notebooks = [n for n in notebooks if not any(
                part in exclude_names or part.startswith("."
                ) for part in n.relative_to(inp).parts)]
            print(f"🔍 Dry run: {len(notebooks)} notebooks to translate")
            for nb in notebooks:
                print(f"  📄 {nb.relative_to(inp)}")
        else:
            batch_translate(client, str(input_path), output_dir, incremental=args.incremental)
    else:
        output = args.output or (input_path.stem + "-zh" + ".ipynb")
        translate_file(client, str(input_path), output, incremental=args.incremental)


if __name__ == "__main__":
    main()
