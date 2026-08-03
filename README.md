# WYOC Japan Tracker

2026年ハイフェイ世界ユース大会の日本代表3チームを追跡し、WBF公式ページの結果から注目ボードとダブルダミー解析を日本語Markdown／JSONで生成します。

対象は `U26 JAPAN`、`U21 JAPAN`、`U26 Women JAPAN` の3チームです。`JAPONG` は対象外です。

## ローカル実行

Python 3.11（または互換版）で依存関係をインストールします。

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m wyoc_tracker.cli --round 1 --output-dir reports
```

生成物は `reports/round-01.md` と `reports/round-01.json` です。取得済みHTMLは `data/cache/` にURLのSHA-256名で保存され、同じラウンドの再実行時に再利用できます。`--no-cache` を付けると再取得します。

ネットワークを使わずDDSと表示を確認する場合は、同梱のBoard 6を使います。

```bash
python -m wyoc_tracker.cli --round 1 --input data/sample_round1.json --output-dir reports
```

## GitHub Actions

Actionsの **Analyze WYOC Japan round** を `workflow_dispatch` で起動し、`round_number` を入力します。テスト、WBF取得、DDS、レポート生成を行い、Markdown・JSON・取得キャッシュをartifactに保存します。

現在は誤ったラウンドを自動生成しないよう、定期実行を無効にしています。大会日程と公式結果から対象ラウンドを安全に特定する処理を追加した後にscheduleを有効化します。

## 解析仕様

- PBNは52枚の重複と各13枚を検証し、不完全な手はDDSを実行しません。
- DDSは `North/South/East/West × NT/♠/♥/♦/♣` の20セルをBo Haglund DDS（`endplay`）で計算します。
- Par contractとPar score、実戦契約のダブルダミー上のメイク可能性、実戦トリックとの差を出力します。
- 注目ボードは日本側から見た符号付きIMP差を最優先し、スラム・ダブル等の契約、両室のトリック差を補助基準として最大5枚を選びます。
- ハンドレコードは十字配置で、カード順は `AKQJT98765432`、ボイドは `—` です。
- プレー記録がない場合、ダブルダミーとの差から特定のミスを断定しません。
- 公式順位ページがラウンド履歴を提供しない場合、順位は「公式順位ページの取得時点」と明記します。
- 公式日程の中国時間は日本時間（JST）へ1時間加算して表示します。

## 検証状況

GitHub Actions上でpytest 6件が成功し、第1ラウンドの実データについて以下を確認済みです。

- U26 JAPAN: Board 6 +12、9 +9、8 -8、12 -6、5 +6 IMP
- U21 JAPAN: Board 6 -13、5 -13、14 -11、9 -11、4 +10 IMP
- U26 Women JAPAN: Board 6 +15、2 -14、9 -10、14 -10、4 +10 IMP
- 次ラウンド開始時刻を12:50 JSTとして出力
- 順位を「公式順位ページの取得時点」と明記

## WBF／Vugraph URL

WBF取得先は `wyoc_tracker/scraper.py` の設定にまとめています。大会サイトのHTML構造が変わった場合は、そこだけを修正します。Vugraphは公式スケジュールに日本戦が確認できた場合のみURLを出し、確認できない場合はその状態を明記します。

## ライセンス

このプロジェクトのコードはMIT Licenseです。ダブルダミー計算はBo Haglund DDSを利用する `endplay` に依存します。大会サイトのコンテンツはWBFの利用条件に従ってください。
