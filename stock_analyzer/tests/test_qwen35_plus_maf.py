
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agent_framework import ChatAgent
from stock_analyzer.llm_client import create_openai_client, create_chat_client
from stock_analyzer.llm_helpers import call_agent_with_model
from pydantic import BaseModel, Field

# 定义测试用的 Pydantic 模型
class TestResult(BaseModel):
    logic_check: bool = Field(description="逻辑是否正确")
    result_value: int = Field(description="计算结果")

async def verify_qwen35_maf_encapsulation():
    model_id = "qwen3.5-plus"
    print(f"=== 验证 MAF 封装 {model_id} ===")
    
    # 1. 创建底层客户端
    openai_client = create_openai_client()
    chat_client = create_chat_client(openai_client, model_id)
    
    # 2. 使用 MAF ChatAgent 封装
    # 注意：这里同时传递了 response_format 和 extra_body
    agent = ChatAgent(
        chat_client=chat_client,
        name="qwen35_tester",
        instructions="你是一个数学验证专家。请计算 (50+50)*2 并验证结果。必须严格输出 JSON，使用 'logic_check' (bool) 和 'result_value' (int) 作为键名。",
        default_options={
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "extra_body": {"enable_thinking": True}
        }
    )
    
    print(f"  - Agent '{agent.name}' 已创建，配置：Thinking=True, JSON_Mode=True")
    
    # 3. 执行调用（使用项目自带的 llm_helpers 以确保持续兼容流式模式）
    try:
        # 为了规避超时，生产环境下建议 stream=True
        result = await call_agent_with_model(
            agent=agent,
            message="请开始任务。",
            model_cls=TestResult,
            stream=True 
        )
        
        print(f"  - ✅ MAF 调用成功！")
        print(f"  - 解析后的 Pydantic 模型: {result}")
        assert result.result_value == 200
        assert result.logic_check is True
        print("  - 结论: qwen3.5-plus 在 MAF 框架下完美支持参数共存。")
        
    except Exception as e:
        print(f"  - ❌ MAF 调用或解析失败: {e}")

if __name__ == "__main__":
    asyncio.run(verify_qwen35_maf_encapsulation())
