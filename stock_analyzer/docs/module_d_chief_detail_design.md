# 模块D：首席分析师（最终综合判定）— 详细设计

## 一、模块概述

### 1.1 定位

模块D是 `stock_analyzer` 的收口模块，负责将模块A（AKShare结构化数据）、模块B（网络深度研究）、模块C（月K技术分析）三份报告综合为一份最终投资结论。

核心职责：

- 给出五个维度的分项评分（技术面、基本面、估值、资金面、情绪面）
- 给出非线性综合总分（0-10，不是简单均值）
- 给出三个时间窗口建议（1个月、6个月、1年）
- 输出最终投资分析报告（目标 800-1200 字，硬上限 2000 字符）

非职责：

- 不负责重新抓取数据
- 不负责替代 A/B/C 的细分分析逻辑
- 不做复杂多Agent辩论编排（仅单Agent综合）

### 1.2 输入输出

输入（代码层）：

- `AKShareData`（来自 `stock_analyzer/module_a_models.py`）
- `WebResearchResult`（来自 `stock_analyzer/models.py`）
- `TechnicalAnalysisResult`（来自 `stock_analyzer/module_c_models.py`）

输出（代码层）：

- `FinalReport`（新增于 `stock_analyzer/module_d_models.py`）

输出（文件层）：

- 项目根目录输出：`/opt/fin_analysis/output/{symbol}_final_report.json`
- 相对路径写法：`output/{symbol}_final_report.json`（以项目根目录为基准）

### 1.3 技术选型

与 A/B/C 保持一致：

- Agent 框架：Microsoft Agent Framework（`agent-framework==1.0.0b260130`）
- LLM 接入：DashScope OpenAI Compatible（复用 `llm_client.py`）
- 数据校验：Pydantic v2
- 编排方式：纯 Python + `asyncio`（不使用 MAF Builder）

版本来源：项目根目录 `pyproject.toml`

### 1.4 设计原则

- 强约束输出：必须严格匹配 `FinalReport` Schema
- 非线性决策：严重风险可显著拉低总分
- 可解释性：每个维度必须给出简明解释
- 低耦合：模块D只消费 A/B/C 标准输出，不依赖其内部实现细节
- 失败可诊断：输入缺失、字段异常、模型输出异常需可定位

## 二、架构设计

### 2.1 流程总览

```text
AKShareData + WebResearchResult + TechnicalAnalysisResult
                    |
                    v
         输入校验 + 全量数据格式对齐
                    |
                    v
         组装 Chief Agent Prompt（默认全量，不做截断）
                    |
                    v
            Chief Analyst ChatAgent 推理
                    |
                    v
          Pydantic 严格校验 LLMChiefOutput
                    |
                    v
        业务规则校验（validate_business_rules）
                    |
                    v
          注入 meta 并组装 FinalReport
                    |
      +-------------+-------------+
      |                           |
      v                           v
  返回 FinalReport         dump_final_report_json()
                                   |
                                   v
          /opt/fin_analysis/output/{symbol}_final_report.json
```

### 2.2 建议文件结构

```text
fin_analysis/
├── output/                     # 统一结果输出目录（与模块A/B/C一致）
└── stock_analyzer/
    ├── module_d_models.py      # 模块D输出模型
    ├── module_d_chief.py       # 模块D主流程
    ├── run_module_d.py         # 模块D独立运行脚本
    ├── prompts.py              # 新增 CHIEF_ANALYST_SYSTEM_PROMPT
    ├── agents.py               # 新增 create_chief_agent()
    ├── exceptions.py           # 新增 ChiefInputError/ChiefAnalysisError
    └── docs/module_d_chief_detail_design.md
```

### 2.3 与 MAF 的关系

本模块对 MAF 的使用方式：

- 使用 `ChatAgent` 封装首席分析师
- 复用 `OpenAIChatClient`
- 复用结构化输出（JSON + Pydantic）策略

本模块不使用：

- `ConcurrentBuilder`
- `SequentialBuilder`
- `GroupChat`
- `HandoffBuilder`

原因：模块D本质是单Agent综合判断，不存在多Agent会话编排需求。

## 三、配置设计（复用 config.py）

### 3.1 新增配置项

建议在 `stock_analyzer/config.py` 添加：

