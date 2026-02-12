# 模块C：月K线技术分析（计算 + Agent）— 详细设计

## 一、模块概述

### 1.1 定位

模块C 是 `stock_analyzer` 的技术面分析模块，负责：

1. 通过 AKShare 拉取目标股票月K线（前复权）
2. 使用 `pandas-ta` 计算技术指标（纯代码）
3. 由 Qwen LLM（通过 Microsoft Agent Framework 的 `ChatAgent`）做技术面推理与评分
4. 输出结构化 `TechnicalAnalysisResult`（Pydantic）

该模块属于 `stock_analyzer` 子模块，不单独建项目，复用现有公共组件：

- `stock_analyzer/config.py`
- `stock_analyzer/logger.py`
- `stock_analyzer/llm_client.py`
- `stock_analyzer/exceptions.py`

### 1.2 输入输出

| | 说明 |
|---|---|
| 输入 | `symbol`（6位纯数字）、`name`（股票名称） |
| 输出 | `TechnicalAnalysisResult`（Pydantic 对象） |

### 1.3 技术选型

| 组件 | 选型 | 说明 |
|---|---|---|
| Python | 3.12+ | 与项目一致（`pyproject.toml`） |
| Agent 框架 | `agent-framework==1.0.0b260130` | 与项目一致 |
| LLM | DashScope Qwen（默认 `qwen-plus`） | 通过 OpenAI 兼容接口 |
| 行情数据 | AKShare `stock_zh_a_hist` | 月K线前复权数据 |
| 技术指标 | `pandas-ta` | MA/MACD/RSI/BOLL/KDJ |
| 数据处理 | pandas | 指标计算和特征提取 |
| 校验 | Pydantic v2 | 强类型输出 |

### 1.4 设计原则

1. 计算和推理解耦：指标计算由代码完成，LLM只负责解释和评分。
2. 输入可追溯：传给 LLM 的特征全部来自可复算的指标结果。
3. 结构化优先：最终结果强制 Pydantic 校验，不接受自由文本直出。
4. 容错优先：AKShare 或 LLM失败时不崩溃，给出可解释降级结果。

### 1.5 与概要设计的一致性说明（重要）

本详细设计对 `stock-analysis-design-v3.1.md` 中模块C的扁平输出结构进行了有意升级：

1. 概要设计中的扁平字段（如 `ma_alignment`, `macd_status`）改为嵌套子模型；
2. 目的是按语义分组（趋势/动量/波动/量价/关键位），降低模块D解析歧义；
3. 模块C实现以本详细设计为准；
4. 模块D读取路径必须同步为嵌套字段路径（见第 9.3 节映射表）。

---

## 二、架构设计

### 2.1 流程总览

```
输入 symbol/name
    │
    ▼
AKShare: stock_zh_a_hist(period="monthly", adjust="qfq")
    │
    ▼
数据清洗与标准化（日期排序、数值列转float、缺失值处理）
    │
    ▼
pandas-ta计算指标（MA/MACD/RSI/BOLL/KDJ）
    │
    ▼
构造技术特征摘要 + 最近N个月明细（压缩后的JSON）
    │
    ▼
MAF ChatAgent（Qwen）推理与评分
    │
    ▼
Pydantic 校验 + 必要降级
    │
    ▼
TechnicalAnalysisResult
```

### 2.2 模块边界

| 能力 | 归属 |
|---|---|
| 获取月K线 | 模块C（AKShare） |
| 指标计算 | 模块C（纯代码） |
| 技术面解释与评分 | 模块C（Qwen + MAF） |
| 最终投资建议（跨模块综合） | 模块D（不在本模块） |

### 2.3 建议文件结构

```
stock_analyzer/
├── module_c_technical.py              # 模块C主流程（采集+计算+Agent）
├── module_c_models.py                 # 模块C Pydantic 模型
├── run_module_c.py                    # 模块C独立运行脚本（调试/回归）
├── prompts.py                         # 新增 TECHNICAL_AGENT_SYSTEM_PROMPT
├── config.py                          # 新增模块C配置项
├── exceptions.py                      # 新增模块C异常类
└── docs/
    └── module_c_technical_analysis_detail_design.md
```

