# 底部反转（平底锅）形态选股策略设计文档 (v2 - Hybrid AI)

本文档设计了一个**混合型**量化选股工具 (`analysis/find_bottom.py`)，结合传统数学规则与 AI 视觉识别能力，精准挖掘“长期超跌、底部横盘”的潜力标的。

## 1. 策略核心理念

采用 **漏斗式 (Funnel)** 筛选架构：
1.  **宽口径粗筛 (Mathematical Filter)**: 利用 Pandas 进行向量化计算，快速排除掉 90% 明显不符合（如一直在涨、刚开始跌）的股票，保留“疑似”标的。
2.  **AI 视觉精选 (Visual Re-ranking)**: 利用多模态大模型 (Multimodal LLM) 的视觉理解能力，像人类专家一样审视 K 线图，剔除“阴跌不止”或“形态破位”的伪信号，找出形态最完美的“平底锅”。

## 2. 形态量化定义 (粗筛层)

为了给 AI 提供足够的候选样本，数学规则应适当**放宽**。

| 维度 | 指标名称 | 计算公式 | 粗筛阈值 (v2) | 原严格阈值 |
| :--- | :--- | :--- | :--- | :--- |
| **跌幅** | 历史回撤 | `(当前价 / 历史高点) - 1` | `< -40%` | `< -50%` |
| **时效** | 高点账龄 | `NOW - 高点时间` | `> 2 年` | `> 3 年` |
| **横盘** | 底部振幅 | `近3年 (最高/最低)` | `< 3.0` | `< 2.0` |

## 3. 系统架构设计

### 3.1 模块结构

```text
/opt/fin_analysis/
├── analysis/
│   ├── __init__.py
│   ├── find_bottom.py      <-- 流程控制器
│   └── ai_evaluator.py     <-- (新增) AI 视觉评分模块
```

### 3.2 数据流 (Pipeline)

1.  **数据快照**: SQL 拉取全量 OHLC。
2.  **特征计算**: Pandas 计算回撤、振幅。
3.  **规则粗筛**: 筛选出 `Top N` (如 50-100 只) 候选股。
4.  **绘图生成**: 调用 `visualization.plot_kline` 生成临时图片。
5.  **AI 评分**: 
    *   遍历图片，调用 `ai_evaluator.evaluate(image_path)`。
    *   LLM 返回评分 (0-10) 和理由。
6.  **最终报告**: 按 AI 评分排序，输出 HTML/CSV 报告。

## 4. 详细实施方案

### 4.1 AI 评分模块 (`ai_evaluator.py`)

该模块负责与大模型 (如 GPT-4o, Gemini 1.5 Pro) 交互。

**Prompt 设计**:
> "你是一位资深的证券技术分析师。请分析这张月 K 线图。我正在寻找'底部反转'形态（俗称平底锅）。
> 
> **标准形态特征**：
> 1. 左侧：曾有大幅下跌。
> 2. 底部：长期（2年以上）横盘震荡，箱体稳定，无明显下跌趋势。
> 3. 右侧：近期价格平稳或微涨，未出现破位大跌。
> 
> 请忽略具体的股票代码和价格绝对值，仅关注 K 线形态。
> 请给出 0-10 分的打分：
> - 0-4分：处于下跌趋势中，或底部震荡时间太短。
> - 5-7分：基本符合底部特征，但形态不够标准（如波动过大）。
> - 8-10分：完美的平底锅形态，长期横盘且波动极小，蓄势待发。
> 
> 返回格式 JSON: `{'score': 8.5, 'reason': '...'}`"

### 4.2 主流程逻辑 (`find_bottom.py`)

```python
def main():
    # 1. 粗筛
    candidates = mathematical_scan() # 返回 DataFrame
    logger.info(f"粗筛选中 {len(candidates)} 只股票")

    # 2. 准备 AI 评审列表 (按数学特征排序，取前 N 只以节省 Token)
    top_candidates = candidates.head(50) 
    
    results = []
    for code in top_candidates['code']:
        # 3. 生成图片
        img_path = f"temp/{code}.png"
        plot_kline(code, out=img_path, start='2010-01-01')
        
        # 4. AI 评分
        try:
            eval_result = ai_evaluator.evaluate(img_path) # score, reason
            results.append({**eval_result, 'code': code})
        except Exception:
            logger.error(f"AI eval failed for {code}")

    # 5. 输出
    save_report(results)
```

## 5. 开发计划

1.  **Phase 1 (基础)**: 实现 SQL+Pandas 粗筛逻辑，并生成图片。
2.  **Phase 2 (智能)**: 实现 `ai_evaluator`，对接 OpenAI/Gemini API 接口。

## 6. 使用示例

```bash
# 仅执行数学粗筛 (无 AI)
python -m analysis.find_bottom --no-ai

# 执行完整流程 (筛选 + AI 评分)
python -m analysis.find_bottom --top-n 20
```
