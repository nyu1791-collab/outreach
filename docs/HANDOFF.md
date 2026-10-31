# outreach 引き継ぎ

## 目的と構成

事業3の営業支援です。候補検索 → 企業サイト解析 → 個別提案文 → フォーム入力 → 人間の最終確認、メールだけの相手にはGmail下書きを作ります。`office-worker` の受託ツールを売るために使えますが、受注から案件フォルダを自動作成する連携は未実装です。

[3リポジトリの構成・合併判断](https://github.com/nyu1791-collab/office-worker/blob/bde57750200924a357414216a13248c7a1720894/docs/BUSINESS_ARCHITECTURE.md)に従い、リポジトリ名は継続。動画制作・動画編集は対象外です。

## 今回の修正

- 実際の問い合わせページにも営業お断り表記があれば入力しない。
- 確認画面への移動だけで `sent` と記録しない。自動処理は送信完了の根拠を要求。
- Gmail APPENDの拒否を検出。保存失敗は `mail_only` と理由を残し、`drafts` の再実行で再試行。
- CSVの欠損URLを読み飛ばし、未対応文字コードを明示エラーにする。
- AIブラウザとFirecrawlの依存は任意導入。基本のフォーム入力はPlaywright。
- 外部通信なしの回帰テストとテスト用Actionsを追加。

## 追加の見直しで修正した点

- `--limit` / `-n` の負数を拒否。`0` は設定読み込みや外部処理を行わず終了。
- CSVは一時ファイルへ書き込み、書き込み成功後に置換。途中失敗で既存の履歴を消さない。
- Sheetsは先に全件削除せず、不要な末尾行を空欄にした1回の更新で置換。
- フォームとGmail下書きは、副作用の前に `filling` / `drafting` を保存。中断後は自動で再実行しない。
- Gmailの明確な保存拒否は再試行できるが、APPENDの応答不明は `draft_uncertain` として保留。
- フォーム試行日時を記録し、スキップ・失敗も日次枠に含める。改行や「営業目的での」「営業・勧誘目的」等の禁止表記にも対応。

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

通常テストでは実ブラウザのテストを省略します。ChromiumのDOM検証も行う場合は `OUTREACH_BROWSER_TESTS=1` を指定し、必要なら `CHROME_PATH` で実行ファイルを選びます。ローカルChromiumでメモリ内HTMLを使った5件を含む29件が成功しました。実際の企業サイトや送信先へ接続するテストではありません。

Python 3.12の専用venvに基本依存を導入し、`pip check` と `status` も確認しました。ブラウザ未導入での通常実行はDOM検証5件を省略し、24件を実行します。

## 状態と運用

通常の状態は `new → scraped → written → filled → sent`。`no_sales`、`no_contact`、`mail_only`、`drafted`、`skipped`、`error` もあります。CSVは `data/leads.csv`、Sheets設定時はシートを使います。

外部処理の前には `filling` / `drafting` を保存します。この状態が次回まで残っている場合、または `fill_uncertain` / `draft_uncertain` の場合は、送信・保存が完了したか不明なので自動再実行しません。対象サイトやGmailの実際の状態と照合してください。未処理と確認できた場合だけ、データをバックアップしたうえでフォームは `written`、メールは `mail_only` に戻します。処理済みなら `sent` / `drafted` に変更します。

`form_attempted_at` はフォームへの入力を試みた日時です。入力後にスキップした場合や処理結果が不明な場合も日次枠を消費します。旧形式でこの列がない履歴は、従来の `filled/sent` と更新日で数えます。CSV/Sheetsを同時に複数のプロセスから書き換えないでください。

既定 `auto_submit: false`。画面ありの入力でEnterを押す操作は「自分で送信した」という人間の申告です。`filled` は未送信または結果未確定であり、`sent` と区別してください。自動判定は完了文言を使うため、全フォームでの確定を保証するものではありません。

`config.yaml` の氏名・連絡先・offerは例です。自分の情報と実際に提供できる商品へ変更します。返信や配信停止の自動取り込みはないので、不要と返答された相手は人間が `skipped` にし、再送しないよう管理します。

## 未確認・次の作業

Windows PowerShell 5.1での基本セットアップと回帰テストをCIへ追加しています。`windows-setup` はChromium DOM検証も含めて実行します。実行結果はPRで確認できます。`setup.ps1` は日本語を正しく読むためUTF-8 BOM付きで保存します。

出力先が日本語を扱えない場合は、その文字だけをエスケープして処理を続けます。日本語のログをそのまま保存したい場合は、起動前に `PYTHONIOENCODING=utf-8` を設定します。コンソールの既存の文字コードは自動変更しません。

Gemini、実browser-use SDK、Firecrawl、Sheets、Gmail本接続、実サイトのフォーム操作は今回未検証です。入力欄の値はプレースホルダ化しますが、署名を含む営業文もAIブラウザへ渡るため、個人情報が一切AIに渡らない設計ではありません。

まず売上CSV→Excel集計という1商品にofferを揃え、少数の候補について根拠のある文面と送信先を確認します。価格・納期・収益は実測で決める段階です。

## 2026-10-31 追記
- `config.yaml` の `offer` を商品「売上CSV集計」（office-worker/products/sales-csv-to-excel）に合わせた。`short`（AIキー無しのテンプレ用）と `target_hint`（1店舗の相手には売り込まない）を追加
- Googleシート保存で行数が既定の1000行を超えると範囲外エラーになっていた → 更新前にシートを拡張（回帰テスト追加）

## 2026-10-31 見直し（2回目）
- フォーム入力後の確認は **y=送信した / s=送らない / Enter=入力だけ（未送信）**。Enter だけで「送信済み」にしない
- 姓/名・セイ/メイの分割欄に分けて入力（同じ表の行に並ぶ配置も直前の見出しで判定）。都道府県は送り手住所から選ぶ。当てはまらない選択肢は選ばない（以前は末尾を選んでいた）
- Gmail 下書きはサイトと同じドメインのアドレスにだけ作る。別ドメインだけの相手は `mail_check`（制作会社のクレジット等の誤送信防止）。確認後に `email` 列を直して `status` を `mail_only` に戻す
- AI の応答に本文が無い/短い場合はテンプレ文面にする（署名だけのメッセージを防ぐ）