---

## 三、配置设计（复用 config.py）

在 `stock_analyzer/config.py` 中新增模块C配置项：

```python
# ============================================================
# Module C: Technical analysis config
# ============================================================

# LLM model for technical analysis agent
MODEL_TECHNICAL_AGENT: str = os.getenv("MODEL_TECHNICAL_AGENT", "qwen-plus")

# AKShare monthly K-line fetch params
TECH_START_DATE: str = os.getenv("TECH_START_DATE", "20000101")
TECH_ADJUST: str = os.getenv("TECH_ADJUST", "qfq")

# How many recent months to send to LLM (控制 token)
TECH_AGENT_LOOKBACK_MONTHS: int = int(os.getenv("TECH_AGENT_LOOKBACK_MONTHS", "36"))

# Minimum months required to enter technical analysis pipeline
TECH_MIN_MONTHS: int = int(os.getenv("TECH_MIN_MONTHS", "24"))

# Minimum months required to use long-trend MA60
TECH_LONG_TREND_MIN_MONTHS: int = int(
    os.getenv("TECH_LONG_TREND_MIN_MONTHS", "60")
)

# Indicator params
TECH_MA_SHORT: int = int(os.getenv("TECH_MA_SHORT", "5"))
TECH_MA_MID: int = int(os.getenv("TECH_MA_MID", "10"))
TECH_MA_LONG: int = int(os.getenv("TECH_MA_LONG", "20"))
TECH_MA_TREND: int = int(os.getenv("TECH_MA_TREND", "60"))
TECH_RSI_LENGTH: int = int(os.getenv("TECH_RSI_LENGTH", "14"))
TECH_BOLL_LENGTH: int = int(os.getenv("TECH_BOLL_LENGTH", "20"))
TECH_KDJ_K: int = int(os.getenv("TECH_KDJ_K", "14"))
TECH_KDJ_D: int = int(os.getenv("TECH_KDJ_D", "3"))
TECH_KDJ_SMOOTH: int = int(os.getenv("TECH_KDJ_SMOOTH", "3"))
```

说明：

1. LLM 统一使用 Qwen，默认 `qwen-plus`。
2. 默认仅传最近 36 个月给 Agent（`TECH_AGENT_LOOKBACK_MONTHS`）。
3. 指标参数可配置，便于回测和A/B实验。
4. 采用双阈值策略：`TECH_MIN_MONTHS=24`（进入流程）与
   `TECH_LONG_TREND_MIN_MONTHS=60`（启用 MA60）。
5. `TECH_AGENT_LOOKBACK_MONTHS` 定为 36 而非更短的 24，是有意调整：36 个月可覆盖约 3 年周期，
   对月线趋势切换更稳定，同时能提供更完整的 MA20/BOLL/KDJ 上下文。

---

## 四、数据模型设计（module_c_models.py）

```python
from typing import Literal
from pydantic import BaseModel, Field


class TechnicalMeta(BaseModel):
    symbol: str
    name: str
    analysis_time: str
    data_start: str | None = None
    data_end: str | None = None
    total_months: int = 0
    data_quality_warnings: list[str] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    ma_alignment: str = ""
    price_vs_ma20: str = ""
    trend_6m: str = ""
    trend_12m: str = ""
    trend_judgment: str = ""


class MomentumAnalysis(BaseModel):
    macd_status: str = ""
    rsi_value: float | None = None
    rsi_status: str = ""
    kdj_status: str = ""


class VolatilityAnalysis(BaseModel):
    boll_position: str = ""
    boll_width: str = ""


class VolumeAnalysis(BaseModel):
    recent_vs_avg: str = ""
    volume_price_relation: str = ""


class KeyLevels(BaseModel):
    support_1: float | None = None
    support_2: float | None = None
    resistance_1: float | None = None
    resistance_2: float | None = None


class LLMTechnicalOutput(BaseModel):
    """LLM 仅负责输出技术分析内容，不包含 meta。"""
    score: float = Field(ge=0, le=10)
    signal: Literal["强烈看多", "看多", "中性", "看空", "强烈看空"]
    confidence: float = Field(ge=0, le=1)
    trend_analysis: TrendAnalysis
    momentum: MomentumAnalysis
    volatility: VolatilityAnalysis
    volume_analysis: VolumeAnalysis
    key_levels: KeyLevels
    summary: str = Field(max_length=1200)


class TechnicalAnalysisResult(LLMTechnicalOutput):
    """模块C最终输出（代码注入 meta 后形成）。"""
    meta: TechnicalMeta
```

