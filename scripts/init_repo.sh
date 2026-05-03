#!/bin/bash
# ── init_repo.sh ──
# 初始化中文翻译仓库：创建 GitHub 仓库 + 首次全量翻译
#
# 用法:
#   ./scripts/init_repo.sh [--skip-translate]
#
# 配置:
#   .env 文件或环境变量中设置 OPENAI_API_KEY, OPENAI_BASE_URL, TRANSLATE_MODEL

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
REPO_NAME="reasoning-from-scratch-zh"
UPSTREAM="https://github.com/rasbt/reasoning-from-scratch.git"

# Load .env
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    source "$REPO_DIR/.env"
    set +a
fi

echo "═══════════════════════════════════════"
echo "  📖 reasoning-from-scratch 中文翻译"
echo "  初始化仓库 + 首次全量翻译"
echo "═══════════════════════════════════════"
echo ""

# Check prerequisites
echo "🔍 检查环境..."
command -v gh >/dev/null 2>&1 || { echo "❌ 需要 gh CLI: https://cli.github.com/"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "❌ 请先登录 gh: gh auth login"; exit 1; }

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "❌ 需要设置 API 配置"
    echo "   方法1: 编辑 .env 文件 (cp .env.example .env)"
    echo "   方法2: export OPENAI_API_KEY=your-key"
    exit 1
fi

echo "  ✅ gh CLI 已登录"
echo "  ✅ API: ${OPENAI_BASE_URL:-https://api.openai.com/v1} / ${TRANSLATE_MODEL:-gpt-4o-mini}"
echo ""

# Create GitHub repo
echo "📦 创建 GitHub 仓库: $REPO_NAME ..."
if gh repo view "$(gh auth status --hostname github.com 2>&1 | grep -oP '(?<=account )\S+')/$REPO_NAME" &>/dev/null; then
    echo "  ℹ️  仓库已存在，跳过创建"
else
    gh repo create "$REPO_NAME" --public \
        --description "《Build A Reasoning Model (From Scratch)》中文翻译 | Chinese translation"
    echo "  ✅ 仓库已创建"
fi

# Initialize local git if not already
cd "$REPO_DIR"
if [ ! -d ".git" ]; then
    git init
    git remote add origin "git@github.com:$(gh auth status --hostname github.com 2>&1 | grep -oP '(?<=account )\S+')/$REPO_NAME.git"
fi

# Add upstream remote
git remote remove upstream 2>/dev/null || true
git remote add upstream "$UPSTREAM"

# Fetch upstream and copy notebooks
echo ""
echo "📥 同步上游仓库..."
git fetch upstream

if [ ! -f ".upstream-commit" ]; then
    # Initialize commit tracking
    python "$SCRIPT_DIR/sync_upstream.py" --repo-dir "$REPO_DIR" --init

    # Copy upstream notebook files
    echo "📋 复制上游 notebook 文件..."
    TMPDIR=$(mktemp -d)
    git clone --depth 1 "$UPSTREAM" "$TMPDIR/upstream" --quiet

    find "$TMPDIR/upstream" -name "*.ipynb" -not -path "*/.ipynb_checkpoints/*" | while read f; do
        rel="${f#$TMPDIR/upstream/}"
        mkdir -p "$(dirname "$rel")"
        cp "$f" "$rel"
        echo "  📄 $rel"
    done

    rm -rf "$TMPDIR"
    echo "  ✅ 上游文件已复制"
fi

# Full translation
if [ "${1:-}" != "--skip-translate" ]; then
    echo ""
    echo "🚀 开始全量翻译..."
    echo "   模型: ${TRANSLATE_MODEL:-gpt-4o-mini}"
    echo "   地址: ${OPENAI_BASE_URL:-https://api.openai.com/v1}"
    echo "   (这可能需要较长时间)"
    echo ""

    python "$SCRIPT_DIR/translate_notebook.py" "$REPO_DIR" "$REPO_DIR" 2>&1 | tee translate_init.log

    echo ""
    echo "✅ 全量翻译完成!"
fi

# Initial commit & push
echo ""
echo "📝 提交并推送..."
git add -A
git commit -m "init: full Chinese translation of reasoning-from-scratch

- Model: ${TRANSLATE_MODEL:-gpt-4o-mini}
- Upstream: $UPSTREAM
- Cell-level translation metadata for incremental updates" \
    --allow-empty

git push -u origin main 2>/dev/null || git push origin main

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ 初始化完成!"
echo ""
echo "  📋 下一步 (在 GitHub 仓库中配置):"
echo "  1. Settings → Secrets → Actions → New secret:"
echo "     Name: TRANSLATE_API_KEY"
echo "     Value: <你的 API 秘钥>"
echo ""
echo "  2. Settings → Variables → New variable:"
echo "     TRANSLATE_BASE_URL = https://token-plan-cn.xiaomimimo.com/v1"
echo "     TRANSLATE_MODEL = mimo-v2.5-pro"
echo ""
echo "  3. GitHub Action 将每天北京时间 00:00 自动运行"
echo "═══════════════════════════════════════"
