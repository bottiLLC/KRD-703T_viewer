"""Streamlit dashboard for Omron KRD-703T body composition analysis and visualization."""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from typing import Final

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is present in sys.path regardless of execution working directory
_APP_ROOT: Final[Path] = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from backup_manager import get_backup_dir, run_backup, set_backup_dir
from db import (
    clear_db,
    get_default_db_path,
    init_db,
    insert_data,
    load_data,
    parse_csv_bytes,
)

METRIC_LABELS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "体重 (kg)": "weight",
        "体脂肪率 (%)": "body_fat_pct",
        "体脂肪量 (kg)": "body_fat_mass",
        "骨格筋率 (%)": "skeletal_muscle_pct",
        "骨格筋量 (kg)": "skeletal_muscle_mass",
        "内臓脂肪レベル": "visceral_fat_level",
        "BMI": "bmi",
        "基礎代謝 (kcal)": "bmr",
        "体年齢 (才)": "body_age",
        "骨格筋率・両腕 (%)": "skeletal_muscle_arms_pct",
        "骨格筋率・体幹 (%)": "skeletal_muscle_trunk_pct",
        "骨格筋率・両脚 (%)": "skeletal_muscle_legs_pct",
        "皮下脂肪率・全身 (%)": "subcutaneous_fat_pct",
        "皮下脂肪率・両腕 (%)": "subcutaneous_fat_arms_pct",
        "皮下脂肪率・体幹 (%)": "subcutaneous_fat_trunk_pct",
        "皮下脂肪率・両脚 (%)": "subcutaneous_fat_legs_pct",
    }
)

METRIC_COLORS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "weight": "#2563EB",
        "body_fat_pct": "#DC2626",
        "body_fat_mass": "#EA580C",
        "skeletal_muscle_pct": "#16A34A",
        "skeletal_muscle_mass": "#059669",
        "visceral_fat_level": "#D97706",
        "bmi": "#7C3AED",
        "bmr": "#0284C7",
        "body_age": "#64748B",
        "skeletal_muscle_arms_pct": "#3B82F6",
        "skeletal_muscle_trunk_pct": "#10B981",
        "skeletal_muscle_legs_pct": "#F59E0B",
        "subcutaneous_fat_pct": "#E11D48",
        "subcutaneous_fat_arms_pct": "#FB7185",
        "subcutaneous_fat_trunk_pct": "#F43F5E",
        "subcutaneous_fat_legs_pct": "#BE123C",
    }
)

SEGMENT_COLORS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "両腕": "#3B82F6",
        "体幹": "#10B981",
        "両脚": "#F59E0B",
    }
)


def calculate_delta(series: pd.Series[float]) -> float | None:
    """Calculate difference between the latest and previous measurement.

    Args:
        series: Numerical series sorted chronologically.

    Returns:
        Delta value or None if insufficient observations.
    """
    valid_series = series.dropna()
    if len(valid_series) < 2:
        return None
    return float(valid_series.iloc[-1]) - float(valid_series.iloc[-2])


