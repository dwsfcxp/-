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


def _fmt_money(val: float) -> str:
    """金额格式化为显示串：整数去小数点。"""
    if val <= 0:
        return ""
    return f"{int(val)}" if val == int(val) else f"{val:g}"


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
        ('claims',   r'诉讼\s*请求|请求\s*事项|请求\s*如下'),
        ('facts',    r'事实\s*(?:和|与)\s*理由'),
        ('evidence', r'证据(?:清单|目录|列表|材料)?'),
        ('tail',     r'此\s*致|谨\s*此|敬呈|具状人|起诉人|申请人'),
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
    # 统一社会信用代码（法人，18位含字母）—— 若没匹配到身份证，再试一次
    if not info['id']:
        m = re.search(r'统一社会信用代码\s*[：:]\s*([0-9A-Za-z]{15,20})', segment)
        if m:
            info['id'] = m.group(1)
    # 电话
    m = RE_PHONE.search(segment)
    if m:
        info['phone'] = m.group(0)
    # 固话兜底（010-88888001）
    if not info['phone']:
        m = re.search(r'(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)', segment)
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
    m = re.search(r'(?:住所|住址|户籍地|居住地|住址地|现住|住|营业场所|注册地)\s*[：:是为]?\s*([^，。；,;！\n]+)', segment)
    if m:
        addr = m.group(1).strip()
        # 去掉可能粘上的"身份证号"等
        addr = re.sub(r'身份证.*$', '', addr).strip()
        addr = re.sub(r'电话.*$', '', addr).strip()
        addr = re.sub(r'统一社会信用代码.*$', '', addr).strip()
        info['addr'] = addr
    # 姓名：多模式匹配（normalize后冒号为半角":"），含 role 前缀。
    # {2,20} 兼顾自然人(2-4字)与法人单位名称(可达20字)
    for pat in (
        r'(?:原告|被告|申请人|上诉人|被申请人|第三人|反诉原告|反诉被告|申请执行人|被申请执行人|异议人)\s*[（(][^)）]*[)）]\s*[：:;；]?\s*([一-龥·]{2,20}?)[,，。；;.\s]',
        r'(?:原告|被告|申请人|上诉人|被申请人|第三人|反诉原告|反诉被告|申请执行人|被申请执行人|异议人)\s*[：:;；]?\s*([一-龥·]{2,20}?)[,，。；;.\s]',
        r'(?:原告|被告|申请人|上诉人|被申请人|第三人|反诉原告|反诉被告|申请执行人|被申请执行人|异议人)\s*[：:;；]?\s*([一-龥·]{2,20})',
    ):
        m = re.search(pat, segment)
        if m:
            info['name'] = m.group(1)
            break
    return info


