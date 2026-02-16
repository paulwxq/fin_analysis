"""Tests for flatbottom_pipeline.refinement_llm (image_loader, llm_analyzer, models)."""
import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from flatbottom_pipeline.refinement_llm.models import StockImage, AnalysisResult
from flatbottom_pipeline.refinement_llm.image_loader import ImageLoader


# ===========================================================================
# ImageLoader.extract_stock_code
# ===========================================================================

class TestExtractStockCode:
    def setup_method(self):
        self.loader = ImageLoader("/dummy")

    def test_normal(self):
        assert self.loader.extract_stock_code("000876.SZ_kline.png") == "000876.SZ"

    def test_multiple_underscores(self):
        assert self.loader.extract_stock_code("600000.SH_kline_extra.png") == "600000.SH"

    def test_no_underscore(self):
        """No underscore → returns full filename."""
        assert self.loader.extract_stock_code("abc.png") == "abc.png"

    def test_empty_string(self):
        assert self.loader.extract_stock_code("") == ""


# ===========================================================================
# ImageLoader.validate_image
# ===========================================================================

class TestValidateImage:
    def setup_method(self):
        self.loader = ImageLoader("/dummy")

    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.exists", return_value=True)
    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.getsize", return_value=1024)
    def test_valid_png(self, mock_size, mock_exists):
        assert self.loader.validate_image("/path/to/image.png") is True

    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.exists", return_value=False)
    def test_missing_file(self, mock_exists):
        assert self.loader.validate_image("/path/to/missing.png") is False

    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.exists", return_value=True)
    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.getsize", return_value=0)
    def test_empty_file(self, mock_size, mock_exists):
        assert self.loader.validate_image("/path/to/empty.png") is False

    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.exists", return_value=True)
    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.getsize", return_value=1024)
    def test_not_png(self, mock_size, mock_exists):
        assert self.loader.validate_image("/path/to/image.jpg") is False


# ===========================================================================
# ImageLoader.scan_images
# ===========================================================================

class TestScanImages:
    @patch("flatbottom_pipeline.refinement_llm.image_loader.os.path.getsize", return_value=2048)
    @patch("flatbottom_pipeline.refinement_llm.image_loader.glob.glob")
    def test_scan_returns_stock_images(self, mock_glob, mock_size):
        mock_glob.return_value = [
            "/output/000876.SZ_kline.png",
            "/output/600000.SH_kline.png",
        ]
        loader = ImageLoader("/output")
        # validate_image needs to pass — patch it
        with patch.object(loader, "validate_image", return_value=True):
            images = loader.scan_images()

        assert len(images) == 2
        assert images[0].stock_code == "000876.SZ"
        assert images[1].stock_code == "600000.SH"
        assert all(isinstance(img, StockImage) for img in images)

    @patch("flatbottom_pipeline.refinement_llm.image_loader.glob.glob", return_value=[])
    def test_scan_empty_dir(self, mock_glob):
        loader = ImageLoader("/empty")
        images = loader.scan_images()
        assert images == []


# ===========================================================================
# LLMAnalyzer.parse_llm_response
# ===========================================================================

class TestParseLlmResponse:
    """Test JSON parsing without instantiating the full LLMAnalyzer (skip __init__ deps)."""

    def _parse(self, text, code="TEST"):
        # Import the class and call parse_llm_response as unbound
        from flatbottom_pipeline.refinement_llm.llm_analyzer import LLMAnalyzer
        # Create a minimal instance without calling __init__
        analyzer = object.__new__(LLMAnalyzer)
        return analyzer.parse_llm_response(text, code)

    def test_valid_json(self):
        resp = json.dumps({"score": 8.5, "reasoning": "Good pattern"})
        result = self._parse(resp)
        assert result["score"] == 8.5
        assert result["reasoning"] == "Good pattern"

    def test_markdown_code_block(self):
        resp = '```json\n{"score": 7.0, "reasoning": "OK"}\n```'
        result = self._parse(resp)
        assert result["score"] == 7.0

    def test_extra_text_around_json(self):
        resp = 'Here is the result: {"score": 6.0, "reasoning": "Moderate"} end.'
        result = self._parse(resp)
        assert result["score"] == 6.0

    def test_malformed_returns_default(self):
        resp = "This is not JSON at all"
        result = self._parse(resp)
        assert result["score"] == 0.0
        assert "JSON Parse Error" in result["reasoning"]

    def test_score_as_string(self):
        resp = json.dumps({"score": "8.5", "reasoning": "String score"})
        result = self._parse(resp)
        assert result["score"] == 8.5
        assert isinstance(result["score"], float)

    def test_empty_json_object(self):
        resp = "{}"
        result = self._parse(resp)
        assert isinstance(result, dict)


# ===========================================================================
# Dataclass models
# ===========================================================================

class TestModels:
    def test_stock_image_creation(self):
        img = StockImage(
            stock_code="000876.SZ",
            file_path="/output/000876.SZ_kline.png",
            file_size=2048,
            valid=True,
        )
        assert img.stock_code == "000876.SZ"
        assert img.file_size == 2048
        assert img.valid is True

    def test_analysis_result_creation(self):
        result = AnalysisResult(
            stock_code="000876.SZ",
            score=8.5,
            pattern_name="Flat Bottom",
            reasoning="Good",
            stage="Stage 1",
            ma30_status="Above",
            volume_pattern="Increasing",
            image_path="/output/000876.SZ_kline.png",
            analysis_timestamp=datetime.now(),
            success=True,
        )
        assert result.score == 8.5
        assert result.error_message is None  # default

    def test_analysis_result_with_error(self):
        result = AnalysisResult(
            stock_code="000876.SZ",
            score=0.0,
            pattern_name="",
            reasoning="",
            stage="",
            ma30_status="",
            volume_pattern="",
            image_path="",
            analysis_timestamp=datetime.now(),
            success=False,
            error_message="API timeout",
        )
        assert result.success is False
        assert result.error_message == "API timeout"
