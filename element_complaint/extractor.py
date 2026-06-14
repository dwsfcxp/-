# -*- coding: utf-8 -*-
"""
规则抽取器 —— 用正则与模式匹配，从普通叙述式起诉状中抽取结构化要素。

擅长：精确字段：身份证号、手机号、银行卡号、金额、日期，以及当事人/诉讼请求/证据段落。
不擅长？自然语言的灵活表达（如把"借给"写成"出借资金给"）—— 那交给 llm_extractor。
"""

import re
from typing import Dict, List, Optional, Tuple

from .schemas import (
    get_schema, all_causes, full_groups, Field, ElementGroup,
)
import config


# ─────────────────────────────────────────────
# 正则库
# ─────────────────────────────────────────────
RE_PHONE   = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')   # 前后非数字，避免匹配身份证号子串
RE_IDCARD  = re.compile(r'[1-9]\d{16}[\dXx]')
RE_BANKCARD = re.compile(r'\b\d{16,19}\b')
RE_DATE    = re.compile(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日')
# 金额正则（借鉴法穿 execution_request_utils.AMOUNT_WITH_UNIT_PATTERN）：
# [0-9][0-9,]* 不限制千分位格式（520000 / 520,000 均可），(万)? 单独捕获便于×10000换算
AMOUNT_WITH_UNIT_PATTERN = r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万)?\s*元?"
RE_MONEY = re.compile(AMOUNT_WITH_UNIT_PATTERN)


def parse_amount_value(num_str: str, wan_flag: str) -> float:
    """金额换算：去千分位、'万'则×10000（借鉴法穿 parse_amount_value）。"""
    try:
        val = float(num_str.replace(',', ''))
    except ValueError:
        return 0.0
    if wan_flag:      # 含"万" → ×10000
        val *= 10000
    return val


# 中文数字 → 阿拉伯（利率倍数"四倍LPR"等，借鉴法穿 parse_multiplier_value）
_CN_DIGIT = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}


def parse_cn_number(s: str) -> int:
    """中文数字转int：'四'→4, '十'→10, '二十'→20, '二十四'→24"""
    if s.isdigit():
        return int(s)
    if s == '十':
        return 10
    if '十' in s:
        a, _, b = s.partition('十')
        tens = _CN_DIGIT.get(a, 1) if a else 1
        ones = _CN_DIGIT.get(b, 0) if b else 0
        return tens * 10 + ones
    return _CN_DIGIT.get(s, 0)
# 中文金额（简）
RE_CN_NUM  = re.compile(r'[零一二三四五六七八九十佰仟万亿两壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元整]+')

# 民族
RE_NATION  = re.compile(r'([一-龥]{1,4})族')
# 性别
RE_GENDER  = re.compile(r'[男女]')

# 中文姓名（2-4字，允许·）
RE_CN_NAME = re.compile(r'[一-龥·]{2,6}')


# ─────────────────────────────────────────────
# 文本预处理
# ─────────────────────────────────────────────
_FULL2HALF = str.maketrans('０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ，。：；！？（）【】',
                           '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ,.:;!?()[]')


def normalize(text: str) -> str:
    """全角转半角、归一空白，保留换行以便段落切分。"""
    if not text:
        return ""
    text = text.translate(_FULL2HALF)
    # 多余空格压缩
    text = re.sub(r'[ \t]+', ' ', text)
    # 去除连续空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ─────────────────────────────────────────────
# 案由识别
# ─────────────────────────────────────────────
def detect_cause(text: str) -> str:
    """关键词匹配案由。匹配数最多的胜出。"""
    scores = {}
    for cause, keywords in config.CAUSE_KEYWORDS:
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            scores[cause] = score
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return config.DEFAULT_CAUSE


