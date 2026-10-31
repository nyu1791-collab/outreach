# outreach — AI営業リスト抽出 ＆ パーソナライズ営業自動化

検索 → サイト解析 → 相手専用の営業文生成 → お問い合わせフォーム自動入力 → **人間が目視して送信**（半自動）までを1コマンドで回す。
メールアドレスしか無い相手は Gmail の下書きに自動保存。

```
discover(検索) → scrape(連絡先/本文) → write(Gemini) → fill(Playwright / browser-use) → 人間が送信
   new            scraped               written          filled → sent / skipped
                  no_contact / mail_only → drafts(Gmail下書き)
```

## 参考にした仕組み
| 元ネタ | 取り込んだ部分 |
|---|---|
| [firecrawl](https://github.com/mendableai/firecrawl) | URL → LLM向けMarkdown化（キーがあれば Firecrawl、無ければ BeautifulSoup に自動フォールバック） |
| [browser-use](https://github.com/browser-use/browser-use) | `--agent` で AI がフォームを読んで入力（複雑・多段フォーム用） |
| 各種 form-filler / 営業リスト系ツール | ラベル・placeholder・name 属性のキーワード照合による高速入力（AIトークン不要） |
| n8n 的なステータス駆動 | 1行=1リード、`status` 列で次工程を決める。途中で止めても再実行で続きから |

## 最短スタート（Windows）
```powershell
git clone <このリポジトリ> ; cd outreach
.\setup.ps1                       # venv・ライブラリ・Chromium を一括導入
notepad .env                      # GEMINI_API_KEY を記入
notepad config.yaml               # 自分の名前・提案内容を記入
.\.venv\Scripts\Activate.ps1

python -m outreach discover "渋谷 美容室" -n 20
python -m outreach run --limit 10        # 解析→文面→フォーム入力。ブラウザで確認して送信→Enter
python -m outreach status
```

## コマンド
| コマンド | 内容 |
|---|---|
| `discover "クエリ" -n 20` | DuckDuckGo検索で候補サイトを追加（キー不要・ドメイン重複除外） |
| `add URL --name 名前` / `import file.csv` | 手動追加・CSV一括（列: `name,url`） |
| `scrape` | お問い合わせURL・メール・SNS・本文を取得 |
| `write` | `prompts/message.md` で1社ごとの営業文を生成（キー無しならテンプレ） |
| `fill` | フォーム自動入力 → `data/shots/<id>.png` に保存 → 人間が送信 |
| `fill --agent` | browser-use のAIエージェントで入力 |
| `fill --headless` | 画面なしで入力＋スクショのみ（`auto_submit: true` なら送信まで） |
| `drafts` | メールのみの相手を Gmail 下書きに保存（要アプリパスワード） |
| `run` | scrape → write → fill を連続実行 |

## データ置き場
- 既定: `data/leads.csv`（Excelで開ける）
- `.env` に `GOOGLE_SHEET_ID` とサービスアカウントJSONを置くと **Googleスプレッドシートが管理画面** になる（シートをサービスアカウントのメールに共有）

## 売り方
- 自分の受託案件（office-worker）の集客に使う
- 「営業代行 1件◯円」「自動営業システム構築 5〜15万円」としてココナラ/ランサーズで販売。`config.yaml` と `prompts/` を差し替えるだけで別クライアント用になる

## 注意
- 「営業お断り」と書かれたフォームには送らない（`write` 前に `summary` を見て `status` を `skipped` に変えればよい）
- メール送信は特定電子メール法の表示義務あり（署名と配信停止文は `config.yaml` で自動付与）
- 既定の `daily_limit: 30` / `interval_sec: 5` を目安に
