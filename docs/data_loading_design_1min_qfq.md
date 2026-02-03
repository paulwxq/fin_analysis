# A股分时数据加载模块设计文档

## 1. 概述
本模块旨在将存储在 `/mnt/d/BaiduNetdiskDownload/A股分时数据/A股_分时数据_沪深/1分钟_前复权_按年汇总` 目录下的 A股 1分钟前复权分时数据（Zip压缩包格式）高效加载到 PostgreSQL 18 + TimescaleDB 数据库中。

## 2. 目标环境
- **操作系统**: Linux (WSL)
- **数据库**: PostgreSQL 18
- **扩展**: TimescaleDB
- **数据库名**: `fin_db`
- **主机**: `172.29.128.1`
- **用户**: `postgres`
- **密码**: `PostgreSQL-18`

## 3. 数据源分析
- **路径**: `/mnt/d/BaiduNetdiskDownload/A股分时数据/A股_分时数据_沪深/1分钟_前复权_按年汇总`
- **文件格式**: Zip 压缩包（按年命名，如 `2000_1min.zip`）。
- **包内文件**: CSV 文件（按股票代码命名，如 `sh600000_2000.csv`）。
- **文件结构摘要**:
  ```csv
  时间,代码,名称,开盘价,收盘价,最高价,最低价,成交量,成交额,涨幅,振幅
  2000-06-09 09:30:00,sh600000,浦发银行,-2.01,-2.01,-2.01,-2.01,129,309600,0.0,-0.0
  ```
- **CSV 结构**:
  - 编码: **UTF-8-SIG** (自动处理 BOM)
  - 头部: `时间,代码,名称,开盘价,收盘价,最高价,最低价,成交量,成交额,涨幅,振幅`

### 3.1 实际数据验证
已对源数据目录及参考代码进行实际抽样验证：
1.  **文件抽样**:
    -   `2000_1min.zip`: 包含早期数据，部分价格显示为负值（如 `-2.01`）。
        -   **关于负数价格**: 经查证，这是前复权（尤其是减法复权）的正常现象。对于长期高分红的股票，累计分红可能超过早期股价，导致调整后价格为负。**这是真实数据，数据库必须支持存储负值。**
    -   `2023_1min.zip`: 包含近期数据，格式一致，价格为正值（如 `6.21`）。
    -   所有CSV文件均包含统一的头部：`时间,代码,名称,开盘价,收盘价,最高价,最低价,成交量,成交额,涨幅,振幅`。
2.  **代码参考**:
    -   参考路径: `/mnt/d/BaiduNetdiskDownload/复权因子/分钟数据前复权代码/stock_a_1min_qfq.py`
    -   确认逻辑: 该脚本读取原始分钟数据并应用复权因子。生成的列顺序与上述CSV结构完全一致。
    -   **关键发现**: 代码中包含 `parse_ts_code` 函数，将 `sh600000` 转换为 `600000.SH`，本加载模块应复用此逻辑以保持代码标准化。

## 4. 数据库设计

### 4.1 表结构
目标表名为 `stock_1min_qfq`。采用标准的 OHLC 字段顺序，但在加载时需注意与 CSV 顺序的映射。

**字段映射对照表**:
| CSV 列名 | 数据库字段 | 说明 |
| :--- | :--- | :--- |
| 时间 | `time` | |
| 代码 | `code` | 需标准化 (如 `sh600000` -> `600000.SH`) |
| 名称 | `name` | |
| 开盘价 | `open` | |
| **收盘价** | **`close`** | **注意：CSV中在第5列** |
| **最高价** | **`high`** | **注意：CSV中在第6列** |
| **最低价** | **`low`** | **注意：CSV中在第7列** |
| 成交量 | `volume` | |
| 成交额 | `amount` | |
| 涨幅 | `change_pct` | |
| 振幅 | `amplitude` | |

```sql
CREATE TABLE IF NOT EXISTS stock_1min_qfq (
    time        TIMESTAMP NOT NULL, -- 使用不带时区的时间戳，存储交易所本地时间（北京时间）
    code        TEXT NOT NULL,
    name        TEXT,
    open        NUMERIC(16, 4), -- 指定精度，支持负数
    high        NUMERIC(16, 4),
    low         NUMERIC(16, 4),
    close       NUMERIC(16, 4),
    volume      BIGINT,
    amount      NUMERIC(20, 4), -- 成交额可能较大
    change_pct  NUMERIC(10, 4),
    amplitude   NUMERIC(10, 4),
    -- 优化索引策略：
    -- 使用 (code, time) 作为唯一约束，既满足去重，又天然优化了 "按代码查询时间序列" 的场景。
    -- 这样可以省去额外的 (code, time) 辅助索引，大幅降低写入开销。
    UNIQUE (code, time)
);
```

