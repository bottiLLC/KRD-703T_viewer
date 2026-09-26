![CI](https://github.com/bottiLLC/KRD-703T_viewer/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.14-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.64.0-FF4B4B.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

# KRD-703T Body Composition Viewer

## Overview
オムロン両手両足測定体組成計「KRD-703T」が出力する生ログCSVを取り込み、部位別（両腕・体幹・両脚）骨格筋率・皮下脂肪率を含む体組成データをSQLiteへ永続化および可視化するStreamlitダッシュボード。

## Quick Start (TL;DR)
```bash
# 1. 依存関係の同期
uv sync

# 2. 自動テスト & 型検査の実行
uv run pytest --cov=db --cov=backup_manager --cov-branch && uv run mypy --strict app.py db.py backup_manager.py test_db.py test_backup_manager.py

# 3. アプリケーション起動（または run.bat をダブルクリック）
uv run streamlit run app.py
```

## Architecture & Features
- **自動文字コード判定 & BOM耐性**: オムロンConnect由来のUTF-8（BOM付き含む）およびCP932（Shift-JIS）を自動判定してパース。
- **SQLite隔離永続化 & 冪等登録**: `./data`配下へのDB完全隔離と、重複測定日時（`measured_at`）に対する`INSERT OR IGNORE`競合解消。
- **整合性検証付き自動バックアップ**: `backup_manager.py`によるZIP一時生成・`testzip()`完全性検証・アトミック退避、UIからの保存先（Google Drive等）変更・永続化およびUIレシート通知。
- **KRD-703T部位別分析 & トレンド推移**: 両腕・体幹・両脚のバランスを可視化するレーダーチャートと7日〜30日移動平均付き2軸時系列プロット。
- **測定ログ管理 & エクスポート**: 全レコードのソート・基本統計量表示・CSVエクスポート・DB初期化（全消去）を統合。

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
