"""批次計算結果的呈現：結果文字與曲線圖／長條圖／龍捲風圖。

只在 UI 執行緒、結果仍屬於目前這一輪計算時使用（見 ``BatchModule`` 的 publish）。
輸入是 application 回傳的結構化結果（canonical SI），依輸出單位系統換算與格式化；
不做任何計算，也不持有模組狀態。
"""

from __future__ import annotations

from math import nan

from matplotlib.figure import Figure

from application.batch import FLUID_VARIABLE, BatchTarget, SensitivityOutcome, SweepOutcome
from domain.batch import BatchPoint

from ...ui.theme import TOKENS
from ..unit.UnitConverter import UnitConverter
from .result_formatting import ResultFormatter

# 各性質在結果中的小數位數；無因次指標（COP、壓縮比）使用 NO_UNIT_DIGITS。
DIGITS = {"T": 1, "DeltaT": 1, "H": 1, "Power": 3, "MassFlow": 4, "VolumeFlow": 2, "P": 1,
          "Eff": 1, "EntropyFlow": 5}
NO_UNIT_DIGITS = 3
LOW_COLOR = "#2563EB"
HIGH_COLOR = "#EA580C"


class BatchPresenter:
    """把一次批次結果依輸出單位系統寫成結果文字並畫圖；每次發布建立一個。"""

    def __init__(self, unit_converter: UnitConverter, use_imperial: bool) -> None:
        """建立呈現器。

參數：
    unit_converter: 共用單位轉換器。
    use_imperial: 是否以英制輸出。

回傳：
    無。"""
        self.unit_converter = unit_converter
        self.formatter = ResultFormatter(unit_converter, use_imperial)

    def format_quantity(self, prop_code: str | None, value: float) -> str:
        """把 SI 數值格式化為目前輸出單位的「數值 單位」。

參數：
    prop_code: 性質代碼；None 表示無因次。
    value: SI 數值。

回傳：
    文字。"""
        if prop_code is None:
            return f"{value:.{NO_UNIT_DIGITS}f}"
        return self.formatter.quantity(prop_code, value, DIGITS.get(prop_code, 2))

    def format_input(self, target: BatchTarget, variable: str, value) -> str:
        """格式化一個輸入值（冷媒名稱原樣輸出）。

參數：
    target: 計算對象。
    variable: 輸入欄位名稱。
    value: 輸入值。

回傳：
    文字。"""
        if variable == FLUID_VARIABLE:
            return str(value)
        return self.format_quantity(target.variable(variable).prop_code, value)

    def add_position(self, prefix: str, target: BatchTarget, point: BatchPoint, variables: list[str]) -> None:
        """為一個點的每個掃描變數各寫一列「{prefix}時的{變數名稱}: 數值」。

每列的數值都很短，雙變數時也不會擠壓名稱欄；數值欄只含非中文字元（冷媒名稱原樣）。

參數：
    prefix: 列名稱前綴（例如「最大值」）。
    target: 計算對象。
    point: 批次點。
    variables: 掃描變數。

回傳：
    無。"""
        for variable in variables:
            name = "冷媒" if variable == FLUID_VARIABLE else target.variable(variable).label
            self.formatter.add_text(f"{prefix}時的{name}", self.format_input(target, variable, point.inputs[variable]))

    def chart_value(self, prop_code: str | None, value: float | None) -> float:
        """把 SI 數值換成圖表使用的輸出單位數值；失敗點為 NaN（圖上斷線）。

參數：
    prop_code: 性質代碼；None 表示無因次。
    value: SI 數值或 None。

回傳：
    數值。"""
        if value is None:
            return nan
        if prop_code is None:
            return value
        return self.unit_converter.convert_from_si(prop_code, value, self.formatter.unit(prop_code))

    def axis_title(self, label: str, prop_code: str | None) -> str:
        """圖表座標軸標題。

參數：
    label: 名稱。
    prop_code: 性質代碼；None 表示無因次。

回傳：
    例如「冷凝溫度 [°C]」。"""
        return label if prop_code is None else f"{label} [{self.formatter.unit(prop_code)}]"

    def sweep_text(self, outcome: SweepOutcome) -> str:
        """把掃描結果寫成「名稱: 數值」文字：摘要、每條曲線的數值與無法計算的點。

參數：
    outcome: 掃描結果。

回傳：
    結果文字。"""
        target, result, metric = outcome.target, outcome.result, outcome.metric
        formatter = self.formatter
        variables = [axis.variable for axis in result.axes]
        succeeded = result.succeeded
        formatter.section("摘要")
        formatter.add_text("計算點數", f"{len(succeeded)} / {len(result.points)}")
        if succeeded:
            best = max(succeeded, key=lambda point: point.metrics[metric.key])
            worst = min(succeeded, key=lambda point: point.metrics[metric.key])
            formatter.add_text("最大值", self.format_quantity(metric.prop_code, best.metrics[metric.key]))
            self.add_position("最大值", target, best, variables)
            formatter.add_text("最小值", self.format_quantity(metric.prop_code, worst.metrics[metric.key]))
            self.add_position("最小值", target, worst, variables)
        x_variable = variables[0]
        for group, values in result.series(metric.key):
            if group is None:
                formatter.section(metric.label)
            elif len(variables) > 1 and variables[1] == FLUID_VARIABLE:
                formatter.section(f"{metric.label}（{group}）")
            else:
                name = target.variable(variables[1]).label
                formatter.section(f"{metric.label}（{name} {self.format_input(target, variables[1], group)}）")
            for x_value, value in values:
                x_text = self.format_input(target, x_variable, x_value)
                label = x_text if x_variable == FLUID_VARIABLE else f"{target.variable(x_variable).label} {x_text}"
                formatter.add_text(label, "-" if value is None else
                                   self.format_quantity(metric.prop_code, value))
        if result.failed:
            formatter.section("無法計算的點")
            for point in result.failed:
                where = "、".join(
                    self.format_input(target, variable, point.inputs[variable])
                    if variable == FLUID_VARIABLE else
                    f"{target.variable(variable).label} {self.format_input(target, variable, point.inputs[variable])}"
                    for variable in variables)
                formatter.lines.append(f"{where}：{point.error}")
        return formatter.text()

    def plot_sweep(self, figure: Figure, outcome: SweepOutcome) -> None:
        """畫掃描曲線（橫軸為第一軸）；第一軸是冷媒時畫長條圖。

參數：
    figure: 要重畫的 Matplotlib figure（呼叫端負責通知圖表面板更新）。
    outcome: 掃描結果。

回傳：
    無。"""
        target, result, metric = outcome.target, outcome.result, outcome.metric
        variables = [axis.variable for axis in result.axes]
        figure.clear()
        # 圖表面板會依畫面寬度調整 figure 尺寸；constrained layout 在每次重繪時重新配置，座標軸標題不會被裁掉。
        figure.set_layout_engine("constrained")
        axes = figure.add_subplot(111)
        series = result.series(metric.key)
        if variables[0] == FLUID_VARIABLE:
            (_, values), = series
            names = [str(name) for name, _ in values]
            heights = [self.chart_value(metric.prop_code, value) for _, value in values]
            axes.bar(names, heights, color=TOKENS.primary)
            for index, height in enumerate(heights):
                if height == height:  # NaN 不標示
                    axes.annotate(self.format_quantity(metric.prop_code, values[index][1]),
                                  (index, height), ha="center", va="bottom", fontsize=9)
            axes.set_xlabel("冷媒")
        else:
            x_variable = target.variable(variables[0])
            for group, values in series:
                xs = [self.chart_value(x_variable.prop_code, x) for x, _ in values]
                ys = [self.chart_value(metric.prop_code, value) for _, value in values]
                if group is None:
                    label = None
                elif variables[1] == FLUID_VARIABLE:
                    label = str(group)
                else:
                    label = f"{target.variable(variables[1]).symbol} = " \
                            f"{self.format_input(target, variables[1], group)}"
                axes.plot(xs, ys, marker="o", markersize=4, linewidth=1.6, label=label)
            axes.set_xlabel(self.axis_title(x_variable.label, x_variable.prop_code))
            if len(series) > 1:
                axes.legend(fontsize=8)
        axes.set_ylabel(self.axis_title(metric.label, metric.prop_code))
        axes.grid(True, alpha=0.3)

    def plot_tornado(self, figure: Figure, outcome: SensitivityOutcome) -> None:
        """畫龍捲風圖：每個輸入一列，由基準值畫到 −Δ 與 +Δ 時的指標值；影響最大者在最上方。

參數：
    figure: 要重畫的 Matplotlib figure（呼叫端負責通知圖表面板更新）。
    outcome: 敏感度結果。

回傳：
    無。"""
        target, result, metric = outcome.target, outcome.result, outcome.metric
        base = self.chart_value(metric.prop_code, result.base_value)
        figure.clear()
        # 圖表面板會依畫面寬度調整 figure 尺寸；constrained layout 在每次重繪時重新配置，座標軸標題不會被裁掉。
        figure.set_layout_engine("constrained")
        axes = figure.add_subplot(111)
        rows = list(reversed(result.rows))
        labels = []
        for index, row in enumerate(rows):
            variable = target.variable(row.variable)
            delta = self.format_quantity(variable.delta_prop_code, row.delta)
            labels.append(f"{variable.label} ± {delta}")
            for point, color, name in ((row.low, LOW_COLOR, "−Δ"), (row.high, HIGH_COLOR, "+Δ")):
                value = self.chart_value(metric.prop_code, row.metric(point, metric.key))
                if value == value:
                    axes.barh(index, value - base, left=base, color=color, height=0.6,
                              label=name if index == 0 else None)
        axes.axvline(base, color="#374151", linewidth=1)
        axes.set_yticks(range(len(rows)), labels)
        axes.set_xlabel(self.axis_title(metric.label, metric.prop_code))
        axes.legend(fontsize=8, loc="lower right")
        axes.grid(True, axis="x", alpha=0.3)

    def sensitivity_text(self, outcome: SensitivityOutcome) -> str:
        """敏感度結果文字：基準值、影響最大的輸入，以及每個輸入 ±Δ 時的指標值與變化量。

參數：
    outcome: 敏感度結果。

回傳：
    結果文字。"""
        target, result, metric = outcome.target, outcome.result, outcome.metric
        formatter = self.formatter
        formatter.section("摘要")
        formatter.add_text("基準值", self.format_quantity(metric.prop_code, result.base_value))
        top = result.rows[0]
        formatter.add_text("影響最大", target.variable(top.variable).symbol)
        formatter.add_text("最大變化幅度", self.format_quantity(metric.prop_code, result.swing(top))
                           if metric.prop_code != "T" else formatter.quantity("DeltaT", result.swing(top), 1))
        failures = []
        for row in result.rows:
            variable = target.variable(row.variable)
            delta = self.format_quantity(variable.delta_prop_code, row.delta)
            formatter.section(f"{variable.label}（± {delta}）")
            for point, sign in ((row.low, "−"), (row.high, "+")):
                value = row.metric(point, metric.key)
                if value is None:
                    formatter.add_text(f"{sign}Δ 時的{metric.label}", "-")
                    failures.append(f"{variable.label} {sign}{delta}：{point.error}")
                    continue
                formatter.add_text(f"{sign}Δ 時的{metric.label}",
                                   self.format_quantity(metric.prop_code, value))
        if failures:
            formatter.section("無法計算的變動")
            formatter.lines.extend(failures)
        return formatter.text()