### 4.2 TimescaleDB Hypertable
将 `stock_1min_qfq` 转换为超表，按 `time` 分区。

```sql
-- 转换为 Hypertable，显式指定 Chunk 时间间隔为 7 天
SELECT create_hypertable('stock_1min_qfq', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- 启用压缩功能
ALTER TABLE stock_1min_qfq SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'code',
    timescaledb.compress_orderby = 'time DESC'
);

-- 注意：由于是加载大量历史数据，不建议立即添加自动压缩策略。
-- 建议在数据加载全部完成后，手动执行全量压缩以立即释放空间和提升性能。
-- 手动压缩示例（加载完成后执行）：
-- SELECT compress_chunk(i) from show_chunks('stock_1min_qfq') i;
```

## 5. 模块设计

### 5.1 目录结构
在项目根目录下创建 `load_data` 模块：

```
/opt/fin_analysis/
├── .env                  # 数据库连接信息
├── pyproject.toml        # 依赖管理
├── load_data/
│   ├── __init__.py
│   ├── config.py         # 配置加载 (读取 .env)
│   ├── db.py             # 数据库连接与初始化
│   ├── utils.py          # 工具函数 (代码转换等)
│   ├── loader.py         # 数据加载核心逻辑
│   └── main.py           # 入口脚本
```

### 5.2 依赖管理
使用 `uv` 管理依赖。需要在 `pyproject.toml` 中添加以下依赖：
- `psycopg[binary]`: 高性能 PostgreSQL 驱动 (v3)。
- `python-dotenv`: 加载环境变量。
- `tqdm`: 进度条显示。
- **摒弃 Pandas**:
  - 为了最大化性能和最小化内存占用，**不使用 Pandas**。
  - 采用 Python 标准库 `csv` + `io.StringIO` 进行流式处理。
  - 理由: 纯 Python 处理在生成 `COPY` 文本流时更直接、更轻量，避免了 DataFrame 的内存开销。

### 5.3 核心逻辑

#### 5.3.1 配置 (config.py)
配置项应通过环境变量 ( `.env` ) 和 `config.py` 结合管理：

| 参数项 | 说明 | 来源 | 默认值/示例 |
| :--- | :--- | :--- | :--- |
| `DB_DSN` | 数据库连接串 | `.env` | `postgresql://postgres:PostgreSQL-18@172.29.128.1:5432/fin_db` |
| `DATA_DIR` | 源数据 Zip 目录 | `config.py` | `/mnt/d/BaiduNetdiskDownload/.../按年汇总` |
| `MAX_WORKERS` | 并行进程数 | `config.py` | 取 min(本地CPU核心数, 数据库核心数 * 2)。建议 8-16，避免过度竞争。 |
| `BATCH_SIZE` | 批量提交的行数阈值 | `config.py` | 50,000 行 (一个事务包含的行数) |
| `MAX_SKIPPED_ROWS` | 允许跳过的最大坏行数 | `config.py` | 1000 行 (超过则标记 FAILED) |
| `MAX_SKIPPED_RATIO` | 允许跳过的坏行比例 | `config.py` | 0.01 (1%) |
| `LOG_LEVEL` | 日志级别 | `config.py` | `INFO` |
| `STANDARDIZE_CODE` | 是否标准化股票代码 | `config.py` | `True` |

#### 5.3.2 数据库操作 (db.py)
- 提供 `get_db_connection()` 函数。
- 提供 `init_db()` 函数，用于创建表和 Hypertable。同时创建**加载日志表**用于断点续传：
    ```sql
    CREATE TABLE IF NOT EXISTS load_log (
        filename TEXT PRIMARY KEY, -- 存储文件名（假设同目录下无重名）。
        processed_at TIMESTAMP DEFAULT NOW(),
        status TEXT, -- 'SUCCESS', 'WARNING', 'FAILED'
        skipped_lines INTEGER DEFAULT 0,
        error_msg TEXT,
        file_size BIGINT, -- 增加文件大小校验，防止同名文件内容变更被忽略
        last_modified TIMESTAMP -- 增加文件修改时间校验
    );
    ```
