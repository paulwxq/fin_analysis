"""Tests for workflow CLI runner error handling and success output."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import stock_analyzer.run_workflow as run_workflow_runner
from stock_analyzer.exceptions import (
    ChiefAnalysisError,
    StockInfoLookupError,
    WorkflowCircuitBreakerError,
)


@pytest.mark.asyncio
async def test_run_workflow_usage_error_returns_code_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_workflow_runner.sys, "argv", ["run_workflow.py"])

    with pytest.raises(SystemExit) as exc:
        await run_workflow_runner.main()

    assert exc.value.code == 2
    assert "Usage:" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_workflow_success_writes_report(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        run_workflow_runner.sys,
        "argv",
        ["run_workflow.py", "600519.SH"],
    )
    monkeypatch.setattr(run_workflow_runner, "WORKFLOW_OUTPUT_DIR", str(tmp_path))

    fake_report = MagicMock()
    fake_report.meta = MagicMock()
    fake_report.meta.symbol = "600519"

    monkeypatch.setattr(
        run_workflow_runner,
        "run_workflow",
        AsyncMock(return_value=fake_report),
    )
    monkeypatch.setattr(
        run_workflow_runner,
        "dump_final_report_json",
        lambda _: '{"ok": true}',
    )

    await run_workflow_runner.main()

    output_path = tmp_path / "600519_final_report.json"
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == '{"ok": true}'

    captured = capsys.readouterr()
    assert '{"ok": true}' in captured.out
    assert "[workflow] 开始全流程分析" in captured.err
    assert "[workflow] 最终报告已保存到" in captured.err


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_exit_code", "expected_message"),
    [
        (ValueError("bad symbol"), 2, "[workflow] 输入错误:"),
        (StockInfoLookupError("lookup failed"), 2, "[workflow] 股票信息查询失败:"),
        (WorkflowCircuitBreakerError("breaker"), 1, "[workflow] 熔断触发，作业中止:"),
        (ChiefAnalysisError("chief failed"), 1, "[workflow] 首席分析失败:"),
    ],
)
async def test_run_workflow_expected_errors(
    monkeypatch,
    capsys,
    error: Exception,
    expected_exit_code: int,
    expected_message: str,
) -> None:
    monkeypatch.setattr(
        run_workflow_runner.sys,
        "argv",
        ["run_workflow.py", "600519"],
    )
    monkeypatch.setattr(
        run_workflow_runner,
        "run_workflow",
        AsyncMock(side_effect=error),
    )

    with pytest.raises(SystemExit) as exc:
        await run_workflow_runner.main()

    assert exc.value.code == expected_exit_code
    assert expected_message in capsys.readouterr().err

