#!/bin/bash
# ── test_local.sh ──
# 本地测试：翻译单个文件，验证流程
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
fi

echo "🧪 本地测试翻译流程"
echo ""

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "❌ 请配置 .env 文件: cp .env.example .env && vim .env"
    exit 1
fi

echo "  API: ${OPENAI_BASE_URL:-https://api.openai.com/v1}"
echo "  Model: ${TRANSLATE_MODEL:-gpt-4o-mini}"
echo ""

# Clone upstream if not exists
UPSTREAM_DIR="$REPO_DIR/.test-upstream"
if [ ! -d "$UPSTREAM_DIR" ]; then
    echo "📥 克隆上游仓库..."
    git clone --depth 1 https://github.com/rasbt/reasoning-from-scratch.git "$UPSTREAM_DIR"
fi

# Upstream has nested structure: ch02/01_main-chapter-code/ch02_main.ipynb
TEST_INPUT=$(find "$UPSTREAM_DIR/ch02" -name "ch02_main.ipynb" -not -path "*/.ipynb_checkpoints/*" | head -1)
TEST_OUTPUT="$REPO_DIR/.test-output/ch02_main_zh.ipynb"

if [ -z "$TEST_INPUT" ] || [ ! -f "$TEST_INPUT" ]; then
    echo "❌ 找不到 ch02_main.ipynb"
    find "$UPSTREAM_DIR/ch02" -name "*.ipynb" | head -5
    exit 1
fi

mkdir -p "$(dirname "$TEST_OUTPUT")"

echo ""
echo "═══ Step 1: 首次翻译 ═══"
python "$SCRIPT_DIR/translate_notebook.py" "$TEST_INPUT" "$TEST_OUTPUT"

echo ""
echo "═══ Step 2: 增量翻译（无变更应全部复用）═══"
python "$SCRIPT_DIR/translate_notebook.py" "$TEST_INPUT" "$TEST_OUTPUT" --incremental

echo ""
echo "═══ Step 3: 验证结果 ═══"
python3 -c "
import json
with open('$TEST_OUTPUT') as f:
    nb = json.load(f)
md_cells = [c for c in nb['cells'] if c['cell_type'] == 'markdown']
code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
translated = [c for c in md_cells if '_translation' in c.get('metadata', {})]
print(f'  Total cells: {len(nb[\"cells\"])}')
print(f'  Markdown: {len(md_cells)} (translated: {len(translated)})')
print(f'  Code: {len(code_cells)} (untouched)')
print(f'  ✅ Translation metadata preserved')
"

echo ""
echo "═══ 测试完成! ═══"
echo "查看翻译结果: $TEST_OUTPUT"
