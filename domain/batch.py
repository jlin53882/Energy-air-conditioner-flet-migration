"""批次計算引擎：同一個計算以多組輸入重複執行（參數掃描、類別維度比較、單因子敏感度）。

引擎只處理「輸入組合 → 計算函式 → 數值指標」的流程，不知道任何特定計算；
計算函式由 application 層提供，輸入與輸出都是 canonical SI 的結構化數值，
不解析顯示文字。單一點的 ``ValueError``（輸入不合理、狀態無法計算）記錄為
該點失敗、其餘點照常計算；其他例外視為程式錯誤，直接往外拋出。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from math import isfinite

# 每個掃描軸最多點數與一次批次的總計算次數上限，避免一次送出過大的計算量。
MAX_AXIS_POINTS = 41
MAX_TOTAL_POINTS = 400
MAX_AXES = 2

InputValue = float | str
Evaluate = Callable[[Mapping[str, InputValue]], Mapping[str, float]]


def linear_values(start: float, stop: float, count: int) -> tuple[float, ...]:
    """回傳由 start 到 stop（含兩端）等間距的 count 個數值。

參數：
    start: 起點。
    stop: 終點。
    count: 點數（2 至 ``MAX_AXIS_POINTS``）。

回傳：
    數值 tuple；最後一點精確等於 stop。

引發：
    ValueError：點數超出範圍、起終點不是有限數字或相同時。"""
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= MAX_AXIS_POINTS:
        raise ValueError(f"點數必須是 2 至 {MAX_AXIS_POINTS} 的整數。")
    if not (isfinite(start) and isfinite(stop)):
        raise ValueError("起點與終點必須是有限數字。")
    if start == stop:
        raise ValueError("起點與終點不可相同。")
    step = (stop - start) / (count - 1)
    return tuple(start + step * index for index in range(count - 1)) + (stop,)


@dataclass(frozen=True)
class SweepAxis:
    """一個掃描維度：輸入名稱與依序計算的數值（數值或類別，例如冷媒名稱）。"""

    variable: str
    values: tuple[InputValue, ...]

    def __post_init__(self) -> None:
        """驗證名稱與數值。

回傳：
    無。

引發：
    ValueError：名稱空白、沒有數值、超過點數上限、數值重複或數值不是有限數字時。"""
        if not isinstance(self.variable, str) or not self.variable.strip():
            raise ValueError("掃描變數名稱不可空白。")
        values = tuple(self.values)
        if not values:
            raise ValueError("掃描變數至少需要一個數值。")
        if len(values) > MAX_AXIS_POINTS:
            raise ValueError(f"每個掃描變數最多 {MAX_AXIS_POINTS} 個數值。")
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError("掃描數值必須是數字或文字。")
            if isinstance(value, (int, float)) and not isfinite(value):
                raise ValueError("掃描數值必須是有限數字。")
        if len(set(values)) != len(values):
            raise ValueError("掃描數值不可重複。")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class BatchPoint:
    """一組輸入的計算結果；失敗時 ``metrics`` 為 None，``error`` 為原因。"""

    inputs: Mapping[str, InputValue]
    metrics: Mapping[str, float] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """此點是否計算成功。

回傳：
    bool。"""
        return self.metrics is not None


@dataclass(frozen=True)
class BatchResult:
    """掃描結果：依軸的笛卡兒積排列（第一軸變化最慢）。"""

    axes: tuple[SweepAxis, ...]
    points: tuple[BatchPoint, ...]

    @property
    def succeeded(self) -> tuple[BatchPoint, ...]:
        """計算成功的點。

回傳：
    BatchPoint tuple。"""
        return tuple(point for point in self.points if point.ok)

    @property
    def failed(self) -> tuple[BatchPoint, ...]:
        """計算失敗的點。

回傳：
    BatchPoint tuple。"""
        return tuple(point for point in self.points if not point.ok)

    def series(self, metric: str) -> list[tuple[InputValue | None, list[tuple[InputValue, float | None]]]]:
        """依最後一軸以外的軸分組，回傳各組沿第一軸的指標值（失敗點為 None）。

單軸時只有一組，組名為 None；雙軸時每個第二軸數值一組，x 為第一軸數值。

參數：
    metric: 指標名稱。

回傳：
    [(組名, [(x, 指標值或 None), ...]), ...]。"""
        x_axis = self.axes[0]
        groups = self.axes[1].values if len(self.axes) > 1 else (None,)
        result = []
        for group in groups:
            values = []
            for point in self.points:
                if len(self.axes) > 1 and point.inputs[self.axes[1].variable] != group:
                    continue
                values.append((point.inputs[x_axis.variable],
                               point.metrics[metric] if point.metrics is not None else None))
            result.append((group, values))
        return result


def evaluate_point(evaluate: Evaluate, inputs: Mapping[str, InputValue]) -> BatchPoint:
    """計算一組輸入；只把 ``ValueError`` 視為此點失敗。

參數：
    evaluate: 計算函式，回傳 {指標名稱: SI 數值}。
    inputs: 完整輸入。

回傳：
    BatchPoint。"""
    try:
        metrics = dict(evaluate(inputs))
    except ValueError as exc:
        return BatchPoint(dict(inputs), error=str(exc))
    return BatchPoint(dict(inputs), metrics=metrics)


def run_sweep(evaluate: Evaluate, base: Mapping[str, InputValue], axes: Sequence[SweepAxis]) -> BatchResult:
    """在 base 輸入上以一或兩個掃描軸的所有組合執行計算。

