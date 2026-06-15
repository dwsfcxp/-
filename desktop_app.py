# -*- coding: utf-8 -*-
"""
桌面应用：pywebview 包装 Gradio 成原生窗口。

启动：python desktop_app.py  （或双击桌面快捷方式）
- 后台线程启动 Gradio（127.0.0.1:7860，不弹浏览器）
- 主线程开 pywebview 窗口加载该地址 → 像native 应用

复用 OCR 桌面应用同款模式（见 memory/ocr-desktop-project.md）。
"""
import threading
import time
import urllib.request

import webview


def _wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def start_gradio():
    """子线程启动 Gradio 服务。"""
    import app as gradio_app
    gradio_app.app.launch(
        server_name="127.0.0.1", server_port=7860,
        inbrowser=False, prevent_thread_lock=True, show_api=False,
        allowed_paths=gradio_app.ALLOWED_PATHS,
    )


def main():
    threading.Thread(target=start_gradio, daemon=True).start()

    url = "http://127.0.0.1:7860"
    if not _wait_for_server(url):
        # Gradio 未起来，仍尝试开窗（至少能看到错误）
        pass

    webview.create_window(
        "要素式文书转换器",
        url,
        width=1320, height=880,
        min_size=(960, 640),
    )
    webview.start()   # 阻塞主线程，关窗即退出


if __name__ == "__main__":
    main()
