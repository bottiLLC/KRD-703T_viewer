"""Unit test suite for pure analytical chart generators and transformation primitives."""

from __future__ import annotations

import pandas as pd
import pytest

from charts import (
    calculate_delta,
    create_composition_stack_chart,
    create_scatter_correlation_chart,
    create_segmental_history_chart,
    create_segmental_radar_chart,
    create_trend_chart,
)


@pytest.fixture
def sample_measurements_df() -> pd.DataFrame:
    """Provide structured DataFrame for chart generation tests."""
    dates = pd.date_range("2026-10-01 08:00", periods=10, freq="D")
    return pd.DataFrame(
        {
            "measured_at": dates,
            "weight": [65.0 + i * 0.2 for i in range(10)],
            "body_fat_pct": [18.0 - i * 0.1 for i in range(10)],
            "body_fat_mass": [11.7 - i * 0.05 for i in range(10)],
            "skeletal_muscle_pct": [34.0 + i * 0.1 for i in range(10)],
            "skeletal_muscle_mass": [22.1 + i * 0.1 for i in range(10)],
            "skeletal_muscle_arms_pct": [30.0 + i * 0.1 for i in range(10)],
            "skeletal_muscle_trunk_pct": [32.0 + i * 0.1 for i in range(10)],
            "skeletal_muscle_legs_pct": [48.0 + i * 0.1 for i in range(10)],
            "subcutaneous_fat_arms_pct": [15.0 - i * 0.1 for i in range(10)],
            "subcutaneous_fat_trunk_pct": [16.0 - i * 0.1 for i in range(10)],
            "subcutaneous_fat_legs_pct": [17.0 - i * 0.1 for i in range(10)],
        }
    )


def test_calculate_delta_insufficient_or_nan() -> None:
    """Verify calculate_delta returns None on empty or single-observation series."""
    empty_series: pd.Series[float] = pd.Series([1.0], dtype=float).iloc[:0]
    assert calculate_delta(empty_series) is None
    assert calculate_delta(pd.Series([65.0], dtype=float)) is None
    assert calculate_delta(pd.Series([float("nan"), 65.0], dtype=float)) is None
    assert calculate_delta(pd.Series([float("nan"), float("nan")], dtype=float)) is None


def test_calculate_delta_success() -> None:
    """Verify calculate_delta computes correct numerical difference."""
    series = pd.Series([65.0, 64.5, 64.2])
    delta = calculate_delta(series)
    assert delta is not None
    assert pytest.approx(delta, rel=1e-3) == -0.3


def test_create_trend_chart_empty_or_no_labels() -> None:
    """Verify create_trend_chart returns blank figure on empty input."""
    fig_empty_df = create_trend_chart(pd.DataFrame(), ["体重 (kg)"])
    fig_no_labels = create_trend_chart(
        pd.DataFrame({"measured_at": [pd.Timestamp("2026-10-01")]}), []
    )
    assert len(fig_empty_df.data) == 0
    assert len(fig_no_labels.data) == 0