```python
# ============================================================
# Module D: chief analyst config
# ============================================================

# LLM model used by chief analyst
MODEL_CHIEF_AGENT: str = os.getenv("MODEL_CHIEF_AGENT", "qwen-plus")

# Total context soft guard (0 means disabled / no limit)
CHIEF_INPUT_MAX_CHARS_TOTAL: int = int(
    os.getenv("CHIEF_INPUT_MAX_CHARS_TOTAL", "0")
)

# Retry times when chief agent output fails validation
CHIEF_OUTPUT_RETRIES: int = int(os.getenv("CHIEF_OUTPUT_RETRIES", "1"))
```

### 3.2 配置说明

- `MODEL_CHIEF_AGENT`：可与 B/C 解耦，后续单独切换模型
- `CHIEF_INPUT_MAX_CHARS_TOTAL`：总输入保护开关，默认 `0` 表示不限制（全量投喂）
- `CHIEF_OUTPUT_RETRIES`：模型格式错误时允许有限重试

长上下文模型建议：

- 默认全量投喂：`CHIEF_INPUT_MAX_CHARS_TOTAL=0`
- 如需运维保护，可设置较大阈值（例如 `200000`）用于 fail-fast
- 当设置阈值时，超限策略建议为“报错退出”，不要静默截断
- 默认模型可先用 `qwen-plus`；若在超长 JSON + 否决规则场景下稳定性不足，可切换 `qwen-max` 做对照验证

## 四、数据模型设计（module_d_models.py）

### 4.1 输出模型

```python
from typing import Literal
from pydantic import BaseModel, Field


class FinalMeta(BaseModel):
    symbol: str
    name: str
    analysis_time: str


class DimensionBrief(BaseModel):
    score: float = Field(ge=0, le=10)
    brief: str = Field(max_length=80)


class DimensionScores(BaseModel):
    technical: DimensionBrief
    fundamental: DimensionBrief
    valuation: DimensionBrief
    capital_flow: DimensionBrief
    sentiment: DimensionBrief


class TimeframeAdvice(BaseModel):
    timeframe: Literal["1个月", "6个月", "1年"]
    recommendation: Literal["强烈买入", "买入", "持有", "卖出", "强烈卖出"]
    reasoning: str = Field(max_length=180)


class LLMChiefOutput(BaseModel):
    dimension_scores: DimensionScores
    overall_score: float = Field(ge=0, le=10)
    overall_confidence: Literal["高", "中", "低"]
    veto_triggered: bool = False
    veto_reason: str = ""
    score_cap: float | None = Field(default=None, ge=0, le=10)
    advice: list[TimeframeAdvice] = Field(min_length=3, max_length=3)
    report: str = Field(max_length=2000)
    key_catalysts: list[str] = Field(min_length=1, max_length=3)
    primary_risks: list[str] = Field(min_length=1, max_length=3)


class FinalReport(LLMChiefOutput):
    meta: FinalMeta
```

说明：

- 这里将 `dimension_scores` 固定为五个字段，避免 `dict[str, ...]` 带来的键名漂移
- `LLMChiefOutput` 专用于校验 LLM 原始输出（不含 `meta`）
- `overall_confidence` 用于表达“最终结论可靠性”，便于下游决策分层
- `TimeframeAdvice.reasoning`（`max_length=180`）定位为“核心理由摘要”，建议 1-2 句话
- `veto_*` 字段用于审计“是否触发一票否决逻辑”，便于回放和测试
- 当 `veto_triggered=true` 时，`veto_reason` 应提供具体理由（建议不少于 10 个字符）
- `FinalReport` 由代码基于 `LLMChiefOutput` 注入 `meta` 后构造

### 4.2 输入对象（运行时）

运行时不新增复杂输入模型，直接使用 A/B/C 的现有 Pydantic 对象，避免重复定义。

## 五、输入归一化与特征提取

### 5.1 目标

将 A/B/C 全量数据以统一格式注入 Chief Agent，最大化信息保真度，并通过提示词优先级引导模型聚焦关键证据。

### 5.2 维度映射表（评分优先级引导）

| 维度 | 核心来源 | 关键字段 |
|------|----------|----------|
| 技术面 | 模块C | `score`, `signal`, `confidence`, `trend_analysis.*`, `momentum.*`, `volume_analysis.*` |
| 基本面 | 模块A + 模块B | `financial_indicators`, `company_info`, `competitive_advantage`, `industry_outlook` |
| 估值 | 模块A + 模块B | `valuation_history`, `valuation_vs_industry`, `analyst_opinions.average_target_price` |
| 资金面 | 模块A + 模块C | `fund_flow.summary`, `sector_flow`, `northbound`, `volume_analysis` |
| 情绪面 | 模块B | `news_summary`, `risk_events`, `analyst_opinions` |

### 5.3 关键实现策略

核心原则：全量投喂，不做业务字段裁剪。

