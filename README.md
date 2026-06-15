# 要素式文书转换器

> 把普通（叙述式）**民事起诉状 / 强制执行申请书**，自动转换为法院推行的**要素式文书**。
> 三种入口：**桌面应用**（双击图标）· **命令行** · **Web 界面**。生成 Word 可一键发到手机微信。

---

## 一、功能

| 能力 | 说明 |
|---|---|
| 🏛 **要素式民事起诉状** | 7 大案由：民间借贷、买卖合同、物业服务、金融借款、信用卡、劳动争议、离婚 |
| ⚖️ **要素式强制执行申请书** | 移植自法穿 `execution_request` 引擎：金额/利息/费用解析 + 逾期利息计算 + 申请执行事项生成 |
| 🖥 **桌面应用** | pywebview 包装成本地窗口（双击桌面图标启动，无浏览器） |
| 💬 **发手机微信** | Tailscale 一键把生成的 Word 推到手机，手机端转发微信 |
| 🔒 **法院官方 API** | 移植法穿 znszj 客户端，产出法院官方格式 docx（需联网） |
| 📐 **表格封闭外框** | docx 表格最外层周边粗线封闭（法院文书规范），内部细线分隔 |

---

## 二、快速开始

### 0. 安装

```bash
pip install -r requirements.txt     # python-docx / gradio / pywebview / rich
```

### 1. 桌面应用（推荐，律师/当事人用）

```bash
# 双击桌面【要素式文书转换器】图标（首次运行 install_desktop.bat 创建）
# 或手动启动：
python desktop_app.py
```

弹出的窗口里：选文书类型（起诉状/申请书）→ 粘贴普通文书 → 点【转换】预览要素式 → 【下载 Word】或【💬 发到手机微信】。

### 2. 命令行

```bash
# 民事起诉状 → 要素式（Markdown / Word）
python cli.py samples/普通起诉状_民间借贷.txt --format docx

# 强制执行申请书 → 要素式（移植法穿引擎）
python cli.py samples/普通强制执行申请书_借贷.txt --execution --format docx --cutoff 2025-06-14

# 法院官方格式（znszj）
python cli.py samples/普通起诉状_民间借贷.txt --court

# 启用 LLM 补抽（需配 GLM API Key）
python cli.py samples/普通起诉状_民间借贷.txt --use-llm
```

### 3. Web 界面

```bash
python app.py      # 浏览器打开 http://127.0.0.1:7860
```

---

## 三、架构

```
                    普通文书.txt（起诉状 / 申请书）
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
    【起诉状本地引擎】   【强制执行申请书】    【法院官方API】
     RuleExtractor       execution_request      znszj
     规则+可选LLM        (移植法穿全代码)      (移植法穿)
     7案由Schema         金额/利息/费用解析      认证3步
     证据拆分            逾期利息计算            转换4步
            │                 │                 │
            └─────────────────┴─────────────────┘
                              ▼
                    renderer（表格封闭外框）
                              │
                 要素式 .docx / .md / .txt
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              桌面窗口下载         Tailscale→手机微信
```

---

## 四、强制执行申请书（沿用法穿全部代码）

`element_complaint/execution_request/` 子包**完整移植**自法穿 `FachuanHybridSystem/backend/apps/documents/services/placeholders/litigation/execution_request_*.py`：

| 法穿原文件 | 本项目 | 适配 |
|---|---|---|
| `execution_request_models.py` | 同名 | 原样（纯 dataclass） |
| `execution_request_utils.py` | 同名 | 原样（金额/Decimal/日期工具） |
| `execution_request_parser.py` | 同名 | 原样（金额/费用解析） |
| `execution_request_clause_extractor.py` | 同名 | 原样（利息分段/连带/补充/优先受偿条款） |
| `execution_request_interest.py` | 同名 | 去 Django `Case`；`InterestCalculator` 用本包实现 |
| `execution_request_text_generator.py` | 同名 | 原样（申请执行事项文本生成） |
| `execution_request_llm_fallback.py` | 同名 | Ollama 改 urllib 直连（可选） |
| `execution_request_service.py` | `adapter.py` | 重写为纯函数 `build_execution_request(main_text, ...)`，去 Case/CaseNumber |
| （法穿 finance.InterestCalculator） | `interest_calculator.py` | 独立纯 Python 实现，LPR 用内置历史表 |