---

## 五、核心流程详细设计（module_c_technical.py）

### 5.1 对外入口

```python
async def run_technical_analysis(symbol: str, name: str) -> TechnicalAnalysisResult:
    """
    模块C对外入口：
    1) 拉取月K
    2) 计算指标
    3) 构造特征
    4) 调用技术分析Agent
    5) 校验与降级
    """
```

### 5.2 月K线获取

函数：`ak.stock_zh_a_hist(symbol, period="monthly", start_date=..., adjust="qfq")`

关键点：

1. `symbol` 使用纯6位代码（如 `600519`）。
2. 固定 `period="monthly"`。
3. 默认 `adjust="qfq"`；若接口报错可降级为 `adjust=""` 重试一次。
4. 返回空表时抛 `TechnicalDataError`（或返回降级对象，见第八章）。

### 5.3 清洗与标准化

原始列（AKShare）通常为：

- `日期`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率`

处理规则：

1. 统一转英文字段：`date/open/high/low/close/volume/amount/...`
2. `date` 转 `datetime64[ns]` 并升序排序。
3. 价格、成交量列用 `pd.to_numeric(errors="coerce")`。
4. 去除 `date` 或 `close` 缺失行。
5. 记录数据质量告警，不直接崩溃。

### 5.4 技术指标计算（pandas-ta）

最小计算集合：

1. MA：`SMA_5`, `SMA_10`, `SMA_20`, `SMA_60`（`SMA_60` 为长周期指标）
2. MACD：`MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`
3. RSI：`RSI_14`
4. BOLL：`BBL_20_2.0`, `BBM_20_2.0`, `BBU_20_2.0`
5. KDJ（stoch）：`STOCHk_14_3_3`, `STOCHd_14_3_3`

指标分层定义：

1. 核心指标：`SMA_5/10/20`、`MACD`、`RSI`、`BOLL`、`KDJ`
2. 长周期指标：`SMA_60`

规则：

1. 当 `total_months < TECH_MIN_MONTHS`：不进入完整指标流程，直接硬降级。
2. 当 `TECH_MIN_MONTHS <= total_months < TECH_LONG_TREND_MIN_MONTHS`：
   核心指标照常计算，`SMA_60` 允许为空并视为软降级。
3. 当 `total_months >= TECH_LONG_TREND_MIN_MONTHS`：完整使用所有指标（含 `SMA_60`）。

若 `pandas_ta` 不可用：

1. 记录错误并抛 `TechnicalIndicatorError`
2. 由上层决定返回降级结果（不建议静默跳过）

### 5.5 派生特征（给 Agent 的结构化输入）

从指标 DataFrame 计算确定性特征：

1. `trend_6m_pct`: 最近6个月涨跌幅
2. `trend_12m_pct`: 最近12个月涨跌幅
3. `ma_alignment`: 多头/空头/缠绕
4. `price_vs_ma20_pct`: 当前收盘价相对 MA20 偏离
5. `macd_cross`: 最近3个月是否金叉/死叉
6. `macd_hist_direction`: 柱状图放大/缩小
7. `rsi_value`, `rsi_status`: 超买/超卖/中性
8. `boll_pos`: 上轨附近/中轨附近/下轨附近
9. `boll_width_trend`: 开口扩大/收窄
10. `volume_ratio_3m_12m`: 近3月均量 / 近12月均量
11. `support_1/support_2`: 近6月、近12月低点
12. `resistance_1/resistance_2`: 近6月、近12月高点

`SMA_60` 不足样本处理（必须显式实现）：

1. `SMA_60` 全 NaN 时，不参与 `ma_alignment` 计算。
2. `ma_alignment` 仅基于 `SMA_5/10/20` 输出。
3. 在 `meta.data_quality_warnings` 增加：
   `样本不足60个月，未使用MA60长周期趋势判断`
4. `confidence` 上限收敛到 `0.65`（软降级），由代码强制执行，不依赖 Prompt。

### 5.6 发送给 LLM 的数据载荷

只发送两部分：

1. `features`（确定性摘要，几十个标量）
2. `recent_rows`（最近 `TECH_AGENT_LOOKBACK_MONTHS` 的关键列）

推荐关键列：

- `date`, `close`, `volume`
- `SMA_5`, `SMA_10`, `SMA_20`, `SMA_60`（当不可用时允许为 `null`）
- `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`
- `RSI_14`, `BBL_20_2.0`, `BBM_20_2.0`, `BBU_20_2.0`
- `STOCHk_14_3_3`, `STOCHd_14_3_3`

序列化注意事项（NaN / datetime）：

1. 不使用 `to_dict + json.dumps` 路径，避免 `NaN` 非标准 JSON 和 `Timestamp` 序列化异常；
2. 统一使用 pandas `to_json`，同时处理：
   `NaN -> null`、`datetime -> ISO 字符串`、`中文不转义`。

```python
rows_df = feature_df[columns_for_llm].tail(lookback_months).copy()
rows_json = rows_df.to_json(
    orient="records",
    force_ascii=False,
    date_format="iso",
)
```

### 5.7 Agent 推理（Qwen + MAF）

创建方式与模块B一致，复用：

- `create_openai_client()`（`stock_analyzer/llm_client.py`）
- `create_chat_client()`（`stock_analyzer/llm_client.py`）
- `ChatAgent`（MAF）

`response_format` 兼容说明（与模块B保持一致）：

1. 当前项目使用 `agent-framework==1.0.0b260130`；
2. 实践上不直接传 Pydantic 模型给 `ChatAgent` 的 `response_format`；
3. 统一使用 `{"type": "json_object"}`，并采用“两步构造”：
   `json.loads(...) -> LLMTechnicalOutput.model_validate(...) -> 注入 meta -> TechnicalAnalysisResult.model_validate(...)`。

Agent 参数：

```python
ChatAgent(
    chat_client=technical_chat_client,
    name="technical_analyst",
    instructions=TECHNICAL_AGENT_SYSTEM_PROMPT,
    default_options={
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    },
)
```

推理后流程（两步构造，避免 LLM 生成 meta）：

1. 取 Agent 文本输出
2. `json.loads` 解析
3. `LLMTechnicalOutput.model_validate(...)` 校验 LLM 输出
4. 代码构造 `TechnicalMeta`（`analysis_time/data_quality_warnings` 等）
5. 合并后校验最终结果：

```python
llm_output = LLMTechnicalOutput.model_validate(parsed_json)
meta = TechnicalMeta(
    symbol=symbol,
    name=name,
    analysis_time=datetime.now().isoformat(),
    data_start=data_start,
    data_end=data_end,
    total_months=total_months,
    data_quality_warnings=warnings,
)
final_result = TechnicalAnalysisResult.model_validate(
    {"meta": meta.model_dump(), **llm_output.model_dump()}
)

