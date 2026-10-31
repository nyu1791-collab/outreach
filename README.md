# outreach — AI営業リスト抽出 ＆ パーソナライズ営業自動化

検索 → サイト解析 → 相手専用の営業文生成 → お問い合わせフォーム自動入力 → **人間が目視して送信**（半自動）までを1コマンドで回す。
メールアドレスしか無い相手は Gmail の下書きに自動保存。

[引き継ぎ・再開手順](docs/HANDOFF.md) に実装済みの範囲、状態の意味、未確認の外部連携をまとめています。`office-worker` の集客を担当しますが、受注から案件作成への自動連携は未実装です。

```
discover(Firecrawl検索) → scrape(Firecrawl + Gemini抽出) → write(Gemini) → fill(高速入力 → 難しければ browser-use) → 人間が送信
   new                      scraped                         written          filled → sent / skipped
                            no_contact → research(browser-use) → scraped
                            no_sales（営業お断り表記）は自動で除外 / mail_only → drafts(Gmail下書き)
```

## 取り込んだリポジトリ
| 元リポジトリ | 取り込み方 | このツールでの役割 |
|---|---|---|
| [browser-use/browser-use](https://github.com/browser-use/browser-use)（MIT） | 任意: `vendor/browser-use`（git submodule, 0.13.14）を editable install | ① 自動入力しにくいフォームを AI が読んで入力（入力欄の値はプレースホルダ化。署名を含む文面はAIへ渡る）② `research`: SNS等の連絡先・最新活動を調査 |
| [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl)（本体 AGPL / SDK MIT） | 任意: `vendor/firecrawl`（git submodule, v2.11.642）。本体は無改変で Docker 起動、SDK は editable install | JS描画サイトの Markdown 取得・問い合わせページ発見・検索。ローカル運用にもPC資源と外部APIの費用・制限がある |
| フォーム入力ツール一般の手法 | 自前実装 | ラベル/placeholder/name のキーワード照合で即入力（AI 代ゼロ）。2項目未満しか入らなければ browser-use へ自動切替 |

## 最短スタート（Windows）
```powershell
git clone https://github.com/nyu1791-collab/outreach.git
cd outreach
.\setup.ps1                       # 基本機能・venv・Chromium（AIブラウザ/Firecrawlは任意）
notepad .env                      # GEMINI_API_KEY を記入
notepad config.yaml               # 自分の名前・提案内容を記入
.\.venv\Scripts\Activate.ps1

python -m outreach discover "渋谷 美容室" -n 20
python -m outreach run --limit 10        # 解析→文面→フォーム入力。ブラウザで確認して送信→Enter
python -m outreach status
```

AIブラウザは `./setup.ps1 -WithBrowser`、Firecrawl SDKは `./setup.ps1 -WithFirecrawl` で追加します。Linuxは `bash setup.sh` に必要な時だけ `--with-browser` / `--with-firecrawl` を付けます。どちらも基本のCSV管理や文面生成に必須ではありません。

Firecrawlをローカル起動する場合は、SDKの追加後に `./scripts/firecrawl.ps1 up`（要Docker Desktop）を実行し、`.env` の `FIRECRAWL_API_URL=http://localhost:3002` を設定します。既存の `.env` にFirecrawl設定がある場合も、先に `-WithFirecrawl` でSDKを導入してください。

## キャンペーン（営業先の種類ごとに切替）
`config.yaml` の `campaigns` に、営業先ごとの提案・文面・連絡手段を書く。`--campaign 名前` で対象を付ける/絞る。

| キャンペーン | 相手 | 連絡手段 | 商品（office-worker） |
|---|---|---|---|
| `sales-csv` | 複数店舗の小売・飲食・EC | フォーム / メール | products/sales-csv-to-excel |
| `shop-diary` | 写メ日記を更新している店舗 | フォーム / メール | products/shop-diary |
| `creator-edit` | 動画を出しているクリエイター | **DM下書き**（送信は人） | products/creator-edit |
| `doujin` | 翻訳版の無い同人作家 | **DM下書き**＋サンプル画像 | products/doujin-translation |

```powershell
python -m outreach import 作家リスト.csv --campaign doujin      # 列: name,url,sample（sample は提案用の訳サンプル画像）
python -m outreach scrape --campaign doujin                       # 作品・販売数・翻訳版の有無を抽出（翻訳版ありは自動除外）
python -m outreach write --campaign doujin                        # → dm_ready
python -m outreach export-dm --campaign doujin                    # → data/dm_doujin.csv を見ながら手で送る
python -m outreach mark <id> sent                                 # 送ったら記録（replied / ng なども自由に）
python -m outreach status                                         # キャンペーン別の件数
```
- DM は**自動送信しない**（各SNSの規約・アカウント凍結対策）。X/MyFans などのプロフィールは `research` で browser-use に調べさせられる
- DLsite の年齢確認は `cookies` 設定で通過

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
- 問い合わせページの「営業お断り」を入力前に検査します。禁止表記の検出を保証するものではないため、人間も確認します。
- `filled` は入力済み、`sent` は送信完了確認済みです。確認画面への遷移だけでは自動で送信済みにしません。
- Gmail下書き保存が拒否された場合は理由を残し、次の `drafts` 実行で再試行します。
- 配信停止返信の自動取り込みは未実装です。不要と返答された相手は手動で `skipped` にして再連絡しないよう管理します。
- メール送信は特定電子メール法の表示義務あり（署名と配信停止文は `config.yaml` で自動付与）
- 既定の `daily_limit: 30` / `interval_sec: 5` を目安に

## Gemini の接続（情報収集・執筆・読み取り・翻訳）
1. キー発行: https://aistudio.google.com/apikey
2. PC（3リポジトリ共通で1回だけ）: PowerShell で `setx GEMINI_API_KEY "キー"` → PowerShell を開き直す（各 `.env` の `GEMINI_API_KEY=` は空のままでよい）
3. 確認: `python -m outreach llm-check`（用途ごとの接続先と、検索の裏付けが取れるかを表示）
4. 用途ごとの使い分けは `.env` の `GEMINI_MODEL_WRITE` 等（例: 記事だけ `gemini-2.5-pro`）。安全フィルタで止まる内容は `GEMINI_SAFETY=relaxed`、それでも止まる用途だけ `LLM_PROVIDER_<用途>=openrouter`

- このリポジトリでの用途: サイト内容の整理（extract）、**相手の最近の動きを Google 検索で出典付き調査**（research、`config.yaml` の `web_research`）、営業文・DM（write）
