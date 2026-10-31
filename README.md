# outreach — AI営業リスト抽出 ＆ パーソナライズ営業自動化

検索 → サイト解析 → 相手専用の営業文生成 → お問い合わせフォーム自動入力 → **人間が目視して送信**（半自動）までを1コマンドで回す。
メールアドレスしか無い相手は Gmail の下書きに自動保存。

```
discover(Firecrawl検索) → scrape(Firecrawl + Gemini抽出) → write(Gemini) → fill(高速入力 → 難しければ browser-use) → 人間が送信
   new                      scraped                         written          filled → sent / skipped
                            no_contact → research(browser-use) → scraped
                            no_sales（営業お断り表記）は自動で除外 / mail_only → drafts(Gmail下書き)
```

## 取り込んだリポジトリ
| 元リポジトリ | 取り込み方 | このツールでの役割 |
|---|---|---|
| [browser-use/browser-use](https://github.com/browser-use/browser-use)（MIT） | `vendor/browser-use`（git submodule, 0.13.14）を editable install | ① 自動入力しにくいフォームを AI が読んで入力（構造化結果・個人情報はプレースホルダで LLM に見せない・対象ドメイン外へ移動禁止）② `research`: YouTuber/SNS の連絡先・最新活動を調査（公式サンプル find_influencer_profiles を応用） |
| [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl)（本体 AGPL / SDK MIT） | `vendor/firecrawl`（git submodule, v2.11.642）。本体は無改変で Docker 起動、SDK は editable install | JS描画サイトも綺麗な Markdown で取得・サイトマップから問い合わせページ発見（map）・検索（search）。ローカル起動ならキー不要・無制限 |
| フォーム入力ツール一般の手法 | 自前実装 | ラベル/placeholder/name のキーワード照合で即入力（AI 代ゼロ）。2項目未満しか入らなければ browser-use へ自動切替 |

## 最短スタート（Windows）
```powershell
git clone --recursive <このリポジトリ> ; cd outreach
.\setup.ps1                       # submodule取得・venv・ライブラリ・Chromium を一括導入
.\scripts\firecrawl.ps1 up        # （任意・要Docker Desktop）Firecrawl をローカル起動 → .env に FIRECRAWL_API_URL=http://localhost:3002
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
| `scrape` | Firecrawl で取得 → Gemini で「会社名・概要・最近の動き・課題仮説・冒頭フック・営業お断り」を抽出、問い合わせURL/メール/SNS も取得 |
| `research` | 連絡先が見つからない相手を browser-use が SNS・YouTube概要欄・検索で調査 |
| `write` | `prompts/message.md` で1社ごとの営業文を生成（キー無しならテンプレ） |
| `fill` | フォーム自動入力（入らなければ browser-use に自動切替）→ `data/shots/<id>.png` → 人間が送信 |
| `fill --agent` | 最初から browser-use の AI エージェントで入力 |
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
