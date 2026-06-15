# -*- coding: utf-8 -*-
"""
Gradio Web 界面：普通起诉状/申请书 → 要素式

启动：python app.py，浏览器打开 http://127.0.0.1:7860
桌面应用：python desktop_app.py（pywebview 包装成本地窗口）
"""
import os
import subprocess
from datetime import date, datetime

import gradio as gr

from element_complaint import convert, convert_via_court, convert_application, all_causes
import config

PHONE_TARGET = "z-fold7"   # Tailscale 手机设备名（见 send-to-phone skill）


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def run(text, doc_type, cause, use_llm, use_court, cutoff_str):
    """转换回调。返回 (markdown预览, docx文件, 信息串, 最近docx路径)。"""
    if not text or not text.strip():
        return "⚠️ 请先粘贴文书文本", None, "⚠️ 未输入", ""

    c = None if cause == "自动识别" else cause

    try:
        if doc_type == "强制执行申请书":
            cutoff = None
            if cutoff_str and cutoff_str.strip():
                try:
                    y, m, d = cutoff_str.strip().split('-')
                    cutoff = date(int(y), int(m), int(d))
                except Exception:
                    return "⚠️ 截止日格式应为 YYYY-MM-DD", None, "⚠️ 截止日格式错误", ""
            os.makedirs(config.OUTPUT_DIR, exist_ok=True)
            md = convert_application(text, fmt="markdown", cutoff_date=cutoff)
            docx_path = os.path.join(config.OUTPUT_DIR, "要素式强制执行申请书.docx")
            convert_application(text, fmt="docx", out_path=docx_path, cutoff_date=cutoff)
            comp = md["computation"]
            total = comp.structured_params.get("total")
            warn_n = len(comp.warnings)
            info = f"✅ 强制执行申请书  合计:{total}元" + (f"  ⚠️{warn_n}条提示" if warn_n else "")
            return md["output"], docx_path, info, docx_path

        if use_court:
            res = convert_via_court(text, cause=c)
            info = f"✅ 法院官方格式（znszj）  案由: {res['cause']}  mbid: {res['mbid']}"
            return f"已生成法院官方格式 docx：\n`{res['output']}`", res["output"], info, res["output"]

        # 民事起诉状：本地引擎
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        md = convert(text, cause=c, use_llm=use_llm, fmt="markdown")
        docx_path = os.path.join(config.OUTPUT_DIR, f"要素式起诉状_{md['cause']}.docx")
        convert(text, cause=c, use_llm=use_llm, fmt="docx", out_path=docx_path)
        info = f"✅ 案由: {md['cause']}    抽取来源: {md['source']}"
        return md["output"], docx_path, info, docx_path

    except Exception as e:
        return f"❌ 转换失败: {e}", None, f"❌ {e}", ""


def send_wechat(docx_path):
    """把最近生成的 docx 通过 Tailscale 发到手机，由手机端转发微信。"""
    if not docx_path or not os.path.exists(docx_path):
        return "⚠️ 没有可发送的文件，请先点【转换】生成文书"
    try:
        r = subprocess.run(
            ["tailscale", "file", "cp", docx_path, f"{PHONE_TARGET}:"],
            capture_output=True, text=True, timeout=90,
        )
    except FileNotFoundError:
        return "❌ 未找到 tailscale 命令，请确认 Tailscale 已安装并在 PATH"
    except subprocess.TimeoutExpired:
        return "❌ 发送超时（手机可能离线）"
    if r.returncode == 0:
        name = os.path.basename(docx_path)
        return f"✅ 已通过 Tailscale 发送到手机（{PHONE_TARGET}）\n文件：{name}\n📱 手机下拉通知栏接收 → 用微信打开/转发"
    return f"❌ 发送失败：{r.stderr.strip() or r.stdout.strip() or '未知错误'}"


CAUSE_CHOICES = ["自动识别"] + all_causes()
DOC_TYPES = ["民事起诉状", "强制执行申请书"]

with gr.Blocks(title="要素式文书转换器", theme=gr.themes.Soft()) as app:
    last_docx = gr.State(value="")

    gr.Markdown(
        "# 📋 普通文书 → 要素式 转换器\n"
        "粘贴普通（叙述式）**民事起诉状** 或 **强制执行申请书**，自动转换为法院要素式文书，可下载 Word 或一键发到手机微信。\n\n"
        "- **民事起诉状**：规则抽取 + 可选 LLM 补抽 / 法院官方 API\n"
        "- **强制执行申请书**：移植自法穿 execution_request 引擎（金额/利息/费用解析 + 利息计算）"
    )

    with gr.Row():
        with gr.Column(scale=1):
            doc_type_in = gr.Radio(DOC_TYPES, value="民事起诉状", label="文书类型")
            text_in = gr.Textbox(
                label="普通文书（输入）", lines=18,
                placeholder="在此粘贴完整的普通民事起诉状 或 强制执行申请书全文……",
            )
            cause_in = gr.Dropdown(CAUSE_CHOICES, value="自动识别", label="案由（起诉状用）")
            with gr.Row():
                llm_chk = gr.Checkbox(label="启用 LLM 补抽\n(起诉状,需GLM)")
                court_chk = gr.Checkbox(label="法院官方 API\n(znszj)")
            cutoff_in = gr.Textbox(value=_today_str(), label="利息截止日 YYYY-MM-DD（执行申请书用）")
            with gr.Row():
                btn = gr.Button("🚀 转换", variant="primary")
                wx_btn = gr.Button("💬 发到手机微信")

        with gr.Column(scale=1):
            info_out = gr.Textbox(label="状态", interactive=False)
            md_out = gr.Markdown(label="要素式文书预览")
            file_out = gr.File(label="下载 Word 文档")

    btn.click(run, [text_in, doc_type_in, cause_in, llm_chk, court_chk, cutoff_in],
              [md_out, file_out, info_out, last_docx])
    wx_btn.click(send_wechat, [last_docx], [info_out])

    gr.Examples(
        examples=[
            [open(os.path.join(config.SAMPLES_DIR, "普通起诉状_民间借贷.txt"), encoding="utf-8").read(),
             "民事起诉状", "自动识别", False, False, _today_str()],
            [open(os.path.join(config.SAMPLES_DIR, "普通起诉状_买卖合同.txt"), encoding="utf-8").read(),
             "民事起诉状", "自动识别", False, False, _today_str()],
            [open(os.path.join(config.SAMPLES_DIR, "普通强制执行申请书_借贷.txt"), encoding="utf-8").read(),
             "强制执行申请书", "自动识别", False, False, "2025-06-14"],
        ],
        inputs=[text_in, doc_type_in, cause_in, llm_chk, court_chk, cutoff_in],
    )


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
