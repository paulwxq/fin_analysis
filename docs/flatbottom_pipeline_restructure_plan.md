# flatbottom_pipeline 重构迁移方案（v2）

## 1. 背景与目标

当前链路 A（平底锅筛选流水线）的 3 个业务模块分散在项目根目录：

1. `selection` — 规则筛选（平底锅形态识别）
2. `visualization` — K 线图生成
3. `refinement_llm` — LLM 视觉评分（细化打分）

它们共同构成一条完整的业务流水线：

```
selection → visualization → refinement_llm
```

目标是将这 3 个业务模块统一收敛到 `flatbottom_pipeline/` 子目录，并将相关测试迁入 `flatbottom_pipeline/tests/`，形成自包含的业务能力包。

**核心原则：只动业务模块，不动基础设施。**

## 2. 关键设计决策

### 2.1 `data_infra` 不迁入

`data_infra` 模块的职责是**数据基础设施**，而非平底锅业务逻辑：

| 文件 | 功能 | 性质 |
|------|------|------|
| `loader.py` / `main.py` | 从 ZIP 批量导入 1 分钟 K 线到 TimescaleDB | 数据加载 |
| `aggregate.py` | 创建 `stock_monthly_kline` 月线聚合视图 | 数据加工 |
| `compress_manual.py` | TimescaleDB chunk 压缩 | 数据库运维 |
| `db.py` | `get_db_connection()` 公共数据库连接 | 公共工具 |
| `stock_code.py` | `classify_cn_stock()` 股票代码分类 | 公共工具 |

`selection` 和 `visualization` 依赖 `data_infra.db` 和 `data_infra.stock_code`。将 `data_infra` 保留在根目录，可以：
- 保持语义清晰（基础设施 vs 业务流水线）
- 避免未来其他链路引用时出现 `from flatbottom_pipeline.data_infra.db import ...` 的别扭路径
- 减小迁移范围和风险

### 2.2 不设代码兼容层

经排查，**代码层**没有外部消费者依赖旧路径：
- 根目录 `main.py` 是空壳（仅 `print("Hello")`）
- `stock_analyzer`、`analysis_llm` 不依赖这 3 个模块
- 无外部脚本通过 import 引用旧包名

因此不需要在旧路径放置 wrapper 转发代码。直接迁移，一步到位。

> **但请注意**：`docs/` 目录下大量文档包含旧路径的命令示例（如 `python -m selection.find_flatbottom`），
> 这些属于"用户可见接口"，必须在 Phase 6 同步更新，详见 §7 Phase 6。

### 2.3 共享 `.env` 配置

整个项目共用根目录下的 `.env` 文件。迁移后各子模块的 `config.py` 通过 `python-dotenv` 加载 `.env` 时，需确保路径解析指向项目根目录，而非子模块目录。

## 3. 迁移范围

### In Scope

- 迁移 3 个业务模块：`selection/`、`visualization/`、`refinement_llm/`
- 迁移相关测试到 `flatbottom_pipeline/tests/`
- 新增统一编排入口 `flatbottom_pipeline/run_pipeline.py`
- 更新所有受影响的导入路径
- 更新 `README.md` 文档

### Out of Scope

- 不改业务算法逻辑（筛选规则、评分规则、指标计算）
- 不改数据库 schema
- 不动 `data_infra/`、`analysis_llm/`、`stock_analyzer/` 的代码和位置
- 不动 `.env` 文件位置

## 4. 目标目录结构

