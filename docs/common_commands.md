# 常见执行命令速查

## 流水线一键运行

```bash
# 跑通完整链路 A（select → plot → refine）
python -m flatbottom_pipeline.run_pipeline --step all

# 仅运行某个阶段
python -m flatbottom_pipeline.run_pipeline --step select
python -m flatbottom_pipeline.run_pipeline --step plot
python -m flatbottom_pipeline.run_pipeline --step refine

# 检查前置条件（不执行）
python -m flatbottom_pipeline.run_pipeline --preflight-only
```

## 选股（平底锅初筛）

```bash
# 使用默认预设
python -m flatbottom_pipeline.selection.find_flatbottom

# 指定预设
python -m flatbottom_pipeline.selection.find_flatbottom --preset aggressive
python -m flatbottom_pipeline.selection.find_flatbottom --preset balanced
python -m flatbottom_pipeline.selection.find_flatbottom --preset conservative

# 仅筛选文件内股票（每行一个 code）
python -m flatbottom_pipeline.selection.find_flatbottom -f flatbottom_pipeline/selection/check_list.txt

# 查看当前配置
python -m flatbottom_pipeline.selection.find_flatbottom --show-config
```

## 诊断（单股/批量）

```bash
# 单只股票诊断
python -m flatbottom_pipeline.selection.diagnose_code --code 600583

# 批量诊断（文件内多只）
python -m flatbottom_pipeline.selection.diagnose_code -f flatbottom_pipeline/selection/check_list.txt
```

## 月K图生成（visualization）

```bash
# 单只股票
python -m flatbottom_pipeline.visualization.plot_kline 600000

# 文件批量
python -m flatbottom_pipeline.visualization.plot_kline -f flatbottom_pipeline/visualization/stocks.txt

# 从预选表读取（按 score DESC）
python -m flatbottom_pipeline.visualization.plot_kline --from-preselect-table

# 从预选表读取并限制数量
python -m flatbottom_pipeline.visualization.plot_kline --from-preselect-table --preselect-limit 50
```

## 精细化筛选（LLM 视觉分析）

```bash
# 使用默认配置运行 (读取 ./output/*.png)
python -m flatbottom_pipeline.refinement_llm.main

# 指定 K 线图目录
python -m flatbottom_pipeline.refinement_llm.main --image-dir ./output

# 限制分析数量（测试用）
python -m flatbottom_pipeline.refinement_llm.main --limit 10

# 调整并发数
python -m flatbottom_pipeline.refinement_llm.main --concurrency 5

# 设定汇总评分阈值
python -m flatbottom_pipeline.refinement_llm.main --threshold 7.5

# 开启调试模式
python -m flatbottom_pipeline.refinement_llm.main --debug
```