# 等价简写（推荐）
# final_result = TechnicalAnalysisResult(meta=meta, **llm_output.model_dump())
```

6. 对 `24~59` 个月样本执行软降级置信度裁剪（在 `final_result` 构造后）：

```python
if total_months < TECH_LONG_TREND_MIN_MONTHS:
    final_result = final_result.model_copy(
        update={"confidence": min(final_result.confidence, 0.65)}
    )
```

7. 任一校验失败时抛 `TechnicalAnalysisError` 或降级返回

8. 序列化输出时若希望 `meta` 固定排在最前（与本文示例一致），
   不直接使用 `final_result.model_dump()`，而是显式重排：

```python
output_dict = {
    "meta": final_result.meta.model_dump(),
    **final_result.model_dump(exclude={"meta"}),
}
json_str = json.dumps(output_dict, ensure_ascii=False, indent=2)
```

---

## 六、Prompt 设计（prompts.py）

新增：

- `TECHNICAL_AGENT_SYSTEM_PROMPT`

建议内容要点：

1. 角色：A股月线技术分析师
2. 只基于输入数据，不得编造数据
3. 必须输出 JSON 对象
4. 结论优先级：
   - 趋势（MA + 价格位置）
   - 动量（MACD/RSI/KDJ）
   - 波动（BOLL）
   - 量价关系
5. 输出字段必须与 `LLMTechnicalOutput` Schema 匹配（不包含 `meta` 字段，`meta` 由系统自动注入）
6. `score` 在 0-10，`confidence` 在 0-1
7. `summary` 字段不超过 1200 字符（约 1200 汉字，按 Python 字符长度计）

用户提示模板建议：

```text
请基于以下月线技术数据输出结构化分析结果（JSON）：