def create_trend_chart(
    df: pd.DataFrame,
    selected_labels: list[str],
    show_ma: bool = False,
    ma_window: int = 7,
) -> go.Figure:
    """Generate interactive multi-metric time series line chart.

    Args:
        df: Filtered measurements DataFrame.
        selected_labels: Display labels of metrics to plot.
        show_ma: Flag to render rolling moving average.
        ma_window: Rolling window size for moving average.

    Returns:
        Plotly Figure object.
    """
    fig = go.Figure()
    if not selected_labels:
        return fig

    is_dual_axis = len(selected_labels) == 2
    for idx, label in enumerate(selected_labels):
        col = METRIC_LABELS[label]
        color = METRIC_COLORS.get(col, "#4B5563")
        yaxis_name = "y" if idx == 0 else "y2" if (is_dual_axis and idx == 1) else "y"

        fig.add_trace(
            go.Scatter(
                x=df["measured_at"],
                y=df[col],
                mode="lines+markers",
                name=label,
                yaxis=yaxis_name,
                marker={"size": 5, "color": color},
                line={"width": 2, "color": color},
                hovertemplate=f"<b>{label}</b>: %{{y:.1f}}<extra></extra>",
            )
        )

        if show_ma and len(df) >= ma_window:
            ma_series = df[col].rolling(window=ma_window, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["measured_at"],
                    y=ma_series,
                    mode="lines",
                    name=f"{label} ({ma_window}日移動平均)",
                    yaxis=yaxis_name,
                    line={"width": 1.5, "dash": "dash", "color": color},
                    opacity=0.7,
                )
            )

    layout: dict[str, object] = {
        "hovermode": "x unified",
        "xaxis": {
            "title": "測定日時",
            "rangeslider": {"visible": True},
            "type": "date",
        },
        "yaxis": {
            "title": selected_labels[0],
            "showgrid": True,
        },
        "margin": {"l": 50, "r": 50, "t": 30, "b": 40},
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        "template": "plotly_white",
    }

    if is_dual_axis:
        layout["yaxis2"] = {
            "title": selected_labels[1],
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        }

    fig.update_layout(**layout)
    return fig


def create_segmental_radar_chart(
    muscle_arms: float,
    muscle_trunk: float,
    muscle_legs: float,
    fat_arms: float,
    fat_trunk: float,
    fat_legs: float,
) -> go.Figure:
    """Generate radar (polar) chart for arms, trunk, and legs balance.

    Args:
        muscle_arms: Skeletal muscle % of arms.
        muscle_trunk: Skeletal muscle % of trunk.
        muscle_legs: Skeletal muscle % of legs.
        fat_arms: Subcutaneous fat % of arms.
        fat_trunk: Subcutaneous fat % of trunk.
        fat_legs: Subcutaneous fat % of legs.

    Returns:
        Plotly Figure object.
    """
    categories = ["両腕", "体幹", "両脚"]
    muscle_vals = [muscle_arms, muscle_trunk, muscle_legs]
    fat_vals = [fat_arms, fat_trunk, fat_legs]

    categories_closed = [*categories, categories[0]]
    muscle_closed = [*muscle_vals, muscle_vals[0]]
    fat_closed = [*fat_vals, fat_vals[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=muscle_closed,
            theta=categories_closed,
            fill="toself",
            name="骨格筋率 (%)",
            line={"color": "#10B981", "width": 2},
            fillcolor="rgba(16, 185, 129, 0.2)",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=fat_closed,
            theta=categories_closed,
            fill="toself",
            name="皮下脂肪率 (%)",
            line={"color": "#F43F5E", "width": 2},
            fillcolor="rgba(244, 63, 94, 0.2)",
        )
    )
    max_val = max(max(muscle_vals, default=0.0), max(fat_vals, default=0.0))
    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, max_val + 5]}},
        margin={"l": 40, "r": 40, "t": 30, "b": 30},
        template="plotly_white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "center",
            "x": 0.5,
        },
    )
    return fig


def create_segmental_history_chart(
    df: pd.DataFrame,
    col_prefix: str,
    title: str,
) -> go.Figure:
    """Generate time series comparison of arms, trunk, and legs.

    Args:
        df: Filtered measurements DataFrame.
        col_prefix: 'skeletal_muscle' or 'subcutaneous_fat'.
        title: Plot title.

    Returns:
        Plotly Figure object.
    """
    col_map = {
        "両腕": f"{col_prefix}_arms_pct",
        "体幹": f"{col_prefix}_trunk_pct",
        "両脚": f"{col_prefix}_legs_pct",
    }

    fig = go.Figure()
    for segment_name, col_name in col_map.items():
        if col_name in df.columns:
            color = SEGMENT_COLORS.get(segment_name, "#4B5563")
            fig.add_trace(
                go.Scatter(
                    x=df["measured_at"],
                    y=df[col_name],
                    mode="lines+markers",
                    name=segment_name,
                    line={"width": 2, "color": color},
                    marker={"size": 4},
                    hovertemplate=f"<b>{segment_name}</b>: %{{y:.1f}}%<extra></extra>",
                )
            )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        xaxis={"title": "測定日時", "type": "date"},
        yaxis={"title": "(%)", "showgrid": True},
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
        template="plotly_white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    return fig


