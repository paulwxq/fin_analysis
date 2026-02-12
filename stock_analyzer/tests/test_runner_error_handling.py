"""Tests for user-friendly runner error handling in modules A/B/C."""

from __future__ import annotations

import pytest

import stock_analyzer.run_module_a as run_a
import stock_analyzer.run_module_b as run_b
import stock_analyzer.run_module_c as run_c
from stock_analyzer.exceptions import (
    AKShareCollectionError,
    TechnicalAnalysisError,
    WebResearchError,
)


def test_run_module_a_input_error_returns_code_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_a.sys, "argv", ["run_module_a.py", "bad_symbol", "贵州茅台"])

    with pytest.raises(SystemExit) as exc:
        run_a.main()

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "[module A] 输入错误:" in err


def test_run_module_a_runtime_error_returns_code_1(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_a.sys, "argv", ["run_module_a.py", "600519", "贵州茅台"])
    monkeypatch.setattr(run_a, "normalize_symbol", lambda raw: "600519")

    def fake_collect_akshare_data(symbol: str, name: str):
        raise AKShareCollectionError(symbol=symbol, errors=["network error"])

    monkeypatch.setattr(run_a, "collect_akshare_data", fake_collect_akshare_data)

    with pytest.raises(SystemExit) as exc:
        run_a.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "[module A] 运行失败:" in err


@pytest.mark.asyncio
async def test_run_module_b_input_error_returns_code_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_b.sys, "argv", ["run_module_b.py", "600519.SH", "贵州茅台", " "])

    with pytest.raises(SystemExit) as exc:
        await run_b.main()

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "[module B] 输入错误:" in err


@pytest.mark.asyncio
async def test_run_module_b_runtime_error_returns_code_1(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_b.sys, "argv", ["run_module_b.py", "600519.SH", "贵州茅台", "白酒"])

    async def fake_run_web_research(symbol: str, name: str, industry: str):
        raise WebResearchError("deep research failed")

    monkeypatch.setattr(run_b, "run_web_research", fake_run_web_research)

    with pytest.raises(SystemExit) as exc:
        await run_b.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "[module B] 运行失败:" in err


@pytest.mark.asyncio
async def test_run_module_c_input_error_returns_code_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_c.sys, "argv", ["run_module_c.py", "bad_symbol", "贵州茅台"])

    with pytest.raises(SystemExit) as exc:
        await run_c.main()

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "[module C] 输入错误:" in err


@pytest.mark.asyncio
async def test_run_module_c_runtime_error_returns_code_1(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_c.sys, "argv", ["run_module_c.py", "600519", "贵州茅台"])
    monkeypatch.setattr(run_c, "normalize_symbol", lambda raw: "600519")

    async def fake_run_technical_analysis(symbol: str, name: str):
        raise TechnicalAnalysisError("technical failed")

    monkeypatch.setattr(run_c, "run_technical_analysis", fake_run_technical_analysis)

    with pytest.raises(SystemExit) as exc:
        await run_c.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "[module C] 运行失败:" in err
