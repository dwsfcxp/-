# -*- coding: utf-8 -*-
"""
znszj（智能诉讼）法院官方要素式转换客户端
移植自法穿 FachuanHybridSystem/backend/apps/doc_convert/services/znszj_private/znszj_client.py

调用广东肇庆法院智能诉讼服务平台公开API，把传统文书转成【法院官方格式的要素式 docx】。

认证流程（3步）：
  1. POST gdzqfy.gov.cn/api/utils/getscwsurl → signatureCode
  2. POST znszj-touch/api/v1/pcqsz/authentication → token + mac
  3. POST znszj-touch/touch/getCodeByMac → sbbs

转换流程（4步）：
  1. POST uploadOriginQsz（仅 mac，上传文书提取文本）
  2. POST text2model（token+mac，文本→结构化要素）
  3. POST saveAndGetDownloadUrl（token+mac，→ 下载链接）
  4. GET  download/docx（token+mac，→ docx 字节）

依赖：requests（requirements.txt 已含）。平台证书与本地代理可能冲突，故 verify=False。
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse, parse_qs

# requests 懒加载：未安装时只要不调用本客户端即可（不影响纯规则模式）
logger = logging.getLogger(__name__)


def _require_requests():
    try:
        import requests  # noqa: WPS433
        return requests
    except ImportError as exc:
        raise ZnszjError(
            "使用法院官方 API 后端需要 requests 库，请运行: pip install requests"
        ) from exc

GDZQFY_URL = "https://www.gdzqfy.gov.cn/api/utils/getscwsurl"
ZNSZJ_BASE = "https://wxfxpg.susong51.com/znszj-touch"
TIMEOUT = 60


class ZnszjError(Exception):
    """znszj 调用异常"""


def _session():
    """构造 session：自动用系统代理、跳过 SSL 验证（平台证书链常被代理 MITM）。"""
    requests = _require_requests()
    s = requests.Session()
    s.verify = False
    return s


class ZnszjClient:
    """znszj 要素式转换客户端（法院官方格式）。"""

    def convert_document(self, *, file_content: bytes, filename: str, mbid: str) -> bytes:
        """完整转换流程，返回法院官方格式的 .docx 字节。"""
        auth = self._authenticate()
        return self._run_conversion(
            file_content=file_content, filename=filename, mbid=mbid,
            token=auth["token"], mac=auth["mac"], sbbs=auth["sbbs"],
        )

    def _authenticate(self) -> dict[str, str]:
        with _session() as s:
            # Step 1: signatureCode
            r1 = s.post(GDZQFY_URL, timeout=TIMEOUT)
            r1.raise_for_status()
            d1 = r1.json()
            if d1.get("code") != "200":
                raise ZnszjError(f"getscwsurl 失败: {d1}")
            auth_url: str = d1["data"]
            signature_code = auth_url.split("signatureCode=")[1]

            # Step 2: token + mac
            r2 = s.post(
                f"{ZNSZJ_BASE}/api/v1/pcqsz/authentication",
                json={"signatureCode": signature_code, "sessionId": "", "mbid": ""},
                timeout=TIMEOUT,
            )
            r2.raise_for_status()
            d2 = r2.json()
            if not d2.get("success"):
                raise ZnszjError(f"authentication 失败: {d2}")
            mac, token = d2["data"]["mac"], d2["data"]["token"]

            # Step 3: sbbs
            r3 = s.post(f"{ZNSZJ_BASE}/touch/getCodeByMac", params={"mac": mac}, timeout=TIMEOUT)
            r3.raise_for_status()
            d3 = r3.json()
            if not d3.get("success"):
                raise ZnszjError(f"getCodeByMac 失败: {d3}")
            sbbs = d3["code"]

        logger.info("znszj 认证成功")
        return {"token": token, "mac": mac, "sbbs": sbbs}

    def _run_conversion(self, *, file_content: bytes, filename: str, mbid: str,
                        token: str, mac: str, sbbs: str) -> bytes:
        headers = {"token": token, "mac": mac}
        with _session() as s:
            # Step 1: 上传传统文书，提取纯文本
            r1 = s.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/uploadOriginQsz",
                headers={"mac": mac},
                files={"file": (filename, file_content, "application/octet-stream")},
                timeout=TIMEOUT,
            )
            r1.raise_for_status()
            d1 = r1.json()
            if not d1.get("success"):
                raise ZnszjError(f"uploadOriginQsz 失败: {d1.get('message', d1)}")
            extracted_text: str = d1["data"]

            # Step 2: 文本 → 结构化要素
            r2 = s.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/text2model",
                headers=headers,
                json={"text": extracted_text, "mbid": mbid},
                timeout=TIMEOUT,
            )
            r2.raise_for_status()
            d2 = r2.json()
            if not d2.get("success"):
                raise ZnszjError(f"text2model 失败: {d2.get('message', d2)}")
            structured_data = d2["data"]

            # Step 3: 保存并获取下载链接
            r3 = s.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/saveAndGetDownloadUrl",
                headers=headers,
                json={"mbid": mbid, "data": structured_data, "sbbs": sbbs},
                timeout=TIMEOUT,
            )
            r3.raise_for_status()
            d3 = r3.json()
            if not d3.get("success"):
                raise ZnszjError(f"saveAndGetDownloadUrl 失败: {d3.get('message', d3)}")
            download_rel: str = d3["data"]

            # Step 4: 下载 docx
            parsed = urlparse(download_rel)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            r4 = s.get(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/download/docx",
                headers=headers, params=params, timeout=TIMEOUT,
            )
            r4.raise_for_status()
            logger.info("znszj 下载成功 mbid=%s", mbid)
            return r4.content
