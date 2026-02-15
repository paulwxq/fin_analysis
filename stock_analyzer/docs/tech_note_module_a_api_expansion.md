# Tech Note: Module A 扩展 API 探测与整合方案

**日期**：2026-02-13  
**版本**：AKShare 1.18.22  
**状态**：已验证 (Verified)

---

## 1. 扩充动机
为提升“首席分析师 (Module D)”的判断深度，Module A 需在原有财务数据基础上增加：
1. **盈利一致预期**：了解市场专业机构对未来 1-3 年的增长预判。
2. **机构持仓底牌**：分析大资金（基金、社保等）的进出动态。
3. **主营构成账本**：拆解公司真实的收入来源（产品、地域）。

---

## 2. API 选型与实测结论

经过对多个候选接口的探测，选定以下最优路径：

| 维度 | 最终选定 API | 输入格式 | 核心返回字段 |
| :--- | :--- | :--- | :--- |
| **一致预期** | `stock_profit_forecast_ths` | 纯6位代码 | `年度`, `预测机构数`, `均值`, `行业平均数` |
| **机构持仓** | `stock_institute_hold_detail` | 纯6位 + 报告期 | `持股机构类型`, `持股机构简称`, `持股比例` |
| **主营结构** | `stock_zygc_em` | 大写市场前缀 | `分类类型`, `主营构成`, `收入比例`, `毛利率` |

### 2.1 避坑说明
*   **盈利预测**：`stock_profit_forecast_em` 在当前版本 SDK 下存在解析 Bug，已回退至 `ths` 源。
*   **机构持仓**：需配合 `_get_recent_quarter_ends` 逻辑自动推算 `quarter` 参数（如 `20243` 代表 2024 三季报）。
*   **主营结构**：必须使用 `SH600519` 或 `SZ000001` 这种带市场前缀的格式。

---

## 3. 核心探测代码参考

```python
import akshare as ak

# 1. 获取一致预期
df_forecast = ak.stock_profit_forecast_ths(symbol="600519")
# 提取：df_forecast[['年度', '预测机构数', '均值', '行业平均数']]

# 2. 获取机构持仓详情 (以2024三季报为例)
df_hold = ak.stock_institute_hold_detail(stock="600519", quarter="20243")
# 提取：df_hold[['持股机构类型', '持股机构简称', '最新持股比例']]

# 3. 获取主营构成
df_zygc = ak.stock_zygc_em(symbol="SH600519")
# 提取：df_zygc[df_zygc['分类类型'] == '按产品分类']
```

---

## 4. 结果整合建议 (Final Schema)

建议将新数据挂载至 `AKShareData` 顶层，并采用以下结构进行归一化：

### 4.1 `consensus_forecast` (List)
*   `year`: 预测年度 (如 "2025")
*   `inst_count`: 参与预测的机构数
*   `eps_avg`: EPS 均值
*   `industry_avg`: 行业 EPS 均值对比

### 4.2 `institutional_holdings` (List)
*   `institution_type`: 机构类别 (基金/保险/社保等)
*   `institution_name`: 机构名称
*   `hold_ratio`: 持股占总股本比例 (%)

### 4.3 `business_composition` (List)
*   `item_name`: 产品或地区名称
*   `revenue_ratio`: 收入占比 (%)
*   `gross_margin`: 毛利率 (%)

---

## 5. 验证工具
本项目已建立自动化探测脚本：`stock_analyzer/tests/probe_new_akshare_apis.py`
