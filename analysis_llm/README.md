# Analysis LLM 执行说明

## 简介

股票分析 LLM 流水线，支持两步执行：
- **Step 1**: 数据收集与分析（新闻、板块、K线）
- **Step 2**: 基于 Step1 数据生成持有推荐评分

## 环境准备

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 配置环境变量（在项目根目录的 .env 文件）
DASHSCOPE_API_KEY=your_dashscope_key
DEEPSEEK_API_KEY=your_deepseek_key
```

## 使用方法

### 🚀 快速开始（完整流程）

```bash
# 一键执行 Step1 → Step2
python -m analysis_llm.main 603080.SH
```

**输出**: `HoldRecommendation` JSON（包含评分和推荐理由）

---

### 🔧 分步执行（开发/调试）

#### Step 1: 数据收集

```bash
# 执行 Step1，保存结果
python -m analysis_llm.main 603080.SH --step 1 > output/step1_603080.json
```

**输出**: `Step1Output` JSON（包含 news、sector、kline）

#### Step 2: 评分生成

```bash
# 基于 Step1 结果执行 Step2
python -m analysis_llm.main --step 2 --input output/step1_603080.json
```

**输出**: `HoldRecommendation` JSON

**优势**: Step1 结果可复用，调试 Step2 时无需重复调用 API

---

## 命令行参数

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `stock_code` | 条件必填* | 股票代码 | `603080.SH` |
| `--step {1,2}` | 可选 | 指定执行步骤 | `--step 1` |
| `--input FILE` | 条件必填** | Step1 输出文件 | `--input step1.json` |

\* Step1 或完整流程时必填
\** 单独执行 Step2 时必填

---

## 输出格式

### Step1 输出 (`Step1Output`)

```json
{
  "timestamp": "2026-02-05T12:00:00Z",
  "news": {
    "data_type": "news",
    "stock_code": "603080.SH",
    "stock_name": "新疆火炬",
    "positive_news": [...],
    "negative_news": [...],
    "news_summary": "...",
    "sentiment_score": 0.8
  },
  "sector": {...},
  "kline": {...}
}
```

### Step2 输出 (`HoldRecommendation`)

```json
{
  "data_type": "hold_recommendation",
  "timestamp": "2026-02-05T12:05:00Z",
  "stock_code": "603080.SH",
  "stock_name": "新疆火炬",
  "hold_score": 7.5,
  "summary_reason": "综合技术面、基本面和板块热度分析..."
}
```

---

## 常见场景

### 场景 1: 生产环境批量处理

```bash
#!/bin/bash
for stock in 603080.SH 600519.SH 000001.SZ; do
  python -m analysis_llm.main $stock > output/${stock}_recommendation.json
done
```

### 场景 2: 开发调试 Step2

```bash
# 一次性收集数据
python -m analysis_llm.main 603080.SH --step 1 > step1.json

# 反复测试 Step2（修改代码后重新运行）
python -m analysis_llm.main --step 2 --input step1.json
```

### 场景 3: 数据收集与分析分离

```bash
# 白天收集数据
python -m analysis_llm.main 603080.SH --step 1 > data/603080_$(date +%Y%m%d).json

# 晚上批量分析
find data -name "*.json" -exec \
  python -m analysis_llm.main --step 2 --input {} \;
```

---

## 注意事项

1. **API 密钥**: 确保 `.env` 文件中配置了正确的 API 密钥
2. **网络连接**: Step1 需要联网搜索，Step2 的 ScoreAgent 也支持联网补充信息
3. **超时设置**: 默认超时 60 秒，可通过环境变量 `API_TIMEOUT` 调整
4. **日志文件**: 详细日志保存在 `logs/analysis_llm.log`
5. **图片文件**: K线图片需放在 `output/` 目录，命名格式如 `603080.SH_kline.png`

---

## 故障排查

### 问题: ModuleNotFoundError

```bash
# 解决: 确保已激活虚拟环境
source .venv/bin/activate
```

### 问题: API Key 未设置

```bash
# 解决: 检查 .env 文件
cat .env | grep API_KEY
```

### 问题: Step2 提示 input 文件缺失

```bash
# 解决: 使用绝对路径或相对路径
python -m analysis_llm.main --step 2 --input ./output/step1.json
```

---

## 技术架构

- **Step1**: `ConcurrentBuilder` 并发执行（NewsAgent, SectorAgent, KlineAgent）
- **Step2**: `MagenticBuilder` 闭环编排（Manager + ScoreAgent + ReviewAgent）
- **模型**: DashScope (qwen-plus/qwen-max) + DeepSeek (deepseek-chat)
- **框架**: Magentic Agent Framework (MAF)

---

## 相关文档

- 详细设计: `docs/analysis_llm/step1_detailed_design.md`
- 详细设计: `docs/analysis_llm/step2_detailed_design.md`
- 技术说明: `docs/analysis_llm/tech_note_maf_dashscope_integration.md`
