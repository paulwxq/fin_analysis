# 数据清洗规则说明书 v2 (进阶版)

本文档在 v1 版的基础上，进一步强化了金融业务逻辑的自洽性校验。旨在下一阶段的代码迭代中实施，以实现“金融级”的数据质量控制。

## 1. 新增核心规则：OHLC 全逻辑闭环

在 v1 版中，我们仅校验了 `High >= Low`。v2 版要求 K 线数据的四个核心价格（Open, High, Low, Close）必须严格满足定义上的数学关系。

### 校验公式
无论数据是否复权（数值正负），以下不等式组必须**全部同时成立**：

1.  `High >= Open`
2.  `High >= Close`
3.  `High >= Low` (v1 已包含)
4.  `Low <= Open`
5.  `Low <= Close`

### 异常处理
*   **动作**：违反任意一条规则，该行数据视为逻辑崩坏（Corrupted），**直接跳过**。
*   **日志**：记录 `[WARNING] OHLC Logic Error: H=... L=... O=... C=...`。

## 2. 规则推导示例

假设复权后价格为负数，逻辑依然成立：
*   **正常数据**: Open=-5, Close=-2, High=-1, Low=-6
    *   -1 >= -5 (True)
    *   -1 >= -2 (True)
    *   -1 >= -6 (True)
    *   -6 <= -5 (True)
    *   -6 <= -2 (True)
    *   **结果**: 通过。

*   **异常数据**: Open=-1, High=-5 (最高价竟然比开盘价还低？)
    *   -5 >= -1 (False)
    *   **结果**: 拦截。

## 3. 实施建议 (Python 代码片段)

在 `loader.py` 的 `clean_row_data` 函数中，将原有的 High/Low 检查扩展为：

```python
# v2 OHLC Validation
p_open = prices["Open"]
p_close = prices["Close"]
p_high = prices["High"]
p_low = prices["Low"]

if not (p_high >= p_open and p_high >= p_close and p_high >= p_low and 
        p_low <= p_open and p_low <= p_close):
    raise ValueError(
        f"OHLC Logic Error: O={p_open}, H={p_high}, L={p_low}, C={p_close}"
    )
```

## 4. 其他潜在优化 (待定)

*   **停牌填充检查**: 如果 `Volume=0` 且 `High != Low`（无成交但有振幅），是否视为脏数据？
*   **极值跳变**: 单分钟价格跳变超过 50% 是否拦截？

(目前优先实施 OHLC 全逻辑闭环)
