# Deep Research 实现原理与提示词设计指南

## 📚 概述

Deep Research 是一个智能的多轮深度研究系统，通过**递归搜索**和**动态提示词**技术，实现从广泛到精准的渐进式知识探索。

**核心特点：**
- 🌳 树状探索：先广度发散，再深度聚焦
- 🧠 知识累积：每轮学习成果自动传递到下一轮
- 🔄 自适应提示词：无需预设多个模板，动态构建上下文
- 🎯 智能收拢：自动去重合并，生成统一报告

---

## 🎯 核心设计思想

### 分而治之策略

就像人类研究员的思考过程：

1. **初步探索（广度）**：从多个角度同时了解话题
2. **深入研究（深度）**：针对每个角度继续追问
3. **知识整合（收拢）**：将所有发现汇总成报告

### 关键参数

- **breadth（广度）**：每轮生成几个并行搜索查询（1-10）
- **depth（深度）**：总共研究几轮（1-5）

### 自动收拢机制

- 每深入一层，breadth 自动减半（`breadth // 2`）
- 使用 `max(1, ...)` 确保至少保留1个查询
- 最终用集合（set）去重合并所有结果

---

## 🔧 实现原理

### 1. 多轮搜索的递归机制

**核心代码逻辑：**

```python
async def deep_research(query, breadth, depth, learnings=[], visited_urls=[]):
    # 生成搜索查询（数量 = breadth）
    serp_queries = await generate_serp_queries(query, num_queries=breadth, learnings=learnings)
    
    # 并行执行所有查询
    for serp_query in serp_queries:
        # 1. 执行搜索
        result = firecrawl.search(serp_query.query)
        
        # 2. 提取 learnings 和 follow-up questions
        processed = await process_serp_result(result)
        all_learnings = learnings + processed["learnings"]
        
        # 3. 判断是否继续深入
        new_breadth = max(1, breadth // 2)  # 减半
        new_depth = depth - 1
        
        if new_depth > 0:
            # 4. 递归调用（关键！）
            next_query = f"Previous goal: {research_goal}\nFollow-up: {follow_up_questions}"
            deeper_result = await deep_research(
                next_query,
                new_breadth,     # 传递减半后的breadth
                new_depth,       # 传递递减后的depth
                all_learnings,   # 传递累积的learnings
                all_urls
            )
            return deeper_result
    
    # 5. 收拢：合并所有分支结果
    return merge_all_results()
```

**关键点：**
- 每个查询分支独立递归
- learnings 跨层累积传递
- breadth 自动递减控制规模

---

### 2. 参数控制与收拢

**breadth 递减规则：**

| 初始 breadth | 第1轮 | 第2轮 | 第3轮 | 第4轮 |
|-------------|-------|-------|-------|-------|
| 10 | 10 | 5 | 2 | 1 |
| 6 | 6 | 3 | 1 | 1 |
| 3 | 3 | 1 | 1 | 1 |
| 1 | 1 | 1 | 1 | 1 |

**收拢实现：**

```python
# 并发执行所有查询
results = await asyncio.gather(*tasks)

# 合并结果（自动去重）
all_learnings = set()
all_urls = set()

for result in results:
    all_learnings.update(result.learnings)
    all_urls.update(result.visited_urls)

return ResearchResult(
    learnings=list(all_learnings),
    visited_urls=list(all_urls)
)
```

---

## 💡 提示词设计体系

### 设计理念

**统一系统提示词 + 动态任务提示词**

不需要为每轮编写不同提示词，而是通过**条件拼接**实现上下文演进。

---

### 提示词1：系统提示词（基础层）

**位置：** `src/prompt.py`  
**作用：** 定义AI研究员角色，所有调用共享

```
You are an expert researcher. Today is {current_time}.
- Be highly organized and detailed
- Treat the user as an expert
- Value good arguments over authorities
- Consider new technologies and contrarian ideas
...
```

---

### 提示词2：生成搜索查询（核心层）

**位置：** `src/deep_research.py` - `generate_serp_queries()`  
**作用：** 根据当前问题和已有知识生成搜索查询

**第1轮（无历史知识）：**

```
Given the following prompt from the user, generate a list of SERP queries 
to research the topic. Return a maximum of {num_queries} queries...

<prompt>{user_question}</prompt>
```

**第2+轮（带历史知识）：**

```
<prompt>{user_question}</prompt>

Here are some learnings from previous research, use them to generate 
more specific queries:
- {learning_1}
- {learning_2}
- {learning_3}
...
```

**输出格式：**
```json
{
  "queries": [
    {
      "query": "具体搜索词",
      "research_goal": "研究目标和后续方向"
    }
  ]
}
```

---

### 提示词3：提取知识点（核心层）

**位置：** `src/deep_research.py` - `process_serp_result()`  
**作用：** 从网页内容中提取结构化知识