參數：
    evaluate: 計算函式。
    base: 基準輸入；掃描變數必須是其中的鍵。
    axes: 1 至 ``MAX_AXES`` 個掃描軸，變數不可重複。

回傳：
    BatchResult。

引發：
    ValueError：軸數不合、變數重複或不在基準輸入中、總點數超過上限時。"""
    axes = tuple(axes)
    if not 1 <= len(axes) <= MAX_AXES:
        raise ValueError(f"掃描變數必須是 1 至 {MAX_AXES} 個。")
    names = [axis.variable for axis in axes]
    if len(set(names)) != len(names):
        raise ValueError("兩個掃描變數不可相同。")
    for name in names:
        if name not in base:
            raise ValueError(f"未知的掃描變數：{name}")
    total = 1
    for axis in axes:
        total *= len(axis.values)
    if total > MAX_TOTAL_POINTS:
        raise ValueError(f"一次最多計算 {MAX_TOTAL_POINTS} 點（目前 {total} 點）；請減少點數。")
    points = tuple(
        evaluate_point(evaluate, {**base, **dict(zip(names, combination))})
        for combination in product(*(axis.values for axis in axes))
    )
    return BatchResult(axes, points)


# ======================================================
# 單因子敏感度（龍捲風圖）
# ======================================================
@dataclass(frozen=True)
class Perturbation:
    """敏感度分析的一個輸入：在基準值上下各變動 delta（與輸入同單位的正值）。"""

    variable: str
    delta: float

    def __post_init__(self) -> None:
        """驗證變動量。

回傳：
    無。

引發：
    ValueError：名稱空白或變動量不是正的有限數字時。"""
        if not isinstance(self.variable, str) or not self.variable.strip():
            raise ValueError("敏感度變數名稱不可空白。")
        if isinstance(self.delta, bool) or not isinstance(self.delta, (int, float)) \
                or not isfinite(self.delta) or self.delta <= 0:
            raise ValueError("敏感度變動量必須是正的有限數字。")


@dataclass(frozen=True)
class SensitivityRow:
    """一個輸入往下（base − delta）與往上（base + delta）時的指標值；失敗側為 None 並附原因。"""

    variable: str
    delta: float
    low: BatchPoint
    high: BatchPoint

    def metric(self, point: BatchPoint, metric: str) -> float | None:
        """讀取一側的指標值。

參數：
    point: low 或 high。
    metric: 指標名稱。

回傳：
    指標值；該側失敗時為 None。"""
        return point.metrics[metric] if point.metrics is not None else None


@dataclass(frozen=True)
class SensitivityResult:
    """單因子敏感度結果；``rows`` 依指標變化幅度由大到小排列。"""

    metric: str
    base: BatchPoint
    rows: tuple[SensitivityRow, ...]

    @property
    def base_value(self) -> float:
        """基準點的指標值。

回傳：
    指標值。"""
        return self.base.metrics[self.metric]

    def swing(self, row: SensitivityRow) -> float:
        """一個輸入造成的指標變化幅度：兩側相對基準的最大絕對差（失敗側不計）。

參數：
    row: 敏感度列。

回傳：
    非負數；兩側都失敗時為 0。"""
        changes = [abs(value - self.base_value)
                   for value in (row.metric(row.low, self.metric), row.metric(row.high, self.metric))
                   if value is not None]
        return max(changes, default=0.0)


def run_sensitivity(
    evaluate: Evaluate, base: Mapping[str, InputValue], perturbations: Sequence[Perturbation], metric: str
) -> SensitivityResult:
    """一次只變動一個輸入（其餘固定在基準），比較指標變化並依幅度排序。

參數：
    evaluate: 計算函式。
    base: 基準輸入。
    perturbations: 要分析的輸入與變動量，變數不可重複。
    metric: 用來排序的指標名稱。

回傳：
    SensitivityResult。

引發：
    ValueError：沒有輸入、變數重複或不在基準輸入中（或不是數值）、基準點本身無法計算，
    或指標名稱不存在時。"""
    perturbations = tuple(perturbations)
    if not perturbations:
        raise ValueError("請至少選擇一個敏感度變數。")
    names = [item.variable for item in perturbations]
    if len(set(names)) != len(names):
        raise ValueError("敏感度變數不可重複。")
    for item in perturbations:
        value = base.get(item.variable)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"敏感度變數必須是基準輸入中的數值：{item.variable}")
    base_point = evaluate_point(evaluate, base)
    if not base_point.ok:
        raise ValueError(f"基準條件無法計算：{base_point.error}")
    if metric not in base_point.metrics:
        raise ValueError(f"未知的指標：{metric}")
    rows = [
        SensitivityRow(
            item.variable,
            item.delta,
            evaluate_point(evaluate, {**base, item.variable: float(base[item.variable]) - item.delta}),
            evaluate_point(evaluate, {**base, item.variable: float(base[item.variable]) + item.delta}),
        )
        for item in perturbations
    ]
    result = SensitivityResult(metric, base_point, tuple(rows))
    # 穩定排序：幅度相同時維持輸入順序。
    return SensitivityResult(metric, base_point, tuple(sorted(rows, key=result.swing, reverse=True)))
