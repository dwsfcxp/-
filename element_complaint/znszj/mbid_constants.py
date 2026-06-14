# -*- coding: utf-8 -*-
"""
文书类型定义（mbid）—— 移植自法穿 doc_convert/constants.py

mbid 是法院智能诉讼平台对每种文书类型的拼音首字母编码。
覆盖起诉状/答辩状/申请书/调解等 60+ 种，其中起诉状即"要素式起诉状"。
"""

from __future__ import annotations
from collections import defaultdict
from typing import TypedDict


class MbidDefinition(TypedDict):
    mbid: str
    name: str
    category: str


MBID_DEFINITIONS: list[MbidDefinition] = [
    # ─── 起诉状（要素式） ───
    {"mbid": "mjjdqsz", "name": "民间借贷起诉状", "category": "起诉状"},
    {"mbid": "lhjfqsz", "name": "离婚纠纷起诉状", "category": "起诉状"},
    {"mbid": "mmhtqsz", "name": "买卖合同起诉状", "category": "起诉状"},
    {"mbid": "wyfwqsz", "name": "物业服务起诉状", "category": "起诉状"},
    {"mbid": "ldzyqsz", "name": "劳动争议起诉状", "category": "起诉状"},
    {"mbid": "jdcjtsgqsz", "name": "机动车交通事故起诉状", "category": "起诉状"},
    {"mbid": "jrjkqsz", "name": "金融借款起诉状", "category": "起诉状"},
    {"mbid": "yhxykqsz", "name": "银行信用卡起诉状", "category": "起诉状"},
    {"mbid": "rzzlhtqsz", "name": "融资租赁合同起诉状", "category": "起诉状"},
    {"mbid": "bzbxhtqsz", "name": "保证保险合同起诉状", "category": "起诉状"},
    {"mbid": "zqxjcszrqsz", "name": "证券虚假陈述责任起诉状", "category": "起诉状"},
    {"mbid": "fwmmhtjfmsqsz", "name": "房屋买卖合同起诉状", "category": "起诉状"},
    {"mbid": "fwzlhtjfmsqsz", "name": "房屋租赁合同起诉状", "category": "起诉状"},
    {"mbid": "ccssbxhtjfmsqsz", "name": "财产损失保险合同起诉状", "category": "起诉状"},
    {"mbid": "jsgcsghtjfmsqsz", "name": "建设工程施工合同起诉状", "category": "起诉状"},
    {"mbid": "zrbxhtjfmsqsz", "name": "责任保险合同起诉状", "category": "起诉状"},
    {"mbid": "rsbxhtjfmsqsz", "name": "人身保险合同起诉状", "category": "起诉状"},
    {"mbid": "jshtjfmsqsz", "name": "技术合同纠纷起诉状", "category": "起诉状"},
    # ─── 申请书（强制执行申请书要素式） ───
    {"mbid": "qzzxsqs", "name": "强制执行申请书", "category": "申请书"},
    {"mbid": "zsjcczfjgtxzcssqs", "name": "暂时解除乘坐飞机、高铁限制措施申请书", "category": "申请书"},
    {"mbid": "cyfpsqs", "name": "参与分配申请书", "category": "申请书"},
    {"mbid": "zxdbsqs", "name": "执行担保申请书", "category": "申请书"},
    {"mbid": "zxyysqs", "name": "执行异议申请书", "category": "申请书"},
    {"mbid": "zxfysqs", "name": "执行复议申请书", "category": "申请书"},
    {"mbid": "zxjdsqs", "name": "执行监督申请书", "category": "申请书"},
    {"mbid": "qryxgmqsqs", "name": "确认优先购买权申请书", "category": "申请书"},
    {"mbid": "byzxzccjdjshgzzqwssqs", "name": "不予执行申请书", "category": "申请书"},
    # ─── 答辩状 ───
    {"mbid": "mjjddbz", "name": "民间借贷答辩状", "category": "答辩状"},
    {"mbid": "lhjfdbz", "name": "离婚纠纷答辩状", "category": "答辩状"},
    {"mbid": "mmhtdbz", "name": "买卖合同答辩状", "category": "答辩状"},
    {"mbid": "wyfwdbz", "name": "物业服务答辩状", "category": "答辩状"},
    {"mbid": "ldzydbz", "name": "劳动争议答辩状", "category": "答辩状"},
    {"mbid": "jdcjtsgdbz", "name": "机动车交通事故答辩状", "category": "答辩状"},
    {"mbid": "jrjkdbz", "name": "金融借款答辩状", "category": "答辩状"},
    {"mbid": "yhxykdbz", "name": "银行信用卡答辩状", "category": "答辩状"},
    {"mbid": "rzzlhtdbz", "name": "融资租赁合同答辩状", "category": "答辩状"},
    {"mbid": "bzbxhtdbz", "name": "保证保险合同答辩状", "category": "答辩状"},
    {"mbid": "zqxjcszrdbz", "name": "证券虚假陈述责任答辩状", "category": "答辩状"},
    {"mbid": "fwmmhtjfmsdbz", "name": "房屋买卖合同纠纷答辩状", "category": "答辩状"},
    {"mbid": "fwzlhtjfmsdbz", "name": "房屋租赁合同纠纷答辩状", "category": "答辩状"},
    {"mbid": "ccssbxhtjfmsdbz", "name": "财产损失保险合同纠纷民事答辩状", "category": "答辩状"},
    {"mbid": "jsgcsghtjfmsdbz", "name": "建设工程施工合同纠纷答辩状", "category": "答辩状"},
    {"mbid": "zrbxhtjfmsdbz", "name": "责任保险合同纠纷民事答辩状", "category": "答辩状"},
    {"mbid": "rsbxhtjfmsdbz", "name": "人身保险合同纠纷民事答辩状", "category": "答辩状"},
    {"mbid": "jshtjfmsdbz", "name": "技术合同纠纷答辩状", "category": "答辩状"},
    {"mbid": "xzdbz", "name": "行政答辩状", "category": "答辩状"},
    # ─── 调解申请书 / 调解答辩意见书 ───
    {"mbid": "mjjdjftjsqs", "name": "民间借贷纠纷调解申请书", "category": "调解申请书"},
    {"mbid": "lhjftjsqs", "name": "离婚纠纷调解申请书", "category": "调解申请书"},
    {"mbid": "ldjftjsqs", "name": "劳动纠纷调解申请书", "category": "调解申请书"},
    {"mbid": "jdcjtsgzrjftjsqs", "name": "机动车交通事故责任纠纷调解申请书", "category": "调解申请书"},
    {"mbid": "mjjdjftjdbyjs", "name": "民间借贷纠纷调解答辩意见书", "category": "调解答辩意见书"},
    {"mbid": "lhjftjdbyjs", "name": "离婚纠纷调解答辩意见书", "category": "调解答辩意见书"},
    {"mbid": "ldjftjdbyjs", "name": "劳动纠纷调解答辩意见书", "category": "调解答辩意见书"},
    {"mbid": "jdcjtsgzrjftjdbyjs", "name": "机动车交通事故责任纠纷调解答辩意见书", "category": "调解答辩意见书"},
    # ─── 陈述书 ───
    {"mbid": "sbcxfsxzjfdsryjcss", "name": "商标撤销复审行政纠纷第三人意见陈述书", "category": "陈述书"},
    {"mbid": "sbwxxzjfdsryjcss", "name": "商标无效行政纠纷第三人意见陈述书", "category": "陈述书"},
    {"mbid": "zlwxxzjfdsryjcss", "name": "专利无效行政纠纷第三人意见陈述书", "category": "陈述书"},
    # ─── 其他 ───
    {"mbid": "zjqd", "name": "证据清单", "category": "其他"},
    {"mbid": "zcsqs", "name": "仲裁申请书", "category": "其他"},
    {"mbid": "sqwtsgr", "name": "授权委托书（个人）", "category": "其他"},
    {"mbid": "xzfysqsgr", "name": "行政复议申请书（个人）", "category": "其他"},
    {"mbid": "xzfysqsdw", "name": "行政复议申请书（单位）", "category": "其他"},
]


# 本项目 7 大案由 → 法院平台 mbid 映射
CAUSE_TO_MBID = {
    "民间借贷纠纷":       "mjjdqsz",
    "买卖合同纠纷":       "mmhtqsz",
    "物业服务合同纠纷":   "wyfwqsz",
    "金融借款合同纠纷":   "jrjkqsz",
    "信用卡纠纷":         "yhxykqsz",
    "劳动争议":           "ldzyqsz",
    "离婚纠纷":           "lhjfqsz",
}


def get_mbid_set() -> set[str]:
    return {item["mbid"] for item in MBID_DEFINITIONS}


def get_mbid_by_category() -> dict[str, list[MbidDefinition]]:
    result: dict[str, list[MbidDefinition]] = defaultdict(list)
    for item in MBID_DEFINITIONS:
        result[item["category"]].append(item)
    return dict(result)


def get_mbid_for_cause(cause: str) -> str | None:
    """本项目案由名 → 法院平台 mbid（用于 znszj 后端）。无映射返回 None。"""
    return CAUSE_TO_MBID.get(cause)
