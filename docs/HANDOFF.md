# outreach 引き継ぎ

## 目的と構成

事業3の営業支援です。候補検索 → 企業サイト解析 → 個別提案文 → フォーム入力 → 人間の最終確認、メールだけの相手にはGmail下書きを作ります。`office-worker` の受託ツールを売るために使えますが、受注から案件フォルダを自動作成する連携は未実装です。

[3リポジトリの構成・合併判断](https://github.com/nyu1791-collab/office-worker/blob/ccr-aac984d0-n27k7c/docs/BUSINESS_ARCHITECTURE.md)に従い、リポジトリ名は継続。動画制作・動画編集は対象外です。

## 今回の修正

- 実際の問い合わせページにも営業お断り表記があれば入力しない。
- 確認画面への移動だけで `sent` と記録しない。自動処理は送信完了の根拠を要求。
- Gmail APPENDの拒否を検出。保存失敗は `mail_only` と理由を残し、`drafts` の再実行で再試行。
- CSVの欠損URLを読み飛ばし、未対応文字コードを明示エラーにする。
- AIブラウザとFirecrawlの依存は任意導入。基本のフォーム入力はPlaywright。
- 外部通信なしの回帰テストとテスト用Actionsを追加。

## 再開コマンド

```powershell
.\setup.ps1
.\.venv\Scripts\python -m outreach status
.\.venv\Scripts\python -m unittest discover -s tests -v
# 必要になった機能だけ追加
.\setup.ps1 -WithBrowser
.\setup.ps1 -WithFirecrawl
```

`status` と回帰テストは営業送信を行いません。Linuxは `bash setup.sh`、追加機能は `--with-browser` / `--with-firecrawl` です。

通常テストでは実ブラウザのテストを省略します。ChromiumのDOM検証も行う場合は `OUTREACH_BROWSER_TESTS=1` を指定し、必要なら `CHROME_PATH` で実行ファイルを選びます。今回、ローカルChromiumでメモリ内HTMLを使った4件を含む12件を確認しました。実際の企業サイトや送信先へ接続するテストではありません。

Python 3.12の専用venvに基本依存を導入し、`pip check` と `status` も確認しました。通常のテストCIはブラウザ4件を省略し、8件を実行します。

## 状態と運用

通常の状態は `new → scraped → written → filled → sent`。`no_sales`、`no_contact`、`mail_only`、`drafted`、`skipped`、`error` もあります。CSVは `data/leads.csv`、Sheets設定時はシートを使います。

既定 `auto_submit: false`。画面ありの入力でEnterを押す操作は「自分で送信した」という人間の申告です。`filled` は未送信または結果未確定であり、`sent` と区別してください。自動判定は完了文言を使うため、全フォームでの確定を保証するものではありません。

`config.yaml` の氏名・連絡先・offerは例です。自分の情報と実際に提供できる商品へ変更します。返信や配信停止の自動取り込みはないので、不要と返答された相手は人間が `skipped` にし、再送しないよう管理します。

## 未確認・次の作業

WindowsのPowerShellセットアップは今回未検証です。

Gemini、実browser-use SDK、Firecrawl、Sheets、Gmail本接続、実サイトのフォーム操作は今回未検証です。入力欄の値はプレースホルダ化しますが、署名を含む営業文もAIブラウザへ渡るため、個人情報が一切AIに渡らない設計ではありません。

まず売上CSV→Excel集計という1商品にofferを揃え、少数の候補について根拠のある文面と送信先を確認します。価格・納期・収益は実測で決める段階です。
