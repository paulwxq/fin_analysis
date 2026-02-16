import json
import base64
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential

from agent_framework import ChatAgent, ChatMessage, Content
from agent_framework.openai import OpenAIChatClient

from .config import RefinementConfig
from .models import AnalysisResult, StockImage
from .prompts import SYSTEM_PROMPT, get_user_prompt
from .logger import LoggerConfig

logger = LoggerConfig.setup_logger("llm_analyzer")

class LLMAnalyzer:
    def __init__(self, model_name: str, api_key: str, base_url: str):
        """
        Initialize LLM Analyzer with Agent Framework
        """
        # Configure the Client
        # Note: We prefer environment variables, but allow explicit override
        self.client = OpenAIChatClient(
            model_id=model_name,
            api_key=api_key,
            base_url=base_url
        )
        
        # Configure the Agent
        self.agent = ChatAgent(
            name="FlatBottomAnalyzer",
            chat_client=self.client,
            instructions=SYSTEM_PROMPT,
            description="A technical analysis expert specializing in stock patterns."
        )

    async def analyze_kline(self, image_path: str, stock_code: str) -> AnalysisResult:
        """
        Analyze a single K-line image using the multimodal agent.
        """
        try:
            # 1. Read and Encode Image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            image_uri = f"data:image/png;base64,{image_data}"

            # 2. Build Message
            # Construct a multimodal user message
            user_message = ChatMessage(
                role="user",
                contents=[
                    Content.from_text(text=get_user_prompt(stock_code)),
                    Content.from_uri(uri=image_uri, media_type="image/png")
                ]
            )

            # 3. Call Agent (with Retry and Thinking enabled if configured)
            options = {}
            if RefinementConfig.ENABLE_THINKING:
                options["extra_body"] = {
                    "enable_thinking": True
                }
            
            response_text = await self._call_agent_with_retry(user_message, options=options)
            
            logger.debug(f"[{stock_code}] Raw LLM Response: {response_text}")

            # 4. Parse Response
            parsed_data = self.parse_llm_response(response_text, stock_code)
            
            return AnalysisResult(
                stock_code=stock_code,
                score=parsed_data.get("score", 0.0),
                pattern_name=parsed_data.get("pattern_name", "Unknown"),
                reasoning=parsed_data.get("reasoning", ""),
                stage=parsed_data.get("stage", "Unknown"),
                ma30_status=parsed_data.get("ma30_status", "Unknown"),
                volume_pattern=parsed_data.get("volume_pattern", "Unknown"),
                image_path=image_path,
                analysis_timestamp=datetime.now(),
                success=True
            )

        except Exception as e:
            logger.error(f"[{stock_code}] Analysis failed: {e}", exc_info=True)
            return AnalysisResult(
                stock_code=stock_code,
                score=0.0,
                pattern_name="",
                reasoning="",
                stage="",
                ma30_status="",
                volume_pattern="",
                image_path=image_path,
                analysis_timestamp=datetime.now(),
                success=False,
                error_message=str(e)
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_agent_with_retry(self, message: ChatMessage, options: Optional[Dict[str, Any]] = None) -> str:
        """Helper to call agent with retry logic"""
        response_message = await self.agent.run(message, options=options)
        return response_message.text

    def parse_llm_response(self, response_text: str, expected_code: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response. Handles Markdown code blocks and messy text.
        """
        clean_text = response_text.strip()
        
        # Try to find the JSON object boundaries
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        
        if start != -1 and end != -1:
            clean_text = clean_text[start:end+1]
        
        try:
            data = json.loads(clean_text)
            
            # Validation
            # Ensure score is float
            if "score" in data:
                data["score"] = float(data["score"])
            
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error for {expected_code}: {e}")
            logger.debug(f"Raw Response: {response_text}")
            # Return default failed structure
            return {
                "score": 0.0,
                "reasoning": f"JSON Parse Error. Raw: {response_text[:100]}..."
            }

    async def batch_analyze(self, images: List[StockImage], concurrency: int = 5) -> List[AnalysisResult]:
        """
        Analyze multiple images concurrently.
        """
        sem = asyncio.Semaphore(concurrency)
        
        async def _analyze_safe(img: StockImage):
            async with sem:
                logger.info(f"Analyzing {img.stock_code}...")
                return await self.analyze_kline(img.file_path, img.stock_code)
                
        tasks = [_analyze_safe(img) for img in images]
        results = await asyncio.gather(*tasks)
        return results
