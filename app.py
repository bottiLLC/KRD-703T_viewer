"""Streamlit dashboard for Omron KRD-703T body composition analysis and visualization."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Final

import pandas as pd
import streamlit as st

# Ensure project root is present in sys.path regardless of execution working directory
_APP_ROOT: Final[Path] = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from backup_manager import get_backup_dir, run_backup, set_backup_dir
from charts import (
    METRIC_LABELS,
    calculate_delta,
    create_composition_stack_chart,
    create_scatter_correlation_chart,
    create_segmental_history_chart,
    create_segmental_radar_chart,
    create_trend_chart,
)
from db import (
    clear_db,
    get_default_db_path,
    init_db,
    insert_data,
    load_data,
    parse_csv_bytes,
)


@st.cache_data
def get_cached_measurements(db_path_str: str) -> pd.DataFrame:
    """Load all measurements from SQLite database with Streamlit caching.

    Args:
        db_path_str: Path string to the SQLite database.

    Returns:
        DataFrame containing all stored measurements chronologically.
    """
    return load_data(Path(db_path_str))


def render_backup_sidebar() -> None:
    """Render standardized data protection backup trigger and receipts in sidebar."""
    with st.sidebar:
        st.divider()
        st.subheader("データ保護・バックアップ")

        current_dir = str(get_backup_dir())
        new_dir = st.text_input("保存先フォルダ", value=current_dir)
        if new_dir != current_dir and st.button("保存先パスを更新", width="stretch"):
            save_res = set_backup_dir(new_dir)
            if save_res["success"]:
                st.success(save_res["message"])
                st.rerun()
            else:
                st.error(save_res["message"])

        if st.button("今すぐバックアップを実行", width="stretch"):
            with st.spinner("圧縮・整合性検証中..."):
                res = run_backup(app_name="krd703t")
            if res["success"]:
                st.success(res["message"])
                st.caption(f"完了日時: {res['timestamp']}")
                st.caption(f"保存先: {res['destination']}")
            else:
                st.error(res["message"])


def render_header_and_kpis(filtered_df: pd.DataFrame) -> None:
    """Render title, metadata caption, and top 6 KPI metric cards.

    Args:
        filtered_df: Chronologically sorted filtered measurement DataFrame.
    """
    st.title("⚡ オムロン KRD-703T 体組成ダッシュボード")
    total_count = len(filtered_df)
    latest_ts = filtered_df["measured_at"].max().strftime("%Y/%m/%d %H:%M")
    st.caption(
        f"📊 表示対象: **{total_count} 件** | 最新測定日時: **{latest_ts}** | 機種: **KRD-703T**"
    )

    st.subheader("📌 最新測定サマリー")
    latest_row = filtered_df.iloc[-1]
    kpi_cols = st.columns(6)

    with kpi_cols[0]:
        delta_wt = calculate_delta(filtered_df["weight"])
        st.metric(
            label="体重",
            value=f"{float(latest_row['weight']):.2f} kg",
            delta=f"{delta_wt:+.2f} kg" if delta_wt is not None else None,
            delta_color="inverse",
        )

    with kpi_cols[1]:
        delta_fat = calculate_delta(filtered_df["body_fat_pct"])
        st.metric(
            label="体脂肪率",
            value=f"{float(latest_row['body_fat_pct']):.1f} %",
            delta=f"{delta_fat:+.1f} %" if delta_fat is not None else None,
            delta_color="inverse",
        )

    with kpi_cols[2]:
        delta_muscle = calculate_delta(filtered_df["skeletal_muscle_pct"])
        st.metric(
            label="骨格筋率",
            value=f"{float(latest_row['skeletal_muscle_pct']):.1f} %",
            delta=f"{delta_muscle:+.1f} %" if delta_muscle is not None else None,
            delta_color="normal",
        )

    with kpi_cols[3]:
        delta_visc = calculate_delta(filtered_df["visceral_fat_level"])
        st.metric(
            label="内臓脂肪レベル",
            value=f"{float(latest_row['visceral_fat_level']):.1f}",
            delta=f"{delta_visc:+.1f}" if delta_visc is not None else None,
            delta_color="inverse",
        )

    with kpi_cols[4]:
        delta_bmi = calculate_delta(filtered_df["bmi"])
        st.metric(
            label="BMI",
            value=f"{float(latest_row['bmi']):.1f}",
            delta=f"{delta_bmi:+.1f}" if delta_bmi is not None else None,
            delta_color="inverse",
        )

    with kpi_cols[5]:
        delta_bmr = calculate_delta(filtered_df["bmr"].astype(float))
        st.metric(
            label="基礎代謝",
            value=f"{int(latest_row['bmr'])} kcal",
            delta=f"{delta_bmr:+.0f} kcal" if delta_bmr is not None else None,
            delta_color="normal",
        )


def render_trend_tab(filtered_df: pd.DataFrame, show_ma: bool, ma_window: int) -> None:
    """Render Tab 1 for metric trend waveform and multi-axis visualization.

    Args:
        filtered_df: Filtered measurement DataFrame.
        show_ma: Whether moving average lines should be rendered.
        ma_window: Rolling window size in days for moving average.
    """
    st.markdown("#### 指標トレンド波形")
    metric_options = list(METRIC_LABELS.keys())
    selected_metrics = st.multiselect(
        "プロットする指標を選択（2つ選択時は左右2軸表示）",
        options=metric_options,
        default=["体重 (kg)", "体脂肪率 (%)"],
    )
    if selected_metrics:
        trend_fig = create_trend_chart(
            filtered_df,
            selected_metrics,
            show_ma=show_ma,
            ma_window=ma_window,
        )
        st.plotly_chart(trend_fig, width="stretch")
    else:
        st.info("表示する指標を1つ以上選択してください。")


def render_segmental_tab(filtered_df: pd.DataFrame, latest_row: pd.Series[Any]) -> None:
    """Render Tab 2 for KRD-703T segmental skeletal muscle and fat analysis.

    Args:
        filtered_df: Filtered measurement DataFrame.
        latest_row: Latest measurement record Series.
    """
    st.markdown("#### 部位別骨格筋・皮下脂肪バランス分析")
    sub_col1, sub_col2 = st.columns([1, 1])

    with sub_col1:
        st.markdown("##### 最新測定の部位別レーダー")
        radar_fig = create_segmental_radar_chart(
            muscle_arms=float(str(latest_row.get("skeletal_muscle_arms_pct", 0.0) or 0.0)),
            muscle_trunk=float(str(latest_row.get("skeletal_muscle_trunk_pct", 0.0) or 0.0)),
            muscle_legs=float(str(latest_row.get("skeletal_muscle_legs_pct", 0.0) or 0.0)),
            fat_arms=float(str(latest_row.get("subcutaneous_fat_arms_pct", 0.0) or 0.0)),
            fat_trunk=float(str(latest_row.get("subcutaneous_fat_trunk_pct", 0.0) or 0.0)),
            fat_legs=float(str(latest_row.get("subcutaneous_fat_legs_pct", 0.0) or 0.0)),
        )
        st.plotly_chart(radar_fig, width="stretch")

    with sub_col2:
        segment_summary = pd.DataFrame(
            {
                "部位": ["両腕", "体幹", "両脚"],
                "骨格筋率 (%)": [
                    latest_row.get("skeletal_muscle_arms_pct"),
                    latest_row.get("skeletal_muscle_trunk_pct"),
                    latest_row.get("skeletal_muscle_legs_pct"),
                ],
                "皮下脂肪率 (%)": [
                    latest_row.get("subcutaneous_fat_arms_pct"),
                    latest_row.get("subcutaneous_fat_trunk_pct"),
                    latest_row.get("subcutaneous_fat_legs_pct"),
                ],
            }
        )
        st.markdown("##### 部位別の最新数値")
        st.dataframe(segment_summary, width="stretch", hide_index=True)

    st.divider()
    st.markdown("##### 部位別推移グラフ")
    hist_col1, hist_col2 = st.columns(2)
    with hist_col1:
        muscle_hist_fig = create_segmental_history_chart(
            filtered_df, "skeletal_muscle", "部位別 骨格筋率の推移 (%)"
        )
        st.plotly_chart(muscle_hist_fig, width="stretch")

    with hist_col2:
        fat_hist_fig = create_segmental_history_chart(
            filtered_df, "subcutaneous_fat", "部位別 皮下脂肪率の推移 (%)"
        )
        st.plotly_chart(fat_hist_fig, width="stretch")


def render_composition_tab(filtered_df: pd.DataFrame) -> None:
    """Render Tab 3 for body composition breakdown stack and correlation scatter.

    Args:
        filtered_df: Filtered measurement DataFrame.
    """
    st.markdown("#### 体組成の内訳および相関")
    stack_fig = create_composition_stack_chart(filtered_df)
    st.plotly_chart(stack_fig, width="stretch")

    st.divider()
    st.markdown("##### 体重 vs 体脂肪率 の散布図 (体型変化トラッキング)")
    scatter_fig = create_scatter_correlation_chart(filtered_df)
    st.plotly_chart(scatter_fig, width="stretch")


def render_management_tab(filtered_df: pd.DataFrame, db_path: Path) -> None:
    """Render Tab 4 for raw measurement log tables, export, and fail-safe DB clear.

    Args:
        filtered_df: Filtered measurement DataFrame.
        db_path: Deterministic Path to SQLite database.
    """
    st.markdown("#### 測定ログ一覧")
    st.dataframe(
        filtered_df.sort_values(by="measured_at", ascending=False),
        width="stretch",
        hide_index=True,
    )

    st.markdown("##### 統計サマリー (基本統計量)")
    st.dataframe(filtered_df.describe().T, width="stretch")

    st.markdown("##### データエクスポート")
    csv_buffer = filtered_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="💾 表示中データをCSVエクスポート",
        data=csv_buffer,
        file_name="krd703t_filtered_measurements.csv",
        mime="text/csv",
        type="secondary",
        width="stretch",
    )

    st.divider()
    st.markdown("##### データベース管理")
    with st.expander("⚙️ データベース初期化 (全データ消去)", expanded=False):
        st.warning("⚠️ SQLiteデータベース内の全測定レコードが完全に削除されます。")
        confirmed = st.checkbox("全測定データの完全消去を確認しました")
        if st.button(
            "🗑️ 全データを消去して初期化",
            type="primary",
            disabled=not confirmed,
            width="stretch",
        ):
            clear_db(db_path)
            get_cached_measurements.clear()
            st.success("データベースを初期化しました。")
            st.rerun()


def main() -> None:
    """Launch and orchestrate the Streamlit dashboard application."""
    st.set_page_config(
        page_title="オムロン KRD-703T 体組成ダッシュボード",
        page_icon="⚖️",
        layout="wide",
    )

    db_path = get_default_db_path()
    init_db(db_path)

    with st.sidebar:
        st.header("📥 データ投入・同期")
        uploaded_file = st.file_uploader(
            "オムロンのCSVファイルを投入",
            type=["csv"],
            help="オムロンConnectアプリ等から出力されたCSVに対応（UTF-8 / CP932自動判定）",
        )
        if uploaded_file is not None:
            content = uploaded_file.read()
            try:
                raw_df = parse_csv_bytes(content)
                inserted = insert_data(raw_df, db_path)
                get_cached_measurements.clear()
                st.success(f"同期完了: {inserted} 件の測定ログを新規保存しました。")
            except (ValueError, pd.errors.ParserError, KeyError) as exc:
                st.error(f"取り込みエラー: {exc}")

    df = get_cached_measurements(str(db_path))

    if df.empty:
        render_backup_sidebar()
        st.info(
            "👋 測定データが登録されていません。サイドバーからCSVファイルをアップロードしてください。"
        )
        st.stop()

    with st.sidebar:
        st.divider()
        st.header("🔍 フィルタ設定")
        min_date = df["measured_at"].min().date()
        max_date = df["measured_at"].max().date()

        date_range = st.date_input(
            "測定期間フィルタ",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        show_ma = st.checkbox("移動平均線を表示 (トレンド平滑化)", value=True)
        ma_window = st.slider("移動平均の日数", min_value=3, max_value=30, value=7)

    render_backup_sidebar()

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        mask = (df["measured_at"].dt.date >= start_date) & (df["measured_at"].dt.date <= end_date)
        filtered_df = df[mask].copy()
    else:
        filtered_df = df.copy()

    if filtered_df.empty:
        st.warning("指定された期間の測定データが存在しません。期間を変更してください。")
        st.stop()

    render_header_and_kpis(filtered_df)

    latest_row = filtered_df.iloc[-1]
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 トレンド推移",
            "🦾 部位別バランス (KRD-703T特有)",
            "📊 体組成構成 & 相関",
            "📋 測定ログ管理",
        ]
    )

    with tab1:
        render_trend_tab(filtered_df, show_ma=show_ma, ma_window=ma_window)

    with tab2:
        render_segmental_tab(filtered_df, latest_row=latest_row)

    with tab3:
        render_composition_tab(filtered_df)

    with tab4:
        render_management_tab(filtered_df, db_path=db_path)


if __name__ == "__main__":
    main()
