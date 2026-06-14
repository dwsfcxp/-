# -*- coding: utf-8 -*-
"""
LLM 语义抽取器（可选）

设计借鉴法穿 execution_request_llm_fallback.py：
  1. 规则引擎抽不到的字段，才交给 LLM 补抽 —— merge 时【只填空，不覆盖】规则结果
  2. 强制 LLM 只返回 JSON，做容错解析（支持 ```json``` 围栏、提取首个 {...}）
  3. 金额统一换算为"元"

用标准库 urllib 调智谱GLM（OpenAI 兼容协议），无需额外 SDK。
未配置 API Key 时整体跳过，回退纯规则。
"""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, Optional

import config
from .schemas import get_schema


def _build_extraction_prompt(text: str, cause: str) -> str:
    """构造抽取 prompt：把该案由的要素字段列给模型。"""
    schema = get_schema(cause)
    fact_lines = []
    if schema:
        for g in schema.fact_groups:
            for f in g.fields:
                unit = f"（单位：{f.unit}）" if f.unit else ""
                fact_lines.append(f"  - {f.key}：{f.label}{unit}；{f.hint}")
    facts_desc = "\n".join(fact_lines) if fact_lines else "  （该案由无额外事实要素）"

    return f"""你是法律文书要素抽取助手。从下面的【民事起诉状】文本中抽取要素，仅输出一个JSON对象，不要输出任何其他文字、不要markdown代码块标记。

要求：
1. 所有金额统一换算为"元"（如"5万元"=50000，"3.5万"=35000，"1,000.50元"=1000.5）。
2. 日期统一为"YYYY年MM月DD日"格式。
3. claims 为数组，一项诉讼请求一个元素（原文）。
4. evidence 为数组，每项含 name(证据名称)、purpose(证明对象)。
5. plaintiff/defendant 含：name,gender,birth,nation,id,addr,phone；若为法人单位，gender/birth/nation 留空字符串，id 填统一社会信用代码。
6. facts 为该案由专属事实要素对象，键如下，抽不到的留空字符串：
{facts_desc}

输出JSON示例：
{{"plaintiff":{{"name":"","gender":"","birth":"","nation":"","id":"","addr":"","phone":""}},"defendant":{{"name":"","gender":"","birth":"","nation":"","id":"","addr":"","phone":""}},"claims":[],"evidence":[{{"name":"","purpose":""}}],"facts":{{}}}}

【民事起诉状】：
{text[:6000]}"""


def _call_llm(prompt: str) -> Optional[str]:
    """调用智谱GLM / OpenAI兼容接口，返回模型输出文本。失败返回 None。"""
    if not config.llm_enabled():
        return None
    url = config.LLM_BASE_URL.rstrip('/') + '/chat/completions'
    body = json.dumps({
        "model": config.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data['choices'][0]['message']['content']
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
            json.JSONDecodeError, TimeoutError, ConnectionError) as e:
        print(f"[LLM] 调用失败，回退纯规则: {e}")
        return None


def _extract_json(content: str) -> Optional[dict]:
    """容错解析 JSON（借鉴法穿 _extract_json_object）。"""
    if not content:
        return None
    s = content.strip()
    # 去 ```json ... ``` 围栏
    s = re.sub(r'^```(?:json)?\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*```$', '', s.strip())
    # 提取首个 {...}
    m = re.search(r'\{.*\}', s, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def extract_with_llm(text: str, cause: str) -> Optional[dict]:
    """调 LLM 抽取，返回结构化 dict 或 None。"""
    content = _call_llm(_build_extraction_prompt(text, cause))
    return _extract_json(content) if content else None


def merge_into(result: Dict, llm_data: Dict) -> bool:
    """
    把 LLM 结果合并进规则抽取结果 —— 仅填充规则未抽到的字段（不覆盖）。
    返回是否有变化。（借鉴法穿 merge_llm_fallback 的"只填空"原则）
    """
    changed = False

    # 当事人
    for role in ('plaintiff', 'defendant'):
        party = llm_data.get(role, {})
        if not isinstance(party, dict):
            continue
        for k, v in party.items():
            if not result[role].get(k) and v:
                result[role][k] = str(v).strip()
                changed = True

    # 诉讼请求
    if not result.get('claims') and isinstance(llm_data.get('claims'), list):
        items = [str(c).strip() for c in llm_data['claims'] if str(c).strip()]
        if items:
            result['claims'] = items
            changed = True

    # 证据
    if not result.get('evidence') and isinstance(llm_data.get('evidence'), list):
        ev = []
        for e in llm_data['evidence']:
            if isinstance(e, dict):
                ev.append({
                    'name': str(e.get('name', '')).strip(),
                    'form': str(e.get('form', '')).strip(),
                    'purpose': str(e.get('purpose', '')).strip(),
                    'source': str(e.get('source', '')).strip(),
                })
        if ev:
            result['evidence'] = ev
            changed = True

    # 事实要素
    facts = llm_data.get('facts', {})
    if isinstance(facts, dict):
        for k, v in facts.items():
            if not result['facts'].get(k) and v:
                result['facts'][k] = str(v).strip()
                changed = True

    if changed:
        result['source'] = 'rule+llm'
    return changed
