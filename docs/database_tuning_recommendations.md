# 数据库性能调优建议：A股分时数据全量加载

本着“**以最小的持久性风险换取最大的写入吞吐量**”的原则，针对 75 亿行 A 股分时数据（约 300GB+）的首次全量加载任务，基于您的硬件配置（8 Core / 32GB RAM / SSD），提出以下 PostgreSQL 参数调整建议。

> **⚠️ 注意**：以下配置主要针对**批量导入阶段**优化。数据加载完成并建立索引后，建议恢复部分安全性设置（特别是 `synchronous_commit` 和 `autovacuum`）。

## 1. 核心加速参数 (性能提升的关键)

请优先应用以下设置。它们能显著减少磁盘 I/O 等待，将写入速度提升 2-5 倍。

| 参数名 | 当前值 | **建议值** | 说明 |
| :--- | :--- | :--- | :--- |
| `synchronous_commit` | `on` (默认) | **`off`** | **最关键优化**。允许事务提交后立即返回，无需等待 SSD 物理落盘。风险仅限于数据库崩溃时丢失最近 <1秒的数据（可通过脚本断点续传恢复）。 |
| `max_wal_size` | `4GB` | **`20GB`** | 增大 WAL 日志容量，大幅减少 Checkpoint（全量刷盘）的频率，平滑 I/O 峰值。 |
| `checkpoint_timeout` | `15min` | **`30min`** | 延长强制 Checkpoint 的间隔，充分利用内存缓冲写入。 |

## 2. 内存与并发优化

利用 32GB 内存优势，减少 I/O 争用。

| 参数名 | 当前值 | **建议值** | 说明 |
| :--- | :--- | :--- | :--- |
| `wal_buffers` | `16MB` | **`64MB`** | 增大 WAL 写入缓冲区，防止多进程并行写入时日志缓冲区成为瓶颈。 |
| `maintenance_work_mem`| `1GB` | **`4GB`** | 加速后续的索引创建和 Vacuum 操作（如果加载过程中触发）。 |
| `autovacuum` | `on` | **`off`** | **仅加载期间关闭**。避免后台清理进程在全速写入时争抢磁盘 I/O。**务必在加载完成后重新开启并手动执行 VACUUM ANALYZE。** |

## 3. 实施步骤

您可以通过 SQL 命令动态修改这些参数（大部分无需重启，除 `wal_buffers` 外），或者直接修改 `postgresql.conf` 文件。

### 方式 A: SQL 动态修改 (推荐，无需重启数据库服务，部分生效)

```sql
-- 1. 允许异步提交 (立即生效，无需重启)
ALTER SYSTEM SET synchronous_commit = 'off';

-- 2. 调整 Checkpoint 策略 (立即生效，无需重启)
ALTER SYSTEM SET max_wal_size = '20GB';
ALTER SYSTEM SET checkpoint_timeout = '30min';

-- 3. 临时关闭自动清理 (立即生效，无需重启)
ALTER SYSTEM SET autovacuum = 'off';

-- 4. 应用配置
SELECT pg_reload_conf();
```

> **注意**: `wal_buffers` 修改需要重启数据库才能生效。如果不想重启，可以跳过它，仅应用上述 4 项也能获得 90% 的性能提升。

### 方式 B: 修改配置文件 (需重启)

在 `postgresql.conf` 中找到对应行并修改：

```ini
synchronous_commit = off
max_wal_size = 20GB
checkpoint_timeout = 30min
wal_buffers = 64MB
maintenance_work_mem = 4GB
autovacuum = off
```

修改后重启 PostgreSQL 服务。

## 4. 加载后的收尾工作 (🚨 必须执行)

数据加载全部完成后，**必须**执行以下操作以恢复数据库至生产状态。如果不执行，将面临严重风险！

1.  **恢复关键配置**:
    *   **`autovacuum = on` (必改)**: 如果长期关闭，数据库表会无限膨胀，严重时会导致事务 ID 回卷 (Wraparound)，**引发数据库宕机且难以恢复**。
    *   **`synchronous_commit = on` (必改)**: 恢复数据的强一致性。否则数据库一旦崩溃，会丢失已提交的交易记录，这对金融数据是不可接受的。
    *   `max_wal_size`: 可选。您可以将其保留在 `8GB` - `12GB` 以获得更好的日常性能，或者恢复默认值以节省磁盘空间。

    ```sql
    -- 1. 恢复数据强一致性 (必须)
    ALTER SYSTEM SET synchronous_commit = 'on';

    -- 2. 恢复自动清理 (必须)
    ALTER SYSTEM SET autovacuum = 'on';

    -- 3. 调整 WAL 大小 (可选，建议保留 8GB 或恢复默认)
    -- ALTER SYSTEM RESET max_wal_size; -- 恢复默认
    ALTER SYSTEM SET max_wal_size = '8GB'; -- 或保留适度大小

    -- 4. 生效配置
    SELECT pg_reload_conf();
    ```

2.  **手动维护 (VACUUM ANALYZE)**:
    由于加载期间我们关闭了 `autovacuum`，且进行了海量写入，数据库目前处于“统计信息缺失”和“潜在空间未回收”的状态。
    *   **为什么要执行？**
        1.  **更新统计信息**: 告诉查询优化器表里到底有多少数据、分布如何。如果没有它，查询（如“查询某只股票”）可能会全表扫描，速度极慢。
        2.  **标记死元组**: 清理加载过程中可能产生的死数据（Dead Tuples），让后续写入能复用空间。
    *   **执行命令**:
        ```sql
        -- 这是一个重型操作，可能需要几分钟到十几分钟
        -- 务必等待其完成
        VACUUM ANALYZE stock_1min_qfq;
        ```
