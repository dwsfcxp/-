# -*- coding: utf-8 -*-
"""
Gradio Web 界面：普通起诉状 → 要素式起诉状

启动：python app.py，浏览器打开 http://127.0.0.1:7860
"""
import os

import gradio as gr

from element_complaint import convert, convert_via_court, all_causes
import config


def run(text, cause, use_llm, use_court):
    """转换回调。返回 (markdown预览, docx文件, 信息串)。"""
    if not text or not text.strip():
        return "⚠️ 请先粘贴普通起诉状文本", None, ""

    c = None if cause == "自动识别" else cause

    try:
        if use_court:
            res = convert_via_court(text, cause=c)
            info = f"✅ 法院官方格式（znszj）  案由: {res['cause']}  mbid: {res['mbid']}"
            return f"已生成法院官方格式 docx：\n`{res['output']}`", res["output"], info

        # 本地引擎：Markdown 预览 + docx 下载
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        md = convert(text, cause=c, use_llm=use_llm, fmt="markdown")
        docx_path = os.path.join(config.OUTPUT_DIR, f"要素式起诉状_{md['cause']}.docx")
        convert(text, cause=c, use_llm=use_llm, fmt="docx", out_path=docx_path)
        info = f"✅ 案由: {md['cause']}    抽取来源: {md['source']}"
        return md["output"], docx_path, info

    except Exception as e:
        return f"❌ 转换失败: {e}", None, f"❌ {e}"


CAUSE_CHOICES = ["自动识别"] + all_causes()

with gr.Blocks(title="要素式起诉状转换器", theme=gr.themes.Soft()) as app:
    gr.Markdown(
        "# 📋 普通起诉状 → 要素式起诉状 转换器\n"
        "粘贴普通（叙述式）民事起诉状，自动抽取要素并重组为法院要素式起诉状。\n\n"
        "- **本地引擎**：规则抽取 + 可选 LLM 补抽，离线可用，输出 Markdown/Word\n"
        "- **法院官方API**：调用智能诉讼平台，产出法院官方格式 docx（需联网、装 requests）"
    )

    with gr.Row():
        with gr.Column(scale=1):
            text_in = gr.Textbox(
                label="普通起诉状（输入）", lines=20,
                placeholder="在此粘贴完整的普通民事起诉状全文……",
            )
            cause_in = gr.Dropdown(CAUSE_CHOICES, value="自动识别", label="案由")
            with gr.Row():
                llm_chk = gr.Checkbox(label="启用 LLM 补抽\n(需配 GLM Key)")
                court_chk = gr.Checkbox(label="法院官方 API\n(znszj)")
            btn = gr.Button("🚀 转换为要素式起诉状", variant="primary")

        with gr.Column(scale=1):
            info_out = gr.Textbox(label="状态", interactive=False)
            md_out = gr.Markdown(label="要素式起诉状预览")
            file_out = gr.File(label="下载 Word 文档")

    gr.Examples(
        examples=[
            [open(os.path.join(config.SAMPLES_DIR, "普通起诉状_民间借贷.txt"), encoding="utf-8").read(),
             "自动识别", False, False],
            [open(os.path.join(config.SAMPLES_DIR, "普通起诉状_买卖合同.txt"), encoding="utf-8").read(),
             "自动识别", False, False],
        ],
        inputs=[text_in, cause_in, llm_chk, court_chk],
    )

    btn.click(run, [text_in, cause_in, llm_chk, court_chk], [md_out, file_out, info_out])


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
