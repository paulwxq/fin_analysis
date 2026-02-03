import pytest
from unittest.mock import MagicMock, patch
from http import HTTPStatus
from agent_framework import ChatMessage, Role, Content
from qwen3 import QwenChatClient, QwenChatOptions, QwenAPIError, ThinkingModeRequiresStreamError

@pytest.fixture
def mock_dashscope_call():
    with patch("dashscope.Generation.call") as mock:
        yield mock

class TestQwenChatClient:
    def test_init(self):
        """测试初始化"""
        client = QwenChatClient(api_key="test-key")
        assert client.model_id == "qwen-plus"
        assert client.api_key == "test-key"

    def test_message_conversion(self):
        """测试消息格式转换"""
        client = QwenChatClient(api_key="test-key")
        messages = [
            ChatMessage(role="user", text="Hello"),
            ChatMessage(role="assistant", text="Hi")
        ]
        
        converted = client._convert_messages(messages)
        assert len(converted) == 2
        assert converted[0] == {"role": "user", "content": "Hello"}
        assert converted[1] == {"role": "assistant", "content": "Hi"}

    def test_build_request_params(self):
        """测试请求参数构建"""
        client = QwenChatClient(api_key="test-key")
        messages = [ChatMessage(role="user", text="test")]
        options: QwenChatOptions = {
            "temperature": 0.5,
            "enable_search": True,
            "enable_thinking": True,
            "thinking_budget": 1024
        }
        
        params = client._build_request_params(messages, **options)
        
        assert params["model"] == "qwen-plus"
        assert params["temperature"] == 0.5
        assert params["enable_search"] is True
        assert params["enable_thinking"] is True
        assert params["thinking_budget"] == 1024
        assert params["incremental_output"] is True

    @pytest.mark.asyncio
    async def test_get_response_success(self, mock_dashscope_call):
        """测试非流式响应成功"""
        # 使用字典模拟 message，避免 MagicMock.get() 返回 Mock 对象
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.OK
        mock_response.output.choices = [
            MagicMock(message={"content": "Hello World", "reasoning_content": None}, finish_reason="stop")
        ]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        
        mock_dashscope_call.return_value = mock_response
        
        client = QwenChatClient(api_key="test-key")
        response = await client.get_response([ChatMessage(role="user", text="Hi")])
        
        assert response.text == "Hello World"
        assert response.usage_details["input_tokens"] == 10
        assert response.usage_details["output_tokens"] == 5

    @pytest.mark.asyncio
    async def test_thinking_mode_requires_stream(self):
        """测试思考模式必须流式调用的约束"""
        client = QwenChatClient(api_key="test-key")
        messages = [ChatMessage(role="user", text="Hi")]
        
        # 显式开启 enable_thinking 应抛出异常
        with pytest.raises(ThinkingModeRequiresStreamError):
            await client.get_response(messages, enable_thinking=True)

    @pytest.mark.asyncio
    async def test_streaming_response_with_thinking(self, mock_dashscope_call):
        """测试带思考过程的流式响应"""
        # Mock 流式 chunk
        chunk1 = MagicMock()
        chunk1.status_code = HTTPStatus.OK
        chunk1.output.choices = [MagicMock(message={"reasoning_content": "Thinking...", "content": ""}, finish_reason="null")]
        
        chunk2 = MagicMock()
        chunk2.status_code = HTTPStatus.OK
        chunk2.output.choices = [MagicMock(message={"reasoning_content": "", "content": "Answer"}, finish_reason="stop")]
        chunk2.usage.input_tokens = 10
        chunk2.usage.output_tokens = 5

        # 设置 Mock 返回值为迭代器
        mock_dashscope_call.return_value = iter([chunk1, chunk2])
        
        client = QwenChatClient(api_key="test-key")
        updates = []
        async for update in client.get_streaming_response([ChatMessage(role="user", text="Hi")], enable_thinking=True):
            updates.append(update)
            
        assert len(updates) >= 2
        assert "<thinking>Thinking...</thinking>" in updates[0].text
        assert "Answer" in updates[1].text
        
        # 验证 Token 统计 (使用字典访问)
        last_update = updates[-1]
        usage = last_update.additional_properties.get("usage_details")
        assert usage["input_tokens"] == 10

    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_dashscope_call):
        """测试 API 错误处理"""
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.BAD_REQUEST
        mock_response.code = "InvalidParameter"
        mock_response.message = "Test Error"
        mock_response.request_id = "req-123"
        
        mock_dashscope_call.return_value = mock_response
        
        client = QwenChatClient(api_key="test-key")
        
        with pytest.raises(QwenAPIError) as exc:
            await client.get_response([ChatMessage(role="user", text="Hi")])
        
        assert "InvalidParameter" in str(exc.value)
