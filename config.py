# -*- coding: utf-8 -*-
"""
要素式起诉状转换器 - 全局配置

LLM 配置优先级：环境变量 > 本文件常量 > 不启用（纯规则模式）
"""

import os

# ─────────────────────────────────────────────
# LLM 配置（智谱 GLM / OpenAI 兼容协议）
# ─────────────────────────────────────────────
# 申请地址：https://open.bigmodel.cn/
# 也可通过环境变量 ZHIPU_API_KEY / GLM_BASE_URL 覆盖

LLM_API_KEY = os.getenv("ZHIPU_API_KEY", "")           # 智谱 API Key
LLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
LLM_MODEL = os.getenv("GLM_MODEL", "glm-4-flash")      # 廉价快速；要更强可改 glm-4-plus / glm-4

# 是否在未配置 Key 时静默回退到纯规则模式
LLM_FALLBACK_TO_RULES = True


# ─────────────────────────────────────────────
# 案由识别关键词映射（顺序敏感：越具体越靠前）
# ─────────────────────────────────────────────
CAUSE_KEYWORDS = [
    ("民间借贷纠纷",   ["民间借贷", "借款", "借条", "欠条", "偿还借款", "借给"]),
    ("金融借款合同纠纷", ["金融借款", "银行贷款", "按揭贷款", "借款合同.*银行", "信贷"]),
    ("信用卡纠纷",     ["信用卡", "透支", "信用卡透支"]),
    ("买卖合同纠纷",   ["买卖合同", "货款", "交货", "发货", "购销合同", "供货"]),
    ("物业服务合同纠纷", ["物业服务", "物业费", "物业管理", "小区物业"]),
    ("劳动争议",       ["劳动合同", "工资", "劳动报酬", "解除劳动合同", "工伤", "社保", "用人单位", "加班费"]),
    ("离婚纠纷",       ["离婚", "夫妻感情破裂", "抚养权", "婚内", "共同财产.*分割"]),
]

# 兜底案由
DEFAULT_CAUSE = "民间借贷纠纷"   # 当识别失败时使用（最常见案由之一）


# ─────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")


# ─────────────────────────────────────────────
# 文档输出
# ─────────────────────────────────────────────
# 法院提交的民事起诉状一般用宋体小四（12pt）、A4
DOCX_FONT = "宋体"
DOCX_FONT_SIZE = 12          # pt，小四
DOCX_TITLE_FONT = "黑体"
DOCX_TITLE_SIZE = 16         # pt，三号偏大
DOCX_HEADING_FONT = "黑体"
DOCX_HEADING_SIZE = 14       # pt，四号


def llm_enabled() -> bool:
    """LLM 是否可用（配了 Key 才算可用）"""
    return bool(LLM_API_KEY and LLM_API_KEY.strip())
