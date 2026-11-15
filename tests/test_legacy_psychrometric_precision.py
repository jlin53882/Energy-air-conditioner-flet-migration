"""舊濕空氣模型的中間值不再四捨五入：回傳值等於公式的完整浮點結果。"""

from __future__ import annotations

import pytest

from Flet_ui.PsychrometricChart import PsychrometricChart_01_ASHF_model as model


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (lambda: model.cal_p(123.456), 101.325 * ((1 - 2.25577e-5 * 123.456) ** 5.2559)),
        (lambda: model.cal_Ws(101.325, 3.1699123), (0.621945 * 3.1699123) / (101.325 - 3.1699123)),
        (lambda: model.cal_W(0.0201234, 30.0, 24.3), ((2501 - 2.326 * 24.3) * 0.0201234 - 1.006 * (30.0 - 24.3))
         / ((2501 + 1.86 * 30.0) - 4.186 * 24.3)),
        (lambda: model.cal_Pw(101.325, 0.0123456), (101.325 * 0.0123456) / (0.621945 + 0.0123456)),
        (lambda: model.cal_v(26.7, 101.325, 1.98765), (8314.742 * (26.7 + 273.15) / (28.966 * (101.325 - 1.98765))) / 1000),
        (lambda: model.cal_h(26.7, 0.0123456), 1.006 * 26.7 + 0.0123456 * (2501 + 1.86 * 26.7)),
        (lambda: model.cal_Pws_Rh(47.3, 3.1699123), 47.3 / 100 * 3.1699123),
    ],
    ids=["p", "Ws", "W", "Pw", "v", "h", "Pw_from_RH"],
)
def test_intermediate_values_are_not_rounded(value, expected: float) -> None:
    """各函式回傳完整精度；顯示位數由畫面格式化決定。

回傳：
    無。"""
    # 相對容差 1e-15 只容許浮點運算順序差異；四捨五入到小數 9 位的誤差（約 1e-10）會被抓出來。
    result = value()
    assert result == pytest.approx(expected, rel=1e-15, abs=0.0)
    assert result != round(result, 9)
