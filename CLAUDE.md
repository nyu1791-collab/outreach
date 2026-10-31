# outreach
- 再開時は `docs/HANDOFF.md` を読む。基本導入は submodule 不要、AIブラウザ / Firecrawl は `setup.ps1 -WithBrowser/-WithFirecrawl` で追加。検証は `python -m unittest discover -s tests -v`。
- 実行: `python -m outreach <cmd>`。エントリは `outreach/__main__.py`
- 工程は `status` 列で進む: new→scraped→written→filled→sent。工程追加は `step(from, to, fn, limit)` を1つ足すだけ
- データ層は `store.Table`（CSV / Googleシート自動切替）。列を増やすなら `COLS` に追記
- LLM は `llm.ask(prompt, json_mode=True)`。キー無しで None → 呼び出し側でフォールバック
- 文面の調整は `prompts/message.md` と `config.yaml` だけ触れば済む
- 取り込み元は `vendor/`（submodule・改変しない）。browser-use 連携は `outreach/agent.py`、Firecrawl は `outreach/fc.py`
