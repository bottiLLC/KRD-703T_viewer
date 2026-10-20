"""Pure analytical chart generators and transformation primitives for KRD-703T metrics.

Isolates domain transformations, calculations, and Plotly visualization engines
from the Streamlit GUI presentation layer, guaranteeing 100% testability and SRP.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

import numpy as np
import pandas as pd
import plotly.graph_objects as go

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
        df: Filtered measurement DataFrame with datetime column.
        selected_labels: Display metric names selected by user.
        show_ma: Whether to render rolling moving average line.
        ma_window: Rolling window size in days.

    Returns:
        Plotly Figure object configured with primary and secondary axes.
    """
    fig = go.Figure()
    if df.empty or not selected_labels:
        fig.update_layout(template="plotly_white")
        return fig

    primary_col = METRIC_LABELS.get(selected_labels[0])
    secondary_col = METRIC_LABELS.get(selected_labels[1]) if len(selected_labels) > 1 else None

    if primary_col and primary_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["measured_at"],
                y=df[primary_col],
                name=selected_labels[0],
                mode="lines+markers",
                line={"color": METRIC_COLORS.get(primary_col, "#1E293B"), "width": 2},
                marker={"size": 4},
                yaxis="y",
            )
        )
        if show_ma and len(df) >= ma_window:
            rolling_series = df[primary_col].rolling(window=ma_window, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["measured_at"],
                    y=rolling_series,
                    name=f"{selected_labels[0]} ({ma_window}日MA)",
                    line={
                        "color": METRIC_COLORS.get(primary_col, "#1E293B"),
                        "width": 1.5,
                        "dash": "dot",
                    },
                    yaxis="y",
                )
            )

    if secondary_col and secondary_col in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["measured_at"],
                y=df[secondary_col],
                name=selected_labels[1],
                mode="lines+markers",
                line={
                    "color": METRIC_COLORS.get(secondary_col, "#DC2626"),
                    "width": 2,
                },
                marker={"size": 4},
                yaxis="y2",
            )
        )
        if show_ma and len(df) >= ma_window:
            rolling_series_sec = df[secondary_col].rolling(window=ma_window, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["measured_at"],
                    y=rolling_series_sec,
                    name=f"{selected_labels[1]} ({ma_window}日MA)",
                    line={
                        "color": METRIC_COLORS.get(secondary_col, "#DC2626"),
                        "width": 1.5,
                        "dash": "dot",
                    },
                    yaxis="y2",
                )
            )

    layout_updates: dict[str, object] = {
        "xaxis": {"title": "測定日時", "showgrid": True},
        "yaxis": {"title": selected_labels[0], "showgrid": True},
        "hovermode": "x unified",
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        "margin": {"l": 40, "r": 40, "t": 30, "b": 40},
        "template": "plotly_white",
    }
    if secondary_col:
        layout_updates["yaxis2"] = {
            "title": selected_labels[1],
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
        }

    fig.update_layout(**layout_updates)
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
        muscle_arms: Skeletal muscle percentage of arms.
        muscle_trunk: Skeletal muscle percentage of trunk.
        muscle_legs: Skeletal muscle percentage of legs.
        fat_arms: Subcutaneous fat percentage of arms.
        fat_trunk: Subcutaneous fat percentage of trunk.
        fat_legs: Subcutaneous fat percentage of legs.

    Returns:
        Plotly Figure radar chart with closed loops.
    """
    categories = ["両腕", "体幹", "両脚"]
    fig = go.Figure()

    fig.add_trace(
        go.Scatterpolar(
            r=[muscle_arms, muscle_trunk, muscle_legs, muscle_arms],
            theta=categories + [categories[0]],
            fill="toself",
            name="骨格筋率 (%)",
            line={"color": "#16A34A", "width": 2},
            fillcolor="rgba(22, 163, 74, 0.25)",
        )
    )

    fig.add_trace(
        go.Scatterpolar(
            r=[fat_arms, fat_trunk, fat_legs, fat_arms],
            theta=categories + [categories[0]],
            fill="toself",
            name="皮下脂肪率 (%)",
            line={"color": "#DC2626", "width": 2},
            fillcolor="rgba(220, 38, 38, 0.25)",
        )
    )

    fig.update_layout(
        polar={"radialaxis": {"visible": True, "showline": True, "showgrid": True}},
        showlegend=True,
        template="plotly_white",
        margin={"l": 30, "r": 30, "t": 30, "b": 30},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.2, "xanchor": "center", "x": 0.5},
    )
    return fig


def create_segmental_history_chart(df: pd.DataFrame, col_prefix: str, title: str) -> go.Figure:
    """Generate time series comparison of arms, trunk, and legs.

    Args:
        df: Filtered measurement DataFrame with segment metrics.
        col_prefix: Metric prefix ('skeletal_muscle' or 'subcutaneous_fat').
        title: Chart title.

    Returns:
        Plotly Figure time series object.
    """
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title=title, template="plotly_white")
        return fig

    segments = [("両腕", "_arms_pct"), ("体幹", "_trunk_pct"), ("両脚", "_legs_pct")]
    for label, suffix in segments:
        col = f"{col_prefix}{suffix}"
        if col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["measured_at"],
                    y=df[col],
                    name=label,
                    mode="lines+markers",
                    line={"color": SEGMENT_COLORS.get(label, "#64748B"), "width": 2},
                    marker={"size": 4},
                )
            )

    fig.update_layout(
        title=title,
        xaxis={"title": "測定日時", "showgrid": True},
        yaxis={"title": "割合 (%)", "showgrid": True},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        template="plotly_white",
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
    )
    return fig


def create_composition_stack_chart(df: pd.DataFrame) -> go.Figure:
    """Generate stacked area chart breaking down weight into muscle, fat, and others.

    Args:
        df: Filtered measurement DataFrame.

    Returns:
        Plotly Figure stacked area object.
    """
    fig = go.Figure()
    if df.empty:
        fig.update_layout(template="plotly_white")
        return fig

    other_mass = np.maximum(0.0, df["weight"] - df["skeletal_muscle_mass"] - df["body_fat_mass"])

    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=df["skeletal_muscle_mass"],
            name="骨格筋量 (kg)",
            mode="lines",
            stackgroup="one",
            line={"width": 0.5, "color": "#16A34A"},
            fillcolor="rgba(22, 163, 74, 0.6)",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=df["body_fat_mass"],
            name="体脂肪量 (kg)",
            mode="lines",
            stackgroup="one",
            line={"width": 0.5, "color": "#EA580C"},
            fillcolor="rgba(234, 88, 12, 0.6)",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=other_mass,
            name="水分・骨・その他 (kg)",
            mode="lines",
            stackgroup="one",
            line={"width": 0.5, "color": "#94A3B8"},
            fillcolor="rgba(148, 163, 184, 0.5)",
        )
    )

    fig.update_layout(
        title="体組成内訳の推移 (積層エリア)",
        xaxis={"title": "測定日時", "showgrid": True},
        yaxis={"title": "重量 (kg)", "showgrid": True},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        template="plotly_white",
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
    )
    return fig


def create_scatter_correlation_chart(df: pd.DataFrame) -> go.Figure:
    """Generate scatter tracking chart between weight and body fat percentage.

    Args:
        df: Filtered measurement DataFrame with weight and body_fat_pct.

    Returns:
        Plotly Figure scatter plot with chronological color gradient.
    """
    fig = go.Figure()
    if df.empty:
        fig.update_layout(template="plotly_white")
        return fig

    fig.add_trace(
        go.Scatter(
            x=df["weight"],
            y=df["body_fat_pct"],
            mode="markers+lines",
            marker={
                "size": 8,
                "color": np.arange(len(df)),
                "colorscale": "Blues",
                "showscale": True,
                "colorbar": {"title": "測定順 (濃い色=直近)"},
            },
            line={"width": 1, "color": "rgba(100, 116, 139, 0.4)"},
            text=df["measured_at"].dt.strftime("%Y/%m/%d %H:%M"),
            hovertemplate="<b>%{text}</b><br>体重: %{x:.2f} kg<br>体脂肪率: %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis={"title": "体重 (kg)", "showgrid": True},
        yaxis={"title": "体脂肪率 (%)", "showgrid": True},
        template="plotly_white",
        margin={"l": 40, "r": 40, "t": 30, "b": 40},
    )
    return fig
