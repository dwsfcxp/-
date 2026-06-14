# -*- coding: utf-8 -*-
"""
渲染器：把抽取结果渲染成要素式起诉状。

三种输出：
  - render_text()     纯文本（可直接贴入法院系统/打印）
  - render_markdown() Markdown（含表格，便于预览/版本管理）
  - render_docx()     Word .docx（符合法院提交格式：宋体小四、A4）
"""

import io
from typing import Dict, List, Tuple

from .schemas import get_schema, COMMON_PARTY_GROUP_PLAINTIFF, COMMON_PARTY_GROUP_DEFENDANT


# ─────────────────────────────────────────────
# 统一数据收集：把 result 转成有序的渲染单元
# ─────────────────────────────────────────────
def _gather(result: Dict, cause: str) -> List[Tuple[str, object, str]]:
    """
    返回 [(group_name, payload, kind), ...]
    kind:
      'table'    payload = [(label, value, required), ...]
      'list'     payload = [str, ...]   （诉讼请求）
      'evidence' payload = [{name,form,purpose,source}, ...]
    """
    items: List[Tuple[str, object, str]] = []

    def _party_rows(role: str):
        group = COMMON_PARTY_GROUP_PLAINTIFF if role == 'plaintiff' else COMMON_PARTY_GROUP_DEFENDANT
        return [(f.label, result[role].get(f.key, ''), f.required) for f in group.fields]

    items.append(('原告信息', _party_rows('plaintiff'), 'table'))
    items.append(('被告信息', _party_rows('defendant'), 'table'))
    items.append(('诉讼请求', result.get('claims', []) or [], 'list'))

    schema = get_schema(cause)
    if schema:
        for g in schema.fact_groups:
            rows = []
            for f in g.fields:
                label = f"{f.label}（{f.unit}）" if f.unit else f.label
                rows.append((label, result['facts'].get(f.key, ''), f.required))
            items.append((g.name, rows, 'table'))

    items.append(('证据清单', result.get('evidence', []) or [], 'evidence'))
    return items


# ─────────────────────────────────────────────
# 纯文本
# ─────────────────────────────────────────────
def render_text(result: Dict, cause: str) -> str:
    lines = []
    lines.append("民事起诉状".center(28))
    lines.append("（要素式）".center(26))
    lines.append("")
    lines.append(f"案    由：{cause}")
    lines.append("")

    for name, payload, kind in _gather(result, cause):
        lines.append(f"【{name}】")
        if kind == 'table':
            for label, value, required in payload:
                if value:
                    lines.append(f"    {label}：{value}")
                elif required:
                    lines.append(f"    {label}：________________（待填）")
            lines.append("")
        elif kind == 'list':
            if not payload:
                lines.append("    1. ____________________________（待填）")
            else:
                for i, c in enumerate(payload, 1):
                    lines.append(f"    {i}. {c}")
            lines.append("    本案诉讼费用由被告承担。")
            lines.append("")
        elif kind == 'evidence':
            if not payload:
                lines.append("    1. ____________________________（请补充证据）")
            else:
                for i, e in enumerate(payload, 1):
                    purpose = f"（证明对象：{e.get('purpose','')}）" if e.get('purpose') else ""
                    lines.append(f"    {i}. {e.get('name','')}{purpose}")
            lines.append("")

    lines.append("此    致")
    lines.append("          ____________________人民法院")
    lines.append("")
    lines.append("                              具状人（签名/盖章）：")
    lines.append("                                  ______年______月______日")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Markdown
# ─────────────────────────────────────────────
def render_markdown(result: Dict, cause: str) -> str:
    md = []
    md.append("# 民事起诉状（要素式）\n")
    md.append(f"**案由：** {cause}\n")

    for name, payload, kind in _gather(result, cause):
        md.append(f"\n## {name}\n")
        if kind == 'table':
            md.append("| 字段 | 内容 |")
            md.append("|---|---|")
            for label, value, required in payload:
                if value:
                    md.append(f"| {label} | {value} |")
                elif required:
                    md.append(f"| {label} | _待填_ |")
        elif kind == 'list':
            if not payload:
                md.append("1. _待填_")
            else:
                for i, c in enumerate(payload, 1):
                    md.append(f"{i}. {c}")
            md.append("\n本案诉讼费用由被告承担。")
        elif kind == 'evidence':
            md.append("| 序号 | 证据名称 | 证据形式 | 证明对象 | 来源 |")
            md.append("|---|---|---|---|---|")
            if not payload:
                md.append("| 1 | _请补充_ | | | |")
            else:
                for i, e in enumerate(payload, 1):
                    md.append(f"| {i} | {e.get('name','')} | {e.get('form','')} | {e.get('purpose','')} | {e.get('source','')} |")

    md.append("\n---\n")
    md.append("此致  __________人民法院\n")
    md.append("具状人（签名/盖章）：__________   日期：____年__月__日")
    return "\n".join(md)