股票：{symbol} {name}
数据区间：{data_start} ~ {data_end}
总月数：{total_months}

【确定性特征】
{features_json}

【最近{lookback_months}个月关键指标明细】
{rows_json}
```

---

## 七、输出示例（technical_analysis.json）

```json
{
  "meta": {
    "symbol": "600519",
    "name": "贵州茅台",
    "analysis_time": "2026-02-11T20:20:00",
    "data_start": "2001-08-31",
    "data_end": "2026-01-31",
    "total_months": 294,
    "data_quality_warnings": []
  },
  "score": 6.9,
  "signal": "看多",
  "confidence": 0.74,
  "trend_analysis": {
    "ma_alignment": "中期多头排列（MA5>MA10>MA20）",
    "price_vs_ma20": "收盘价位于MA20上方约6.2%",
    "trend_6m": "近6个月上涨8.4%",
    "trend_12m": "近12个月上涨11.7%",
    "trend_judgment": "中期上升趋势延续"
  },
  "momentum": {
    "macd_status": "MACD位于零轴上方，柱状图小幅收敛",
    "rsi_value": 61.3,
    "rsi_status": "中性偏强",
    "kdj_status": "K值高位回落，短期有震荡风险"
  },
  "volatility": {
    "boll_position": "价格位于布林中轨与上轨之间",
    "boll_width": "布林带开口小幅收窄"
  },
  "volume_analysis": {
    "recent_vs_avg": "近3月均量约为近12月均量的1.08倍",
    "volume_price_relation": "量价配合中性偏正"
  },
  "key_levels": {
    "support_1": 1530.0,
    "support_2": 1468.0,
    "resistance_1": 1715.0,
    "resistance_2": 1798.0
  },
  "summary": "月线级别中期趋势仍偏多，但动量指标高位有分化，短期更可能震荡上行。"
}
```

---

## 八、异常与降级设计

### 8.1 新增异常类（exceptions.py）

```python
class TechnicalDataError(Exception):
    """AKShare月K线数据不可用或数据量不足。"""

class TechnicalIndicatorError(Exception):
    """技术指标计算失败。"""

class TechnicalAnalysisError(Exception):
    """LLM技术分析阶段失败或输出校验失败。"""