推荐处理顺序：

1. 读取 A/B/C 完整 Pydantic 对象并 `model_dump()`
2. 仅清理极少数系统级噪声字段（如内部追踪 ID；业务字段不删）
3. 进行格式对齐（稳定 key 顺序、统一标签分段）
4. 将三份 JSON 原文直接注入 Prompt（不做字段筛选/不做静默截断）
5. 若启用 `CHIEF_INPUT_MAX_CHARS_TOTAL > 0` 且超限，则 fail-fast 报错

格式建议：

- 使用 `json.dumps(..., ensure_ascii=False, indent=2)` 生成可读 JSON
- 使用明确分段标签：`<akshare_data>`, `<web_research>`, `<technical_analysis>`
- 保留 `data_quality_report` 作为“输入质量证据”，不替代原始数据

### 5.4 建议函数

```python
def build_chief_context(
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> dict:
    """Build full-fidelity, format-aligned context from A/B/C outputs."""
```

建议输出结构（示意）：

```python
{
  "akshare_data_full": {...},      # 模块A全量
  "web_research_full": {...},      # 模块B全量
  "technical_analysis_full": {...},# 模块C全量
  "data_quality_report": {
    "module_a_success_ratio": "10/12",
    "module_b_search_confidence": "中",
    "module_b_is_fallback": False,
    "module_c_confidence": 0.68,
    "module_c_warnings_top": ["样本区间不足60月，长期趋势可靠性受限"],
    "overall_data_gaps": ["行业景气度前瞻证据不足"]
  },
}
```

说明：

- `data_quality_report` 仅用于给 `overall_confidence` 提供证据，不替代 A/B/C 全量原文
- 若模型支持超长上下文，默认使用全量投喂策略

### 5.5 `overall_confidence` 决策规则（建议）

建议采用“LLM最终决策，代码提供证据并做校验保护”的方式：

1. 决策权归属：
   - `overall_confidence` 由 Chief Agent 最终输出（高/中/低）
   - 代码层不常规覆盖该字段，避免与 `report` 叙事冲突
2. 证据输入：
   - 在 `build_chief_context` 中生成 `data_quality_report`，显式提供：
     - 模块A：`successful_topics / 12`
     - 模块B：`search_confidence`、是否 fallback
     - 模块C：`confidence`、关键 warning
3. 代码层职责：
   - 校验 `overall_confidence` 枚举合法
   - 仅在硬失败场景触发保护（如关键输入缺失导致无法可信评估时强制降级或报错）
4. 一致性要求：
   - 若 `overall_confidence = "低"`，`report` 必须明确主要不确定性来源
   - 若 `overall_confidence = "低"`，每条 `advice.reasoning` 建议以“（基于有限证据）”开头
   - 若 `overall_confidence = "高"`，`report` 仍需说明信息盲区与边界条件

## 六、核心流程设计（module_d_chief.py）

### 6.1 对外入口

```python
async def run_chief_analysis(
    symbol: str,
    name: str,
    akshare_data: AKShareData,
    web_research: WebResearchResult,
    technical_analysis: TechnicalAnalysisResult,
) -> FinalReport:
    """Run chief analyst workflow and return validated FinalReport."""
```

### 6.2 主流程步骤

1. 输入对象类型校验（确保是 A/B/C 的模型实例）
2. 构建全量上下文（格式对齐 + 分段标签）
3. 创建 Chief Agent（`create_chief_agent`）
4. 调用 LLM 并解析为 `LLMChiefOutput`（含重试）
5. 执行业务规则校验（`validate_business_rules(output)`）
6. 注入 `meta.analysis_time`，组装 `FinalReport`
7. 返回结构化结果

#### 6.2.1 LLM 调用实现草图

为避免实现歧义，建议在 `module_d_chief.py` 明确复用现有辅助函数：

```python
llm_output = await call_agent_with_model(
    agent=chief_agent,
    message=user_message,
    model_cls=LLMChiefOutput,
)
```

说明：

- `call_agent_with_model` 来源：`stock_analyzer.llm_helpers`
- 该函数负责：`ChatAgent.run` 调用 + JSON 提取 + Pydantic 解析
- 因此集成测试可稳定 mock `stock_analyzer.module_d_chief.call_agent_with_model`

### 6.3 业务规则校验函数（关键）

建议在 `module_d_chief.py` 显式定义：

