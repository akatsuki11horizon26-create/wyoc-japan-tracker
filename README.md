# WYOC Japan Tracker

2026年ハイフェイ世界ユース大会について、日本代表3チームの試合結果、注目ボード、ハンドレコード、Vugraph、DDSダブルダミー解析を日本語Markdown／JSONで自動生成します。

対象:

- `U26 JAPAN`
- `U21 JAPAN`
- `U26 Women JAPAN`

`JAPONG` は対象外です。

## 主な機能

- WBF公式結果から対戦相手、IMP、VP、次戦を取得
- 公式結果の公開状況から最新完了ラウンドを自動判定
- 日本側から見た符号付きIMPを基準に、各チーム最大5ボードを選定
- 全52枚を十字配置で表示
- `North/South/East/West × NT/♠/♥/♦/♣` の20セルをBo Haglund DDS（`endplay`）で実計算
- パー契約、パースコア、実戦契約との比較を出力
- 公式ページに存在する場合のみオークションとプレイ記録を掲載
- BBO Vugraphの中継URLとアーカイブURLを確認
- 中国時間を日本時間（JST）へ変換
- ラウンド別順位履歴を `data/history/` に保存
- GitHub Actions artifactとリポジトリ内の `reports/` に結果を保存

## ローカル実行

Python 3.11で実行します。

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m wyoc_tracker.cli --round auto
```

特定ラウンドを再生成する場合:

```bash
python -m wyoc_tracker.cli --round 1
```

HTMLキャッシュを使わず再取得する場合:

```bash
python -m wyoc_tracker.cli --round auto --no-cache
```

ネットワークを使わずサンプルBoard 6を確認する場合:

```bash
python -m wyoc_tracker.cli \
  --round 1 \
  --input data/sample_round1.json \
  --output-dir reports
```

## 出力

```text
reports/
  round-01.md
  round-01.json
  round-02.md
  round-02.json

data/history/
  round-01.json
  round-02.json

data/cache/
  <URLのSHA-256>.html
```

`reports/` と `data/history/` は本番実行後にGitHub Actionsが `main` へコミットします。内容に変化がない場合はコミットしません。`data/cache/` はActions cacheとartifactに保存し、Gitには追加しません。

## GitHub Actions

**Analyze WYOC Japan round** は次の場合に実行されます。

- Pull Request
- `main` へのPush
- 手動実行（`workflow_dispatch`）
- 30分ごとの定期実行

手動実行の `round_number` には、ラウンド番号または `auto` を指定します。定期実行では、3部門すべてでスコアが公開された最新ラウンドだけを処理します。未完了ラウンドは生成しません。

## 順位の扱い

最新完了ラウンドはWBF公式順位ページの順位を使用します。過去ラウンドの公式順位履歴を取得できない場合は、各ラウンドのVPを累積して順位を再計算します。同VPの公式タイブレークは推測せず、同順位として扱い、その方法をレポートに明記します。

保存済みの `data/history/round-XX.json` がある場合は、再実行時にそのスナップショットを優先します。

## オークションとプレイ記録

WBFの契約ポップアップまたはPlay Detailsページに記録がある場合のみ掲載します。記録が取得できない場合は「公式記録では確認できず」と表示します。ダブルダミーとの差だけから、特定のプレイや判断をミスと断定しません。

## Vugraph

BBO公式スケジュールと公式アーカイブを確認し、日本戦とラウンドを照合できた場合だけ直接URLを掲載します。直接URLを確認できない場合は、推測したURLを作りません。

## 解析上の注意

- PBNは各プレイヤー13枚、全52枚の重複なしを検証します。
- 不完全なハンドではDDSを実行しません。
- DDSで計算していない値を推測で埋めません。
- WBFやBBOのHTML構造が変わった場合は `wyoc_tracker/scraper.py` とfixtureを更新します。
- 外部サイトへのアクセスを抑えるため、完了済みラウンドはHTMLキャッシュを再利用します。

## ライセンス

このプロジェクトのコードはMIT Licenseです。ダブルダミー計算はBo Haglund DDSを利用する `endplay` に依存します。大会サイトおよびBBOのコンテンツは各提供元の利用条件に従ってください。
