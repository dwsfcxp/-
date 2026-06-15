# -*- coding: utf-8 -*-
"""强制执行申请书 - 要素式转换引擎（移植自法穿 FachuanHybridSystem）.

沿用法穿 execution_request_* 全部解析/计算/生成逻辑，仅把 Django 案件模型与
finance 利息服务替换为本包的纯 Python 实现（见 adapter.py / interest_calculator.py）。

对外入口：
  build_execution_request(main_text, ...) → ExecutionComputation
"""

from .adapter import (
    build_execution_request,
    extract_case_number,
    extract_document_name,
)
from .execution_request_models import ExecutionComputation

__all__ = [
    "build_execution_request",
    "extract_case_number",
    "extract_document_name",
    "ExecutionComputation",
]
