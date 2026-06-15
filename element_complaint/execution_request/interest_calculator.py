"""强制执行申请书 - 独立利息计算器.

法穿原版依赖 Django finance 模块（InterestCalculator + LPR rate_service + 数据库）。
本独立小工具不能拉整条 finance 依赖链，故在此提供一个**纯 Python 等价实现**：
  - 利息公式与法穿一致（固定年利率 / LPR 倍数 / 日利率千分之·万分之）
  - LPR 一年期利率用内置历史表（公开数据，可自行更新）
  - 接口与法穿 InterestCalculator 对齐：calculate() / calculate_with_principal_changes()
    返回带 total_interest 属性的对象，供 execution_request_interest 原样调用。

LPR 历史为近似公开值，正式生产应以央行最新公布为准（见 LPR_1Y_HISTORY 注释）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .execution_request_utils import normalize_date_inclusion, normalize_year_days


@dataclass
class PrincipalPeriod:
    """本金变动区间（等价法穿 apps.finance.services.lpr.rate_service.PrincipalPeriod）。"""
    start_date: date
    end_date: date
    principal: Decimal


@dataclass
class InterestResult:
    total_interest: Decimal


# 一年期 LPR 历史利率（%，近似公开值；按生效日升序）。
# 数据来源：全国银行间同业拆借中心公布的 1Y LPR。如需精确，请按央行最新公告更新本表。
LPR_1Y_HISTORY: list[tuple[date, Decimal]] = [
    (date(2019, 8, 20), Decimal("4.25")),
    (date(2020, 4, 20), Decimal("3.85")),
    (date(2020, 5, 20), Decimal("3.85")),
    (date(2021, 12, 20), Decimal("3.80")),
    (date(2022, 1, 20), Decimal("3.70")),
    (date(2022, 5, 20), Decimal("3.70")),
    (date(2022, 8, 22), Decimal("3.65")),
    (date(2023, 6, 20), Decimal("3.55")),
    (date(2023, 8, 21), Decimal("3.45")),
    (date(2024, 7, 22), Decimal("3.35")),
    (date(2024, 10, 21), Decimal("3.10")),
    (date(2025, 5, 20), Decimal("3.00")),
]
# 兜底默认（找不到任何历史记录时）
_DEFAULT_LPR_1Y = Decimal("3.45")


def lpr_1y_for(target_date: date) -> Decimal:
    """取 ≤ target_date 的最近一次一年期 LPR（%）。"""
    rate = _DEFAULT_LPR_1Y
    for effective, r in LPR_1Y_HISTORY:
        if effective <= target_date:
            rate = r
        else:
            break
    return rate


def _days_between(start_date: date, end_date: date, date_inclusion: str) -> int:
    """计息天数。raw = (end-start).days（含首不含尾）。

    date_inclusion:
      both       → 含起止      = raw + 1
      start_only → 含起不含尾  = raw
      end_only   → 不含起含尾  = raw
      neither    → 不含起止    = raw - 1
    """
    raw = max((end_date - start_date).days, 0)
    mode = normalize_date_inclusion(date_inclusion)
    if mode == "both":
        return raw + 1
    if mode == "neither":
        return max(raw - 1, 0)
    return raw  # start_only / end_only


def _year_base(year_days: int, start_date: date) -> Decimal:
    """计息年天数：360/365 显式指定，0 表示用起算日所在年的实际天数。"""
    if year_days == 360:
        return Decimal("360")
    if year_days == 365:
        return Decimal("365")
    # 0：实际天数（闰年 366）
    return Decimal("366") if _is_leap(start_date.year) else Decimal("365")


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


class InterestCalculator:
    """纯 Python 利息计算器，接口对齐法穿 InterestCalculator。"""

    def calculate(
        self,
        *,
        start_date: date,
        end_date: date,
        principal: Decimal,
        rate_type: str = "1y",
        multiplier: Decimal | None = None,
        custom_rate_unit: str | None = None,
        custom_rate_value: Decimal | None = None,
        year_days: int = 360,
        date_inclusion: str = "both",
    ) -> InterestResult:
        if principal <= 0 or end_date < start_date:
            return InterestResult(Decimal("0"))

        days = _days_between(start_date, end_date, date_inclusion)
        if days <= 0:
            return InterestResult(Decimal("0"))

        yd = _year_base(year_days, start_date)

        # 日利率（千分之/万分之）：按天计，不走年化
        if custom_rate_unit == "permille" and custom_rate_value is not None:
            interest = principal * custom_rate_value / Decimal("1000") * Decimal(days)
        elif custom_rate_unit == "permyriad" and custom_rate_value is not None:
            interest = principal * custom_rate_value / Decimal("10000") * Decimal(days)
        else:
            # 年利率口径：固定年利率% 或 LPR 一年期 × 倍数
            if custom_rate_unit == "percent" and custom_rate_value is not None:
                annual_pct = custom_rate_value
            elif rate_type == "1y":
                lpr = lpr_1y_for(start_date)
                annual_pct = lpr * (multiplier if multiplier is not None and multiplier > 0 else Decimal("1"))
            else:
                return InterestResult(Decimal("0"))
            interest = principal * annual_pct / Decimal("100") * Decimal(days) / yd

        return InterestResult(interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def calculate_with_principal_changes(
        self,
        *,
        principal_periods: list[PrincipalPeriod],
        rate_type: str = "1y",
        year_days: int = 360,
        multiplier: Decimal | None = None,
        date_inclusion: str = "both",
        custom_rate_unit: str | None = None,
        custom_rate_value: Decimal | None = None,
    ) -> InterestResult:
        total = Decimal("0")
        for period in principal_periods:
            result = self.calculate(
                start_date=period.start_date,
                end_date=period.end_date,
                principal=period.principal,
                rate_type=rate_type,
                multiplier=multiplier,
                custom_rate_unit=custom_rate_unit,
                custom_rate_value=custom_rate_value,
                year_days=year_days,
                date_inclusion=date_inclusion,
            )
            total += result.total_interest
        return InterestResult(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