# ─────────────────────────────────────────────
# 段落切分
# ─────────────────────────────────────────────
def split_sections(text: str) -> Dict[str, str]:
    """
    把起诉状切成几个语义段落：
      parties     - 当事人信息（开头到"诉讼请求"前）
      claims      - 诉讼请求段
      facts       - 事实与理由段
      evidence    - 证据段
      tail        - 结尾（致法院、具状人、日期）
    """
    t = normalize(text)

    # 找各段锚点
    anchors = {}
    for key, pat in [
        ('claims',   r'诉讼\s*请求'),
        ('facts',    r'事实\s*(?:和|与)\s*理由'),
        ('evidence', r'证据(?:清单|目录|列表|材料)?'),
        ('tail',     r'此\s*致|谨\s*此|敬呈|具状人|起诉人'),
    ]:
        m = re.search(pat, t)
        if m:
            anchors[key] = m.start()

    parties_end = anchors.get('claims', anchors.get('facts', len(t)))
    sections = {
        'parties':  t[:parties_end].strip(),
        'claims':   '',
        'facts':    '',
        'evidence': '',
        'tail':     '',
    }

    # 顺序切：claims -> facts -> evidence -> tail
    order = ['claims', 'facts', 'evidence', 'tail']
    positions = sorted([(anchors.get(k, len(t)), k) for k in order if k in anchors])
    for i, (pos, key) in enumerate(positions):
        nxt = positions[i + 1][0] if i + 1 < len(positions) else len(t)
        sections[key] = t[pos:nxt].strip()

    return sections


# ─────────────────────────────────────────────
# 当事人解析
# ─────────────────────────────────────────────
def _parse_one_party(segment: str) -> Dict[str, str]:
    """解析单个当事人段（原告或被告的描述），抽取姓名/性别/出生/民族/身份证/住址/电话。"""
    info = {k: "" for k in ('name', 'gender', 'birth', 'nation', 'id', 'addr', 'phone')}
    if not segment:
        return info

    # 身份证
    m = RE_IDCARD.search(segment)
    if m:
        info['id'] = m.group(0)
    # 电话
    m = RE_PHONE.search(segment)
    if m:
        info['phone'] = m.group(0)
    # 出生日期
    m = RE_DATE.search(segment)
    if m:
        info['birth'] = re.sub(r'\s', '', m.group(0))
    # 民族
    m = RE_NATION.search(segment)
    if m:
        info['nation'] = m.group(1) + '族'
    # 性别
    m = RE_GENDER.search(segment)
    if m:
        info['gender'] = m.group(0)
    # 住址：匹配"住/住所/住址/户籍地/居住地"之后到句号或分号
    m = re.search(r'(?:住所|住址|户籍地|居住地|住址地|现住|住)\s*[：:是为]?\s*([^，。；,;！\n]+)', segment)
    if m:
        addr = m.group(1).strip()
        # 去掉可能粘上的"身份证号"等
        addr = re.sub(r'身份证.*$', '', addr).strip()
        info['addr'] = addr
    # 姓名：多模式匹配（normalize后冒号为半角":"），含 role 前缀。
    # {2,20} 兼顾自然人(2-4字)与法人单位名称(可达20字)
    for pat in (
        r'(?:原告|被告|申请人|上诉人|第三人|反诉原告|反诉被告)\s*[（(][^)）]*[)）]\s*[：:;；]?\s*([一-龥·]{2,20}?)[,，。；;.\s]',
        r'(?:原告|被告|申请人|上诉人|第三人|反诉原告|反诉被告)\s*[：:;；]?\s*([一-龥·]{2,20}?)[,，。；;.\s]',
        r'(?:原告|被告|申请人|上诉人|第三人|反诉原告|反诉被告)\s*[：:;；]?\s*([一-龥·]{2,20})',
    ):
        m = re.search(pat, segment)
        if m:
            info['name'] = m.group(1)
            break
    return info


