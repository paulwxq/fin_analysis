import pytest
from unittest.mock import MagicMock, patch
from http import HTTPStatus
from agent_framework import ChatMessage, Role, Content
from qwen3 import QwenVLChatClient, UnsupportedParameterError

@pytest.fixture
def mock_dashscope_vl_call():
    with patch("dashscope.MultiModalConversation.call") as mock:
        yield mock

class TestQwenVLChatClient:
    def test_init(self):
        client = QwenVLChatClient(api_key="test-key")
        assert client.model_id == "qwen3-vl-plus"

    def test_multimodal_message_conversion(self):
        """测试多模态消息转换"""
        client = QwenVLChatClient(api_key="test-key")
        messages = [
            ChatMessage(
                role="user", 
                contents=[
                    Content.from_text(text="Analyze this"),
                    Content.from_uri(uri="https://example.com/img.png")
                ]
            )
        ]
        
        converted = client._convert_messages(messages)
        content_list = converted[0]["content"]
        
        assert len(content_list) == 2
        assert content_list[0] == {"text": "Analyze this"}
        assert content_list[1] == {"image": "https://example.com/img.png"}

    def test_unsupported_search_parameter(self):
        """测试 enable_search 参数拦截"""
        client = QwenVLChatClient(api_key="test-key")
        messages = [ChatMessage(role="user", text="hi")]
        
        # 显式开启 enable_search 应抛出异常
        with pytest.raises(UnsupportedParameterError) as exc:
            client._build_request_params(messages, enable_search=True)
        
        assert "不支持 'enable_search'" in str(exc.value)

    @pytest.mark.asyncio
    async def test_vl_streaming_response(self, mock_dashscope_vl_call):
        """测试 VL 流式响应"""
        chunk1 = MagicMock()
        chunk1.status_code = HTTPStatus.OK
        chunk1.output.choices = [MagicMock(message={"content": [{"text": "A cute"}]}, finish_reason="null")]
        
        chunk2 = MagicMock()
        chunk2.status_code = HTTPStatus.OK
        chunk2.output.choices = [MagicMock(message={"content": [{"text": " cat."}]}, finish_reason="stop")]
        chunk2.usage.input_tokens = 50
        chunk2.usage.output_tokens = 5

        mock_dashscope_vl_call.return_value = iter([chunk1, chunk2])
        
        client = QwenVLChatClient(api_key="test-key")
        updates = []
        async for update in client.get_streaming_response([ChatMessage(role="user", text="hi")]):
            updates.append(update)
            
        assert updates[0].text == "A cute"
        assert updates[1].text == " cat."
        
        # 验证 usage_details (使用字典访问)
        last_update = updates[-1]
        usage = last_update.additional_properties.get("usage_details")
        assert usage["input_tokens"] == 50