```python
def validate_business_rules(output: LLMChiefOutput) -> None:
    """Deterministic business rule validation after pydantic parsing."""
    if output.veto_triggered and output.score_cap is None:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=true but score_cap is None"
        )
    if output.veto_triggered and len(output.veto_reason.strip()) < 10:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=true but veto_reason is too short"
        )
    if (not output.veto_triggered) and output.score_cap is not None:
        raise ChiefAnalysisError(
            "Business rule violation: veto_triggered=false but score_cap is not None"
        )
    if (
        output.veto_triggered
        and output.overall_score > output.score_cap
    ):
        raise ChiefAnalysisError(
            "Business rule violation: "
            f"veto_triggered=true but overall_score={output.overall_score} "
            f"> score_cap={output.score_cap}"
        )
```

执行时机：

- 在 `LLMChiefOutput` Pydantic 校验通过后立即执行
- 若抛错，复用现有重试机制（视为“结果无效”）

### 6.4 JSON 序列化函数

```python
def dump_final_report_json(result: FinalReport) -> str:
    """Serialize final report with meta first for readability."""
```

与模块C、模块B保持一致，便于下游处理。

## 七、Agent 与 Prompt 设计

### 7.1 Agent 工厂（agents.py）

新增：

```python
def create_chief_agent(chat_client: OpenAIChatClient) -> ChatAgent:
    return ChatAgent(
        chat_client=chat_client,
        name="chief_analyst",
        instructions=CHIEF_ANALYST_SYSTEM_PROMPT,
        default_options={
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )
```

### 7.2 System Prompt（prompts.py）

新增 `CHIEF_ANALYST_SYSTEM_PROMPT`，关键约束：

- 必须输出严格 JSON，不允许 Markdown
- `overall_score` 不是分项均值
- 必须覆盖五个分项评分
- 必须输出 1个月/6个月/1年三条建议
- 必须列出关键催化剂与主要风险
- 必须输出 `overall_confidence`（高/中/低）
- 每条 `advice.reasoning` 必须为 1-2 句摘要（<=180 字符）；长篇论述统一写入 `report`
- 若 `overall_confidence` 为“低”，每条 `advice.reasoning` 建议以“（基于有限证据）”开头，体现证据边界
- `report` 字段目标长度 800-1200 字，最大不超过 2000 字符（按字符数，不是 token 数）
- 必须执行“否决规则（Veto Power）”，当触发红线风险时对 `overall_score` 施加硬上限
- `report` 末尾必须增加“数据可信度声明”小节，说明 A/B/C 输入质量对结论的影响
- 必须基于 `<data_quality_report>` 对输入质量做综合判断后输出 `overall_confidence`
- 你将收到 A/B/C 的全量原始数据；除摘要字段外，必须主动挖掘细粒度证据
- 在给出各维度评分时，必须遵循优先级：
  - 基本面：优先查看模块A财务与经营数据，其次模块B行业/竞争信息
  - 估值：优先查看模块A估值历史分位与行业对比，再参考模块B机构目标价
  - 技术面：优先查看模块C结构化指标与结论
- “数据可信度声明”必须至少引用 `data_quality_report` 中 3 个具体指标（示例：`module_a_success_ratio`、`module_b_search_confidence`、`module_c_confidence`），并给出与 `overall_confidence` 一致的结论

建议在 Prompt 中加入明确硬规则（示例）：

```text
否决规则（硬约束）：
1) 若存在退市风险、重大财务造假嫌疑、持续经营重大不确定性三者任一项：
   overall_score 不得超过 3.0
2) 若存在重大监管处罚且对主营业务产生实质影响：
   overall_score 不得超过 4.0
3) 若存在重大诉讼/债务违约风险且可能影响现金流安全：
   overall_score 不得超过 4.5
4) 若未触发上述红线，方可按常规综合评估给分
```

建议要求模型在输出中显式给出：

- `veto_triggered`: 是否触发否决（true/false）
- `veto_reason`: 触发原因（未触发时为空字符串）
- `score_cap`: 否决上限（未触发时为 null）

并增加一致性硬约束（避免脏 JSON）：

- 仅当 `veto_triggered=true` 时允许 `score_cap` 非 null
- 当 `veto_triggered=false` 时，`score_cap` 必须为 null
- 当 `veto_triggered=true` 时，`veto_reason` 需给出具体理由（建议 >=10 字符）

### 7.3 User Message 模板

建议按四个分块注入（全量原始数据 + 数据质量报告）：

```text
请作为首席分析师，基于以下三份报告与数据质量摘要做最终综合判定：

<akshare_data>
...
</akshare_data>

<web_research>
...
</web_research>

<technical_analysis>
...
</technical_analysis>

<data_quality_report>
...
</data_quality_report>
```