def extract_parties(parties_text: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """从当事人段落抽取原告、被告信息。"""
    if not parties_text:
        return ({k: "" for k in ('name', 'gender', 'birth', 'nation', 'id', 'addr', 'phone')},) * 2

    blank = {k: "" for k in ('name', 'gender', 'birth', 'nation', 'id', 'addr', 'phone')}

    # 按原告/被告关键词定位
    def find_role(role):
        # 从 role 关键词位置开始（含 role 前缀，便于后续姓名正则匹配），截到下一个角色
        m = re.search(rf'{role}', parties_text)
        if not m:
            return ""
        start = m.start()
        after = parties_text[start + len(role):]
        end_m = re.search(
            r'(?:原告|被告|第三人|申请人|上诉人|反诉原告|反诉被告|委托(?:诉讼)?代理人|法定代理人)',
            after,
        )
        end = start + len(role) + end_m.start() if end_m else len(parties_text)
        return parties_text[start:end].strip()

    seg_p = find_role('原告')
    seg_d = find_role('被告')
    # 若按关键词没切出来，整段都塞给当事人解析兜底
    if not seg_p and not seg_d:
        # 退而求其次：整段尝试解析（先原告后被告依次）
        lines = re.split(r'[；;\n]', parties_text)
        segs = [l for l in lines if ('原告' in l or '被告' in l)]
        seg_p = next((l for l in segs if '原告' in l), parties_text)
        seg_d = next((l for l in segs if '被告' in l), "")

    return _parse_one_party(seg_p), _parse_one_party(seg_d)


# ─────────────────────────────────────────────
# 诉讼请求 / 证据解析
# ─────────────────────────────────────────────
def extract_claims(claims_text: str) -> List[str]:
    """诉讼请求分项。按 1. 2. / 一、二、 / ① ② 切分。"""
    if not claims_text:
        return []
    # 去掉"诉讼请求:"标题
    body = re.sub(r'^.*?诉讼\s*请求\s*[：:;；]?\s*', '', claims_text, count=1, flags=re.S)
    body = re.sub(r'(事实\s*(?:和|与)\s*理由.*)$', '', body, flags=re.S).strip()
    # 按"序号、"或换行切
    parts = re.split(r'(?:\n|；;|(?<=[。])\s*)(?=\d+[.、)）]|[一二三四五六七八九十]+[、）])', body)
    items = []
    for p in parts:
        p = re.sub(r'^\s*(?:\d+[.、)）]|[一二三四五六七八九十]+[、）])\s*', '', p).strip()
        p = p.strip('；;。. :：')
        if p:
            items.append(p)
    return items


def extract_evidence(evidence_text: str) -> List[Dict[str, str]]:
    """证据清单解析为 [{name, form, purpose, source}, ...]"""
    if not evidence_text:
        return []
    body = re.sub(r'^.*?证据(?:清单|目录|列表|材料)?\s*[：:为有如下]*\s*', '', evidence_text, count=1)
    # 去掉结尾致法院等内容
    body = re.sub(r'(此\s*致.*|谨\s*此.*|敬呈.*|具状人.*)$', '', body, flags=re.S).strip()
    parts = re.split(r'(?:\n|；;|(?<=[。])\s*)(?=\d+[.、)）]|证据[一二三四五六七八九十]+|证据\d+)', body)
    items = []
    for p in parts:
        p = re.sub(r'^\s*(?:\d+[.、)）]|证据[一二三四五六七八九十]+|证据\d+)\s*[：:]?\s*', '', p).strip()
        p = p.strip('；;。. :：')
        if not p:
            continue
        # 简单切分：把"证明xxx"作为 purpose
        purpose = ""
        mp = re.search(r'证明(?:[^，。；,;]*?[，。；,;]?)', p)
        if mp:
            purpose = mp.group(0).strip('，。；,;')
        items.append({
            'name': p,
            'form': '',
            'purpose': purpose,
            'source': '',
        })
    return items


# ─────────────────────────────────────────────
# 案由专属字段抽取
# ─────────────────────────────────────────────
# 字段 key -> 用于在原文中定位的上下文关键词
FIELD_KEYWORDS = {
    # 民间借贷
    'principal':         ['借款本金', '本金', '借给', '借款', '出借', '借人民币', '向.*?借款'],
    'owed_principal':    ['尚欠本金', '欠本金', '未还本金', '本金.*?未还', r'尚欠[^。；\n]{0,10}本金'],
    'owed_interest':     ['尚欠利息', '欠利息', '利息.*?未付', '未付利息'],
    'total_claim':       ['合计', '共计', '总计', '共计人民币', '请求.*?偿还'],
    'paid_principal':    ['已还本金', '偿还本金', '归还本金', '已偿还'],
    'paid_interest':     ['已付利息', '已支付利息', '付清利息'],
    'loan_date':         ['借款时间', '借款日期', r'于.{0,4}年.{0,2}月.{0,2}日.{0,20}借', '签订借条', '出具.*?借条'],
    'interest_rate':     ['年利率', '月息', '月利率', '利息.*?按', '利率'],
    # 买卖
    'total_price':       ['总价', '总货款', '货款总额', '合同总价'],
    'owed_amount':       ['尚欠.*?货款', '拖欠货款', '未付货款', '欠货款'],
    'paid_amount':       ['已付.*?货款', '已支付货款'],
    'penalty_amount':    ['违约金', '滞纳金'],
    # 物业
    'arrears_amount':    ['欠.*?物业费', '拖欠.*?物业费', '累计欠费', '欠费金额'],
    'fee_standard':      ['物业费.*?标准', '收费标准', '元/平方米', '元/平米'],
    # 金融借款 / 信用卡
    'overdue_principal': ['透支本金', '逾期本金'],
    'owed_interest':     ['尚欠利息', '欠息', '利息及罚息'],
    # 劳动
    'salary':            ['月工资', '工资标准', '月薪'],
    'arrears_amount':    ['欠.*?工资', '拖欠工资', '未发工资'],
    'economic_comp':     ['经济补偿金', '赔偿金'],
}

DATE_FIELDS = {'loan_date', 'contract_date', 'repay_due', 'hire_date', 'leave_date',
               'bill_start', 'arrears_start', 'arrears_end', 'overdue_start',
               'marry_date', 'separation_since', 'acceleration'}


def _pick_money_near(text: str, keywords: List[str]) -> str:
    """在包含某关键词的句子附近，找第一个金额。"""
    for kw in keywords:
        for m in re.finditer(kw, text):
            window = text[m.start(): m.start() + 60]
            mm = RE_MONEY.search(window)
            if mm:
                fval = parse_amount_value(mm.group(1), mm.group(2))
                if fval > 0:
                    return f"{int(fval)}" if fval == int(fval) else f"{fval}"
    return ""


def _pick_date_near(text: str, keywords: List[str]) -> str:
    for kw in keywords:
        for m in re.finditer(kw, text):
            window = text[max(0, m.start() - 10): m.start() + 40]
            md = RE_DATE.search(window)
            if md:
                return re.sub(r'\s', '', md.group(0))
    return ""


def extract_fact_fields(facts_text: str, all_text: str, cause: str) -> Dict[str, str]:
    """抽取案由专属事实要素。facts_text:事实段；all_text:全文（兜底搜索）。"""
    result = {}
    schema = get_schema(cause)
    if schema is None:
        return result
    source = (facts_text or "") + "\n" + (all_text or "")

    for group in schema.fact_groups:
        for f in group.fields:
            if f.key in result and result[f.key]:
                continue
            kws = FIELD_KEYWORDS.get(f.key)
            if not kws:
                continue
            if f.key in DATE_FIELDS:
                val = _pick_date_near(source, kws) or _pick_date_near(all_text, kws)
            else:
                val = _pick_money_near(source, kws) or _pick_money_near(all_text, kws)
            if val:
                result[f.key] = val

    # 民间借贷特定兜底：借款时间取事实段首个日期；尚欠本金缺省取本金（本金通常全额未还）
    if cause == '民间借贷纠纷':
        if not result.get('loan_date'):
            md = RE_DATE.search(facts_text or all_text)
            if md:
                result['loan_date'] = re.sub(r'\s', '', md.group(0))
        if not result.get('owed_principal') and result.get('principal'):
            result['owed_principal'] = result['principal']

    return result


# ─────────────────────────────────────────────
# 抽取器主类
# ─────────────────────────────────────────────
class RuleExtractor:
    """规则抽取器：对一段普通起诉状文本做全部要素抽取。"""

    def extract(self, text: str, cause: Optional[str] = None) -> Dict:
        t = normalize(text or "")
        if cause is None:
            cause = detect_cause(t)

        sections = split_sections(t)
        plaintiff, defendant = extract_parties(sections['parties'])
        claims = extract_claims(sections['claims'])
        evidence = extract_evidence(sections['evidence'])
        facts = extract_fact_fields(sections['facts'], t, cause)

        return {
            'cause': cause,
            'plaintiff': plaintiff,
            'defendant': defendant,
            'claims': claims,
            'evidence': evidence,
            'facts': facts,
            'sections': sections,
            'raw_text': t,
            'source': 'rule',
        }
