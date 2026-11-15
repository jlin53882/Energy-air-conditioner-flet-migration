"""壓縮機頻率控制元件：PID 控制器與階梯頻率量化器（``docs/simulation-model.md`` §2.3）。

壓縮機為定頻機型，由外接變頻器在固定階梯（預設 30／40／50／60 Hz）間運轉：
:class:`PidController` 輸出連續的目標頻率，:class:`FrequencyStepper` 再把它換成階梯，
並以遲滯與最短停留時間避免在相鄰階梯間來回跳動。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PidController:
    """位置型 PID（含微分濾波與條件式積分抗飽和）。

    ``u = bias + Kp·e + I + Kp·Td·ė_f``，其中 ``I`` 以 ``Kp/Ti·e·dt`` 累積，
    輸出在 ``(out_min, out_max)`` 之內才積分（避免積分飽和）；``ė_f`` 為經一階低通濾波的誤差變化率。
    ``ti_s``、``td_s`` 為 0 時分別關閉積分與微分。
    """

    kp: float
    ti_s: float
    td_s: float
    out_min: float
    out_max: float
    bias: float = 0.0
    filter_ratio: float = 5.0
    integral: float = 0.0
    _previous_error: float | None = field(default=None, repr=False)
    _derivative: float = field(default=0.0, repr=False)

    def reset(self) -> None:
        """清除積分與微分狀態。

回傳：
            無。"""
        self.integral = 0.0
        self._previous_error = None
        self._derivative = 0.0

    def preset(self, output: float, error: float) -> None:
        """無擾切換：令下一次輸出（不含微分）等於 ``output``。

參數：
            output: 目標輸出。
            error: 目前誤差。

回傳：
            無。"""
        self.integral = output - self.bias - self.kp * error
        self._previous_error = error
        self._derivative = 0.0

    def output(self, error: float) -> float:
        """未夾限的輸出（不推進狀態）。

參數：
            error: 誤差。

回傳：
            控制輸出。"""
        return self.bias + self.kp * error + self.integral + self.kp * self.td_s * self._derivative

    def update(self, error: float, dt_s: float, out_max: float | None = None) -> float:
        """推進一步並回傳夾限後的輸出。

參數：
            error: 誤差（正值表示需要更多輸出）。
            dt_s: 時間步長（秒，須大於 0）。
            out_max: 本步輸出上限（預設為建構時的 ``out_max``）。

回傳：
            夾在 ``[out_min, out_max]`` 之內的控制輸出。

引發：
            ValueError：dt 不為正時。"""
        if dt_s <= 0:
            raise ValueError("時間步長必須大於 0。")
        upper = self.out_max if out_max is None else min(self.out_max, out_max)
        if self.td_s > 0 and self._previous_error is not None:
            raw = (error - self._previous_error) / dt_s
            tau = self.td_s / max(self.filter_ratio, 1e-9)
            self._derivative += (raw - self._derivative) * dt_s / (tau + dt_s)
        self._previous_error = error
        unclamped = self.output(error)
        if self.ti_s > 0 and self.out_min < unclamped < upper:
            self.integral += self.kp / self.ti_s * error * dt_s
        value = self.output(error)
        return max(self.out_min, min(upper, value))


@dataclass
class FrequencyStepper:
    """把連續頻率要求換成固定階梯，帶遲滯與最短停留時間。

    - 往上一階：要求 ≥ 兩階中點 + 遲滯，且該階不高於上限階。
    - 往下一階：要求 ≤ 兩階中點 − 遲滯。
    - 每次變階後至少停留 ``dwell_s`` 才能再變階；高於上限階時**立即**降到上限階。
    """

    steps_hz: tuple[float, ...]
    hysteresis_hz: float = 2.0
    dwell_s: float = 60.0
    current_hz: float = 0.0
    last_change_s: float = -1e9

    def __post_init__(self) -> None:
        """階梯排序並驗證。

回傳：
            無。

引發：
            ValueError：階梯為空時。"""
        if not self.steps_hz:
            raise ValueError("頻率階梯不得為空。")
        self.steps_hz = tuple(sorted(self.steps_hz))
        if self.current_hz <= 0:
            self.current_hz = self.steps_hz[0]

    def nearest(self, frequency_hz: float) -> float:
        """最接近的階梯。

參數：
            frequency_hz: 頻率。

回傳：
            階梯頻率。"""
        return min(self.steps_hz, key=lambda step: abs(step - frequency_hz))

    def cap_step(self, limit_hz: float) -> float:
        """不高於上限的最高階梯（都超過時取最低階）。

參數：
            limit_hz: 頻率上限。

回傳：
            階梯頻率。"""
        allowed = [step for step in self.steps_hz if step <= limit_hz + 1e-9]
        return max(allowed) if allowed else self.steps_hz[0]

    def start(self, request_hz: float, limit_hz: float, now_s: float) -> float:
        """啟動：直接選最接近要求的階梯（不受停留時間限制）。

參數：
            request_hz: 要求頻率。
            limit_hz: 上限。
            now_s: 目前時間。

回傳：
            階梯頻率。"""
        self.current_hz = min(self.nearest(request_hz), self.cap_step(limit_hz))
        self.last_change_s = now_s
        return self.current_hz

    def update(self, request_hz: float, limit_hz: float, now_s: float) -> float:
        """依要求頻率與上限更新階梯。

參數：
            request_hz: 要求頻率。
            limit_hz: 上限。
            now_s: 目前時間。

回傳：
            階梯頻率。"""
        cap = self.cap_step(limit_hz)
        if self.current_hz > cap:
            self.current_hz = cap
            self.last_change_s = now_s
            return self.current_hz
        if now_s - self.last_change_s < self.dwell_s:
            return self.current_hz
        index = self.steps_hz.index(self.current_hz)
        if index + 1 < len(self.steps_hz) and self.steps_hz[index + 1] <= cap:
            midpoint = (self.steps_hz[index] + self.steps_hz[index + 1]) / 2
            if request_hz >= midpoint + self.hysteresis_hz:
                self.current_hz = self.steps_hz[index + 1]
                self.last_change_s = now_s
                return self.current_hz
        if index > 0:
            midpoint = (self.steps_hz[index - 1] + self.steps_hz[index]) / 2
            if request_hz <= midpoint - self.hysteresis_hz:
                self.current_hz = self.steps_hz[index - 1]
                self.last_change_s = now_s
        return self.current_hz