## 八、异常与降级设计

### 8.1 新增异常类（exceptions.py）

```python
class ChiefInputError(Exception):
    """Module D input is missing or invalid."""


class ChiefAnalysisError(Exception):
    """Module D chief analysis failed after retries."""
```

### 8.2 处理策略

| 场景 | 策略 |
|------|------|
| A/B/C 输入对象为空 | 抛 `ChiefInputError` |
| Prompt 构造失败 | 抛 `ChiefAnalysisError` |
| LLM 输出非 JSON | 重试后仍失败则抛 `ChiefAnalysisError` |
| Pydantic 校验失败 | 重试后仍失败则抛 `ChiefAnalysisError` |
| `veto_triggered=true` 且 `score_cap is None` | 判定结果无效，触发一次重试；重试失败抛 `ChiefAnalysisError` |
| `veto_triggered=true` 但 `veto_reason` 为空或少于10字符 | 判定结果无效，触发一次重试；重试失败抛 `ChiefAnalysisError` |
| `veto_triggered=false` 但 `score_cap` 非空 | 判定结果无效，触发一次重试；重试失败抛 `ChiefAnalysisError` |
| `validate_business_rules()` 抛业务规则异常（如 veto 分数越界） | 判定结果无效，触发一次重试；重试失败抛 `ChiefAnalysisError` |

### 8.3 为什么不生成“伪降级报告”

模块D是最终结论模块，若强行输出伪报告，风险高于收益。默认策略为“失败即显式报错”，由上游编排决定是否回退到“仅输出 A/B/C 分报告”。

## 九、运行脚本设计（run_module_d.py）

### 9.1 CLI 约束

建议与当前 runner 规范一致：强制传参，不给默认值。

```bash
.venv/bin/python3 stock_analyzer/run_module_d.py \
  <symbol> <name> <akshare_json_path> <web_json_path> <technical_json_path>
```

### 9.2 行为

- 读取三个 JSON 文件
- 反序列化为 A/B/C Pydantic 模型
- 调用 `run_chief_analysis()`
- 打印最终 JSON
- 写入项目根目录 `output/{symbol}_final_report.json`

## 十、测试设计

### 10.1 单元测试

建议新增 `tests/test_module_d_chief.py`，覆盖：

- `build_chief_context()` 全量拼装与分段标签正确性
- `FinalReport` schema 校验边界
- `validate_business_rules()`：`veto_triggered=true` 且 `score_cap is None` 时抛错
- `validate_business_rules()`：`veto_triggered=true` 且 `veto_reason` 少于10字符时抛错
- `validate_business_rules()`：`veto_triggered=false` 但 `score_cap` 非空时抛错
- `validate_business_rules()`：`veto_triggered=true` 且 `overall_score > score_cap` 时抛错
- 非法建议枚举值能被拦截
- `dump_final_report_json()` 输出结构正确
- `run_chief_analysis()` 在业务规则校验失败时触发重试/失败

### 10.2 集成测试（Mock LLM）

- Mock `stock_analyzer.module_d_chief.call_agent_with_model`，返回合法 `LLMChiefOutput`
- 验证 `run_chief_analysis()` 能注入 `meta.analysis_time`
- 验证 `LLMChiefOutput -> FinalReport` 组装流程正确
- 验证输出文件名与保存逻辑正确

### 10.3 端到端测试（可选）

- 使用固定样本 `A/B/C` JSON 快照
- 跑完整 D 流程，校验输出稳定性（字段齐全、分数范围合法）

## 十一、实现顺序建议

1. 新增 `module_d_models.py`
2. 在 `prompts.py` 增加 `CHIEF_ANALYST_SYSTEM_PROMPT`
3. 在 `agents.py` 增加 `create_chief_agent()`
4. 在 `config.py` 增加 D 模块配置项
5. 实现 `module_d_chief.py` 主流程与序列化函数
6. 实现 `run_module_d.py`
7. 补充单测与集成测试

## 十二、与概要设计的一致性检查

与 `stock_analyzer/docs/stock-analysis-design-v3.1.md` 对齐项：

- 模块D是最终综合判定模块
- 输出五个维度分项评分 + 综合总分 + 三个时间窗口建议
- 读取模块C嵌套结构字段（`trend_analysis.*`, `momentum.*`, `key_levels.*`）
- 使用 MAF ChatAgent，不引入 Builder 类编排

本详细设计补充项：

- 全量投喂策略（默认不限制，可选 fail-fast 保护）
- 强约束模型与错误处理
- 可执行脚本规范（强制参数、统一输出文件）