# ─────────────────────────────────────────────
# Word .docx
# ─────────────────────────────────────────────
def _set_cn_font(run, font_name: str, size_pt: float):
    """设置中文字体（python-docx 需显式设置 eastAsia）。"""
    from docx.shared import Pt
    from docx.oxml.ns import qn
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        from docx.oxml import OxmlElement
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:eastAsia'), font_name)


def render_docx(result: Dict, cause: str, out_path: str) -> str:
    """渲染为 Word 文档，返回保存路径。"""
    import config
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # 标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("民事起诉状（要素式）")
    _set_cn_font(r, config.DOCX_TITLE_FONT, config.DOCX_TITLE_SIZE)
    r.bold = True

    # 案由
    p = doc.add_paragraph()
    r = p.add_run(f"案由：{cause}")
    _set_cn_font(r, config.DOCX_FONT, config.DOCX_FONT_SIZE)
    r.bold = True

    for name, payload, kind in _gather(result, cause):
        # 组标题
        h = doc.add_paragraph()
        r = h.add_run(f"【{name}】")
        _set_cn_font(r, config.DOCX_HEADING_FONT, config.DOCX_HEADING_SIZE)
        r.bold = True

        if kind == 'table':
            rows = [(lbl, val, req) for lbl, val, req in payload if val or req]
            tbl = doc.add_table(rows=1 + len(rows), cols=2)
            tbl.style = 'Table Grid'
            hdr = tbl.rows[0].cells
            for cell, text in zip(hdr, ['要素', '内容']):
                cell.paragraphs[0].add_run(text).bold = True
            for i, (lbl, val, req) in enumerate(rows, 1):
                cells = tbl.rows[i].cells
                cells[0].text = lbl
                cells[1].text = val if val else ('（待填）' if req else '')
        elif kind == 'list':
            if not payload:
                p = doc.add_paragraph('1. ____________________（待填）')
            else:
                for i, c in enumerate(payload, 1):
                    doc.add_paragraph(f"{i}. {c}")
            doc.add_paragraph('本案诉讼费用由被告承担。')
        elif kind == 'evidence':
            evids = payload if payload else [{'name': '', 'form': '', 'purpose': '', 'source': ''}]
            tbl = doc.add_table(rows=1 + len(evids), cols=4)
            tbl.style = 'Table Grid'
            for cell, text in zip(tbl.rows[0].cells, ['序号', '证据名称', '证据形式', '证明对象']):
                cell.paragraphs[0].add_run(text).bold = True
            for i, e in enumerate(evids, 1):
                cells = tbl.rows[i].cells
                cells[0].text = str(i)
                cells[1].text = e.get('name', '')
                cells[2].text = e.get('form', '')
                cells[3].text = e.get('purpose', '')

        doc.add_paragraph('')   # 组间空行

    # 结尾
    doc.add_paragraph('此致')
    doc.add_paragraph('          ____________________人民法院')
    doc.add_paragraph('')
    p = doc.add_paragraph('                              具状人（签名/盖章）：')
    _set_cn_font(p.runs[0] if p.runs else p.add_run(''), config.DOCX_FONT, config.DOCX_FONT_SIZE)
    doc.add_paragraph('                                  ______年______月______日')

    doc.save(out_path)
    return out_path


def docx_bytes_of(result: Dict, cause: str) -> bytes:
    """渲染到内存 bytes（供 Web 下载，不落盘）。"""
    buf = io.BytesIO()
    import config
    from docx import Document
    # 复用 render_docx 的逻辑：先写临时路径再读 bytes 太重，这里直接写 buf
    # 为避免重复实现，临时写文件再读回
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix='.docx')
    os.close(fd)
    try:
        render_docx(result, cause, tmp)
        with open(tmp, 'rb') as f:
            return f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
