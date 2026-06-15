# -*- coding: utf-8 -*-
"""要素式起诉状转换器 - 核心包"""

from .schemas import (
    Field, ElementGroup, CauseSchema,
    COMMON_PARTY_GROUP_PLAINTIFF, COMMON_PARTY_GROUP_DEFENDANT,
    COMMON_CLAIM_GROUP, COMMON_EVIDENCE_GROUP,
    SCHEMAS, get_schema, all_causes, full_groups,
)
from .extractor import RuleExtractor, detect_cause, normalize, parse_amount_value
from .llm_extractor import extract_with_llm, merge_into
from .pipeline import convert, convert_via_court, convert_application
from .renderer import render_markdown, render_text, render_docx
from .renderer import render_execution_markdown, render_execution_text, render_execution_docx

__all__ = [
    "Field", "ElementGroup", "CauseSchema",
    "COMMON_PARTY_GROUP_PLAINTIFF", "COMMON_PARTY_GROUP_DEFENDANT",
    "COMMON_CLAIM_GROUP", "COMMON_EVIDENCE_GROUP",
    "SCHEMAS", "get_schema", "all_causes", "full_groups",
    "RuleExtractor", "detect_cause", "normalize", "parse_amount_value",
    "extract_with_llm", "merge_into",
    "convert", "convert_via_court", "convert_application",
    "render_markdown", "render_text", "render_docx",
    "render_execution_markdown", "render_execution_text", "render_execution_docx",
]

__version__ = "1.0.0"
