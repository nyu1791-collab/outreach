# 取り込んだ外部ソフトウェア
| パス | 取得元 | ライセンス | 備考 |
|---|---|---|---|
| vendor/browser-use | https://github.com/browser-use/browser-use (0.13.14) | MIT | 無改変の git submodule |
| vendor/firecrawl | https://github.com/firecrawl/firecrawl (v2.11.642) | 本体 AGPL-3.0 / apps/python-sdk は MIT | 無改変。本体は別プロセス（Docker）で起動し HTTP で利用。本体を改変して外部にサービス提供する場合は AGPL に従いソース公開が必要 |