def create_composition_stack_chart(df: pd.DataFrame) -> go.Figure:
    """Generate stacked area chart breaking down weight into muscle, fat, and others.

    Args:
        df: Filtered measurements DataFrame.

    Returns:
        Plotly Figure object.
    """
    valid_df = df.dropna(subset=["weight", "skeletal_muscle_mass", "body_fat_mass"]).copy()
    if valid_df.empty:
        return go.Figure()

    other_mass = (
        valid_df["weight"] - (valid_df["skeletal_muscle_mass"] + valid_df["body_fat_mass"])
    ).clip(lower=0)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=valid_df["measured_at"],
            y=valid_df["skeletal_muscle_mass"],
            mode="lines",
            name="骨格筋量 (kg)",
            stackgroup="one",
            line={"width": 0.5, "color": "#10B981"},
            fillcolor="rgba(16, 185, 129, 0.7)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=valid_df["measured_at"],
            y=valid_df["body_fat_mass"],
            mode="lines",
            name="体脂肪量 (kg)",
            stackgroup="one",
            line={"width": 0.5, "color": "#F43F5E"},
            fillcolor="rgba(244, 63, 94, 0.7)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=valid_df["measured_at"],
            y=other_mass,
            mode="lines",
            name="その他 (骨・水分・内臓等) (kg)",
            stackgroup="one",
            line={"width": 0.5, "color": "#94A3B8"},
            fillcolor="rgba(148, 163, 184, 0.5)",
        )
    )

    fig.update_layout(
        title="体重内訳の推移 (スタック構成)",
        hovermode="x unified",
        xaxis={"title": "測定日時", "type": "date"},
        yaxis={"title": "重量 (kg)", "showgrid": True},
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
        template="plotly_white",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    return fig


def render_backup_sidebar() -> None:
    """Render standardized data protection backup trigger and receipts in sidebar."""
    with st.sidebar:
        st.divider()
        st.subheader("データ保護・バックアップ")

        current_dir = str(get_backup_dir())
        new_dir = st.text_input("保存先フォルダ", value=current_dir)
        if new_dir != current_dir and st.button("保存先パスを更新", use_container_width=True):
            save_res = set_backup_dir(new_dir)
            if save_res["success"]:
                st.success(save_res["message"])
                st.rerun()
            else:
                st.error(save_res["message"])

        if st.button("今すぐバックアップを実行", use_container_width=True):
            with st.spinner("圧縮・整合性検証中..."):
                res = run_backup(app_name="krd703t")
            if res["success"]:
                st.success(res["message"])
                st.caption(f"完了日時: {res['timestamp']}")
                st.caption(f"保存先: {res['destination']}")
            else:
                st.error(res["message"])


def main() -> None:
    """Streamlit application main orchestration entry point."""
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
                st.success(f"同期完了: {inserted} 件の測定ログを新規保存しました。")
            except (ValueError, pd.errors.ParserError, KeyError) as exc:
                st.error(f"取り込みエラー: {exc}")

    df = load_data(db_path)

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
            delta=(f"{delta_muscle:+.1f} %" if delta_muscle is not None else None),
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

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 トレンド推移",
            "🦾 部位別バランス (KRD-703T特有)",
            "📊 体組成構成 & 相関",
            "📋 測定ログ管理",
        ]
    )

    with tab1:
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
            st.plotly_chart(trend_fig, use_container_width=True)
        else:
            st.info("表示する指標を1つ以上選択してください。")

    with tab2:
        st.markdown("#### 部位別骨格筋・皮下脂肪バランス分析")
        sub_col1, sub_col2 = st.columns([1, 1])

        with sub_col1:
            st.markdown("##### 最新測定の部位別レーダー")
            radar_fig = create_segmental_radar_chart(
                muscle_arms=float(latest_row.get("skeletal_muscle_arms_pct", 0.0) or 0.0),
                muscle_trunk=float(latest_row.get("skeletal_muscle_trunk_pct", 0.0) or 0.0),
                muscle_legs=float(latest_row.get("skeletal_muscle_legs_pct", 0.0) or 0.0),
                fat_arms=float(latest_row.get("subcutaneous_fat_arms_pct", 0.0) or 0.0),
                fat_trunk=float(latest_row.get("subcutaneous_fat_trunk_pct", 0.0) or 0.0),
                fat_legs=float(latest_row.get("subcutaneous_fat_legs_pct", 0.0) or 0.0),
            )
            st.plotly_chart(radar_fig, use_container_width=True)

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
            st.dataframe(segment_summary, use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("##### 部位別推移グラフ")
        hist_col1, hist_col2 = st.columns(2)
        with hist_col1:
            muscle_hist_fig = create_segmental_history_chart(
                filtered_df, "skeletal_muscle", "部位別 骨格筋率の推移 (%)"
            )
            st.plotly_chart(muscle_hist_fig, use_container_width=True)

        with hist_col2:
            fat_hist_fig = create_segmental_history_chart(
                filtered_df, "subcutaneous_fat", "部位別 皮下脂肪率の推移 (%)"
            )
            st.plotly_chart(fat_hist_fig, use_container_width=True)

    with tab3:
        st.markdown("#### 体組成の内訳および相関")
        stack_fig = create_composition_stack_chart(filtered_df)
        st.plotly_chart(stack_fig, use_container_width=True)

        st.divider()
        st.markdown("##### 体重 vs 体脂肪率 の散布図 (体型変化トラッキング)")
        scatter_fig = go.Figure()
        scatter_fig.add_trace(
            go.Scatter(
                x=filtered_df["weight"],
                y=filtered_df["body_fat_pct"],
                mode="markers+lines",
                marker={
                    "size": 8,
                    "color": np.arange(len(filtered_df)),
                    "colorscale": "Blues",
                    "showscale": True,
                    "colorbar": {"title": "測定順 (濃い色=直近)"},
                },
                line={"width": 1, "color": "rgba(100, 116, 139, 0.4)"},
                text=filtered_df["measured_at"].dt.strftime("%Y/%m/%d %H:%M"),
                hovertemplate="<b>%{text}</b><br>体重: %{x:.2f} kg<br>体脂肪率: %{y:.1f}%<extra></extra>",
            )
        )
        scatter_fig.update_layout(
            xaxis={"title": "体重 (kg)", "showgrid": True},
            yaxis={"title": "体脂肪率 (%)", "showgrid": True},
            template="plotly_white",
            margin={"l": 40, "r": 40, "t": 30, "b": 40},
        )
        st.plotly_chart(scatter_fig, use_container_width=True)

    with tab4:
        st.markdown("#### 測定ログ一覧")
        st.dataframe(
            filtered_df.sort_values(by="measured_at", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("##### 統計サマリー (基本統計量)")
        st.dataframe(filtered_df.describe().T, use_container_width=True)

        st.markdown("##### データエクスポート")
        csv_buffer = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="💾 表示中データをCSVエクスポート",
            data=csv_buffer,
            file_name="krd703t_filtered_measurements.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.divider()
        st.markdown("##### データベース管理")
        with st.expander("⚙️ データベース初期化 (全データ消去)", expanded=False):
            st.warning("⚠️ SQLiteデータベース内の全測定レコードが完全に削除されます。")
            if st.button(
                "🗑️ 全データを消去して初期化",
                type="primary",
                use_container_width=True,
            ):
                clear_db(db_path)
                st.success("データベースを初期化しました。")
                st.rerun()


if __name__ == "__main__":
    main()