- 提供 `bulk_insert(cursor, data_io)` 函数。
  - **重复数据处理策略 (临时表方案)**:
    1.  **创建临时表**: 必须在当前事务/会话中创建。
        ```sql
        -- 使用 LIKE 复制目标表结构，ON COMMIT DROP 确保事务结束后自动清理
        CREATE TEMP TABLE tmp_stock_1min_qfq (
            LIKE stock_1min_qfq INCLUDING DEFAULTS
        ) ON COMMIT DROP;
        ```
    2.  **COPY 写入**: 将内存中的 CSV 数据流写入临时表。
        - **关键**: `COPY` 语句的列顺序必须与 **内存 Buffer (即源 CSV)** 的列顺序严格一致。
        - CSV源顺序: `时间, 代码, 名称, 开盘, 收盘, 最高, 最低...`
        ```sql
        COPY tmp_stock_1min_qfq (time, code, name, open, close, high, low, volume, amount, change_pct, amplitude)
        FROM STDIN WITH (FORMAT CSV, HEADER FALSE);
        ```
    3.  **合并数据**:
        ```sql
        INSERT INTO stock_1min_qfq (
            time, code, name, open, close, high, low, volume, amount, change_pct, amplitude
        )
        SELECT 
            time, code, name, open, close, high, low, volume, amount, change_pct, amplitude
        FROM tmp_stock_1min_qfq
        ON CONFLICT (code, time) DO NOTHING;
        ```

#### 5.3.3 工具函数 (utils.py)
- `transform_code(raw_code)`: 将原始代码标准化为 `Code.Exchange` 格式。参考现有代码逻辑，规则如下：
    - 以 `sh` 开头 (如 `sh600000`) -> 去除前缀，加 `.SH` (如 `600000.SH`)
    - 以 `sz` 开头 (如 `sz000001`) -> 去除前缀，加 `.SZ` (如 `000001.SZ`)
    - 以 `bj` 开头 (如 `bj430090`) -> 去除前缀，加 `.BJ` (如 `430090.BJ`)
    - 其他格式 -> 记录警告日志并原样保留或抛出异常（视严格程度而定）。

#### 5.3.4 加载器 (loader.py)
核心处理流程（运行在 Worker 进程中）：
1.  **文件读取**: 使用 `zipfile` 打开 Zip 包。
2.  **流式处理**: 遍历包内 CSV 文件。
    - 打开 CSV 文件时指定 `encoding='utf-8-sig'` 以自动去除 **BOM**。
    - **头部校验**: 读取第一行并校验**所有 11 个列名**是否符合预期，防止列顺序错位。
        - **失败处理**: 若校验失败，标记文件 `FAILED`，并**立即终止后续处理**（不再处理该 Zip 内剩余的 CSV）。注意：若 Zip 内之前已处理的 CSV 数据已分批提交，该部分数据会保留在数据库中（重跑时会自动去重）。
        - 校验通过后丢弃该行。
    - 逐行读取 CSV。
3.  **数据清洗与转换 (内存中)**:
    - **预校验规则**:
        - **必填项**: `Time`, `Code` 字段不能为空。
        - **时间格式**: 截取前 19 位字符（忽略毫秒），验证是否符合 `YYYY-MM-DD HH:MM:SS`。
        - **价格校验**: `Open`, `Close`, `High`, `Low` 字段**不允许为空/NULL**，且必须能被解析为数字。如果为空或非数字，视为坏行跳过。
        - **非核心字段**: `Volume`, `Amount` 等允许为空。
            - **Volume 特殊处理**: 必须为整数。
            - **精度安全**: 优先尝试整型解析。若遇到浮点格式（如 `123.0` 或 `1E6`），在确保不超过精度安全范围（如 9e15）且实质为整数的前提下，允许转换为整型字符串；否则视为坏行。
        - **空值处理**:
            - Python 端：将空值转换为 `None` 或空字符串 `""`。
            - 写入 Buffer：`csv.writer` 会将 `None` 写入为 `""`。
            - DB 入库：`COPY` 命令中需指定 `NULL ''` 选项，将空字符串正确映射为 SQL `NULL`。
    - **Try-Catch**: 尝试解析字段。如果校验失败，**记录错误并跳过该行**。
    - **转换**: 调用 `utils.transform_code` 标准化股票代码。
    - **写入**:
        - **强制使用 `csv.writer`**: 必须使用 Python 的 `csv.writer(string_io)` 将清洗后的数据写入 Buffer。
        - **禁止字符串拼接**: 严禁使用 `f"{a},{b}..."` 格式，以防止 `name` 字段中包含逗号或引号导致 `COPY` 命令解析错位。
4.  **批量提交**:
    - 当缓冲区行数达到 `BATCH_SIZE` 时，获取 DB 连接，调用 `bulk_insert` 提交事务，然后清空缓冲区。

### 5.4 并行策略
鉴于临时表是**会话级 (Session-level)** 的，采用 **独立 Worker (Independent Workers)** 模型：

- **并行度控制**:
    - **约束**: 并行度受限于本地 CPU、数据库服务器 CPU 以及写入吞吐性能。
    - **建议**: `MAX_WORKERS` 设置为 **min(本地CPU, 数据库CPU * 2)**。例如对于 8 核数据库服务器，建议设置为 8~16。过高的并行度会导致数据库端产生严重的锁竞争和 WAL 瓶颈，反而降低总体吞吐。
