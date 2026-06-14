# -*- coding: utf-8 -*-
"""
要素式起诉状 - Schema 定义

核心思想：要素式起诉状的"要素"对每个民事案由是相对固定的。
本文件用数据结构定义：
  - 公共要素组（所有案由都有）：当事人、诉讼请求、证据清单
  - 案由专属事实要素组：借款事实、合同履行、劳动关系等

抽取器（extractor / llm_extractor）的目标，就是从普通叙述式起诉状文本中，
把这些字段的值填出来；渲染器（renderer）再按表格化模板输出。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────
@dataclass
class Field:
    """单个要素字段"""
    key: str            # 字段标识（英文/拼音，用于程序内部）
    label: str          # 中文显示名（出现在要素式诉状表格里）
    hint: str = ""      # 抽取提示，给 LLM 看的抽取指引
    required: bool = False   # 是否必填要素
    unit: str = ""      # 单位：元 / % / 月 / 元/月


@dataclass
class ElementGroup:
    """要素组：若干相关字段的集合，对应要素式诉状中的一个表格区块"""
    name: str                       # 组名（如"原告信息"、"借款事实"）
    fields: List[Field] = field(default_factory=list)
    repeatable: bool = False        # 是否可重复（如多条诉讼请求、多个证据、多个被告）


@dataclass
class CauseSchema:
    """一个案由的完整要素 Schema"""
    cause: str                                  # 案由名
    fact_groups: List[ElementGroup] = field(default_factory=list)  # 事实要素组（案由专属）


# ─────────────────────────────────────────────
# 公共要素组（所有案由共用）
# ─────────────────────────────────────────────

def _party_group(role: str) -> ElementGroup:
    """当事人要素组。支持自然人/法人（身份证号字段对法人即统一社会信用代码）。
    field key 不带 role 前缀（与 extractor 输出的 plaintiff/defendant dict key 对齐）。"""
    return ElementGroup(
        name=f"{role}信息",
        fields=[
            Field("name",   f"{role}姓名/名称",   hint=f"{role}是自然人填姓名，是单位填名称", required=True),
            Field("gender", f"{role}性别",         hint="自然人填男/女，法人留空"),
            Field("birth",  f"{role}出生日期",     hint="格式：YYYY年MM月DD日，法人留空"),
            Field("nation", f"{role}民族",         hint="如：汉族，法人留空"),
            Field("id",     f"{role}身份证号/统一社会信用代码", hint="18位身份证号或18位统一社会信用代码"),
            Field("addr",   f"{role}住所",         hint="户籍地或经常居住地；法人填注册地址", required=True),
            Field("phone",  f"{role}联系电话",     hint="手机号或固话"),
        ],
    )


COMMON_PARTY_GROUP_PLAINTIFF = _party_group("原告")
COMMON_PARTY_GROUP_DEFENDANT = _party_group("被告")

COMMON_CLAIM_GROUP = ElementGroup(
    name="诉讼请求",
    repeatable=True,
    fields=[
        Field("claim_item", "请求事项", hint="一项请求一个要素行，如：判令被告偿还借款本金XXX元", required=True),
    ],
)

COMMON_COST_CLAIM = ElementGroup(
    name="诉讼费用",
    fields=[
        Field("cost_burden", "诉讼费用承担", hint="如：本案诉讼费由被告承担", required=True),
    ],
)

COMMON_EVIDENCE_GROUP = ElementGroup(
    name="证据清单",
    repeatable=True,
    fields=[
        Field("evidence_name",     "证据名称",   hint="如：借条原件、银行转账凭证、微信聊天记录"),
        Field("evidence_form",     "证据形式",   hint="书证/物证/电子数据/视听资料/证人证言"),
        Field("evidence_purpose",  "证明对象",   hint="该证据证明什么事实"),
        Field("evidence_source",   "证据来源",   hint="原件/复制件/来源说明"),
    ],
)


# ─────────────────────────────────────────────
# 案由专属事实要素组
# ─────────────────────────────────────────────

# 1. 民间借贷纠纷
GROUPS_PRIVATE_LENDING = [
    ElementGroup("借款事实", [
        Field("loan_date",     "借款时间",        hint="YYYY年MM月DD日", required=True),
        Field("principal",     "借款本金",        unit="元", hint="借出本金金额", required=True),
        Field("delivery",      "交付方式",        hint="现金/银行转账/微信支付宝转账"),
        Field("receipt_account", "收款账户/收款人", hint="被告收款账号或收款人"),
    ]),
    ElementGroup("利息与期限", [
        Field("interest_agreed", "是否约定利息",   hint="是/否"),
        Field("interest_rate",   "利率/利息约定",  unit="%或元", hint="如：年利率12%、月息2分"),
        Field("repay_due",       "约定还款期限",   hint="到期日或借期"),
        Field("is_due",          "是否已到期",     hint="是/否"),
    ]),
    ElementGroup("担保与书证", [
        Field("guarantee",  "是否有担保/抵押", hint="有/无；担保人姓名或抵押物"),
        Field("iou",        "是否有借条/借款合同", hint="有/无"),
    ]),
    ElementGroup("履行情况", [
        Field("paid_principal", "被告已还本金", unit="元"),
        Field("paid_interest",  "被告已付利息", unit="元"),
        Field("urged",          "是否催讨及时间", hint="催讨方式与时间"),
    ]),
    ElementGroup("尚欠金额（诉请依据）", [
        Field("owed_principal", "尚欠本金", unit="元", required=True),
        Field("owed_interest",  "尚欠利息", unit="元", hint="利息计算依据，如：以本金X元为基数，按年利率Y%，自Z日起算"),
        Field("total_claim",    "合计诉请", unit="元", required=True),
    ]),
]

# 2. 买卖合同纠纷
GROUPS_SALE_CONTRACT = [
    ElementGroup("合同基本情况", [
        Field("contract_date", "合同签订时间", required=True),
        Field("subject",       "合同标的",   hint="货物名称、规格型号", required=True),
        Field("total_price",   "合同总价款", unit="元", required=True),
        Field("contract_form", "合同形式",   hint="书面合同/口头约定/订单"),
    ]),
    ElementGroup("履行约定", [
        Field("delivery_due",  "约定交货时间"),
        Field("delivery_actual", "实际交货情况", hint="是否已交货、交货时间"),
        Field("payment_due",   "约定付款时间/方式"),
    ]),
    ElementGroup("违约与欠款", [
        Field("paid_amount",   "被告已付货款", unit="元"),
        Field("owed_amount",   "尚欠货款",     unit="元", required=True),
        Field("penalty_agreed", "违约金约定",   hint="违约金条款，如：按日万分之五"),
        Field("urged",         "是否催告及时间"),
    ]),
    ElementGroup("诉请金额", [
        Field("penalty_amount", "违约金/损失", unit="元"),
        Field("total_claim",    "合计诉请",     unit="元", required=True),
    ]),
]

# 3. 物业服务合同纠纷
GROUPS_PROPERTY_SERVICE = [
    ElementGroup("物业服务关系", [
        Field("contract_date",  "物业服务合同/期限"),
        Field("is_owner",       "被告是否业主", required=True),
        Field("written_contract", "是否签订书面物业合同", hint="是/否"),
    ]),
    ElementGroup("物业坐落", [
        Field("property_addr",  "物业坐落", hint="小区/楼栋/房号", required=True),
        Field("area",           "建筑面积", unit="㎡"),
    ]),
    ElementGroup("物业费", [
        Field("fee_standard",   "物业费标准", unit="元/㎡·月或元/月"),
        Field("bill_start",     "计费起始时间"),
        Field("arrears_start",  "欠费起始时间", required=True),
        Field("arrears_end",    "欠费截止时间", required=True),
        Field("arrears_months", "欠费月数",   unit="月"),
        Field("arrears_amount", "累计欠费",   unit="元", required=True),
        Field("late_fee",       "滞纳金/违约金", unit="元"),
    ]),
    ElementGroup("诉请金额", [
        Field("total_claim",    "合计诉请", unit="元", required=True),
    ]),
]

# 4. 金融借款合同纠纷
GROUPS_FINANCIAL_LOAN = [
    ElementGroup("借款合同", [
        Field("contract_date", "借款合同签订时间", required=True),
        Field("bank",          "贷款银行", required=True),
        Field("principal",     "借款本金",   unit="元", required=True),
        Field("loan_term",     "借款期限"),
        Field("interest_rate", "借款利率"),
    ]),
    ElementGroup("放款与担保", [
        Field("lend_date",     "放款时间/放款金额"),
        Field("repay_method",  "还款方式", hint="等额本息/等额本金/到期还本"),
        Field("guarantee",     "抵押/质押/保证", hint="担保方式与担保物"),
    ]),
    ElementGroup("违约与欠款", [
        Field("paid_principal", "被告已还本金", unit="元"),
        Field("paid_interest",  "被告已付利息", unit="元"),
        Field("overdue_start",  "逾期起始时间"),
        Field("acceleration",   "宣布提前到期时间", hint="如已发函宣布贷款提前到期"),
        Field("owed_principal", "尚欠本金", unit="元", required=True),
        Field("owed_interest",  "尚欠利息/罚息", unit="元", hint="利息、罚息、复利的计算依据"),
        Field("total_claim",    "合计诉请", unit="元", required=True),
    ]),
]

# 5. 信用卡纠纷
GROUPS_CREDIT_CARD = [
    ElementGroup("信用卡基本情况", [
        Field("card_tail",   "信用卡卡号（尾号）", required=True),
        Field("bank",        "发卡银行", required=True),
        Field("credit_limit", "信用额度", unit="元"),
    ]),
    ElementGroup("透支与催收", [
        Field("overdue_start", "透支起始时间"),
        Field("overdue_principal", "透支本金", unit="元", required=True),
        Field("overdue_interest",  "透支利息/费用", unit="元", hint="利息、违约金、费用的计算依据"),
        Field("collection",   "催收情况", hint="电话/信函/上门催收记录"),
    ]),
    ElementGroup("履行与诉请", [
        Field("paid_amount",  "被告已还款", unit="元"),
        Field("owed_principal", "尚欠本金", unit="元", required=True),
        Field("owed_interest",  "尚欠利息/费用", unit="元"),
        Field("total_claim",    "合计诉请", unit="元", required=True),
    ]),
]

# 6. 劳动争议
GROUPS_LABOR = [
    ElementGroup("劳动关系", [
        Field("hire_date",    "入职时间", required=True),
        Field("leave_date",   "离职时间"),
        Field("position",     "工作岗位"),
        Field("salary",       "月工资标准", unit="元/月", required=True),
        Field("salary_form",  "工资发放形式", hint="银行转账/现金"),
    ]),
    ElementGroup("劳动合同与社保", [
        Field("contract_signed", "是否签订劳动合同", hint="是/否；未签可主张二倍工资"),
        Field("contract_term",   "合同期限"),
        Field("social_insurance", "是否缴纳社保", hint="是/否"),
    ]),
    ElementGroup("争议事项", [
        Field("arrears_period",  "欠发工资期间", hint="起止时间"),
        Field("arrears_amount",  "欠发工资金额", unit="元"),
        Field("overtime_pay",    "加班费", unit="元"),
        Field("economic_comp",   "经济补偿金/赔偿金", unit="元", hint="解除/终止劳动关系的补偿"),
        Field("termination_reason", "解除/终止原因"),
        Field("work_injury",     "工伤情况（如有）"),
    ]),
    ElementGroup("诉请金额", [
        Field("total_claim", "合计诉请", unit="元", required=True),
    ]),
]

# 7. 离婚纠纷
GROUPS_DIVORCE = [
    ElementGroup("婚姻情况", [
        Field("marry_date",     "登记结婚时间", required=True),
        Field("marriage_cert",  "结婚证编号"),
        Field("breakdown_reason", "感情破裂原因/事实", required=True, hint="如：分居、家暴、出轨、赌博等具体事实"),
        Field("previous_suit",  "是否曾起诉离婚", hint="是/否；何时"),
        Field("separation_since", "分居起始时间"),
    ]),
    ElementGroup("子女情况", repeatable=True, fields=[
        Field("child_name",     "子女姓名"),
        Field("child_age",      "子女年龄"),
        Field("child_custody_now", "现由谁抚养"),
    ]),
    ElementGroup("子女抚养（诉请）", [
        Field("custody_claim",  "抚养权主张", hint="请求子女由谁抚养"),
        Field("support_fee",    "抚养费主张", unit="元/月"),
    ]),
    ElementGroup("财产分割", [
        Field("common_property", "夫妻共同财产", hint="房产/车辆/存款/股权/公积金等，逐项列明"),
        Field("property_split",  "财产分割方案", hint="请求如何分割"),
        Field("common_debt",     "夫妻共同债务"),
    ]),
]


# ─────────────────────────────────────────────
# 汇总：案由 -> Schema
# ─────────────────────────────────────────────
SCHEMAS: Dict[str, CauseSchema] = {
    "民间借贷纠纷":       CauseSchema("民间借贷纠纷",       GROUPS_PRIVATE_LENDING),
    "买卖合同纠纷":       CauseSchema("买卖合同纠纷",       GROUPS_SALE_CONTRACT),
    "物业服务合同纠纷":   CauseSchema("物业服务合同纠纷",   GROUPS_PROPERTY_SERVICE),
    "金融借款合同纠纷":   CauseSchema("金融借款合同纠纷",   GROUPS_FINANCIAL_LOAN),
    "信用卡纠纷":         CauseSchema("信用卡纠纷",         GROUPS_CREDIT_CARD),
    "劳动争议":           CauseSchema("劳动争议",           GROUPS_LABOR),
    "离婚纠纷":           CauseSchema("离婚纠纷",           GROUPS_DIVORCE),
}


def get_schema(cause: str) -> Optional[CauseSchema]:
    """按案由名取 Schema，不存在返回 None"""
    return SCHEMAS.get(cause)


def all_causes() -> List[str]:
    """所有支持的案由"""
    return list(SCHEMAS.keys())


def full_groups(cause: str) -> List[ElementGroup]:
    """
    返回某案由的【完整要素组序列】（公共 + 案由专属），
    供渲染器按顺序输出要素式起诉状。
    """
    schema = get_schema(cause)
    if schema is None:
        return []
    return [
        COMMON_PARTY_GROUP_PLAINTIFF,
        COMMON_PARTY_GROUP_DEFENDANT,
        COMMON_CLAIM_GROUP,
        *schema.fact_groups,
        COMMON_COST_CLAIM,
        COMMON_EVIDENCE_GROUP,
    ]