```text
fin_analysis/
├── .env                            # 共享环境变量（不动）
├── main.py                         # 项目入口占位（不动）
├── pyproject.toml
│
├── data_infra/                      # 数据基础设施（不动）
│   ├── db.py
│   ├── stock_code.py
│   ├── loader.py
│   ├── aggregate.py
│   ├── compress_manual.py
│   └── ...
│
├── flatbottom_pipeline/            # 新：平底锅业务流水线
│   ├── __init__.py
│   ├── run_pipeline.py             # 新增：薄编排入口
│   │
│   ├── selection/                  # 从根目录迁入
│   │   ├── __init__.py
│   │   ├── find_flatbottom.py
│   │   ├── diagnose_code.py
│   │   ├── config.py
│   │   └── logger.py
│   │
│   ├── visualization/              # 从根目录迁入
│   │   ├── __init__.py
│   │   └── plot_kline.py
│   │
│   ├── refinement_llm/             # 从根目录迁入
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db_handler.py
│   │   ├── image_loader.py
│   │   ├── llm_analyzer.py
│   │   ├── models.py
│   │   ├── prompts.py
│   │   └── logger.py
│   │
│   └── tests/                      # 新：流水线测试目录
│       ├── __init__.py
│       ├── test_st_filter.py       # 从 tests/ 迁入
│       └── test_bug_fixes_part3.py # 从 tests/ 迁入
│
├── analysis_llm/                   # 不动
├── stock_analyzer/                 # 不动
│
├── tests/                          # 保留：data_infra 和其他模块的测试
│   ├── test_tiny.py                # data_infra 测试（不动）
│   ├── test_loader.py              # data_infra 测试（不动）
│   ├── test_load_single.py         # data_infra 测试（不动）
│   ├── test_analysis_llm_*.py      # analysis_llm 测试（不动）
│   ├── test_stock_analyzer_*.py    # stock_analyzer 测试（不动）
│   └── ...
│
└── output/                         # 共享输出目录（不动）
```

## 5. 依赖关系

### 5.1 当前代码层依赖（迁移前）

```
selection ──→ data_infra.db, data_infra.stock_code
visualization ──→ data_infra.db, data_infra.stock_code
refinement_llm ──→ （无外部模块依赖，完全自包含）
```

### 5.2 迁移后依赖

```
flatbottom_pipeline.selection ──→ data_infra.db, data_infra.stock_code  （路径不变）
flatbottom_pipeline.visualization ──→ data_infra.db, data_infra.stock_code  （路径不变）
flatbottom_pipeline.refinement_llm ──→ （无变化）
```

**关键点**：因为 `data_infra` 不动，`selection` 和 `visualization` 对 `data_infra` 的导入路径**无需修改**。

### 5.3 完整修改清单

迁移涉及三类路径变更：**import 语句**、**mock patch 字符串**、**代码内命令示例**。

#### A. import 语句（包内互引 + 测试导入）

| 文件 | 旧导入 | 新导入 |
|------|--------|--------|
| `selection/find_flatbottom.py` | `from selection.config import ...` | `from flatbottom_pipeline.selection.config import ...` |
| `selection/find_flatbottom.py` | `from selection.logger import ...` | `from flatbottom_pipeline.selection.logger import ...` |
| `selection/diagnose_code.py` | `from selection.config import ...` | `from flatbottom_pipeline.selection.config import ...` |
| `selection/logger.py` | `from selection import config` | `from flatbottom_pipeline.selection import config` |
| `tests/test_st_filter.py` | `from selection.find_flatbottom import ...` | `from flatbottom_pipeline.selection.find_flatbottom import ...` |
| `tests/test_bug_fixes_part3.py` | `from selection.find_flatbottom import ...` | `from flatbottom_pipeline.selection.find_flatbottom import ...` |
| `tests/test_bug_fixes_part3.py` | `from selection.config import ...` | `from flatbottom_pipeline.selection.config import ...` |

> 注意：
> - `from data_infra.db import get_db_connection` 等导入**不需要改**。
> - 注意同时覆盖 `from X.Y import Z` 和 `from X import Y` 两种形式（如 `selection/logger.py` 使用后者）。

#### B. mock patch 字符串

测试中 `unittest.mock.patch()` 使用的是**字符串路径**，不是 import 语句，容易遗漏：

| 文件 | 旧字符串 | 新字符串 |
|------|---------|---------|
| `tests/test_bug_fixes_part3.py:47` | `patch('selection.find_flatbottom.get_db_connection')` | `patch('flatbottom_pipeline.selection.find_flatbottom.get_db_connection')` |

> 迁移后务必 grep 检查所有 `patch('selection.` / `patch('visualization.` / `patch('refinement_llm.` 形式的字符串。

#### C. 代码内嵌命令示例（argparse help / docstring）

以下代码文件中的命令示例字符串需同步更新，否则会误导使用者：

