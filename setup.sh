#!/usr/bin/env bash
# Mac/Linux/WSL。追加機能だけ明示的に導入する。
set -euo pipefail
cd "$(dirname "$0")"
with_browser=false
with_firecrawl=false
for option in "$@"; do
  case "$option" in
    --with-browser) with_browser=true ;;
    --with-firecrawl) with_firecrawl=true ;;
    *) echo "不明なオプション: $option" >&2; exit 2 ;;
  esac
done
python3 -c 'import sys; sys.exit("Python 3.12以上を使用してください" if sys.version_info < (3, 12) else 0)'
python3 -m venv .venv
PYTHON=.venv/bin/python
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt
if "$with_browser"; then
  git submodule update --init --depth 1 vendor/browser-use
  "$PYTHON" -m pip install -r requirements-browser.txt
fi
if "$with_firecrawl"; then
  git submodule update --init --depth 1 vendor/firecrawl
  "$PYTHON" -m pip install -r requirements-firecrawl.txt
fi
"$PYTHON" -m playwright install chromium
if [ ! -f .env ]; then cp .env.example .env; fi
echo "完了: source .venv/bin/activate"
