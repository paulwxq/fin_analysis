"""Merge outputs from concurrent agents into Step1Output."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List

from agent_framework import ChatMessage

from . import utils
from .models import KLineData, NewsData, SectorData, Step1Output


def merge_results(messages: List[ChatMessage]) -> Step1Output:
    news_data = None
    sector_data = None
    kline_data = None

    parsing_errors: list[str] = []
    for msg in messages:
        # 过滤非 ChatMessage 对象 (如 ExecutorInvokedEvent)
        if not isinstance(msg, ChatMessage):
            continue
            
        try:
            # 1. 提取 JSON 字符串
            json_str = utils.extract_json_str(msg.text)
            # 2. 解析为 Python 字典
            payload = json.loads(json_str)
        except Exception as exc:  # noqa: BLE001
            parsing_errors.append(f"解析失败: {exc}")
            continue

        data_type = payload.get("data_type")
        try:
            if data_type == "news":
                news_data = NewsData.model_validate(payload)
            elif data_type == "sector":
                sector_data = SectorData.model_validate(payload)
            elif data_type == "kline":
                kline_data = KLineData.model_validate(payload)
            else:
                parsing_errors.append(f"未知 data_type: {data_type}")
        except Exception as exc:  # noqa: BLE001
            parsing_errors.append(f"{data_type} 校验失败: {exc}")

    if not all([news_data, sector_data, kline_data]):
        missing: list[str] = []
        if not news_data:
            missing.append("NewsData")
        if not sector_data:
            missing.append("SectorData")
        if not kline_data:
            missing.append("KLineData")
        detail_msg = "\n".join(parsing_errors)
        raise RuntimeError(
            f"Step 1 合并失败，缺失: {', '.join(missing)}\n解析详情:\n{detail_msg}"
        )

    return Step1Output(
        timestamp=datetime.now(timezone.utc).isoformat(),
        news=news_data,
        sector=sector_data,
        kline=kline_data,
    )