| 文件 | 行号 | 旧内容 | 新内容 |
|------|------|--------|--------|
| `selection/find_flatbottom.py` | 709 | `python -m selection.find_flatbottom --preset balanced` | `python -m flatbottom_pipeline.selection.find_flatbottom --preset balanced` |
| `selection/find_flatbottom.py` | 712 | `python -m selection.find_flatbottom --preset balanced --min-drawdown ...` | `python -m flatbottom_pipeline.selection.find_flatbottom --preset balanced --min-drawdown ...` |
| `selection/find_flatbottom.py` | 715 | `python -m selection.find_flatbottom --show-config` | `python -m flatbottom_pipeline.selection.find_flatbottom --show-config` |
| `selection/diagnose_code.py` | 5 | `python -m selection.diagnose_code --code 600583 ...` | `python -m flatbottom_pipeline.selection.diagnose_code --code 600583 ...` |

## 6. `.env` 路径解析策略

各子模块的 `config.py` 使用 `python-dotenv` 加载环境变量。迁移后需确保 `dotenv` 能正确找到项目根目录的 `.env` 文件。

### 当前方式

```python
# refinement_llm/config.py（典型）
from dotenv import load_dotenv
load_dotenv()  # 默认从当前工作目录向上查找 .env
```

### 迁移后保障

`load_dotenv()` 默认行为是从 `os.getcwd()` 向上搜索 `.env`，只要运行命令时在项目根目录执行（如 `python -m flatbottom_pipeline.refinement_llm.main`），则无需修改。

**若需要更强的路径保障**，可在 config 中显式指定：

```python
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # flatbottom_pipeline/xxx/config.py → 上溯 2 级
load_dotenv(PROJECT_ROOT / ".env")
```

各模块的具体修改清单：

| 模块 | config 文件 | `parents` 层级 | 是否需改 |
|------|------------|---------------|---------|
| `selection` | `selection/config.py` | 不使用 dotenv（纯参数配置） | 不需要 |
| `visualization` | 无独立 config | — | 不需要 |
| `refinement_llm` | `refinement_llm/config.py` | `parents[2]` | 检查确认 |

## 7. 实施步骤

### Phase 1：目录迁移与包化

**操作：**

```bash
# 创建目标目录
mkdir -p flatbottom_pipeline/tests

# 迁移业务模块
git mv selection/ flatbottom_pipeline/selection/
git mv visualization/ flatbottom_pipeline/visualization/
git mv refinement_llm/ flatbottom_pipeline/refinement_llm/

# 迁移相关测试
git mv tests/test_st_filter.py flatbottom_pipeline/tests/
git mv tests/test_bug_fixes_part3.py flatbottom_pipeline/tests/

# 创建 __init__.py
touch flatbottom_pipeline/__init__.py
touch flatbottom_pipeline/tests/__init__.py
```

**验证：**
- `python -c "import flatbottom_pipeline"` 不报错
- `python -c "import flatbottom_pipeline.selection"` 不报错

### Phase 2：导入路径重写

按 §5.3 的完整清单（A/B/C 三类）逐文件修改。修改后执行全量检查：

```bash
# A. 检查 import 语句残留（排除 data_infra，那些不需要改）
#    覆盖 "from X.Y import Z" 和 "from X import Y" 两种形式
grep -rn "from selection[\. ]" --include="*.py" .
grep -rn "from visualization[\. ]" --include="*.py" .
grep -rn "from refinement_llm[\. ]" --include="*.py" .
grep -rn "import selection" --include="*.py" .
grep -rn "import visualization" --include="*.py" .
grep -rn "import refinement_llm" --include="*.py" .

# B. 检查 mock patch 字符串残留（单引号和双引号均需覆盖）
grep -rn "patch(['\"]selection\." --include="*.py" .
grep -rn "patch(['\"]visualization\." --include="*.py" .
grep -rn "patch(['\"]refinement_llm\." --include="*.py" .

# C. 检查代码内嵌命令示例残留
grep -rn "python -m selection\." --include="*.py" .
grep -rn "python -m visualization\." --include="*.py" .
grep -rn "python -m refinement_llm\." --include="*.py" .
```

确保上述所有 grep 结果为空（不含 `flatbottom_pipeline.` 前缀的旧引用已全部消除）。

