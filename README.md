# 要素式文书转换器

> 普通文书 → 要素式文书。支持**民事起诉状**与**强制执行申请书**两大类，**本地引擎**与**法院官方 API** 双后端，提供命令行 / Web / **原生桌面应用**三种入口。

---

## 一、这是什么

**要素式文书**是最高人民法院推行的简化、结构化诉讼文书格式（表格化填空），便于法院快速立案、要素式审判、批量类案处理。本工具把普通叙述式文书抽取重组为要素式文书。

支持两类文书：
- **要素式起诉状**（民间借贷、买卖合同、物业服务、金融借款、信用卡、劳动争议、离婚等 7 大案由）
- **要素式强制执行申请书**（移植法穿完整引擎，含本金/5类费用/利息/LPR倍数/计息基数/抵扣顺序/加倍利息/连带责任/优先受偿等全套要素 + 利息计算）

### 📌 调研结论（含 GitHub / 网络 / 本机法穿）

| 来源 | 结论 |
|---|---|
| GitHub 仓库 + 代码搜索 | 搜 `要素式`/`起诉状`/`法律文书` —— **无任何对应开源项目** |
| 网络检索 | 要素式文书仅存在于各地法院电子诉讼平台和商业产品，**全部闭源** |
| **本机法穿 FachuanHybridSystem** | ✅ **找到现成实现可参考**：`doc_convert`(znszj法院API) + `execution_request_*`(强制执行申请书自研引擎) |

因此本项目双管齐下：移植法穿法院 API 后端 + 借鉴/移植法穿规则与强制执行引擎，做成零依赖独立工具。

---

## 二、功能特性

| 能力 | 说明 |
|---|---|
| 🏛️ **要素式起诉状** | 7 大案由要素 Schema，规则抽取 + 可选 LLM 补抽 |
| ⚖️ **强制执行申请书** | 移植法穿完整引擎：金额/利息计算/抵扣顺序/连带/优先受偿 + Ollama LLM 兜底 |
| 🌐 **法院官方后端** | 调用智能诉讼平台(znszj)，60+ 文书类型，产出法院官方格式 docx |
| 🖥️ **三种入口** | 命令行 / Gradio Web / pywebview 原生桌面应用 |
| 📄 **多格式输出** | Word(.docx) / Markdown / 纯文本 |

---

## 三、快速开始

### 1. 安装
```bash
pip install -r requirements.txt
```

### 2. 命令行
```bash
python cli.py samples/普通起诉状_民间借贷.txt                 # Markdown
python cli.py samples/普通起诉状_民间借贷.txt --format docx    # Word
python cli.py samples/普通起诉状_民间借贷.txt --use-llm        # LLM 补抽
python cli.py samples/普通起诉状_民间借贷.txt --court          # 法院官方格式
```

### 3. Web 界面
```bash
python app.py        # http://127.0.0.1:7860
```

### 4. 桌面应用（原生窗口）
```bash
install_desktop.bat    # 创建桌面快捷方式"要素式文书转换器"（仅一次）
python desktop_app.py  # 或双击桌面图标 → pywebview 窗口加载 Gradio
```

### 5. 强制执行申请书（代码调用）
```python
from element_complaint.execution_request.adapter import build_execution_request
text = open("samples/普通强制执行申请书_借贷.txt", encoding="utf-8").read()
result = build_execution_request(text)   # → ExecutionComputation(preview_text, warnings, structured_params)
print(result.preview_text)
```

---

## 四、项目结构

```
要素式起诉状转换器/
├── README.md
├── requirements.txt
├── config.py                     # 配置（GLM API、案由映射、路径）
├── cli.py                        # 命令行
├── app.py                        # Gradio Web
├── desktop_app.py                # pywebview 桌面应用
├── install_desktop.bat           # 桌面快捷方式生成
├── run.bat                       # Web 一键启动
├── element_complaint/
│   ├── schemas.py                # 7大案由要素 Schema
│   ├── extractor.py              # 起诉状规则抽取
│   ├── llm_extractor.py          # 起诉状 LLM 补抽
│   ├── pipeline.py               # 双后端流水线
│   ├── renderer.py               # 渲染(Word/MD/文本)
│   ├── znszj/                    # 法院官方API后端（移植法穿 doc_convert）
│   │   ├── mbid_constants.py     # 60+ 文书类型 mbid
│   │   └── znszj_client.py       # 智能诉讼平台客户端
│   └── execution_request/        # 强制执行申请书引擎（移植法穿 execution_request_*）
│       ├── adapter.py            # 纯函数入口(重写自法穿Django Service)
│       ├── execution_request_parser.py
│       ├── execution_request_interest.py
│       ├── execution_request_text_generator.py
│       ├── execution_request_llm_fallback.py
│       ├── execution_request_models.py
│       ├── execution_request_utils.py
│       ├── execution_request_clause_extractor.py
│       └── interest_calculator.py
├── templates/                    # 7大案由要素式模板
├── samples/                      # 示例（含强制执行申请书样本）
└── output/                       # 输出（gitignore）
```

---

## 五、与法穿 FachuanHybridSystem 的关系

| 法穿原模块 | 本项目对应 | 说明 |
|---|---|---|
| `apps/doc_convert/services/znszj_private/` | `element_complaint/znszj/` | 移植法院 API 客户端 + 60+ mbid |
| `documents/.../litigation/execution_request_*.py` | `element_complaint/execution_request/` | **完整移植**强制执行申请书引擎（8文件） |
| `execution_request_service.py`(Django) | `execution_request/adapter.py` | 重写为纯函数 `build_execution_request`，去 Django 依赖 |
| `execution_request_utils.py` 金额正则 | `extractor.py` | 起诉状复用 `AMOUNT_WITH_UNIT_PATTERN` |
| `execution_request_llm_fallback.py` | `llm_extractor.py` | LLM 兜底设计：强制JSON、容错解析、只填空不覆盖 |

法穿是 Django 大型系统；本项目把"普通文书→要素式"核心逻辑独立抽取为开箱即用的小工具。

---

## 六、配置 LLM（可选）

起诉状 LLM 补抽默认接智谱 GLM；强制执行申请书 LLM 兜底用本地 Ollama（`qwen3.5:0.8b`）。
```bash
setx ZHIPU_API_KEY "你的智谱Key"
```
未配置自动回退纯规则。LLM 遵循法穿原则：**只在规则结果为空时补抽，绝不覆盖精确字段**。

---

## 七、已验证

- 起诉状：民间借贷/买卖合同示例 → 当事人/金额/日期/利率/诉讼请求/证据全部正确抽取，Word 含 7 要素表格
- 强制执行申请书：`adapter.build_execution_request` 可导入调用
- 桌面应用：pywebview 依赖就绪

---

## 八、免责声明

本工具生成的要素式文书供**参考、起草辅助**之用，不构成法律意见。正式提交法院前，请由执业律师核对当事人信息、金额、事实陈述的准确性。

---

*技术栈：Python 3.9+ · python-docx · Gradio · pywebview · requests · 智谱GLM/Ollama（可选）*
*参考：法穿 FachuanHybridSystem · GitHub 无现成开源实现*
