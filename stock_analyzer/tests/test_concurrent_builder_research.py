
import asyncio
import pytest
from pydantic import BaseModel
from agent_framework import ChatMessage, Role
from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._workflow_context import WorkflowContext
from agent_framework._workflows._concurrent import ConcurrentBuilder
from agent_framework._workflows._agent_executor import AgentExecutorRequest
from typing import Any, Never

# Shared input
class StockTask(BaseModel):
    symbol: str
    name: str
    industry: str

# Mock Results
class ResultA(BaseModel):
    data: str = "Module A Result"

class ResultB(BaseModel):
    data: str = "Module B Result"

class ResultC(BaseModel):
    data: str = "Module C Result"

# Custom Executors for Modules A, B, C
class ModuleAExecutor(Executor):
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[ResultA]) -> None:
        print(f"Module A received request")
        await ctx.send_message(ResultA())

class ModuleBExecutor(Executor):
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[ResultB]) -> None:
        print(f"Module B received request")
        await ctx.send_message(ResultB())

class ModuleCExecutor(Executor):
    @handler
    async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[ResultC]) -> None:
        print(f"Module C received request")
        await ctx.send_message(ResultC())

# Custom Aggregator
class MyAggregator(Executor):
    @handler
    async def aggregate(self, results: list[Any], ctx: WorkflowContext[Never, dict]) -> None:
        print(f"Aggregator received {len(results)} results: {results}")
        combined = {}
        for res in results:
            if isinstance(res, ResultA): combined["A"] = res.data
            if isinstance(res, ResultB): combined["B"] = res.data
            if isinstance(res, ResultC): combined["C"] = res.data
        await ctx.yield_output(combined)

@pytest.mark.asyncio
async def test_concurrent_builder_with_agent_request():
    task = StockTask(symbol="600519", name="贵州茅台", industry="白酒")
    request = AgentExecutorRequest(messages=[ChatMessage(role=Role.USER, text=task.model_dump_json())])
    
    # Build workflow
    builder = ConcurrentBuilder()
    builder.participants([
        ModuleAExecutor(id="module_a"),
        ModuleBExecutor(id="module_b"),
        ModuleCExecutor(id="module_c")
    ])
    builder.with_aggregator(MyAggregator(id="aggregator"))
    
    workflow = builder.build()
    
    # Run workflow
    run_result = await workflow.run(request)
    outputs = run_result.get_outputs()
    
    assert len(outputs) == 1
    assert outputs[0] == {"A": "Module A Result", "B": "Module B Result", "C": "Module C Result"}
    print("Workflow finished successfully!")

if __name__ == "__main__":
    asyncio.run(test_concurrent_builder_with_agent_request())