```
Given the following contents from a SERP search for the query 
<query>{search_query}</query>, generate a list of learnings...

The learnings should be:
- Concise and information dense
- Include entities (people, places, companies, products)
- Include exact metrics, numbers, or dates
- Unique and not similar to each other

<contents>
  <content>{webpage_content_1}</content>
  <content>{webpage_content_2}</content>
  ...
</contents>
```

**输出格式：**
```json
{
  "learnings": [
    "知识点1：包含实体、数字、日期",
    "知识点2：信息密集",
    "知识点3：独特不重复"
  ],
  "follow_up_questions": [
    "追问1：深入某个方面",
    "追问2：探索相关领域",
    "追问3：验证关键信息"
  ]
}
```

---

### 提示词4：生成最终报告（输出层）

**位置：** `src/deep_research.py` - `write_final_report()`  
**作用：** 将所有learnings整合成详细报告

```
Given the following prompt from the user, write a final report on the 
topic using the learnings from research. Make it as detailed as possible, 
aim for 3 or more pages, include ALL the learnings from research:

<prompt>{user_question}</prompt>

Here are all the learnings from previous research:

<learnings>
  <learning>{累积的知识点1}</learning>
  <learning>{累积的知识点2}</learning>
  ...共几十条...
</learnings>
```

**输出：** Markdown格式的详细研究报告

---

### 提示词5：生成简短答案（输出层）

**位置：** `src/deep_research.py` - `write_final_answer()`  
**作用：** 当用户需要精确答案而非报告时使用

```
Given the following prompt from the user, write a final answer...
Keep the answer as concise as possible - usually just a few words 
or maximum a sentence. Follow the format specified in the prompt.

<prompt>{user_question}</prompt>

<learnings>
  {所有learnings}
</learnings>
```

**输出：** 简短精确的答案

---

## 📖 完整示例

### 场景设置

**用户问题：** "量子计算的最新进展"  
**参数：** `breadth=3, depth=3`

---

### 🎬 第1轮执行（depth=3, breadth=3）

#### 步骤1：生成搜索查询

**使用提示词2（无历史learnings）**

AI生成3个查询：
- 查询A: "2024量子计算突破性技术"
- 查询B: "IBM谷歌量子计算机进展"
- 查询C: "量子纠错算法最新研究"

#### 步骤2：并行搜索

3个查询同时执行，搜索并爬取网页内容。

#### 步骤3：提取知识

**对每个查询使用提示词3**

**查询A提取的learnings：**
- "IBM在2024年推出433量子比特Osprey处理器"
- "量子退相干时间延长至100微秒"
- "中国祖冲之号实现66量子比特量子优越性"

**查询A生成的follow-up questions（3个）：**
- "Osprey处理器的纠错率是多少？"
- "如何延长退相干时间？"
- "量子优越性的实际应用场景？"

**查询B、C同样处理，各得到3个learnings**

#### 第1轮结果

- **总learnings：** 9个（3×3）
- **总follow-up questions：** 9个
- **访问URLs：** 约15个

---

### 🔍 第2轮执行（depth=2, breadth=1）

**参数变化：**
```python
new_breadth = max(1, 3 // 2) = 1
new_depth = 3 - 1 = 2
```

#### 步骤1：生成搜索查询

**使用提示词2（带上第1轮的9个learnings）**

构建的查询内容：
```
Previous research goal: 探索2024年量子计算突破性技术

Follow-up research directions:
- Osprey处理器的纠错率是多少？
- 如何延长退相干时间？
- 量子优越性的实际应用场景？

Here are some learnings from previous research:
- IBM在2024年推出433量子比特Osprey处理器
- 量子退相干时间延长至100微秒
- 中国祖冲之号实现66量子比特量子优越性
- [其他6个learnings...]
```

AI生成**1个**更精准的查询（因为breadth=1）：
- 查询A-1: "IBM Osprey量子处理器纠错技术详解"

#### 步骤2：搜索并提取

**使用提示词3提取新learnings：**
- "Osprey采用表面码纠错方案，逻辑错误率0.1%"
- "需要1000个物理量子比特支持1个逻辑比特"
- "表面码纠错延迟约10毫秒"

#### 第2轮结果

- **累积learnings：** 9 + 3 = 12个
- **分支B、C也各自深入，总共：** 9 + 9 = 18个

---

### 🔬 第3轮执行（depth=1, breadth=1）

**参数变化：**
```python
new_breadth = max(1, 1 // 2) = max(1, 0) = 1
new_depth = 2 - 1 = 1
```

#### 继续深入

使用提示词2，带上**18个learnings**，生成更细致的查询：
- 查询A-1-1: "量子表面码vs Shor码纠错效率对比"

提取更深层次的learnings...

#### 第3轮结果

- **累积learnings：** 约27个

---

### 🏁 第4轮（depth=0，停止递归）

**判断条件：** `if new_depth > 0` → `0 > 0` 为False

**停止递归，开始收拢！**

---

### 🎯 收拢与生成报告

#### 步骤1：合并所有结果

