import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from analysis_llm import tools, config

@pytest.mark.asyncio
async def test_web_search_tavily():
    """测试 Tavily 搜索路径"""
    
    # Mock TavilyClient (直接 mock tavily 包)
    with patch("tavily.TavilyClient") as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        mock_instance.search.return_value = {
            "results": [
                {"title": "Test News", "url": "http://test.com", "content": "News content"}
            ]
        }
        
        # Mock Config
        with patch.object(config, "SEARCH_PROVIDER", "tavily"), \
             patch.dict("os.environ", {"TAVILY_API_KEY": "fake-key"}):
            
            result_json = await tools.web_search(query="test", max_results=5)
            
            # 验证调用参数
            mock_instance.search.assert_called_with("test", search_depth="advanced", max_results=5)
            
            # 验证返回结果
            results = json.loads(result_json)
            assert len(results) == 1
            assert results[0]["title"] == "Test News"
            assert results[0]["content"] == "News content"

@pytest.mark.asyncio
async def test_web_search_serper():
    """测试 Serper 搜索路径"""
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "organic": [
            {"title": "Serper Result", "link": "http://serper.dev", "snippet": "Serper content"}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    # Mock httpx.AsyncClient
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Mock Config
        with patch.object(config, "SEARCH_PROVIDER", "serper"), \
             patch.object(config, "SERPER_API_KEY", "fake-serper-key"):
            
            result_json = await tools.web_search(query="test", max_results=3)
            
            # 验证调用参数
            mock_client.post.assert_awaited()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://google.serper.dev/search"
            payload = json.loads(call_args[1]["data"])
            assert payload["q"] == "test"
            assert payload["num"] == 3
            
            # 验证返回结果
            results = json.loads(result_json)
            assert len(results) == 1
            assert results[0]["title"] == "Serper Result"
            assert results[0]["url"] == "http://serper.dev"
            assert results[0]["content"] == "Serper content"