**验证：**
- `python -c "from flatbottom_pipeline.selection.find_flatbottom import FlatbottomScreener"` 成功
- `python -c "from flatbottom_pipeline.visualization.plot_kline import *"` 成功
- `python -c "from flatbottom_pipeline.refinement_llm.main import main"` 成功

### Phase 3：`.env` 路径确认

逐一检查各模块 config 中 `load_dotenv()` 的调用方式，确保从项目根目录运行时能正确加载 `.env`。

**验证：**

```bash
# 从项目根目录运行各模块
python -m flatbottom_pipeline.selection.find_flatbottom --help
python -m flatbottom_pipeline.refinement_llm.main --help
```

### Phase 4：统一编排入口

实现 `flatbottom_pipeline/run_pipeline.py`，定位为**带 preflight 校验的薄编排层**：

- 启动时执行前置条件检查（preflight check）
- 按顺序调用各阶段（select → plot → refine）
- 不封装各子模块的个性化参数
- 每个阶段的详细参数由子模块自身的 argparse 处理

```python
"""
flatbottom_pipeline/run_pipeline.py

用法：
  python -m flatbottom_pipeline.run_pipeline --step select
  python -m flatbottom_pipeline.run_pipeline --step plot
  python -m flatbottom_pipeline.run_pipeline --step refine
  python -m flatbottom_pipeline.run_pipeline --step all
  python -m flatbottom_pipeline.run_pipeline --preflight-only  # 仅检查前置条件
"""
```

支持参数：
- `--step select|plot|refine|all` — 选择执行阶段
- `--stop-on-error` — 某阶段失败时是否终止（默认 True）
- `--preflight-only` — 仅执行前置条件检查，不运行任何阶段
- `--skip-preflight` — 跳过前置条件检查（高级用户）

#### 前置条件检查（Preflight Check）

流水线的完整链路实际上是：

```
[data_infra 数据入库] → [data_infra 月线聚合] → selection → visualization → refinement_llm
                        ↑ 不在本流水线内，        ↑ flatbottom_pipeline 负责的范围 ↑
                          但是硬前置条件
```

`selection` 模块依赖 `stock_monthly_kline` 月线聚合视图（由 `data_infra/aggregate.py` 创建），
`refinement_llm` 模块依赖 `output/` 目录下的 K 线图文件（由 `visualization` 生成）。

`run_pipeline.py` 应在**每个阶段执行前**检查该阶段的前置条件（而非一次性检查所有阶段）。
`--step all` 时按顺序逐阶段执行 preflight → run → preflight → run → ...，确保前一阶段的产出能被后一阶段的 preflight 检测到。

| 检查项 | 执行时机 | 检查方式 | 失败时提示 |
|--------|---------|---------|-----------|
| 数据库可连接 | 任何阶段前（仅一次） | `SELECT 1` 测试连接 | 请检查 .env 中数据库配置 |
| `stock_monthly_kline` 视图存在且非空 | `select` 阶段前 | 存在性：`SELECT to_regclass('public.stock_monthly_kline')`；非空性：`SELECT 1 FROM stock_monthly_kline LIMIT 1` | 请先运行 `python -m data_infra.aggregate` |
| `stock_flatbottom_preselect` 表有数据 | `plot` 阶段前 | `SELECT 1 FROM stock_flatbottom_preselect LIMIT 1` | 请先运行 `--step select` |
| `output/` 目录下存在 `*_kline.png` 文件 | `refine` 阶段前 | glob 扫描 `output/*_kline.png` | 请先运行 `--step plot` |

> `--preflight-only` 模式下则一次性检查所有项，用于环境诊断。

各阶段内部通过 `subprocess` 或函数调用方式执行，保持子模块的参数独立性。

### Phase 5：测试迁移与验证

**已迁移的测试文件**（Phase 1 完成）：
- `flatbottom_pipeline/tests/test_st_filter.py`
- `flatbottom_pipeline/tests/test_bug_fixes_part3.py`

**清理 sys.path hack**：

两个测试文件中都有手动修改 `sys.path` 的代码，迁移后应清理：

```python
# 删除以下代码（两个文件中都有类似写法）：
sys.path.insert(0, str(Path(__file__).parent))
```

