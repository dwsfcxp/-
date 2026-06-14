# -*- coding: utf-8 -*-
"""
转换流水线（双后端）：
  - convert()           本地引擎：规则抽取 + 可选LLM补抽 → 要素式文书（text/md/docx）
  - convert_via_court() 法院官方后端：调 znszj 智能诉讼平台 → 法院格式要素式 docx
"""

import os
from typing import Dict, Optional, Union

from .extractor import RuleExtractor, detect_cause
from .renderer import render_text, render_markdown, render_docx
import config


def convert(
    text: str,
    *,
    cause: Optional[str] = None,
    use_llm: bool = False,
    fmt: str = 'markdown',          # 'text' | 'markdown' | 'docx'
    out_path: Optional[str] = None,
) -> Dict:
    """
    本地引擎转换主入口。

    返回:
        {
          'cause': str,
          'result': <extractor 返回的完整结构>,
          'output': str(path 或 内容),
          'source': 'rule' | 'rule+llm',
        }
    """
    extractor = RuleExtractor()
    result = extractor.extract(text, cause=cause)
    cause = result['cause']

    if use_llm:
        try:
            from .llm_extractor import extract_with_llm, merge_into
            llm_data = extract_with_llm(result['raw_text'], cause)
            if llm_data:
                merge_into(result, llm_data)
        except Exception as e:
            print(f"[LLM] 抽取异常，已忽略: {e}")

    # 渲染
    if fmt == 'docx':
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        path = out_path or os.path.join(config.OUTPUT_DIR, f"要素式起诉状_{cause}.docx")
        render_docx(result, cause, path)
        output = path
    elif fmt == 'text':
        output = render_text(result, cause)
    else:  # markdown
        output = render_markdown(result, cause)

    return {
        'cause': cause,
        'result': result,
        'output': output,
        'source': result.get('source', 'rule'),
    }


def convert_via_court(
    text: str,
    *,
    cause: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Dict:
    """
    法院官方后端：调用 znszj 智能诉讼平台，产出法院官方格式的要素式 docx。
    需要联网（访问 gdzqfy.gov.cn / susong51.com）。

    返回:
        {'cause': str, 'mbid': str, 'output': str(path) 或 bytes, 'source': 'znszj'}
    """
    from .znszj import ZnszjClient, get_mbid_for_cause, ZnszjError

    cause = cause or detect_cause(text)
    mbid = get_mbid_for_cause(cause)
    if not mbid:
        raise ValueError(
            f"案由 [{cause}] 暂不支持法院官方转换（znszj 平台无对应模板），"
            f"请使用本地引擎 convert()，或在 znszj/mbid_constants.py 中补充 mbid。"
        )

    # 法院接口需上传文件（.docx/.doc/.pdf），把文本包装成最小 docx
    file_bytes = _wrap_text_as_docx(text)

    client = ZnszjClient()
    docx_bytes = client.convert_document(
        file_content=file_bytes, filename="起诉状.docx", mbid=mbid,
    )

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = out_path or os.path.join(config.OUTPUT_DIR, f"法院格式要素式起诉状_{cause}.docx")
    with open(path, 'wb') as f:
        f.write(docx_bytes)

    return {'cause': cause, 'mbid': mbid, 'output': path, 'source': 'znszj'}


def _wrap_text_as_docx(text: str) -> bytes:
    """把纯文本包装成最小 docx 字节流，供 znszj 上传提取。"""
    import io
    from docx import Document
    doc = Document()
    for line in (text or "").split('\n'):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