def extract_parties(parties_text: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """从当事人段落抽取原告、被告信息。"""
    blank = {k: "" for k in ('name', 'gender', 'birth', 'nation', 'id', 'addr', 'phone')}
    if not parties_text:
        return blank, dict(blank)

    roles = ['原告', '被告', '申请执行人', '被申请执行人', '申请人', '被申请人', '上诉人', '第三人', '异议人']

    # 按角色关键词定位
    def find_role(role):
        # 从 role 关键词位置开始（含 role 前缀，便于后续姓名正则匹配），截到下一个角色
        m = re.search(rf'{role}', parties_text)
        if not m:
            return ""
        start = m.start()
        after = parties_text[start + len(role):]
        end_m = re.search(
            r'(?:原告|被告|第三人|申请人|被申请人|上诉人|被上诉人|委托(?:诉讼)?代理人|法定代理人|负责人|申请执行人|被申请执行人|异议人)',
            after,
        )
        end = start + len(role) + end_m.start() if end_m else len(parties_text)
        return parties_text[start:end].strip()

    # 兼容：起诉状用 原告/被告；申请书用 申请执行人/被申请执行人、申请人/被申请人
    seg_p = find_role('原告') or find_role('申请执行人') or find_role('申请人') or find_role('上诉人')
    seg_d = find_role('被告') or find_role('被申请执行人') or find_role('被申请人') or find_role('被上诉人')
    # 若按关键词没切出来，整段都塞给当事人解析兜底
    if not seg_p and not seg_d:
        # 退而求其次：整段尝试解析（先原告后被告依次）
        lines = re.split(r'[；;\n]', parties_text)
        segs = [l for l in lines if any(r in l for r in roles)]
        seg_p = next((l for l in segs if any(r in l for r in ['原告', '申请执行人', '申请人', '上诉人'])), parties_text)
        seg_d = next((l for l in segs if any(r in l for r in ['被告', '被申请执行人', '被申请人', '被上诉人'])), "")

    return _parse_one_party(seg_p), _parse_one_party(seg_d)


# ─────────────────────────────────────────────
# 诉讼请求 / 证据解析
# ─────────────────────────────────────────────
# 识别"诉讼费用承担"条目（这类请求不进 claims 列表，单独存 cost_burden，避免渲染重复）
_RE_COST_CLAIM = re.compile(r'诉讼费(?:用)?')


def _split_cost_claim(claims: List[str]) -> Tuple[List[str], str]:
    """从 claims 中剥离"诉讼费用承担"条目。返回 (其余请求, 诉讼费条款)。

    若原文有诉讼费条目则取原文表述；否则返回空串（由渲染器补默认条款）。
    """
    rest, cost = [], ""
    for c in claims:
        if _RE_COST_CLAIM.search(c):
            if not cost:
                cost = c
        else:
            rest.append(c)
    return rest, cost


def extract_claims(claims_text: str) -> List[str]:
    """诉讼请求分项。按 1. 2. / 一、二、 / ① ② 切分。"""
    if not claims_text:
        return []
    # 去掉"诉讼请求:"标题
    body = re.sub(r'^.*?(?:诉讼\s*请求|请求\s*事项|请求\s*如下)\s*[：:;；]?\s*', '', claims_text, count=1, flags=re.S)
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


# 证据形式推断（按证据名称关键词 → 书证/物证/电子数据/视听资料/证人证言）
_EVIDENCE_FORM_RULES = [
    (r'微信|短信|QQ|聊天记录|电子邮件|电子数据|截图|支付宝账单|转账记录|网页|区块链', '电子数据'),
    (r'录音|录像|视频|监控|视听', '视听资料'),
    (r'证人|证言|陈述', '证人证言'),
    (r'照片|图片|物证', '物证'),
    (r'借条|合同|协议|凭证|发票|收据|欠条|账单|银行流水|汇款单|对账单|送货单|签收单|快递单|结婚证|营业执照|判决书|裁定书|调解书|公证书|鉴定意见|勘验', '书证'),
]


def _infer_evidence_form(name: str) -> str:
    """根据证据名称推断证据形式（书证/电子数据/...）。"""
    for pat, form in _EVIDENCE_FORM_RULES:
        if re.search(pat, name):
            return form
    return ""


def extract_evidence(evidence_text: str) -> List[Dict[str, str]]:
    """证据清单解析为 [{name, form, purpose, source}, ...]

    证据条目常见格式："1. 借条原件一份，证明原被告之间存在借款关系及...的约定"
    - name:   证据名称（去掉"一份""，证明..."等后缀）
    - form:   证据形式（书证/电子数据/视听资料/证人证言/物证，按名称推断）
    - purpose:证明对象（"证明"后的内容）
    - source: 来源（原件/复制件，按名称中的"原件/复印件/复制件"判断）
    """
    if not evidence_text:
        return []
    body = re.sub(r'^.*?证据(?:清单|目录|列表|材料)?\s*[：:为有如下]*\s*', '', evidence_text, count=1)
    # 去掉结尾致法院等内容
    body = re.sub(r'(此\s*致.*|谨\s*此.*|敬呈.*|具状人.*|申请人.*)$', '', body, flags=re.S).strip()
    parts = re.split(r'(?:\n|；;|(?<=[。])\s*)(?=\d+[.、)）]|证据[一二三四五六七八九十]+|证据\d+)', body)
    items = []
    for p in parts:
        p = re.sub(r'^\s*(?:\d+[.、)）]|证据[一二三四五六七八九十]+|证据\d+)\s*[：:]?\s*', '', p).strip()
        p = p.strip('；; :：')
        if not p:
            continue
        # 切分 name / purpose：以"，证明"或"证明"为界
        purpose = ""
        m = re.search(r'[，,；;]?\s*证明[:：]?\s*(.+?)$', p, flags=re.S)
        if m:
            purpose = m.group(1).strip('，。；,;。. :：')
            name = p[:m.start()].strip('，。；,;。. :：')
        else:
            name = p.strip('。')
        # 证据名称里的"原件/复印件/复制件"归 source，并从名称剥离"一份/两份"等量词后缀
        source = ""
        ms = re.search(r'(原件|复印件|复制件|原物|复制品)', name)
        if ms:
            source = ms.group(1)
        # 剥离尾部量词"一份/两份/各一份/数份"
        name_clean = re.sub(r'[，,]?\s*(各)?\s*[一二三四五六七八九十两\d]+\s*份\s*$', '', name).strip()
        name_clean = re.sub(r'[，,]?\s*(原件|复印件|复制件|原物|复制品)\s*$', '', name_clean).strip()
        if not name_clean:
            name_clean = name
        items.append({
            'name': name_clean,
            'form': _infer_evidence_form(name_clean),
            'purpose': purpose,
            'source': source,
        })
    return items


# ─────────────────────────────────────────────
# 案由专属字段抽取
# ─────────────────────────────────────────────
# 字段 key -> 用于在原文中定位的上下文关键词（供 _pick_money_near / _pick_date_near）
# 注意：dict 字面量里同名 key 会被后者覆盖，故把跨案由共用的 key（owed_interest、
# arrears_amount）合并到最后、聚合所有关键词，修复历史重复 key 导致关键词丢失的 bug。
FIELD_KEYWORDS = {
    # 民间借贷
    'principal':         ['借款本金', '本金', '借给', '借人民币', '向.*?借款', '出借.*?人民币'],
    'owed_principal':    ['尚欠本金', '欠本金', '未还本金', '本金.*?未还', r'尚欠[^。；\n]{0,10}本金'],
    'paid_principal':    ['已还本金', '偿还本金', '归还本金', '已偿还.*?本金'],
    'paid_interest':     ['已付利息', '已支付利息', '付清利息'],
    'total_claim':       ['合计', '共计', '总计', '共计人民币', '请求.*?偿还'],
    'loan_date':         ['借款时间', '借款日期', r'于.{0,4}年.{0,2}月.{0,2}日.{0,20}借', '签订借条', '出具.*?借条'],
    'interest_rate':     ['年利率', '月息', '月利率', '利息.*?按', '利率'],
    # 买卖
    'total_price':       ['总价', '总货款', '货款总额', '合同总价', '合同总价款'],
    'paid_amount':       ['已付.*?货款', '已支付货款', '支付货款', '已付.*?款'],
    'owed_amount':       ['尚欠.*?货款', '拖欠货款', '未付货款', '欠货款', '剩余.*?货款'],
    'penalty_amount':    ['违约金', '滞纳金', '逾期付款违约金'],
    'contract_date':     [r'签订.*?合同', r'合同.*?签订', r'于.{0,8}年.{0,2}月.{0,2}日.{0,12}签订', '签署.*?合同'],
    # 物业
    'fee_standard':      ['物业费.*?标准', '收费标准', '元/平方米', '元/平米', '元/㎡'],
    # 金融借款 / 信用卡
    'overdue_principal': ['透支本金', '逾期本金'],
    # 劳动
    'salary':            ['月工资', '工资标准', '月薪', '工资.*?元/月'],
    'economic_comp':     ['经济补偿金', '赔偿金', '经济补偿'],
    # —— 跨案由共用（聚合，放最后，修复历史重复 key 覆盖 bug）——
    'owed_interest':     ['尚欠利息', '欠利息', '逾期利息', '欠息', '利息及罚息',
                          '利息.*?未付', '未付利息', '罚息', '逾期利息.*?为'],
    'arrears_amount':    ['欠.*?物业费', '拖欠.*?物业费', '累计欠费', '欠费金额',
                          '欠.*?工资', '拖欠工资', '未发工资', '欠发工资', '拖欠.*?报酬'],
}

# 这些金额字段上下文易歧义（如利息"以X元为基数"会把基数当利息），不在通用邻近循环里抽，
# 交给各案由 _fill_* 函数做精确匹配。
_AMBIGUOUS_MONEY_FIELDS = {'owed_interest'}

# 这些日期/文本字段通用邻近匹配不可靠（如"签订"在文中多次出现会把交货日当签订日），
# 交给各案由 _fill_* 函数用更精确的上下文匹配。
_FILL_HANDLED_FIELDS = {'contract_date'}

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
                    return _fmt_money(fval)
    return ""


def _pick_date_near(text: str, keywords: List[str]) -> str:
    for kw in keywords:
        for m in re.finditer(kw, text):
            window = text[max(0, m.start() - 10): m.start() + 40]
            md = RE_DATE.search(window)
            if md:
                return re.sub(r'\s', '', md.group(0))
    return ""


def _yesno(text: str, yes_pats, no_pats=(), yes_label="是", no_label="否") -> str:
    """是/否判断：先看否定模式，再看肯定模式。都未命中返回空。"""
    for p in no_pats:
        if re.search(p, text):
            return no_label
    for p in yes_pats:
        if re.search(p, text):
            return yes_label
    return ""


def _first_money_after(text: str, pat: str, window: int = 40) -> str:
    """匹配 pat，在其后 window 字符内取第一个金额（用于精确上下文的金额抽取）。"""
    for m in re.finditer(pat, text):
        seg = text[m.end(): m.end() + window]
        mm = RE_MONEY.search(seg)
        if mm:
            val = parse_amount_value(mm.group(1), mm.group(2))
            if val > 0:
                return _fmt_money(val)
    return ""


# ─────────────────────────────────────────────
# 案由专属：文本/是/否/易歧义金额字段
# ─────────────────────────────────────────────
def _fill_private_lending(result: Dict, source: str) -> None:
    """民间借贷：交付方式、收款账户、利息约定、期限、是否到期、担保、借条、催讨、已还本金/利息、尚欠利息。"""
    # 交付方式
    if not result.get('delivery'):
        for pat, label in [(r'银行转账|转账', '银行转账'), (r'微信', '微信转账'),
                           (r'支付宝', '支付宝转账'), (r'现金', '现金交付'), (r'汇款', '银行汇款')]:
            if re.search(pat, source):
                result['delivery'] = label
                break
    # 收款账户/收款人
    if not result.get('receipt_account'):
        m = re.search(r'收款人\s*([一-龥·]{2,6})[^。；\n]{0,15}?(?:账号(?:尾号)?)\s*([0-9*]{4,})', source)
        if m:
            result['receipt_account'] = f"收款人{m.group(1)}，账号尾号{m.group(2)}"
        else:
            m = re.search(r'收款人\s*([一-龥·]{2,6})', source)
            if m:
                result['receipt_account'] = f"收款人{m.group(1)}"
    # 是否约定利息
    if not result.get('interest_agreed'):
        result['interest_agreed'] = _yesno(
            source,
            yes_pats=[r'约定.*?(?:年利率|月息|月利率|利息)', r'年利率', r'月息', r'月利率', r'利息.*?按'],
            no_pats=[r'未约定利息', r'无息', r'不支付利息'],
        )
    # 约定还款期限
    if not result.get('repay_due'):
        m = re.search(r'借款期限(?:为)?\s*([^，。；\n]{1,20}?)(?:[，。；])', source)
        if m:
            result['repay_due'] = m.group(1).strip()
        else:
            md = re.search(r'到期[^。；\n]{0,4}?(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', source)
            if md:
                result['repay_due'] = re.sub(r'\s', '', md.group(1))
    # 是否已到期
    if not result.get('is_due'):
        result['is_due'] = _yesno(
            source,
            yes_pats=[r'借款到期后', r'已到期', r'到期.*?(?:未|尚未)', r'期限届满'],
            no_pats=[r'尚未到期', r'未到期', r'期限未满'],
        )
    # 是否有担保/抵押
    if not result.get('guarantee'):
        m = re.search(r'(担保人[^，。；\n]{0,15}|抵押[^，。；\n]{0,15}|质押[^，。；\n]{0,15}|保证人[^，。；\n]{0,10})', source)
        if m:
            result['guarantee'] = '有：' + m.group(1).strip('，。；,;')
        else:
            result['guarantee'] = _yesno(source, yes_pats=[r'担保|抵押|质押|保证人'], yes_label='有', no_label='无') or '无'
    # 是否有借条/借款合同
    if not result.get('iou'):
        result['iou'] = _yesno(
            source,
            yes_pats=[r'出具.*?借条', r'签订.*?借款合同', r'借条', r'借款合同', r'欠条'],
            no_pats=[r'未.*?(?:出具|签订).*?(?:借条|合同)', r'没有.*?借条'],
        ) or '有' if re.search(r'借条|借款合同|欠条', source) else '无'
    # 被告已还本金：若明确"未偿还/未归还本金"→0；否则取"已还/偿还本金X元"
    if not result.get('paid_principal'):
        if re.search(r'未偿还.*?本金|本金.*?未还|至今未还|未归还.*?本金', source):
            result['paid_principal'] = '0'
        else:
            v = _first_money_after(source, r'已还.*?本金|偿还本金|归还本金')
            if v:
                result['paid_principal'] = v
    # 被告已付利息：若明确"未支付利息/未付息"→0
    if not result.get('paid_interest'):
        if re.search(r'未支付.*?利息|未付.*?利息|未付息|未支付任何利息', source):
            result['paid_interest'] = '0'
        else:
            v = _first_money_after(source, r'已付.*?利息|已支付利息')
            if v:
                result['paid_interest'] = v
    # 是否催讨及时间
    if not result.get('urged'):
        m = re.search(r'(多次)?\s*通过\s*([^，。；\n]{2,30}?)\s*(?:向被告)?\s*催[讨收告款]', source)
        if m:
            result['urged'] = '已催讨：通过' + m.group(2).strip() + '催讨'
        elif re.search(r'催[讨收告款]', source):
            result['urged'] = '已催讨'
    # 尚欠利息：精确匹配"暂计X元"（避免被"以X元为基数"的基数误导）
    if not result.get('owed_interest'):
        for pat in [r'暂计[^。；\n]{0,25}?(\d[\d,]*(?:\.\d+)?)\s*万?\s*元',
                    r'逾期利息[^。；\n]{0,30}?为[^。；\n]{0,8}?(\d[\d,]*(?:\.\d+)?)\s*万?\s*元',
                    r'利息[^。；\n]{0,6}?为[^。；\n]{0,8}?(\d[\d,]*(?:\.\d+)?)\s*万?\s*元']:
            m = re.search(pat, source)
            if m:
                val = parse_amount_value(m.group(1), '')
                if val > 0:
                    result['owed_interest'] = _fmt_money(val)
                    break


def _fill_sale_contract(result: Dict, source: str) -> None:
    """买卖合同：合同签订时间、合同标的、合同形式、约定交货、约定付款、违约金约定、催告。"""
    # 合同签订时间：精确匹配"日期...签订"（日期在前，且后接签订），强制覆盖通用邻近匹配
    # （通用循环会把"合同签订后...交付"里的交货日误当签订日，故 contract_date 完全交给这里）
    m = re.search(r'(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)[^。；\n]{0,25}?签订', source)
    if m:
        result['contract_date'] = re.sub(r'\s', '', m.group(1))
    # 合同标的
    if not result.get('subject'):
        m = (re.search(r'供应\s*([^，,。；;\n]{2,30}?)(?:一批|等|，|。|；|,|;|的)', source)
             or re.search(r'《([^》]{2,40})》', source))
        if m:
            s = m.group(1).strip('，。；,;的')
            if len(s) >= 2:
                result['subject'] = s
    # 合同形式
    if not result.get('contract_form'):
        if re.search(r'《[^》]+》|书面合同|签订.*?合同', source):
            result['contract_form'] = '书面合同'
        elif re.search(r'口头', source):
            result['contract_form'] = '口头约定'
    # 约定交货时间
    if not result.get('delivery_due'):
        md = re.search(r'(?:应于|于)\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)[^，,。；;\n]{0,12}?交货', source)
        if md:
            result['delivery_due'] = re.sub(r'\s', '', md.group(1))
    # 实际交货情况（只判断有无交付+验收，不吞尾巴）
    if not result.get('delivery_actual'):
        if re.search(r'交付.{0,12}?(?:验收|签收)|交付被告.{0,12}?签收', source):
            result['delivery_actual'] = '已交付全部货物，被告验收合格并签收'
        elif re.search(r'已.{0,6}?交付', source):
            result['delivery_actual'] = '已交付货物'
    # 约定付款时间/方式
    if not result.get('payment_due'):
        m = re.search(r'(?:应于|于)\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)[^，,。；;\n]{0,10}?(?:前)?\s*(?:付清|支付|付款)', source)
        if m:
            result['payment_due'] = re.sub(r'\s', '', m.group(1)) + '前付清'
    # 违约金约定（只匹配到"按日万分之X"等利率本身，不吃后面"，自2025..."尾巴）
    if not result.get('penalty_agreed'):
        m = re.search(r'(按\s*(?:日\s*)?万分之\s*[一二三四五六七八九十\d]+|按\s*月利率\s*\d+(?:\.\d+)?%?|按\s*年利率\s*\d+(?:\.\d+)?%)', source)
        if m:
            result['penalty_agreed'] = m.group(1)
    # 是否催告（精确短语，不吃尾巴）
    if not result.get('urged'):
        m = re.search(r'(多次发函催告|多次发函|多次催告|发函催告|多次催款)', source)
        if m:
            result['urged'] = '已催告：' + m.group(1)
        elif re.search(r'催[告款收]', source):
            result['urged'] = '已催告'


_FILLERS = {
    '民间借贷纠纷': _fill_private_lending,
    '买卖合同纠纷': _fill_sale_contract,
}


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
            # 易歧义金额字段跳过通用循环，交给 _fill_* 精确处理
            if f.key in _AMBIGUOUS_MONEY_FIELDS or f.key in _FILL_HANDLED_FIELDS:
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

    # 民间借贷兜底：借款时间取事实段首个日期；尚欠本金缺省取本金（本金通常全额未还）
    if cause == '民间借贷纠纷':
        if not result.get('loan_date'):
            md = RE_DATE.search(facts_text or all_text)
            if md:
                result['loan_date'] = re.sub(r'\s', '', md.group(0))
        if not result.get('owed_principal') and result.get('principal'):
            result['owed_principal'] = result['principal']
        if not result.get('total_claim'):
            # 合计 = 尚欠本金 + 尚欠利息（若有）
            op = _to_num(result.get('owed_principal'))
            oi = _to_num(result.get('owed_interest'))
            if op > 0:
                result['total_claim'] = _fmt_money(op + oi)

    # 买卖合同兜底：合计诉请 = 尚欠货款 + 违约金；尚欠货款缺省取 总价-已付
    if cause == '买卖合同纠纷':
        if not result.get('owed_amount'):
            tp = _to_num(result.get('total_price'))
            pa = _to_num(result.get('paid_amount'))
            if tp > 0 and pa >= 0:
                result['owed_amount'] = _fmt_money(tp - pa)
        if not result.get('total_claim'):
            oa = _to_num(result.get('owed_amount'))
            pe = _to_num(result.get('penalty_amount'))
            if oa > 0:
                result['total_claim'] = _fmt_money(oa + pe)

    # 案由专属文本/是/否/易歧义金额字段
    filler = _FILLERS.get(cause)
    if filler:
        filler(result, source)

    return result


def _to_num(s) -> float:
    """把抽取的金额串转 float，失败返回 0。"""
    if not s:
        return 0.0
    try:
        return float(str(s).replace(',', ''))
    except ValueError:
        return 0.0


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
        # 剥离"诉讼费用承担"条目，单独存放（修复渲染时与硬编码条款重复的 bug）
        claims, cost_burden = _split_cost_claim(claims)
        evidence = extract_evidence(sections['evidence'])
        facts = extract_fact_fields(sections['facts'], t, cause)

        return {
            'cause': cause,
            'plaintiff': plaintiff,
            'defendant': defendant,
            'claims': claims,
            'cost_burden': cost_burden,   # 诉讼费条款；空则由渲染器补默认
            'evidence': evidence,
            'facts': facts,
            'sections': sections,
            'raw_text': t,
            'source': 'rule',
        }