```

### 8.2 降级策略

1. 数据层失败（无月K）：
   - 返回最小可用结果：`signal="中性"`, `score=5.0`, `confidence=0.2`
   - `meta.data_quality_warnings` 写明原因

2. 样本数量分级（双阈值）：
   - `< TECH_MIN_MONTHS(24)`：硬降级，不调用 LLM。
   - `24~59`：软降级，允许 `SMA_60` 缺失并限制 `confidence <= 0.65`。
     该上限由代码强制裁剪（`min(confidence, 0.65)`），不是 Prompt 约束。
   - `>= 60`：完整流程。

3. 指标层失败：
   - 若核心指标（`SMA_5/10/20`、`MACD`、`RSI`、`BOLL`、`KDJ`）缺失，直接硬降级，不调用 LLM。
   - 若仅 `SMA_60` 缺失，按软降级继续执行。

4. LLM层失败（超时/解析失败/校验失败）：
   - 使用规则模板构造 fallback（基于确定性特征）
   - `confidence` 下调到 `<=0.35`

5. 所有异常都要进入日志和输出元数据，禁止静默吞错。

### 8.3 样本区间行为表

| 样本区间（月） | MA60 | 流程 | 结果类型 |
|---|---|---|---|
| `< 24` | 不可用 | 不调用LLM，直接硬降级 | 中性 fallback |
| `24 ~ 59` | 不可用（允许） | 调用LLM（核心指标）+ 软降级 | `ma_alignment` 不含 MA60，代码强制 `confidence=min(confidence,0.65)` |
| `>= 60` | 可用 | 完整流程 | 标准结果 |

---

## 九、与模块A/B/D的协同

### 9.1 与模块A

1. 输入符号规则一致（6位数字）
2. 共用 `config.py` 的 API/日志/超时配置风格
3. 共用 `logger.py`，日志统一写 `logs/stock_analyzer.log`

### 9.2 与模块B

1. 共用 DashScope + Qwen 的 `llm_client.py`
2. 共用 MAF `ChatAgent` 使用范式
3. 共用 `exceptions.py` 异常管理

### 9.3 与模块D

模块D消费模块C输出的方式：

1. 读取 `score/signal/confidence`
2. 读取 `trend_analysis/momentum/volatility/volume_analysis/key_levels/summary`
3. 与模块A/B报告并列输入首席分析师

模块D字段映射（从概要设计旧路径迁移到模块C新路径）：

| 概要设计旧路径（扁平） | 模块C新路径（嵌套） |
|---|---|
| `trend_judgment` | `trend_analysis.trend_judgment` |
| `ma_alignment` | `trend_analysis.ma_alignment` |
| `macd_status` | `momentum.macd_status` |
| `rsi_value` | `momentum.rsi_value` |
| `volume_analysis` | `volume_analysis.volume_price_relation`（文本主结论） |
| `support_level` | `key_levels.support_1` |
| `resistance_level` | `key_levels.resistance_1` |

模块D兼容要求：

1. 模块D提示词和解析代码都要使用新路径；
2. 若需要兼容旧数据，可在模块D增加一次性适配层（旧字段映射到新结构）；
3. 新增模块D联调测试，覆盖新旧路径兼容逻辑。

---

## 十、测试设计

### 10.1 单元测试

建议新增 `stock_analyzer/tests/test_module_c_technical.py`：

1. `test_fetch_monthly_kline_success`
2. `test_fetch_monthly_kline_empty`
3. `test_compute_indicators_has_required_columns`
4. `test_build_features_with_insufficient_data`
5. `test_build_features_without_ma60_soft_degrade`（24~59个月）
6. `test_support_resistance_calculation`
7. `test_llm_output_validation_success`
8. `test_llm_output_validation_fallback`

### 10.2 集成测试

1. `run_module_c.py` 对真实股票执行，检查输出文件结构
2. 模拟模块D输入拼装，验证字段兼容
3. 针对停牌/次新股（数据不足）验证降级路径

### 10.3 回归重点

1. AKShare 列名变化（中文字段变化）是否可容错
2. `pandas-ta` 指标列命名变化是否会破坏特征提取
3. LLM 输出偏离 Schema 时是否稳定降级

---

## 十一、实现顺序建议

1. 新建 `module_c_models.py`，先固定输出 Schema。
2. 实现月K获取 + 清洗 + 指标计算（不接 LLM）。
3. 实现特征提取，加入单元测试。
4. 接入 Qwen + MAF `ChatAgent`。
5. 实现 fallback 与异常体系。
6. 增加 `run_module_c.py` 和集成测试。

---

## 十二、依赖与版本说明

当前根 `pyproject.toml` 已包含：

- `agent-framework==1.0.0b260130`
- `akshare>=1.18.22`

模块C实现还必须在根项目安装以下依赖：

```toml
pandas-ta>=0.3.14b0
```

该依赖为模块C开发与运行前置条件。
