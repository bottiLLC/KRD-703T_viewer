[![CI](https://github.com/bottiLLC/KRD-703T_viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/bottiLLC/KRD-703T_viewer/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/Python-3.14-blue.svg) ![Streamlit](https://img.shields.io/badge/Streamlit-1.66.0-FF4B4B.svg) ![Ruff](https://img.shields.io/badge/Ruff-0.16.9-orange.svg) ![Mypy](https://img.shields.io/badge/Mypy-Strict-blue.svg) ![Coverage](https://img.shields.io/badge/Coverage-100%25_C1-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-green.svg)

# KRD-703T Body Composition Viewer

## Overview
オムロン両手両足測定体組成計「KRD-703T」が出力する生ログCSVを取り込み、部位別（両腕・体幹・両脚）骨格筋率・皮下脂肪率を含む体組成データをSQLiteへ永続化および可視化するStreamlitダッシュボード。

## Quick Start (TL;DR)
```bash
# 1. 依存関係の同期
uv sync

# 2. 自動テスト & 型検査の実行
uv run pytest --cov=db --cov=backup_manager --cov=charts --cov-branch && uv run mypy --strict app.py db.py backup_manager.py charts.py test_db.py test_backup_manager.py test_charts.py test_app.py

# 3. アプリケーション起動（または run.bat をダブルクリック）
uv run streamlit run app.py
```

## Architecture & Features
- **`streamlit-gui` 厳格準拠アーキテクチャ**:
  - **画面3ゾーン分割**: Header（タイトル・目的・バージョン）、Sidebar（設定・ヘルプ・メタ情報）、Main Workspace（投入・フィルタ・KPI・分析タブ）の完全分離。
  - **`st.form` によるリソース最適化**: 期間・移動平均フィルタおよびバックアップ設定をFormカプセル化し、入力操作ごとの即時全体リランを抑止。ワンクリック「全期間リセット」動線を配備。
  - **厳格なボタン階層統制**: 画面主動線である「🔍 フィルターを適用」のみを唯一の `type="primary"` に設定し、他アクションを `type="secondary"` に統一。
  - **全ウィジェット Tooltip 完備**: 全入力要素に制約・単位・目的を解説する `help="..."` を網羅。
  - **UI自動回帰テスト (`test_app.py`)**: `streamlit.testing.v1.AppTest` を導入し、初期未登録画面、CSV同期、KPI描画、フィルタ送信、2段階確認消去のUI契約をCIで完全担保。
- **純粋可視化変換層の完全分離 (`charts.py`)**: Plotlyグラフ描画（レーダー・2軸推移・移動平均・積層内訳・散布図）および差分計算ロジックをStreamlit非依存の純粋関数群へ外科分離（単体C1分岐網羅率100%）。
- **自動文字コード判定 & BOM耐性**: オムロンConnectアプリ等から出力されたUTF-8（BOM付き含む）およびCP932（Shift-JIS）を自動判定してパース。
- **SQLite隔離永続化 & 冪等登録**: `./data`配下へのDB完全隔離と、重複測定日時（`measured_at`）に対する`INSERT OR IGNORE`競合解消。
- **整合性検証付き自動バックアップ**: `backup_manager.py`によるZIP一時生成・`testzip()`完全性検証・アトミック退避、UIからの保存先変更・永続化およびUIレシート通知。
- **誤消去防止フェイルセーフ**: データベース初期化に対するチェックボックス確認付き2段階バリデーション機構を搭載（Form外単離配置によりトグル即時性を担保）。

## Environment Variables
| Variable Name | Default Value | Description |
|---|---|---|
| `BACKUP_DIR` | `./backups` | バックアップZIPアーカイブの出力先ディレクトリパス |
| `STREAMLIT_SERVER_PORT` | `8501` | Streamlit Webサーバーの待受ポート番号 |
| `STREAMLIT_SERVER_HEADLESS` | `true` | ヘッドレス動作設定 |

## Limits & Known Trade-offs
- **ローカルSQLite単一DB**: 複数端末での同時並行書き込みを想定しないシングルユーザー設計。
- **タイムゾーン処理**: タイムゾーン文字列は保存されるが、現行プロットでは測定日時文字列をベースとしたタイムゾーン非依存（ローカル時刻）として描画。
- **他機種CSVの互換性**: 部位別測定非対応のオムロン機種CSVの場合、部位別カラムは`NULL`として扱われ全身指標のみ表示。

---
## License
MIT License - Copyright (c) 2026 LLC Bocchi
