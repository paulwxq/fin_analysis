import pytest
from unittest.mock import MagicMock, patch
from http import HTTPStatus
from agent_framework import ChatAgent, ChatMessage, Role
from qwen3 import QwenChatClient, QwenChatOptions

@pytest.fixture
def mock_dashscope_agent_call():
    with patch("dashscope.Generation.call") as mock:
        yield mock

@pytest.mark.asyncio
async def test_agent_integration(mock_dashscope_agent_call):
    """测试与 ChatAgent 的集成"""
    # Mock 响应，使用字典以支持 .get() 且返回真实字符串
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.output.choices = [
        MagicMock(message={"content": "Agent Response", "reasoning_content": None}, finish_reason="stop")
    ]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 10
    
    mock_dashscope_agent_call.return_value = mock_response
    
    # 初始化 Client 和 Agent
    client = QwenChatClient(api_key="test-key")
    agent = ChatAgent(chat_client=client, name="TestAgent")
    
    # 运行 Agent
    response = await agent.run("Hello Agent")
    
    assert response.text == "Agent Response"
    # usage_details 是一个字典
    assert response.usage_details["input_tokens"] == 10

@pytest.mark.asyncio
async def test_agent_streaming_integration(mock_dashscope_agent_call):
    """测试 Agent 流式集成"""
    # Mock 流
    chunk = MagicMock()
    chunk.status_code = HTTPStatus.OK
    chunk.output.choices = [MagicMock(message={"content": "Stream", "reasoning_content": None}, finish_reason="stop")]
    chunk.usage.input_tokens = 5
    chunk.usage.output_tokens = 5
    
    mock_dashscope_agent_call.return_value = iter([chunk])
    
    client = QwenChatClient(api_key="test-key")
    agent = ChatAgent(chat_client=client)
    
    collected_text = ""
    async for update in agent.run_stream("Stream Test"):
        collected_text += update.text
        
    assert collected_text == "Stream"