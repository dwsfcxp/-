# 要素式起诉状转换器

> 把普通（叙述式）民事起诉状，自动转换为法院推行的**要素式起诉状**。支持**本地引擎**与**法院官方 API** 双后端。

---

## 一、这是什么

**要素式起诉状**是最高人民法院推行的一种简化、结构化的民事起诉状格式。与传统"一段一段写"的叙述式起诉状不同，它把诉状内容拆解为若干**要素**（当事人信息、诉讼请求、事实要素、证据清单等），以**表格 / 填空**形式呈现，便于法院快速立案、要素式审判、批量类案处理。

本项目做的事是**把律师/当事人写的普通叙述式起诉状，抽取并重组为要素式起诉状**。

### 📌 调研结论（含 GitHub / 网络 / 本机法穿系统）

| 来源 | 结论 |
|---|---|
| GitHub 仓库 + 代码搜索 | 搜 `要素式`/`起诉状`/`法律文书`/`要素式起诉状` —— **无任何对应开源项目**，命中均为通用 NLP 资源或无关仓库 |
| 网络检索 | 要素式起诉状仅存在于各地法院电子诉讼平台和商业法律科技产品，**全部闭源** |
| **本机法穿 FachuanHybridSystem** | ✅ **找到现成实现可参考**：①`doc_convert` 模块调用法院智能诉讼平台(znszj) API；②`execution_request_*` 系列（强制执行申请书）自研规则+LLM 抽取引擎 |

因此本项目**双管齐下**：直接移植法穿的法院 API 后端 + 借鉴法穿的规则/LLM 抽取思路自研本地引擎。详见下文「与法穿的关系」。

---

## 二、功能特性（双后端）

| 后端 | 实现 | 产出 | 适用 |
|---|---|---|---|
| **本地引擎**（默认） | 规则抽取（正则）+ 可选 LLM 补抽（智谱GLM） | 要素式 Word / Markdown / 文本 | 离线、可控、可定制 |
| **法院官方 API**（`--court`） | 移植法穿，调用智能诉讼平台 | **法院官方格式 docx** | 需联网，格式最权威 |

- ✅ **7 大常见民事案由**：民间借贷、买卖合同、物业服务、金融借款、信用卡、劳动争议、离婚
- ✅ 规则抽取精确字段：金额（含"万元"换算）、日期、身份证号、手机号、银行账号、统一社会信用代码
- ✅ 自然人 + 法人单位当事人识别
- ✅ 法院平台 **60+ 种文书类型**（起诉状/答辩状/申请书/调解等，含强制执行申请书）可选
- ✅ 命令行（批量）+ Gradio Web 界面（交互）

---

## 三、架构

```
                           普通起诉状.txt
                                 │
                ┌────────────────┴────────────────┐
                ▼                                  ▼
        【本地引擎后端】                      【法院官方API后端】
   1. 预处理 normalize()                 移植法穿 ZnszjClient：
   2. 案由识别 detect_cause()             认证3步 → 转换4步
   3. 要素抽取                           (uploadOriginQsz→text2model
      ├ 规则 RuleExtractor               →saveAndGetDownloadUrl→download)
      └ LLM  LLMExtractor(可选)                │
   4. 模板渲染 render()                        ▼
        │                              法院官方格式 .docx
        ▼
   要素式 .docx / .md / .txt
```

---

## 四、快速开始

### 1. 安装

```bash
cd 要素式起诉状转换器
pip install -r requirements.txt
```

### 2. 本地引擎（默认，离线）

```bash
# Markdown 输出到终端
python cli.py samples/普通起诉状_民间借贷.txt

# 输出 Word（到 output/ 目录）
python cli.py samples/普通起诉状_民间借贷.txt --format docx

# 指定案由
python cli.py samples/普通起诉状_民间借贷.txt --cause 民间借贷纠纷

# 启用 LLM 补抽（需先配置 GLM API Key）
python cli.py samples/普通起诉状_民间借贷.txt --use-llm
```

### 3. 法院官方后端（需联网 + requests）

```bash
# 调用智能诉讼平台，产出法院官方格式 docx
python cli.py samples/普通起诉状_民间借贷.txt --court
```

### 4. Web 界面

```bash
python app.py      # 或双击 run.bat
# 浏览器打开 http://127.0.0.1:7860
```

界面里粘贴普通起诉状，选择案由，勾选"法院官方 API"可切换后端，点击转换即可预览要素式起诉状并下载 Word。

---

## 五、与法穿 FachuanHybridSystem 的关系

本项目借鉴/移植了法穿（`C:\Users\Admin\FachuanHybridSystem`）的两套要素式技术：