**场景适配**（在 adapter 层，不改法穿原逻辑）：申请书全文里本金会重复出现（请求事项+事实理由）导致翻倍 → 众数去重；"由被申请人负担"的费用会被法穿保守规则误排除 → 扫描负担句重新纳入。

---

## 五、要素式文书表格规范

法院要素式文书的表格**最外层周边封闭**（粗线外框），内部分隔为细线。由 `renderer._apply_table_borders` 实现：

- 外圈 `top/left/bottom/right`：`sz=12`（1.5pt 粗线，封闭）
- 内部 `insideH/insideV`：`sz=4`（0.5pt 细线）

---

## 六、与法穿的关系

| 法穿原模块 | 本项目对应 | 说明 |
|---|---|---|
| `doc_convert/.../znszj_client.py` | `element_complaint/znszj/znszj_client.py` | 移植：法院官方 API |
| `doc_convert/constants.py` MBID | `znszj/mbid_constants.py` | 移植：60+ 文书类型 |
| `execution_request_*`（8 文件） | `execution_request/`（9 文件） | 全量移植 + Django 适配 |
| `execution_request_utils` 金额正则 | `extractor.py` 金额正则 | 借鉴 |

法穿是 Django 大型系统；本项目把"普通文书→要素式"核心逻辑独立为零依赖小工具，并加上桌面应用、微信分享、表格封闭渲染。

---

## 七、项目结构

```
要素式起诉状转换器/
├── desktop_app.py              # 桌面应用（pywebview 包装 Gradio）
├── install_desktop.bat         # 创建桌面快捷方式
├── app.py                      # Gradio Web 界面（文书类型切换 + 发微信）
├── cli.py                      # 命令行（诉状/申请书/法院/LLM）
├── config.py / requirements.txt
├── element_complaint/          # 核心包
│   ├── schemas.py              # 7 案由要素 Schema
│   ├── extractor.py            # 规则抽取（当事人/金额/证据/案由专属字段）
│   ├── llm_extractor.py        # LLM 语义补抽（只填空不覆盖）
│   ├── pipeline.py             # convert / convert_via_court / convert_application
│   ├── renderer.py             # 渲染（表格封闭外框 + 申请书渲染）
│   ├── znszj/                  # 法院官方 API 后端（移植法穿）
│   └── execution_request/      # 强制执行申请书引擎（全量移植法穿）
├── templates/                  # 7 案由要素式模板
├── samples/                    # 示例（诉状×2 + 强制执行申请书×1）
└── output/                     # 转换结果
```

---

## 八、已验证

| 场景 | 结果 |
|---|---|
| 民间借贷诉状 | 当事人7字段+本金10万+利率12%+尚欠10万+逾期利息2.9万+合计12.9万+交付/借条/催讨/利息要素全抽 |
| 买卖合同诉状 | 签订日2024.6.1+标的办公设备+总价80万+已付30万+尚欠50万+违约金按日万分之五+合计65万 |
| 强制执行申请书 | 本金10万+逾期利息17700(计算)+受理费2150+合计119850+加倍利息条款+文号抽取 |
| 桌面应用 | pywebview 窗口启动，7860 HTTP 200 |
| 发手机微信 | Tailscale 推送成功（退出码0），手机 z-fold7 接收 |
| 边界 | 空文本/纯空白/无关文本/空申请书 均不崩 |

---

## 九、配置 LLM（可选）

```bash
setx ZHIPU_API_KEY "你的智谱API Key"
setx GLM_BASE_URL "https://open.bigmodel.cn/api/paas/v4"
```

未配置时自动回退纯规则模式。LLM 只补抽规则未抽到的字段，不覆盖精确字段。

---

## 十、免责声明

本工具生成的要素式文书供**参考、起草辅助**之用，不构成法律意见。正式提交法院前，请由执业律师核对当事人信息、金额、利息计算、事实陈述的准确性。

---

*技术栈：Python 3.9+ · python-docx · Gradio · pywebview · requests · 智谱GLM（可选）· Tailscale（发手机）*
*参考：法穿 FachuanHybridSystem（execution_request + znszj 全量移植）*