```python
# 所有分支的learnings自动去重合并
all_learnings = set([
    第1轮A的3个, B的3个, C的3个,
    第2轮A-1的3个, B-1的3个, C-1的3个,
    第3轮A-1-1的3个, B-1-1的3个, C-1-1的3个
])
# 去重后约25个独特learnings
```

#### 步骤2：生成最终报告

**使用提示词4，带上所有25个learnings：**

```
<prompt>量子计算的最新进展</prompt>

<learnings>
  <learning>IBM在2024年推出433量子比特Osprey处理器</learning>
  <learning>量子退相干时间延长至100微秒</learning>
  ...共25条...
</learnings>
```

AI生成详细的Markdown报告，包含：
- 引言
- 硬件进展（基于相关learnings）
- 纠错技术（基于相关learnings）
- 应用前景
- 结论
- 来源列表

---

## 📊 执行统计

| 轮次 | depth | breadth | 每分支查询 | 总查询数 | 累积learnings |
|------|-------|---------|-----------|---------|---------------|
| 第1轮 | 3 | 3 | 3 | 3 | 9 |
| 第2轮 | 2 | 1 | 1 | 3 | 18 |
| 第3轮 | 1 | 1 | 1 | 3 | 27 |
| 收拢 | 0 | - | - | **总计9次** | **去重后~25** |

---

## 🎨 设计亮点总结

### 1. 智能的提示词演进

**无需预设多个模板**，通过动态拼接实现：

- 第1轮：仅原始问题
- 第2轮：原始问题 + 第1轮learnings
- 第3轮：原始问题 + 第1、2轮所有learnings

就像**滚雪球**，上下文自动增长！

### 2. 自然的规模控制

- **广度递减**：`breadth // 2` 每层减半
- **深度递减**：`depth - 1` 每层减一
- **保底机制**：`max(1, ...)` 确保不为0

形成**倒金字塔**结构：先广撒网，越深越聚焦。

### 3. 高效的并发架构

```python
# 同一层的查询并行执行
tasks = [process_query(q) for q in queries]
results = await asyncio.gather(*tasks)
```

**时间复杂度：** O(depth) 而非 O(breadth^depth)

### 4. 智能的知识管理

- **跨层传递**：learnings 通过函数参数传递
- **跨分支共享**：所有分支的learnings都传给下一轮
- **自动去重**：使用set合并最终结果

### 5. 结构化输出

所有提示词都使用JSON Schema强制结构化输出：

```python
schema = {
    "type": "object",
    "properties": {
        "learnings": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}}
    }
}
```

确保返回格式可靠，便于程序处理。

---

## 🔑 核心代码位置

| 功能 | 文件路径 | 函数名 |
|-----|---------|--------|
| 系统提示词 | `src/prompt.py` | `system_prompt()` |
| 多轮研究主函数 | `src/deep_research.py` | `deep_research()` |
| 生成搜索查询 | `src/deep_research.py` | `generate_serp_queries()` |
| 提取知识点 | `src/deep_research.py` | `process_serp_result()` |
| 生成报告 | `src/deep_research.py` | `write_final_report()` |
| 生成答案 | `src/deep_research.py` | `write_final_answer()` |
| 生成澄清问题 | `src/feedback.py` | `generate_feedback()` |

---

## 💻 使用示例

### 基础调用

```python
result = await deep_research(
    query="AI在医疗领域的应用",
    breadth=3,  # 每轮3个并行查询
    depth=2     # 共2轮研究
)

print(f"发现 {len(result.learnings)} 个知识点")
print(f"访问 {len(result.visited_urls)} 个网站")
```

### 通过MCP接口

```json
{
  "name": "deep_web_research",
  "arguments": {
    "query": "AI在医疗领域的应用",
    "breadth": 3,
    "depth": 2,
    "output_type": "report",
    "generate_followup": true
  }
}
```

---

## 🎯 适用场景

### ✅ 适合使用

- 复杂话题需要多角度研究
- 需要深入了解某个领域
- 信息分散在多个来源
- 需要最新的实时信息

### ⚠️ 不太适合

- 简单事实查询（单次搜索即可）
- 需要极快响应的场景（深度研究耗时较长）
- 封闭性问题（如数学证明）

---

## 🚀 优化建议

### 参数调优

**快速探索：** `breadth=3, depth=2`（约5-10次查询）  
**平衡模式：** `breadth=4, depth=3`（约15-20次查询）  
**深度研究：** `breadth=5, depth=4`（约40-50次查询）

### 成本控制

- 减少depth可显著降低成本（指数级影响）
- breadth影响较小（线性影响第一轮）
- 使用`CONCURRENCY_LIMIT`控制并发数

---

## 📝 总结

Deep Research 通过**递归+并发+动态提示词**的组合，实现了：

1. **自动化**：无需人工干预，自动规划研究路径
2. **智能化**：根据已有知识调整搜索方向
3. **高效化**：并发执行，自动收拢
4. **可控化**：通过参数精确控制规模

这是一个**模仿人类研究员思维过程**的系统，将复杂的探索性研究自动化。

---

*文档生成时间：2026年2月*  
*基于 deep-research-python 项目*