- **架构**: `ProcessPoolExecutor` 启动多个 Worker 进程。
- **任务分配**: 主进程扫描所有 Zip 文件，将其路径作为任务分发给 Worker。
- **Worker 职责**:
    - 每个 Worker 进程独立维护**自己**的数据库连接。
    - 独立执行完整的 `读取 -> 解析 -> 缓冲 -> 事务(创建临时表/COPY/Insert/Commit)` 流程。
    - 这种模式真正实现了 Share-Nothing 架构，避免了锁竞争和事务冲突。

### 5.5 错误处理与日志

#### 5.5.1 异常捕获策略
- **Zip 文件损坏**: 在解压/打开 Zip 时捕获 `zipfile.BadZipFile` 等异常。记录错误日志（包含文件名），**跳过**该文件，不中断主流程。
- **CSV 解析/数据转换错误**:
    - 在解析 CSV 行或转换数据类型时，使用 `try...except` 块。
    - 若某行数据异常（如非数字字符），记录详细错误（Zip名, CSV文件名, 行号, 内容），**跳过**该行。
- **数据库错误**:
    - 若发生瞬断，抛出异常中止程序（或实现简单的重试机制）。依赖外部调度或人工重启。

#### 5.5.2 日志记录
- 使用 Python `logging` 模块。
- **Console**: 输出进度 (tqdm) 和 INFO 级别关键节点信息。
- **File (`load_errors.log`)**: 专门记录 ERROR/WARNING 级别日志，格式：
  `[时间] [ERROR] 文件: 2000_1min.zip/sh600000.csv - 原因: 无法解析价格 '-2.01-'`

#### 5.5.3 恢复机制 (Checkpointing)
为了避免重启脚本时重复扫描已处理的大型 Zip 文件，实现精细化的文件级断点续传：

1.  **状态定义**:
    Worker 进程在处理完一个 Zip 文件后，根据结果写入 `load_log`（同时记录文件大小和修改时间）：
    -   **SUCCESS**: 所有行均成功入库 (`skipped_lines == 0`)。
    -   **WARNING**: 处理完成，但有少量行因格式错误被跳过 (`0 < skipped_lines < 阈值`)。这通常表示源文件有个别坏数据，但整体可用。
    -   **FAILED**:
        -   发生系统级错误（数据库断连、磁盘错误）。
        -   或者 **跳过行数超过阈值**（如 > 1000 行或 > 1%），视为文件严重损坏。
2.  **跳过逻辑**:
    -   脚本启动时，检查 `load_log` 中是否存在同名文件。
    -   **校验一致性**: 仅当状态为 `SUCCESS`/`WARNING` **且** `file_size` 与 `last_modified` 与当前文件一致时，才跳过。
        -   **时间容差**: `last_modified` 比对允许 2 秒误差，以兼容不同文件系统或数据库的时间精度差异。
        -   **元数据缺失**: 若 DB 中无元数据（NULL），视为不匹配，强制重跑。
    -   自动重跑状态为 `FAILED` 或文件变动过的记录。
3.  **强制重跑选项**:
    -   `--retry-warnings`: 重跑状态为 `WARNING` 的文件（用于修复代码逻辑或源文件后）。
    -   `--force`: 忽略所有日志，强制重跑所有文件。

### 5.6 性能预估
- **数据总量**:
  - 约 5000 只股票 x 25 年数据。
  - 估算行数: 75 亿+ 行。
  - 原始数据量: 300GB+。
- **资源瓶颈**:
  - **IO (Disk)**: 数据库写入 WAL 和数据文件将是最大瓶颈。
  - **CPU**: Python 解析 CSV 和 Zip 解压需要多核支持。
- **配置依赖**:
  - 为达到最佳性能（< 10小时），**强烈建议**在加载期间应用以下优化（详见 `docs/database_tuning_recommendations.md`）：
    - `synchronous_commit = off` (关键：提升 2-5 倍速度)
    - `max_wal_size = 20GB`
    - `checkpoint_timeout = 30min`
    - `autovacuum = off` (仅加载期)
    - **重要警告**: 加载完成后，**必须**将 `autovacuum` 和 `synchronous_commit` 恢复默认值，否则面临数据丢失和数据库损坏的风险。详见调优文档。
- **耗时估算**:
  - **默认配置**: 20 - 26 小时。
  - **优化配置**: **7 - 10 小时**。
  - 单 Worker 峰值速度可达 20,000+ 行/秒，总吞吐量 20万+ 行/秒。

## 6. 实施步骤

1. **添加依赖**:
   ```bash
   uv add psycopg[binary] python-dotenv tqdm
   ```

2. **配置环境**:
   在 `.env` 中设置数据库连接串。

3. **编写代码**:
   按照上述模块结构编写代码。

4. **执行加载**:
   运行 `python -m load_data.main`。

5. **验证**:
   查询数据库确认数据完整性。