迁移后测试文件位于 `flatbottom_pipeline/tests/`，`sys.path.insert(0, parent)` 会将 `flatbottom_pipeline/tests/` 加入路径，语义错误。由于 `pyproject.toml` 已配置 `pythonpath = ["."]`（项目根目录），pytest 运行时可直接使用标准包导入，不需要 sys.path hack。

清理后的导入应为：
```python
# test_st_filter.py — 清理后
from flatbottom_pipeline.selection.find_flatbottom import FlatbottomScreener

# test_bug_fixes_part3.py — 清理后
from flatbottom_pipeline.selection.find_flatbottom import FlatbottomScreener
from flatbottom_pipeline.selection.config import get_config
```

**pytest 配置**（`pyproject.toml`）：

当前配置不设 `testpaths`，保持 pytest 默认的递归发现行为，不做变更：

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "strict"
# 不设 testpaths —— 保持 pytest 默认递归扫描，
# 避免遗漏 tests/、flatbottom_pipeline/tests/ 或未来其他目录下的测试
```

> **不加 `testpaths` 的原因**：若显式设置 `testpaths = ["tests", "flatbottom_pipeline/tests"]`，
> pytest 将只扫描这两个目录，可能遗漏项目中其他位置的测试文件，与"全量验证"目标冲突。

**验证：**

```bash
# 运行流水线测试
pytest flatbottom_pipeline/tests/ -v

# 运行全部测试（确保未破坏其他模块，pytest 会自动发现所有 test_*.py）
pytest -v
```

### Phase 6：文档与命令示例更新

迁移后 `docs/` 下大量文档包含旧路径命令，必须同步更新。

**需更新的文档清单（按优先级）：**

| 优先级 | 文件 | 说明 |
|--------|------|------|
| **P0 必改** | `docs/common_commands.md` | 日常速查文档，所有命令均需更新 |
| **P0 必改** | `README.md` | 目录结构、运行方式、模块说明 |
| **P1 应改** | `docs/monthly_kline_visualization_design.md` | visualization 命令示例 |
| **P1 应改** | `docs/refinement_llm/2.概要设计文档.md` | refinement_llm 命令示例 |
| **P1 应改** | `docs/pre-selection/parameter_tuning_guide.md` | selection 命令示例 |
| **P2 可选** | `docs/pre-selection/flatbottom_screener_v2.md` | 历史设计文档，命令示例较多 |
| **P2 可选** | `docs/pre-selection/flatbottom_screener_v2 copy.md` | 同上副本 |
| **P2 可选** | `docs/pre-selection/FINAL_BUG_FIX_SUMMARY.md` | 历史 bugfix 记录 |
| **P2 可选** | `docs/pre-selection/ALL_BUGS_FIXED_20260128.md` | 历史 bugfix 记录 |
| **P2 可选** | `docs/pre-selection/bugfix_report_20260128*.md` | 历史 bugfix 记录（3 个文件） |
| **P2 可选** | `docs/pre-selection/st_filtering_clarification.md` | 历史说明 |
| **P2 可选** | `docs/pre-selection/flatbottom_pre_screening_algorithm.md` | 算法设计文档 |
| **P2 可选** | `docs/pre-selection/FINAL_SUMMARY_20260128.md` | 历史总结 |
| **P2 可选** | `docs/flatbottom_stock_scanner_design.md` | 早期设计文档 |

> P2 文档为历史记录，不阻塞验收。若纳入本次范围，推荐在文件头部添加迁移提示：
> `> ⚠️ 本文写于迁移前，命令路径已变更为 flatbottom_pipeline.xxx，请参考 common_commands.md`

**验证命令：**

```bash
# 检查 P0/P1 文档中是否还有未更新的旧命令路径
grep -rn "python -m selection\." docs/common_commands.md README.md \
    docs/monthly_kline_visualization_design.md \
    "docs/refinement_llm/2.概要设计文档.md" \
    docs/pre-selection/parameter_tuning_guide.md

grep -rn "python -m visualization\." docs/common_commands.md README.md \
    docs/monthly_kline_visualization_design.md

grep -rn "python -m refinement_llm\." docs/common_commands.md README.md \
    "docs/refinement_llm/2.概要设计文档.md"
