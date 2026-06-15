"""强制执行申请书 - 文本输入适配器（重写自法穿 ExecutionRequestService）.

移植自法穿 FachuanHybridSystem
backend/apps/documents/services/placeholders/litigation/execution_request_service.py

适配点：法穿 Service 依赖 Django（Case/CaseNumber model、InterestCalculator、占位符注册）。
本独立工具不能引入 Django，故把核心的 _build_execution_request 抽成一个**纯函数**：
  - 输入：强制执行申请书全文（或执行依据判决/裁定/调解书主文）
  - 输出：ExecutionComputation(preview_text, warnings, structured_params)

解析、利息计算、文本生成等子逻辑全部沿用 execution_request_* 原模块（已同包移植）。
case.target_amount / case_number.* 等字段改为显式参数，默认值与法穿一致。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any

from . import execution_request_clause_extractor as clause_extractor
from . import execution_request_interest as interest_mod
from . import execution_request_llm_fallback as llm_mod
from . import execution_request_parser as parser_mod
from . import execution_request_text_generator as text_gen
from .execution_request_models import ExecutionComputation, InterestSegment
from .execution_request_utils import (
    format_amount,
    normalize_date_inclusion,
    normalize_text,
    normalize_year_days,
    safe_decimal,
)
from .interest_calculator import InterestCalculator

logger = logging.getLogger(__name__)

# 执行依据文号正则：如 "(2023)京01民初123号" / "（2022）粤03民终456号"
_CASE_NUMBER_PATTERN = re.compile(
    r"[（(]\s*\d{4}\s*[）)]\s*[^\s，。；、]{0,20}?第?\s*\d+\s*号"
)
_DOCUMENT_NAME_PATTERN = re.compile(r"《([^《》]{2,40})》")


def extract_case_number(text: str) -> str:
    """从文书文本抽取执行依据文号。"""
    m = _CASE_NUMBER_PATTERN.search(text or "")
    return m.group(0).strip() if m else ""


def extract_document_name(text: str) -> str:
    """从文书文本抽取文书名称（书名号内）。"""
    m = _DOCUMENT_NAME_PATTERN.search(text or "")
    return f"《{m.group(1)}》" if m else ""


# ─────────────────────────────────────────────
# 场景适配后处理（法穿 parser 原为"判决主文"设计，本工具输入为"申请书全文"）
# ─────────────────────────────────────────────
_BURDEN_SUBJECTS = ("由被申请人", "由被告", "由被执行人", "由各被申请人", "由两被申请人", "由各被告", "由两被告")

_FEE_PATTERNS = {
    "litigation_fee": (r"受理费(?:减半收取)?", "受理费"),
    "preservation_fee": (r"(?:财产保全申请费|保全申请费|财产保全费|保全费)", "财产保全费"),
    "announcement_fee": (r"公告费", "公告费"),
    "attorney_fee": (r"(?:律师代理费|律师费)", "律师代理费"),
    "guarantee_fee": (r"(?:财产保全)?担保费", "财产保全担保费"),
}


def _dedupe_principal(amounts, normalized_text: str) -> None:
    """本金去重：parser 会累加所有"本金X元"匹配；申请书中本金常在"请求事项"和
    "事实理由"重复出现，导致 principal 翻倍。这里取【出现次数最多的单笔金额】。"""
    from collections import Counter

    from .execution_request_utils import AMOUNT_WITH_UNIT_PATTERN, parse_amount_value

    if (amounts.principal or Decimal("0")) <= 0:
        return
    pat = re.compile(rf"(?:借款|货款)(?:本金)?\s*{AMOUNT_WITH_UNIT_PATTERN}")
    values = []
    for m in pat.finditer(normalized_text):
        suffix = normalized_text[m.end(): m.end() + 8]
        if "为基数" in suffix or "为本金" in suffix:
            continue
        val = parse_amount_value(m.group(1), m.group(2))
        if val and val > 0:
            values.append(val)
    if not values:
        return
    # 众数；同票数取较小值（保守，避免翻倍）
    counter = Counter(values)
    top_count = counter.most_common(1)[0][1]
    candidates = [v for v, c in counter.items() if c == top_count]
    amounts.principal = min(candidates)


def _recover_burden_fees(amounts, normalized_text: str) -> None:
    """费用纳入补救：法穿 should_include_fee 只认"由被告负担+预交"，申请书常写
    "由被申请人负担"（无"预交"措辞），导致受理费等被误排除。这里扫描明确的
    "由被申请人/被告负担"的费用句，把被排除的费用重新纳入。"""
    from .execution_request_models import FeeItem
    from .execution_request_utils import AMOUNT_WITH_UNIT_PATTERN, parse_amount_value

    for sentence in re.split(r"[。；\n]", normalized_text):
        compact = sentence.replace(" ", "")
        if "负担" not in compact:
            continue
        if not any(marker in compact for marker in _BURDEN_SUBJECTS):
            continue
        for key, (kw, label) in _FEE_PATTERNS.items():
            if (getattr(amounts, key, Decimal("0")) or Decimal("0")) > 0:
                continue
            m = re.search(rf"{kw}(?:减半收取)?(?:\s*(?:为|计|是))?\s*{AMOUNT_WITH_UNIT_PATTERN}", sentence)
            if not m:
                continue
            val = parse_amount_value(m.group(1), m.group(2))
            if val and val > 0:
                setattr(amounts, key, val)
                amounts.excluded_fees = [f for f in amounts.excluded_fees if f.key != key]


def _format_case_number(number: str, document_name: str) -> str:
    number = (number or "").strip()
    document_name = (document_name or "").strip()
    return f"{number}{document_name}"


def build_execution_request(
    main_text: str,
    *,
    target_amount: Decimal | str | float | None = None,
    paid_amount: Decimal | str | float | None = None,
    cutoff_date: date | None = None,
    year_days: int | None = None,
    date_inclusion: str | None = None,
    use_deduction_order: bool | None = None,
    enable_llm_fallback: bool | None = None,
) -> ExecutionComputation:
    """普通强制执行申请书/执行依据主文 → 要素式申请执行事项。

    参数对应法穿 case/case_number 的相关字段：
      target_amount        涉案金额（本金兜底，原 case.target_amount）
      paid_amount          被执行人已付款（原 case_number.execution_paid_amount）
      cutoff_date          利息截止日（原 case_number.execution_cutoff_date）
      year_days            计息年天数 360/365/0（原 execution_year_days）
      date_inclusion       起止日计入方式（原 execution_date_inclusion）
      use_deduction_order  是否按文书抵扣顺序抵已付款（原 execution_use_deduction_order）
      enable_llm_fallback  是否启用 Ollama 兜底
    """
    warnings: list[str] = []
    main_text = (main_text or "").strip()
    if not main_text:
        return ExecutionComputation("", ["执行依据主文为空，无法解析申请执行事项。"], {})

    normalized_text = normalize_text(main_text)
    target = safe_decimal(target_amount)
    calculator = InterestCalculator()

    amounts = parser_mod.parse_confirmed_amounts(normalized_text)
    # 场景适配：申请书中本金重复出现会翻倍；"由被申请人负担"的费用会被误排除
    _dedupe_principal(amounts, normalized_text)
    _recover_burden_fees(amounts, normalized_text)
    params = interest_mod.parse_interest_params(normalized_text)
    principal_fallback_to_target = False
    if amounts.principal is None:
        inferred_principal = interest_mod.infer_principal_from_interest_base(params)
        if inferred_principal is not None:
            amounts.principal = inferred_principal
            if "货款" in normalized_text:
                amounts.principal_label = "货款本金"
            elif "借款" not in normalized_text:
                amounts.principal_label = "款项本金"
        else:
            if target > 0:
                amounts.principal = target
                if "货款" in normalized_text:
                    amounts.principal_label = "货款本金"
                warnings.append("未从文书解析到本金，已回退使用传入的涉案金额。")
                principal_fallback_to_target = True
            else:
                has_fee_only_items = any(
                    value > 0
                    for value in (
                        amounts.litigation_fee,
                        amounts.preservation_fee,
                        amounts.announcement_fee,
                        amounts.attorney_fee,
                        amounts.guarantee_fee,
                    )
                )
                if not has_fee_only_items and amounts.confirmed_interest <= 0:
                    warnings.append("未能确定本金，申请执行事项未生成。")
                    return ExecutionComputation("", warnings, {})

    paid = max(safe_decimal(paid_amount), Decimal("0"))
    use_order = bool(use_deduction_order) if use_deduction_order is not None else False
    calc_year_days = normalize_year_days(year_days)
    calc_date_inclusion = normalize_date_inclusion(date_inclusion)
    calc_cutoff = cutoff_date or date.today()

    deduction_order = interest_mod.parse_deduction_order(normalized_text)
    amounts, principal_paid, deduction_applied = interest_mod.apply_paid_amount(
        amounts=amounts,
        paid_amount=paid,
        deduction_order=deduction_order if use_order else [],
    )

    has_double_interest_clause = clause_extractor.has_double_interest_clause(normalized_text)
    interest_segments = clause_extractor.parse_interest_segments(normalized_text)
    has_segmented_interest = len(interest_segments) >= 2
    if has_segmented_interest and params.start_date is None:
        params.start_date = min(segment.start_date for segment in interest_segments)
    overdue_interest_rules = clause_extractor.parse_overdue_interest_rules(normalized_text)
    has_multiple_overdue_interest_rules = len(overdue_interest_rules) >= 2
    joint_liability_text = clause_extractor.extract_joint_liability_text(normalized_text)
    supplementary_liability_text = clause_extractor.extract_supplementary_liability_text(normalized_text)
    priority_execution_texts = clause_extractor.extract_priority_execution_texts(normalized_text)
    manual_review_clauses = clause_extractor.extract_manual_review_clauses(
        normalized_text,
        recognized_texts=[
            joint_liability_text,
            supplementary_liability_text,
            *priority_execution_texts,
        ],
    )
    llm_fallback_enabled = True if enable_llm_fallback is None else bool(enable_llm_fallback)
    llm_fallback_used = False
    if llm_fallback_enabled and llm_mod.should_try_llm_fallback(
        text=normalized_text,
        amounts=amounts,
        params=params,
        principal_fallback_to_target=principal_fallback_to_target,
    ):
        llm_data = llm_mod.extract_with_ollama_fallback(normalized_text)
        if llm_data:
            llm_fallback_used = llm_mod.merge_llm_fallback(
                amounts=amounts,
                params=params,
                llm_data=llm_data,
                principal_fallback_to_target=principal_fallback_to_target,
            )
            if llm_data.get("has_double_interest_clause") is True:
                has_double_interest_clause = True
            if llm_fallback_used:
                warnings.append("规则置信度不足，已使用本地Ollama兜底解析。")

    interest_base = interest_mod.resolve_interest_base(
        target_amount=target, amounts=amounts, params=params, principal_paid=principal_paid
    )
    custom_interest_summary = ""
    original_segmented_interest_expression = ""
    overdue_interest_rule_details: list[dict[str, Any]] = []
    if has_multiple_overdue_interest_rules:
        overdue_interest = Decimal("0")
        primary_base = interest_base
        primary_params = params
        primary_segments: list[InterestSegment] = []

        for index, rule in enumerate(overdue_interest_rules):
            rule_params = rule.params
            rule_segments = sorted(rule.segments, key=lambda s: (s.start_date, s.end_date or date.max))
            if rule_segments and rule_params.start_date is None:
                rule_params.start_date = min(segment.start_date for segment in rule_segments)

            if rule_segments:
                rule_base = rule_segments[0].base_amount
                rule_interest = interest_mod.calculate_interest_with_segments(
                    calculator=calculator,
                    segments=rule_segments,
                    params=rule_params,
                    cutoff_date=calc_cutoff,
                    year_days=calc_year_days,
                    date_inclusion=calc_date_inclusion,
                    warnings=warnings,
                )
            else:
                rule_base = interest_mod.resolve_interest_base(
                    target_amount=target,
                    amounts=amounts,
                    params=rule_params,
                    principal_paid=principal_paid,
                )
                rule_interest = interest_mod.calculate_interest(
                    calculator=calculator,
                    principal=rule_base,
                    params=rule_params,
                    cutoff_date=calc_cutoff,
                    year_days=calc_year_days,
                    date_inclusion=calc_date_inclusion,
                    warnings=warnings,
                )

            overdue_interest += rule_interest
            overdue_interest_rule_details.append(
                {
                    "index": index + 1,
                    "source_text": rule.source_text,
                    "interest_start_date": rule_params.start_date.isoformat() if rule_params.start_date else "",
                    "interest_rate_description": rule_params.rate_description,
                    "interest_base": format_amount(rule_base),
                    "interest_segmented": len(rule_segments) >= 2,
                    "interest_segments": [
                        {
                            "base_amount": format_amount(segment.base_amount),
                            "start_date": segment.start_date.isoformat(),
                            "end_date": segment.end_date.isoformat() if segment.end_date else "",
                        }
                        for segment in rule_segments
                    ],
                    "overdue_interest": format_amount(rule_interest),
                }
            )
            if index == 0:
                primary_base = rule_base
                primary_params = rule_params
                primary_segments = rule_segments

        params = primary_params
        interest_base = primary_base
        interest_segments = primary_segments
        has_segmented_interest = any(item["interest_segmented"] for item in overdue_interest_rule_details)
        cutoff_text = f"{calc_cutoff.year}年{calc_cutoff.month}月{calc_cutoff.day}日"
        overdue_label = params.overdue_item_label or "利息"
        if overdue_label == "利息":
            overdue_label = "逾期利息"
        custom_interest_summary = f"{overdue_label}按判决确定的分项规则计算，截至{cutoff_text}{overdue_label}为{format_amount(overdue_interest)}元"
    elif has_segmented_interest:
        interest_base = interest_segments[0].base_amount
        original_segmented_interest_expression = clause_extractor.extract_original_segmented_interest_expression(
            main_text=main_text,
            overdue_label=params.overdue_item_label,
        )
        overdue_interest = interest_mod.calculate_interest_with_segments(
            calculator=calculator,
            segments=interest_segments,
            params=params,
            cutoff_date=calc_cutoff,
            year_days=calc_year_days,
            date_inclusion=calc_date_inclusion,
            warnings=warnings,
        )
    else:
        overdue_interest = interest_mod.calculate_interest(
            calculator=calculator,
            principal=interest_base,
            params=params,
            cutoff_date=calc_cutoff,
            year_days=calc_year_days,
            date_inclusion=calc_date_inclusion,
            warnings=warnings,
        )
    if (
        overdue_interest <= 0
        and params.start_date is not None
        and (params.multiplier is not None or params.custom_rate_value is not None)
        and calc_cutoff >= params.start_date
        and not llm_fallback_used
        and llm_fallback_enabled
        and not has_multiple_overdue_interest_rules
    ):
        llm_data = llm_mod.extract_with_ollama_fallback(normalized_text)
        if llm_data:
            llm_fallback_used = llm_mod.merge_llm_fallback(
                amounts=amounts,
                params=params,
                llm_data=llm_data,
                principal_fallback_to_target=principal_fallback_to_target,
            )
            if llm_data.get("has_double_interest_clause") is True:
                has_double_interest_clause = True
            interest_base = interest_mod.resolve_interest_base(
                target_amount=target, amounts=amounts, params=params, principal_paid=principal_paid
            )
            if has_segmented_interest:
                interest_base = interest_segments[0].base_amount
                overdue_interest = interest_mod.calculate_interest_with_segments(
                    calculator=calculator,
                    segments=interest_segments,
                    params=params,
                    cutoff_date=calc_cutoff,
                    year_days=calc_year_days,
                    date_inclusion=calc_date_inclusion,
                    warnings=warnings,
                )
            else:
                overdue_interest = interest_mod.calculate_interest(
                    calculator=calculator,
                    principal=interest_base,
                    params=params,
                    cutoff_date=calc_cutoff,
                    year_days=calc_year_days,
                    date_inclusion=calc_date_inclusion,
                    warnings=warnings,
                )
            if llm_fallback_used:
                warnings.append("规则利息解析失败，已使用本地Ollama兜底修正。")

    for fee in amounts.excluded_fees:
        # 该类费用已有纳入项时（如同一受理费在另一处被判 include），被排除的同名条目
        # 不再报"已排除"警告，避免误导（金额已在合计中）。
        if (getattr(amounts, fee.key, Decimal("0")) or Decimal("0")) > 0:
            continue
        warnings.append(f"{fee.label}{format_amount(fee.amount)}元已排除：{fee.reason}")

    total = (
        (amounts.principal or Decimal("0"))
        + amounts.confirmed_interest
        + overdue_interest
        + amounts.litigation_fee
        + amounts.preservation_fee
        + amounts.announcement_fee
        + amounts.attorney_fee
        + amounts.guarantee_fee
    )

    case_number = extract_case_number(normalized_text)
    document_name = extract_document_name(normalized_text)
    full_case_number = _format_case_number(case_number, document_name)

    preview_text = text_gen.generate_request_text(
        full_case_number=full_case_number,
        amounts=amounts,
        params=params,
        overdue_interest=overdue_interest,
        interest_base=interest_base,
        cutoff_date=calc_cutoff,
        total=total,
        has_double_interest_clause=has_double_interest_clause,
        interest_segments=interest_segments if has_segmented_interest else [],
        custom_interest_summary=custom_interest_summary,
        joint_liability_text=joint_liability_text,
        supplementary_liability_text=supplementary_liability_text,
        priority_execution_texts=priority_execution_texts,
        manual_review_clauses=manual_review_clauses,
        original_segmented_interest_expression=original_segmented_interest_expression,
    )

    structured = {
        "case_number": case_number,
        "document_name": document_name,
        "principal_label": amounts.principal_label,
        "principal": format_amount(amounts.principal),
        "confirmed_interest": format_amount(amounts.confirmed_interest),
        "litigation_fee": format_amount(amounts.litigation_fee),
        "preservation_fee": format_amount(amounts.preservation_fee),
        "announcement_fee": format_amount(amounts.announcement_fee),
        "attorney_fee": format_amount(amounts.attorney_fee),
        "guarantee_fee": format_amount(amounts.guarantee_fee),
        "paid_amount": format_amount(paid),
        "deduction_order": [interest_mod.DEDUCTION_KEY_TO_LABEL.get(k, k) for k in deduction_order],
        "deduction_applied": [
            {
                "component": interest_mod.DEDUCTION_KEY_TO_LABEL.get(str(item["key"]), str(item["key"])),
                "amount": format_amount(item["amount"] if isinstance(item["amount"], Decimal) else None),
            }
            for item in deduction_applied
        ],
        "interest_start_date": params.start_date.isoformat() if params.start_date else "",
        "interest_rate_description": params.rate_description,
        "overdue_interest_label": params.overdue_item_label,
        "interest_base": format_amount(interest_base),
        "interest_segmented": has_segmented_interest,
        "interest_segments": [
            {
                "base_amount": format_amount(segment.base_amount),
                "start_date": segment.start_date.isoformat(),
                "end_date": segment.end_date.isoformat() if segment.end_date else "",
            }
            for segment in interest_segments
        ],
        "interest_cap": format_amount(params.interest_cap),
        "cutoff_date": calc_cutoff.isoformat(),
        "year_days": calc_year_days,
        "date_inclusion": calc_date_inclusion,
        "has_multiple_overdue_interest_rules": has_multiple_overdue_interest_rules,
        "overdue_interest_rules": overdue_interest_rule_details,
        "overdue_interest": format_amount(overdue_interest),
        "total": format_amount(total),
        "has_double_interest_clause": has_double_interest_clause,
        "has_joint_liability_clause": bool(joint_liability_text),
        "joint_liability_text": joint_liability_text,
        "has_supplementary_liability_clause": bool(supplementary_liability_text),
        "supplementary_liability_text": supplementary_liability_text,
        "has_priority_execution_clauses": bool(priority_execution_texts),
        "priority_execution_clauses": priority_execution_texts,
        "has_manual_review_clauses": bool(manual_review_clauses),
        "manual_review_clauses": manual_review_clauses,
        "llm_fallback_enabled": llm_fallback_enabled,
        "llm_fallback_used": llm_fallback_used,
        "excluded_fees": [
            {"label": fee.label, "amount": format_amount(fee.amount), "reason": fee.reason}
            for fee in amounts.excluded_fees
        ],
    }

    return ExecutionComputation(preview_text=preview_text, warnings=warnings, structured_params=structured)
