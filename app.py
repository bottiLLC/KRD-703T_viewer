"""Streamlit dashboard for Omron KRD-703T body composition analysis and visualization."""

from __future__ import annotations

import datetime
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd
import streamlit as st

_ROOT: Final[Path] = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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


@dataclass(frozen=True)
class FilterCriteria:
    """Immutable filter state contract."""

    start_date: datetime.date
    end_date: datetime.date
    show_ma: bool
    ma_window: int


@st.cache_data
def get_cached_measurements(db_path_str: str) -> pd.DataFrame:
    """Load all measurements from SQLite database with Streamlit caching.

    Args:
        db_path_str: Path string to the SQLite database.

    Returns:
        DataFrame containing all stored measurements chronologically.
    """
    return load_data(Path(db_path_str))


def render_header() -> None:
    """Render standardized top-level header zone with title, objective, and version metadata."""
    st.title("オムロン KRD-703T 体組成ダッシュボード")
    st.caption(
        "両手両足測定型体組成計 KRD-703T の測定ログ蓄積・部位別骨格筋/皮下脂肪バランス分析 | "
        "v1.0.0 | DX Health Analytics"
    )


def render_sidebar(db_path: Path) -> None:
    """Render standardized sidebar zone including instant CSV synchronization, settings, and backup UI.

    Args:
        db_path: Absolute filesystem path to the SQLite database file.
    """
    with st.sidebar:
        with st.container(border=True):
            st.subheader("CSVデータ追加同期")
            uploaded_file = st.file_uploader(
                "オムロンのCSVファイルを選択",
                type=["csv"],
                key="sidebar_csv_uploader",
                help="オムロンConnectアプリ等から出力されたCSVに対応（UTF-8 / CP932自動判定）",
            )
            submit_sync = st.button(
                "CSVを取り込んで同期",
                icon=":material/sync:",
                type="primary",
                width="stretch",
            )

        if submit_sync:
            if not uploaded_file:
                st.warning("追加するCSVファイルを選択してください。")
            else:
                with st.spinner("CSVデータを解析しSQLiteデータベースに格納中..."):
                    try:
                        raw_df = parse_csv_bytes(uploaded_file.getvalue())
                        inserted = insert_data(raw_df, db_path)
                        if inserted > 0:
                            if "測定日" in raw_df.columns:
                                parsed_dates = pd.to_datetime(raw_df["測定日"], errors="coerce")
                                max_dt = parsed_dates.dropna().max()
                                if pd.notnull(max_dt):
                                    st.session_state["filter_end_date"] = max_dt.date()
                            get_cached_measurements.clear()
                            st.toast(
                                f"同期完了: {inserted} 件の測定ログを新規保存しました。",
                                icon=":material/check_circle:",
                            )
                            st.rerun()
                        else:
                            st.info(
                                "新規データはありませんでした（全件登録済みの重複レコードです）。"
                            )
                    except (ValueError, KeyError) as exc:
                        st.error(
                            f"取り込みエラー: {exc}\n\n"
                            "【解決手順】\n"
                            "1. オムロンConnectから出力した未加工CSVであることを確認してください。\n"
                            "2. ヘッダー行に「測定日」および「体重(kg)」が存在するか確認してください。"
                        )

        st.divider()
        st.header("システム設定")
        st.subheader("データ保護・バックアップ")
        current_dir = str(get_backup_dir())
        new_dir = st.text_input("保存先フォルダ", value=current_dir)
        if new_dir != current_dir and st.button(
            "保存先パスを更新", icon=":material/save:", width="stretch"
        ):
            save_res = set_backup_dir(new_dir)
            if save_res["success"]:
                st.toast(str(save_res["message"]), icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(str(save_res["message"]))

        if st.button("今すぐバックアップを実行", icon=":material/backup:", width="stretch"):
            with st.spinner("圧縮・整合性検証中..."):
                res = run_backup(app_name="krd703t")
            if res["success"]:
                st.toast(str(res["message"]), icon=":material/check_circle:")
                st.caption(f"完了日時: {res['timestamp']}")
                st.caption(f"保存先: {res['destination']}")
            else:
                st.error(str(res["message"]))

        st.divider()
        st.header("仕様 & ヘルプ")
        with st.popover("KRD-703T 測定項目解説", icon=":material/help:"):
            st.markdown(
                """
                - **両手両足測定**: 体幹部・四肢のインピーダンスを精密分離測定。
                - **骨格筋率 (両腕/体幹/両脚)**: 各部位ごとの筋肉発達バランス。
                - **皮下脂肪率 (両腕/体幹/両脚)**: 各部位の皮下脂肪蓄積レベル。
                - **内臓脂肪レベル**: 1〜30段階での内臓脂肪断面積推計。
                """
            )

        with st.popover("CSVエクスポート手順", icon=":material/description:"):
            st.markdown(
                """
                1. スマートフォンで「OMRON connect」アプリを開く。
                2. メニューから「データ出力 / CSV」を選択。
                3. 出力したCSVを左サイドバーの「データ同期」へ投入してください。
                """
            )

        st.divider()
        st.caption("v1.0.0 | SQLite 3 Engine | KRD-703T DX Analytics")


def render_empty_state() -> None:
    """Render workspace view when database contains zero measurement records."""
    st.info(
        "測定データが登録されていません。左サイドバーの「データ同期 (CSV)」からオムロン Connect のCSVファイルを投入してください。"
    )

    with st.container(border=True):
        st.subheader("💡 測定データの初期登録手順")
        st.markdown(
            """
            1. お手持ちのスマートフォンで **OMRON connect** アプリを起動します。
            2. 画面メニューから **[データ出力]** または **[CSVファイル書き出し]** を選択します。
            3. 出力した未加工CSVファイルを、画面左側のサイドバーにある **「オムロン Connect CSVファイルを選択」** にドラッグ＆ドロップまたは選択してください。
            4. 投入後、自動で解析・データベース登録が実行され、ダッシュボードが表示されます。
            """
        )


def render_summary_kpis(filtered_df: pd.DataFrame) -> None:
    """Render metadata caption and top 6 KPI metric cards.

    Args:
        filtered_df: Chronologically sorted filtered measurement DataFrame.
    """
    total_count = len(filtered_df)
    latest_ts = filtered_df["measured_at"].max().strftime("%Y/%m/%d %H:%M")
    st.caption(
        f"表示対象: **{total_count} 件** | 最新測定日時: **{latest_ts}** | 機種: **KRD-703T**"
    )

    st.subheader("最新測定サマリー")
    latest_row = filtered_df.iloc[-1]
    with st.container(border=True):
        kpi_cols = st.columns(6)

        with kpi_cols[0]:
            delta_wt = calculate_delta(filtered_df["weight"])
            st.metric(
                label="体重",
                value=f"{float(latest_row['weight']):.2f} kg",
                delta=f"{delta_wt:+.2f} kg" if delta_wt is not None else None,
                delta_color="inverse",
                border=True,
            )

        with kpi_cols[1]:
            delta_fat = calculate_delta(filtered_df["body_fat_pct"])
            st.metric(
                label="体脂肪率",
                value=f"{float(latest_row['body_fat_pct']):.1f} %",
                delta=f"{delta_fat:+.1f} %" if delta_fat is not None else None,
                delta_color="inverse",
                border=True,
            )

        with kpi_cols[2]:
            delta_muscle = calculate_delta(filtered_df["skeletal_muscle_pct"])
            st.metric(
                label="骨格筋率",
                value=f"{float(latest_row['skeletal_muscle_pct']):.1f} %",
                delta=f"{delta_muscle:+.1f} %" if delta_muscle is not None else None,
                delta_color="normal",
                border=True,
            )

        with kpi_cols[3]:
            delta_visc = calculate_delta(filtered_df["visceral_fat_level"])
            st.metric(
                label="内臓脂肪レベル",
                value=f"{float(latest_row['visceral_fat_level']):.1f}",
                delta=f"{delta_visc:+.1f}" if delta_visc is not None else None,
                delta_color="inverse",
                border=True,
            )

        with kpi_cols[4]:
            delta_bmi = calculate_delta(filtered_df["bmi"])
            st.metric(
                label="BMI",
                value=f"{float(latest_row['bmi']):.1f}",
                delta=f"{delta_bmi:+.1f}" if delta_bmi is not None else None,
                delta_color="inverse",
                border=True,
            )

        with kpi_cols[5]:
            delta_bmr = calculate_delta(filtered_df["bmr"].astype(float))
            st.metric(
                label="基礎代謝",
                value=f"{int(latest_row['bmr'])} kcal",
                delta=f"{delta_bmr:+.0f} kcal" if delta_bmr is not None else None,
                delta_color="normal",
                border=True,
            )


@st.fragment
def render_trend_tab(filtered_df: pd.DataFrame, show_ma: bool, ma_window: int) -> None:
    """Render Tab 1 for metric trend waveform and multi-axis visualization.

    Args:
        filtered_df: Filtered measurement DataFrame.
        show_ma: Whether moving average lines should be rendered.
        ma_window: Rolling window size in days for moving average.
    """
    with st.container(border=True):
        st.markdown("#### 指標トレンド波形")
        metric_options = list(METRIC_LABELS.keys())
        selected_metrics = st.multiselect(
            "プロットする指標を選択（2つ選択時は左右2軸表示）",
            options=metric_options,
            default=["体重 (kg)", "体脂肪率 (%)"],
            help="グラフにプロットする体組成指標を選択してください。2項目選択時は左右2軸表示になります。",
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


@st.fragment
def render_segmental_tab(filtered_df: pd.DataFrame, latest_row: pd.Series[Any]) -> None:
    """Render Tab 2 for KRD-703T segmental skeletal muscle and fat analysis.

    Args:
        filtered_df: Filtered measurement DataFrame.
        latest_row: Latest measurement record Series.
    """
    with st.container(border=True):
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

    with st.container(border=True):
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


@st.fragment
def render_composition_tab(filtered_df: pd.DataFrame) -> None:
    """Render Tab 3 for body composition breakdown stack and correlation scatter.

    Args:
        filtered_df: Filtered measurement DataFrame.
    """
    with st.container(border=True):
        st.markdown("#### 体組成の内訳および相関")
        stack_fig = create_composition_stack_chart(filtered_df)
        st.plotly_chart(stack_fig, width="stretch")

    with st.container(border=True):
        st.markdown("##### 体重 vs 体脂肪率 の散布図 (体型変化トラッキング)")
        scatter_fig = create_scatter_correlation_chart(filtered_df)
        st.plotly_chart(scatter_fig, width="stretch")


@st.fragment
def render_management_tab(filtered_df: pd.DataFrame, db_path: Path) -> None:
    """Render Tab 4 for raw measurement log tables, export, and fail-safe DB clear.

    Args:
        filtered_df: Filtered measurement DataFrame.
        db_path: Deterministic Path to SQLite database.
    """
    with st.container(border=True):
        st.markdown("#### 測定ログ一覧")
        st.dataframe(
            filtered_df.sort_values(by="measured_at", ascending=False),
            width="stretch",
            hide_index=True,
        )

    with st.container(border=True):
        st.markdown("##### 統計サマリー (基本統計量)")
        st.dataframe(filtered_df.describe().T, width="stretch")

    with st.container(border=True):
        st.markdown("##### データエクスポート")
        csv_buffer = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="表示中データをCSVエクスポート",
            icon=":material/download:",
            data=csv_buffer,
            file_name="krd703t_filtered_measurements.csv",
            mime="text/csv",
            type="secondary",
            width="stretch",
            help="現在画面にフィルタ表示されている測定レコードをCSVファイルとしてダウンロードします。",
        )

    with st.container(border=True):
        st.markdown("##### データベース管理")
        with st.popover("データベース初期化 (全データ消去)", icon=":material/delete_forever:"):
            st.warning("SQLiteデータベース内の全測定レコードが完全に削除されます。")
            confirmed = st.checkbox(
                "全測定データの完全消去を確認しました",
                help="チェックを入れるとデータベース消去ボタンが有効化されます。",
            )
            if st.button(
                "全データを消去して初期化",
                icon=":material/delete_forever:",
                type="secondary",
                disabled=not confirmed,
                width="stretch",
                help="データベースを完全にクリアし、初期状態に戻します（復元不可）。",
            ):
                clear_db(db_path)
                get_cached_measurements.clear()
                st.toast("データベースを初期化しました。", icon=":material/check_circle:")
                st.rerun()


def main() -> None:
    """Launch and orchestrate the Streamlit dashboard application."""
    st.set_page_config(
        page_title="オムロン KRD-703T 体組成ダッシュボード",
        page_icon=":material/monitor_heart:",
        layout="wide",
    )

    db_path = get_default_db_path()
    init_db(db_path)

    render_header()
    render_sidebar(db_path)

    df = get_cached_measurements(str(db_path))

    # Empty Database State
    if df.empty:
        render_empty_state()
        st.stop()

    # Populated Database State
    min_date = df["measured_at"].min().date()
    max_date = df["measured_at"].max().date()

    # Initialize filter state
    if "filter_start_date" not in st.session_state:
        st.session_state["filter_start_date"] = min_date
    if "filter_end_date" not in st.session_state:
        st.session_state["filter_end_date"] = max_date
    if "filter_show_ma" not in st.session_state:
        st.session_state["filter_show_ma"] = True
    if "filter_ma_window" not in st.session_state:
        st.session_state["filter_ma_window"] = 7

    # Clamp session_state dates if db bounds shifted
    st.session_state["filter_start_date"] = max(st.session_state["filter_start_date"], min_date)
    st.session_state["filter_end_date"] = min(st.session_state["filter_end_date"], max_date)

    # Section 2: Filter Controls Form
    with st.form("filter_controls_form", border=True):
        st.subheader("フィルター設定")
        f_col1, f_col2, f_col3 = st.columns([2, 1, 1])

        with f_col1:
            date_val = st.date_input(
                "測定期間フィルタ",
                value=(st.session_state["filter_start_date"], st.session_state["filter_end_date"]),
                min_value=min_date,
                max_value=max_date,
                help="表示・集計対象とする測定期間の開始日と終了日を選択してください。",
            )

        with f_col2:
            show_ma_val = st.checkbox(
                "移動平均線を表示 (トレンド平滑化)",
                value=st.session_state["filter_show_ma"],
                help="日々の体重・骨格筋率の細かな変動を平滑化し、長期トレンドを可視化します。",
            )

        with f_col3:
            ma_window_val = st.slider(
                "移動平均の日数",
                min_value=3,
                max_value=30,
                value=st.session_state["filter_ma_window"],
                help="移動平均の計算に用いるローリング日数（3〜30日）を指定します。",
            )

        b_col1, b_col2 = st.columns([1, 1])
        with b_col1:
            submit_filter = st.form_submit_button(
                "フィルターを適用",
                icon=":material/filter_alt:",
                type="primary",
                width="stretch",
                help="指定した期間と移動平均設定を集計に反映します。",
            )
        with b_col2:
            reset_filter = st.form_submit_button(
                "期間を全期間にリセット",
                icon=":material/restart_alt:",
                type="secondary",
                width="stretch",
                help="期間フィルタを全期間、移動平均を初期値（7日）にリセットします。",
            )

    if reset_filter:
        st.session_state["filter_start_date"] = min_date
        st.session_state["filter_end_date"] = max_date
        st.session_state["filter_show_ma"] = True
        st.session_state["filter_ma_window"] = 7
        st.rerun()

    if submit_filter:
        if isinstance(date_val, tuple) and len(date_val) == 2:
            st.session_state["filter_start_date"], st.session_state["filter_end_date"] = date_val
        st.session_state["filter_show_ma"] = show_ma_val
        st.session_state["filter_ma_window"] = ma_window_val

    # Apply active filter
    active_start = st.session_state["filter_start_date"]
    active_end = st.session_state["filter_end_date"]
    mask = (df["measured_at"].dt.date >= active_start) & (df["measured_at"].dt.date <= active_end)
    filtered_df = df[mask].copy()

    if filtered_df.empty:
        st.warning("指定された期間の測定データが存在しません。期間を変更してください。")
        st.stop()

    # Section 3: Summary KPIs
    render_summary_kpis(filtered_df)

    # Section 4: Analysis Tabs
    latest_row = filtered_df.iloc[-1]
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "トレンド推移",
            "部位別バランス (KRD-703T特有)",
            "体組成構成 & 相関",
            "測定ログ管理",
        ]
    )

    with tab1:
        render_trend_tab(
            filtered_df,
            show_ma=st.session_state["filter_show_ma"],
            ma_window=st.session_state["filter_ma_window"],
        )

    with tab2:
        render_segmental_tab(filtered_df, latest_row=latest_row)

    with tab3:
        render_composition_tab(filtered_df)

    with tab4:
        render_management_tab(filtered_df, db_path=db_path)


if __name__ == "__main__":
    main()