def test_create_trend_chart_single_metric_with_ma(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify create_trend_chart adds primary trace and moving average trace."""
    fig = create_trend_chart(
        sample_measurements_df,
        selected_labels=["体重 (kg)"],
        show_ma=True,
        ma_window=5,
    )
    assert len(fig.data) == 2
    assert fig.data[0].name == "体重 (kg)"
    assert "5日MA" in str(fig.data[1].name)


def test_create_trend_chart_dual_metric_with_ma(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify create_trend_chart adds dual axes and secondary moving average."""
    fig = create_trend_chart(
        sample_measurements_df,
        selected_labels=["体重 (kg)", "体脂肪率 (%)"],
        show_ma=True,
        ma_window=7,
    )
    assert len(fig.data) == 4
    assert fig.data[0].yaxis == "y"
    assert fig.data[2].yaxis == "y2"
    assert "yaxis2" in fig.layout


def test_create_trend_chart_ma_window_exceeds_length(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify moving average is skipped when window exceeds DataFrame row count."""
    fig = create_trend_chart(
        sample_measurements_df,
        selected_labels=["体重 (kg)", "体脂肪率 (%)"],
        show_ma=True,
        ma_window=50,
    )
    assert len(fig.data) == 2
    assert fig.data[0].name == "体重 (kg)"
    assert fig.data[1].name == "体脂肪率 (%)"


def test_create_trend_chart_unknown_columns(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify unknown labels do not generate traces."""
    fig = create_trend_chart(
        sample_measurements_df,
        selected_labels=["未知指標A", "未知指標B"],
    )
    assert len(fig.data) == 0


def test_create_segmental_radar_chart() -> None:
    """Verify create_segmental_radar_chart generates closed polar traces."""
    fig = create_segmental_radar_chart(
        muscle_arms=30.0,
        muscle_trunk=32.0,
        muscle_legs=48.0,
        fat_arms=15.0,
        fat_trunk=16.0,
        fat_legs=17.0,
    )
    assert len(fig.data) == 2
    assert fig.data[0].name == "骨格筋率 (%)"
    assert fig.data[1].name == "皮下脂肪率 (%)"
    assert len(fig.data[0].r) == 4
    assert fig.data[0].r[0] == fig.data[0].r[3]


def test_create_segmental_history_chart_empty() -> None:
    """Verify create_segmental_history_chart returns blank figure on empty df."""
    fig = create_segmental_history_chart(pd.DataFrame(), "skeletal_muscle", "部位別骨格筋")
    assert len(fig.data) == 0
    assert fig.layout.title.text == "部位別骨格筋"


def test_create_segmental_history_chart_success(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify create_segmental_history_chart generates 3 traces for arms, trunk, legs."""
    fig = create_segmental_history_chart(sample_measurements_df, "skeletal_muscle", "骨格筋推移")
    assert len(fig.data) == 3
    assert [t.name for t in fig.data] == ["両腕", "体幹", "両脚"]


def test_create_segmental_history_chart_missing_columns() -> None:
    """Verify create_segmental_history_chart gracefully handles missing segmental columns."""
    partial_df = pd.DataFrame(
        {
            "measured_at": pd.date_range("2026-10-01", periods=3),
            "skeletal_muscle_arms_pct": [30.0, 31.0, 32.0],
        }
    )
    fig = create_segmental_history_chart(partial_df, "skeletal_muscle", "骨格筋推移")
    assert len(fig.data) == 1
    assert fig.data[0].name == "両腕"


def test_create_composition_stack_chart_empty() -> None:
    """Verify create_composition_stack_chart returns blank figure on empty input."""
    fig = create_composition_stack_chart(pd.DataFrame())
    assert len(fig.data) == 0


def test_create_composition_stack_chart_success(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify create_composition_stack_chart creates 3 stacked area traces."""
    fig = create_composition_stack_chart(sample_measurements_df)
    assert len(fig.data) == 3
    assert fig.data[0].name == "骨格筋量 (kg)"
    assert fig.data[1].name == "体脂肪量 (kg)"
    assert fig.data[2].name == "水分・骨・その他 (kg)"
    assert fig.data[0].stackgroup == "one"


def test_create_composition_stack_chart_clamped_other_mass() -> None:
    """Verify other_mass is non-negative even when muscle and fat sum exceeds weight."""
    df = pd.DataFrame(
        {
            "measured_at": [pd.Timestamp("2026-10-01")],
            "weight": [50.0],
            "skeletal_muscle_mass": [30.0],
            "body_fat_mass": [25.0],
        }
    )
    fig = create_composition_stack_chart(df)
    assert len(fig.data) == 3
    other_trace = fig.data[2]
    assert float(other_trace.y[0]) == 0.0


def test_create_scatter_correlation_chart_empty() -> None:
    """Verify create_scatter_correlation_chart returns empty figure on empty df."""
    fig = create_scatter_correlation_chart(pd.DataFrame())
    assert len(fig.data) == 0


def test_create_scatter_correlation_chart_success(
    sample_measurements_df: pd.DataFrame,
) -> None:
    """Verify create_scatter_correlation_chart creates marker+line scatter plot."""
    fig = create_scatter_correlation_chart(sample_measurements_df)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.mode == "markers+lines"
    assert len(trace.x) == len(sample_measurements_df)
    assert len(trace.y) == len(sample_measurements_df)