```

> P2 历史文档和本迁移方案文档自身包含旧路径（用于对照说明），属于预期命中，不计为残留。

## 8. 验收标准

- [ ] 新路径下三模块均可独立运行
- [ ] `python -m flatbottom_pipeline.run_pipeline --preflight-only` 能正确检测前置条件（数据库连接、关键表、输出文件）
- [ ] `python -m flatbottom_pipeline.run_pipeline --step all` 在前置条件满足时能串行跑通链路 A
- [ ] `python -m flatbottom_pipeline.run_pipeline --step all` 在前置条件不满足时给出明确提示而非报错崩溃
- [ ] 关键输出正常生成：
  - `output/*_kline.png`（visualization）
  - 数据库表 `stock_flatbottom_preselect`（selection）
  - 数据库表 `stock_flatbottom_refinement`（refinement_llm）
- [ ] `pytest flatbottom_pipeline/tests/ -v` 全部通过
- [ ] `pytest -v` 全部通过（全仓递归发现，确保未破坏任何模块）
- [ ] 全量 grep 代码文件（`*.py`）无旧路径残留引用（含 import、patch 字符串、代码内命令示例）
- [ ] P0/P1 文档 grep 无旧命令路径残留
- [ ] `.env` 从项目根目录正确加载
- [ ] P0/P1 文档已全部更新（`common_commands.md`、`README.md` 及 P1 设计文档）
- [ ] P2 历史文档已添加迁移提示（若纳入本次范围）

## 9. 风险与应对

### 风险 1：路径引用遗漏

- **概率**：中（需修改项分三类：import 语句、mock patch 字符串、代码内命令示例，见 §5.3 A/B/C）
- **应对**：Phase 2 的三类全量 grep 检查 + 逐模块 import 冒烟测试。特别注意 `patch()` 字符串路径，它不会在 import 时报错，只会在测试运行时静默 mock 失效

### 风险 2：相对路径引用错误（output/、logs/）

- **概率**：中（`refinement_llm/config.py` 中有 `"./output"` 和 `"./logs"` 相对路径）
- **应对**：Phase 3 逐一检查各 config 文件，确保路径解析基于项目根目录而非模块目录
- **需检查的 config 文件清单**：
  - `flatbottom_pipeline/refinement_llm/config.py` — `DEFAULT_IMAGE_DIR`、`LOG_DIR`
  - `flatbottom_pipeline/selection/logger.py` — `LOG_DIR`

### 风险 3：pytest 测试发现遗漏

- **概率**：低（不修改 `testpaths`，保持 pytest 默认递归扫描）
- **应对**：不在 `pyproject.toml` 中设置 `testpaths`，确保 pytest 自动发现所有目录下的 `test_*.py`

## 10. 回滚方案

本次迁移通过 `git mv` 执行，完整保留 git 历史。若出现阻塞问题：

```bash
# 一键回滚（回到迁移前的 commit）
git revert <migration-commit-hash>
```

建议在独立分支上执行迁移，验收通过后再合入主分支。

## 11. 工时估算

| 阶段 | 工作量 | 预计耗时 |
|------|--------|---------|
| Phase 1：目录迁移与包化 | git mv + __init__.py | 0.5h |
| Phase 2：导入路径重写 | import + patch 字符串 + 命令示例 + grep 验证 | 1h |
| Phase 3：.env 路径确认 | 2 个 config 文件检查 | 0.5h |
| Phase 4：统一编排入口 | run_pipeline.py + preflight check 实现 | 2.5~3.5h |
| Phase 5：测试迁移与验证 | sys.path 清理 + 全量测试 | 0.5~1h |
| Phase 6：文档更新 | P0/P1 文档全量更新 + P2 添加迁移提示 | 1~2h |
| **合计** | | **6~8.5h（约 1~1.5 天）** |

## 12. 结论

本方案采用"**业务归业务、基础设施归基础设施**"的分离策略：
- 仅迁移 `selection`、`visualization`、`refinement_llm` 三个业务模块
- `data_infra` 保留在根目录作为公共数据基础设施
- 不设兼容层，一步到位
- 共享项目根目录 `.env`，不引入新的配置管理机制

相比 v1 方案，迁移范围更小、风险更低、耗时从 3~5 天缩减到约 1~1.5 天。