| 法穿原模块 | 本项目对应 | 借鉴点 |
|---|---|---|
| `apps/doc_convert/services/znszj_private/znszj_client.py` | `element_complaint/znszj/znszj_client.py` | **直接移植**：三步认证 + 四步转换调用智能诉讼平台 |
| `apps/doc_convert/constants.py`（MBID_DEFINITIONS） | `element_complaint/znszj/mbid_constants.py` | **直接移植**：60+ 文书类型 mbid 编码 |
| `documents/.../litigation/execution_request_utils.py` | `extractor.py` 的 `AMOUNT_WITH_UNIT_PATTERN`/`parse_amount_value` | 金额正则、"万元"换算 |
| `execution_request_llm_fallback.py` | `llm_extractor.py` | LLM 兜底设计：强制 JSON 输出、容错解析、**只填空不覆盖** |
| `execution_request_parser.py` 费用纳入规则 | `extractor.py` FIELD_KEYWORDS | 上下文关键词 + 金额邻近匹配 |

法穿是 Django 大型系统（带案件模型、占位符服务框架、利息计算引擎等），本项目把其中的"普通文书→要素式"核心逻辑**独立抽取**为一个零依赖的小工具，开箱即用。

---

## 六、项目结构

```
要素式起诉状转换器/
├── README.md
├── requirements.txt
├── config.py                     # 配置（GLM API、案由映射、路径）
├── cli.py                        # 命令行入口
├── app.py                        # Gradio Web 界面
├── run.bat                       # Windows 一键启动 Web
├── element_complaint/            # 核心包
│   ├── __init__.py
│   ├── schemas.py                # 7大案由的要素Schema（核心）
│   ├── extractor.py              # 规则抽取器（借鉴法穿正则）
│   ├── llm_extractor.py          # LLM语义抽取器（借鉴法穿兜底）
│   ├── pipeline.py               # 双后端转换流水线
│   ├── renderer.py               # 渲染器（Word/Markdown/文本）
│   └── znszj/                    # 法院官方API后端（移植法穿）
│       ├── __init__.py
│       ├── mbid_constants.py     # 60+文书类型 mbid
│       └── znszj_client.py       # 智能诉讼平台客户端
├── templates/                    # 7大案由要素式模板（参考）
│   ├── 民间借贷纠纷.md … 离婚纠纷.md
├── samples/                      # 示例普通起诉状
│   ├── 普通起诉状_民间借贷.txt
│   └── 普通起诉状_买卖合同.txt
└── output/                       # 转换结果输出目录
```

---

## 七、配置 LLM（可选）

规则抽取能搞定金额、日期、身份证、电话等**结构化字段**，但"事实与理由"叙述拆成要素，靠 LLM 更准。默认对接智谱 GLM（OpenAI 兼容协议）：

```bash
# Windows
setx ZHIPU_API_KEY "你的智谱API Key"
setx GLM_BASE_URL "https://open.bigmodel.cn/api/paas/v4"
```

未配置时自动回退纯规则模式。LLM 抽取遵循法穿原则：**只在规则结果为空时补抽，绝不覆盖规则已抽取的精确字段**。

---

## 八、要素是怎么定义的（民间借贷为例）

| 要素类别 | 字段 |
|---|---|
| 当事人 | 姓名/名称、性别、出生日期、民族、身份证号/统一社会信用代码、住所、电话 |
| 借款事实 | 借款时间、本金金额、交付方式、收款账户 |
| 利息与期限 | 是否约定利息、利率、还款期限、是否到期 |
| 担保与书证 | 担保/抵押、借条/借款合同 |
| 履行情况 | 已还本金、已付利息、催讨情况 |
| 尚欠金额 | 尚欠本金、尚欠利息、合计诉请 |
| 证据清单 | 证据名称、形式、证明对象、来源 |

各案由要素全定义在 `element_complaint/schemas.py`，可自行增删。

---

## 九、已验证（冒烟测试）

用两个示例诉状实测，规则模式抽取结果：

```
民间借贷纠纷  原告张三/被告李四  本金100000 利率12% 尚欠本金100000 合计129000 借款日2023.1.1  3项请求3份证据
买卖合同纠纷  原告北京华盛贸易有限公司/被告上海宏达商贸有限公司  总价800000 尚欠货款500000 违约金150000 合计650000  4份证据
```

均正确输出 Markdown 与 Word（含 7 个要素表格）。

---

## 十、局限性

- 规则抽取依赖正则，格式极不规范的手写体诉状可能漏抽——LLM 模式可缓解。
- znszj 法院后端依赖外部平台（广东肇庆法院智能诉讼服务），可用性受平台限制。
- 法人名称、复杂多主体（多个被告/第三人）抽取以正则为主，建议开 LLM。
- 后续可加：批量 Excel、对接法院电子诉讼平台、OCR 识别纸质诉状、利息计算（法穿 `execution_request_interest.py` 可进一步移植）。

---

## 十一、免责声明

本工具生成的要素式起诉状供**参考、起草辅助**之用，不构成法律意见。正式提交法院前，请由执业律师核对当事人信息、诉讼请求金额、事实陈述的准确性。

---

*技术栈：Python 3.9+ · python-docx · Gradio · requests · 智谱GLM（可选）*
*参考：法穿 FachuanHybridSystem · GitHub 无现成开源实现*
