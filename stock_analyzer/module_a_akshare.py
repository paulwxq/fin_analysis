"""Module A: AKShare structured data collection."""

from __future__ import annotations

import inspect
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime

import akshare as ak
import pandas as pd

from stock_analyzer.config import (
    AKSHARE_CALL_INTERVAL,
    AKSHARE_CALL_TIMEOUT,
    AKSHARE_DIVIDEND_YEARS,
    AKSHARE_FINANCIAL_PERIODS,
    AKSHARE_FUND_FLOW_DAYS,
    AKSHARE_MARKET_CACHE_TTL_SEC,
    AKSHARE_MAX_CONSECUTIVE_TIMEOUTS,
    AKSHARE_SHAREHOLDER_PERIODS,
    AKSHARE_TIMEOUT_RETRIES,
)
from stock_analyzer.exceptions import AKShareCollectionError
from stock_analyzer.logger import logger
from stock_analyzer.module_a_models import AKShareData, AKShareMeta
from stock_analyzer.utils import format_symbol, get_market


class AKShareMarketCache:
    """Full-market DataFrame cache for cross-symbol reuse."""

    def __init__(self, ttl_sec: int = AKSHARE_MARKET_CACHE_TTL_SEC):
        self.ttl_sec = ttl_sec
        self._store: dict[str, tuple[float, pd.DataFrame]] = {}

    def get(self, key: str) -> pd.DataFrame | None:
        item = self._store.get(key)
        if item is None:
            return None
        ts, df = item
        if time.time() - ts > self.ttl_sec:
            self._store.pop(key, None)
            return None
        return df.copy(deep=True)

    def set(self, key: str, df: pd.DataFrame) -> None:
        self._store[key] = (time.time(), df.copy(deep=True))


class AKShareCollector:
    """AKShare collector with unified error handling and status tracking."""

    STATUS_OK = "ok"
    STATUS_NO_DATA = "no_data"
    STATUS_FAILED = "failed"

    def __init__(
        self,
        symbol: str,
        name: str,
        market_cache: AKShareMarketCache | None = None,
    ):
        self.symbol = symbol
        self.name = name
        self.errors: list[str] = []
        self.topic_status: dict[str, str] = {}
        self._last_call_time: float = 0.0
        self._consecutive_timeouts: int = 0
        self.market_cache = market_cache or AKShareMarketCache()

    def _wait_interval(self) -> None:
        """Rate-limit AKShare calls to reduce source-site blocking risk."""
        elapsed = time.time() - self._last_call_time
        if elapsed < AKSHARE_CALL_INTERVAL:
            wait = AKSHARE_CALL_INTERVAL - elapsed
            logger.debug(f"Rate limit: waiting {wait:.1f}s before next AKShare call")
            time.sleep(wait)

    def safe_call(self, topic: str, func, *args, **kwargs) -> pd.DataFrame | None:
        """Safely call one AKShare API with soft-timeout and circuit breaker."""
        func_name = func.__name__
        attempts = AKSHARE_TIMEOUT_RETRIES + 1
        for attempt in range(1, attempts + 1):
            self._wait_interval()
            try:
                if attempt == 1:
                    logger.info(f"Fetching [{topic}] via {func_name}...")
                else:
                    logger.info(
                        f"Retrying [{topic}] via {func_name} (attempt {attempt}/{attempts})..."
                    )
                self._last_call_time = time.time()
                df = self._execute_with_timeout(func, *args, **kwargs)

                self._consecutive_timeouts = 0
                if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                    msg = f"{topic}: 返回数据为空 ({func_name})"
                    self.errors.append(msg)
                    logger.warning(msg)
                    return None

                logger.info(
                    f"[{topic}] fetched successfully: {len(df)} rows via {func_name}"
                )
                return df

            except FutureTimeoutError:
                if self._handle_timeout(topic, func_name, attempt, attempts):
                    continue
                return None

            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                if self._is_timeout_exception(exc):
                    if self._handle_timeout(topic, func_name, attempt, attempts):
                        continue
                    return None
                if self._is_retryable_connection_exception(exc):
                    if attempt < attempts:
                        logger.warning(
                            f"{topic}: 连接异常（{type(exc).__name__}）({func_name})，"
                            f"准备重试 {attempt}/{AKSHARE_TIMEOUT_RETRIES}"
                        )
                        continue

                msg = f"{topic}: {type(exc).__name__} - {str(exc)[:200]} ({func_name})"
                self.errors.append(msg)
                logger.error(msg)
                return None

        return None

    def _handle_timeout(
        self,
        topic: str,
        func_name: str,
        attempt: int,
        attempts: int,
    ) -> bool:
        """Handle timeout retry/circuit-breaker. Return True if should retry."""
        if attempt < attempts:
            logger.warning(
                f"{topic}: 调用超时（>{AKSHARE_CALL_TIMEOUT}s）({func_name})，"
                f"准备重试 {attempt}/{AKSHARE_TIMEOUT_RETRIES}"
            )
            return True

        self._consecutive_timeouts += 1
        msg = (
            f"{topic}: 调用超时（>{AKSHARE_CALL_TIMEOUT}s）({func_name})"
            f" [连续超时 {self._consecutive_timeouts}/{AKSHARE_MAX_CONSECUTIVE_TIMEOUTS}]"
        )
        self.errors.append(msg)
        logger.error(msg)

        if self._consecutive_timeouts >= AKSHARE_MAX_CONSECUTIVE_TIMEOUTS:
            breaker_msg = f"连续超时 {self._consecutive_timeouts} 次，达到熔断阈值，中止采集"
            logger.critical(breaker_msg)
            raise AKShareCollectionError(self.symbol, self.errors + [breaker_msg])
        return False

    @staticmethod
    def _is_timeout_exception(exc: Exception) -> bool:
        """Best-effort timeout exception detection across requests/urllib variants."""
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        if "timeout" in name:
            return True
        return "timed out" in message or "timeout" in message

    @staticmethod
    def _is_retryable_connection_exception(exc: Exception) -> bool:
        """Detect transient connection errors worth retrying."""
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        if "connectionerror" in name:
            return True
        transient_markers = (
            "connection aborted",
            "remote end closed connection without response",
            "connection reset by peer",
            "temporarily unavailable",
            "max retries exceeded with url",
        )
        return any(marker in message for marker in transient_markers)

    @staticmethod
    def _execute_with_timeout(func, *args, **kwargs):
        """Execute one AKShare call with per-attempt soft-timeout isolation."""
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(func, *args, **kwargs)
            return future.result(timeout=AKSHARE_CALL_TIMEOUT)
        finally:
            executor.shutdown(wait=False)

    @staticmethod
    def _get_param_names(func) -> set[str]:
        """Return callable param names, empty set if signature is unavailable."""
        try:
            return set(inspect.signature(func).parameters.keys())
        except (TypeError, ValueError):
            return set()

    def safe_call_market_cached(
        self,
        cache_key: str,
        topic: str,
        func,
        *args,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Cache wrapper for full-market AKShare calls."""
        cached = self.market_cache.get(cache_key)
        if cached is not None:
            logger.info(f"[{topic}] cache hit: {cache_key}")
            return cached

        df = self.safe_call(topic, func, *args, **kwargs)
        if df is not None:
            self.market_cache.set(cache_key, df)
            logger.info(f"[{topic}] cache set: {cache_key}, rows={len(df)}")
        return df

    def _safe_filter(
        self,
        df: pd.DataFrame,
        column: str,
        value: str,
        topic: str,
        *,
        method: str = "eq",
    ) -> pd.DataFrame:
        """Defensive DataFrame filtering with column existence check."""
        if column not in df.columns:
            msg = (
                f"{topic}: 预期列 '{column}' 不存在，"
                f"实际列名: {list(df.columns)[:10]}"
            )
            self.errors.append(msg)
            logger.warning(msg)
            return df.iloc[0:0]

        if method == "eq":
            return df[df[column] == value]
        if method == "contains":
            return df[df[column].str.contains(value, na=False, regex=False)]

        msg = f"{topic}: 未知过滤方式 method='{method}'，回退到 'eq' 精确匹配"
        self.errors.append(msg)
        logger.warning(msg)
        return df[df[column] == value]

    @staticmethod
    def _pick_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Pick the first existing column name from candidates."""
        for name in candidates:
            if name in df.columns:
                return name
        return None

    def _safe_collect(self, topic: str, collect_func, *args, **kwargs):
        """Catch parsing-stage errors and keep per-topic status consistent."""
        try:
            result = collect_func(*args, **kwargs)
            if topic not in self.topic_status:
                self.topic_status[topic] = (
                    self.STATUS_OK if result is not None else self.STATUS_FAILED
                )
            return result
        except (KeyboardInterrupt, AKShareCollectionError):
            raise
        except Exception as exc:  # noqa: BLE001
            msg = f"{topic}(解析阶段): {type(exc).__name__} - {str(exc)[:200]}"
            self.errors.append(msg)
            logger.error(msg)
            self.topic_status[topic] = self.STATUS_FAILED
            return None

    def _collect_company_info(self) -> dict | None:
        """主题①：公司基本信息。"""
        df = self.safe_call(
            "company_info",
            ak.stock_individual_info_em,
            symbol=self.symbol,
        )
        if df is None:
            return None

        required_cols = {"item", "value"}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            msg = (
                "company_info: 缺少关键列 "
                f"{sorted(missing_cols)}，无法解析 item-value 结构"
            )
            self.errors.append(msg)
            logger.warning(msg)
            return None

        return self._parse_company_info(df)

    def _parse_company_info(self, df: pd.DataFrame) -> dict:
        """Parse item-value style company info DataFrame."""
        lookup = dict(zip(df["item"], df["value"]))

        return {
            "industry": self._safe_str(lookup.get("行业")),
            "listing_date": self._safe_str(lookup.get("上市时间")),
            "total_market_cap": self._parse_number(lookup.get("总市值"), target_unit="亿"),
            "circulating_market_cap": self._parse_number(
                lookup.get("流通市值"), target_unit="亿"
            ),
            "total_shares": self._parse_number(lookup.get("总股本"), target_unit="亿"),
            "circulating_shares": self._parse_number(
                lookup.get("流通股"), target_unit="亿"
            ),
        }

    @staticmethod
    def _parse_number(value, target_unit: str = "亿") -> float | None:
        """Parse numeric strings with Chinese units and normalize to target unit."""
        if value is None:
            return None

        text = str(value).strip().replace(",", "")
        if text in ("", "-", "--", "nan"):
            return None

        multiplier = 1.0
        if text.endswith("亿"):
            text = text[:-1]
            if target_unit == "万":
                multiplier = 10000.0
            # target_unit == "亿" → multiplier stays 1.0
        elif text.endswith("万"):
            text = text[:-1]
            if target_unit == "亿":
                multiplier = 0.0001
            # target_unit == "万" → multiplier stays 1.0
        else:
            # 无单位后缀：AKShare 返回原始数值（元/股），按目标单位换算
            if target_unit == "亿":
                multiplier = 1e-8
            elif target_unit == "万":
                multiplier = 1e-4

        try:
            return round(float(text) * multiplier, 4)
        except (ValueError, TypeError):
            return None

    def _collect_realtime_quote(self) -> dict | None:
        """主题②：实时行情快照。"""
        df = self.safe_call_market_cached(
            "stock_zh_a_spot_em",
            "realtime_quote",
            ak.stock_zh_a_spot_em,
        )
        if df is None:
            return None

        row = self._safe_filter(df, "代码", self.symbol, "realtime_quote")
        if row.empty:
            msg = f"realtime_quote: 全市场数据中未找到 {self.symbol}"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        r = row.iloc[0]
        return {
            "price": self._safe_float(r.get("最新价")),
            "change_pct": self._safe_float(r.get("涨跌幅")),
            "volume": self._safe_float(r.get("成交量")),
            "turnover": self._safe_float(r.get("成交额")),
            "pe_ttm": self._safe_float(r.get("市盈率-动态")),
            "pb": self._safe_float(r.get("市净率")),
            "turnover_rate": self._safe_float(r.get("换手率")),
            "volume_ratio": self._safe_float(r.get("量比")),
            "change_60d_pct": self._safe_float(r.get("60日涨跌幅")),
            "change_ytd_pct": self._safe_float(r.get("年初至今涨跌幅")),
        }

    @staticmethod
    def _safe_float(value) -> float | None:
        """Safe float conversion with NaN handling."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip().lower()
        if text in ("", "-", "--", "nan", "null", "none"):
            return None
        try:
            parsed = float(value)
            # Normalize NaN/NA-like float payloads to None for stable JSON output.
            if pd.isna(parsed):
                return None
            return parsed
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value) -> int | None:
        """Safe int conversion supporting comma and float-like strings."""
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).replace(",", "").strip()
        if text in ("", "-", "--", "nan"):
            return None
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_str(value, default: str = "") -> str:
        """Safe string conversion that normalizes NA-like payloads to default."""
        if value is None:
            return default
        if isinstance(value, float) and pd.isna(value):
            return default
        text = str(value).strip()
        if text.lower() in ("", "nan", "nat", "none", "null"):
            return default
        return text

    @staticmethod
    def _safe_optional_str(value) -> str | None:
        """Safe optional string conversion where missing values become None."""
        text = AKShareCollector._safe_str(value, default="")
        return text if text else None

    # 东方财富财务指标接口列名 → 内部中文列名映射
    _EM_FINANCIAL_FIELD_MAP: dict[str, str] = {
        "EPSJB": "摊薄每股收益(元)",
        "BPS": "每股净资产_调整后(元)",
        "ROEJQ": "净资产收益率_摊薄(%)",
        "XSMLL": "销售毛利率(%)",
        "XSJLL": "销售净利率(%)",
        "TOTALOPERATEREVETZ": "营业总收入同比增长率(%)",
        "PARENTNETPROFITTZ": "归属母公司股东的净利润同比增长率(%)",
        "ZCFZL": "资产负债率(%)",
        "LD": "流动比率",
    }

    def _collect_financial_indicators(self) -> list[dict] | None:
        """主题③：财务分析指标。

        优先使用东方财富接口（stock_financial_analysis_indicator_em），
        该接口以 '600519.SH' 格式传参，无 start_year 限制。
        若不可用则回退到新浪接口（需注意 start_year 限制）。
        """
        df = self._fetch_financial_indicators_em()
        if df is None:
            df = self._fetch_financial_indicators_sina()
        if df is None:
            return None

        if "报告期" in df.columns:
            df = (
                df.assign(_report_date=pd.to_datetime(df["报告期"], errors="coerce"))
                .sort_values("_report_date", ascending=False, na_position="last")
                .drop(columns=["_report_date"])
            )
        else:
            msg = "financial_indicators: 缺少列 '报告期'，按原始顺序截取最近N期"
            self.errors.append(msg)
            logger.warning(msg)

        df = df.head(AKSHARE_FINANCIAL_PERIODS)

        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "report_date": self._safe_str(row.get("报告期")),
                    "eps": self._safe_float(row.get("摊薄每股收益(元)")),
                    "net_asset_per_share": self._safe_float(
                        row.get("每股净资产_调整后(元)")
                    ),
                    "roe": self._safe_float(row.get("净资产收益率_摊薄(%)")),
                    "gross_margin": self._safe_float(row.get("销售毛利率(%)")),
                    "net_margin": self._safe_float(row.get("销售净利率(%)")),
                    "revenue_growth": self._safe_float(
                        row.get("营业总收入同比增长率(%)")
                    ),
                    "profit_growth": self._safe_float(
                        row.get("归属母公司股东的净利润同比增长率(%)")
                    ),
                    "debt_ratio": self._safe_float(row.get("资产负债率(%)")),
                    "current_ratio": self._safe_float(row.get("流动比率")),
                }
            )

        return results

    def _fetch_financial_indicators_em(self) -> pd.DataFrame | None:
        """东方财富版财务指标接口，无 start_year 限制。"""
        em_func = getattr(ak, "stock_financial_analysis_indicator_em", None)
        if em_func is None:
            return None
        market = get_market(self.symbol).upper()
        em_symbol = f"{self.symbol}.{market}"
        df = self.safe_call(
            "financial_indicators",
            em_func,
            symbol=em_symbol,
            indicator="按报告期",
        )
        if df is None:
            return None
        # 将 REPORT_DATE 转为标准日期字符串，重命名为期望的中文列名
        df = df.copy()
        df["报告期"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
        rename = {k: v for k, v in self._EM_FINANCIAL_FIELD_MAP.items() if k in df.columns}
        return df.rename(columns=rename)

    def _fetch_financial_indicators_sina(self) -> pd.DataFrame | None:
        """新浪版财务指标接口（回退路径）。
        注意：start_year 须为该股票实际有数据的年份，否则返回空 DataFrame。
        从 company_info 的上市日期推断上市年份作为 start_year。
        """
        listing_year = ""
        # 尝试从已采集的 company_info 获取上市年份
        # （collect() 在 financial_indicators 之前已调用 _collect_company_info）
        if hasattr(self, "_cached_listing_year"):
            listing_year = self._cached_listing_year

        params = self._get_param_names(ak.stock_financial_analysis_indicator)
        kwargs: dict = {"symbol": self.symbol}
        if "start_year" in params and listing_year:
            kwargs["start_year"] = listing_year

        return self.safe_call(
            "financial_indicators",
            ak.stock_financial_analysis_indicator,
            **kwargs,
        )

    def _collect_valuation_history(self) -> dict | None:
        """主题④：估值历史数据。"""
        df: pd.DataFrame | None = None
        lg_indicator = getattr(ak, "stock_a_lg_indicator", None)
        if lg_indicator is not None:
            params = self._get_param_names(lg_indicator)
            if "stock" in params:
                kwargs = {"stock": self.symbol}
            elif "symbol" in params:
                kwargs = {"symbol": self.symbol}
            else:
                kwargs = {"symbol": self.symbol}
            df = self.safe_call("valuation_history", lg_indicator, **kwargs)
        else:
            msg = "valuation_history: stock_a_lg_indicator 不可用，回退到 stock_zh_valuation_baidu"
            self.errors.append(msg)
            logger.warning(msg)
            df = self._build_valuation_history_from_baidu()

        if df is None:
            return None

        if "trade_date" in df.columns:
            df = (
                df.assign(_trade_date=pd.to_datetime(df["trade_date"], errors="coerce"))
                .sort_values("_trade_date", ascending=True, na_position="last")
                .drop(columns=["_trade_date"])
            )
        else:
            msg = "valuation_history: 缺少列 'trade_date'，按原始顺序计算当前值与分位数"
            self.errors.append(msg)
            logger.warning(msg)

        latest = df.iloc[-1]

        current_pe_ttm = self._safe_float(latest.get("pe_ttm"))
        current_pb = self._safe_float(latest.get("pb"))

        pe_series = df.get("pe_ttm")
        if pe_series is None:
            msg = "valuation_history: 缺少列 'pe_ttm'，pe_percentile 置为 None"
            self.errors.append(msg)
            logger.warning(msg)
            pe_percentile = None
        else:
            pe_percentile = self._calc_percentile(pe_series, latest.get("pe_ttm"))

        pb_series = df.get("pb")
        if pb_series is None:
            msg = "valuation_history: 缺少列 'pb'，pb_percentile 置为 None"
            self.errors.append(msg)
            logger.warning(msg)
            pb_percentile = None
        else:
            pb_percentile = self._calc_percentile(pb_series, latest.get("pb"))

        pe_desc = self._percentile_description("PE", pe_percentile)
        pb_desc = self._percentile_description("PB", pb_percentile)

        return {
            "current_pe_ttm": current_pe_ttm,
            "current_pb": current_pb,
            "pe_percentile": pe_percentile,
            "pb_percentile": pb_percentile,
            "current_ps_ttm": self._safe_float(latest.get("ps_ttm")),
            "current_dv_ttm": self._safe_float(latest.get("dv_ttm")),
            "history_summary": f"{pe_desc}；{pb_desc}",
        }

    def _build_valuation_history_from_baidu(self) -> pd.DataFrame | None:
        """Fallback valuation history builder when stock_a_lg_indicator is unavailable."""
        valuation_func = getattr(ak, "stock_zh_valuation_baidu", None)
        if valuation_func is None:
            msg = "valuation_history: stock_zh_valuation_baidu 不可用，无法回退"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        # stock_zh_valuation_baidu 仅支持：总市值/市盈率(TTM)/市盈率(静)/市净率/市现率
        # "市销率(TTM)" 和 "股息率(TTM)" 不在支持范围内，请求会导致 TypeError；
        # ps_ttm/dv_ttm 将保持 None，由上层调用者记录。
        indicators = {
            "pe_ttm": "市盈率(TTM)",
            "pb": "市净率",
        }
        merged: pd.DataFrame | None = None
        for field, indicator in indicators.items():
            part = self.safe_call(
                f"valuation_history_baidu:{field}",
                valuation_func,
                symbol=self.symbol,
                indicator=indicator,
                period="近五年",
            )
            if part is None:
                continue
            normalized = self._normalize_valuation_series(part, field, indicator)
            if normalized is None:
                continue

            if merged is None:
                merged = normalized
            else:
                merged = merged.merge(normalized, on="trade_date", how="outer")

        if merged is None or merged.empty:
            msg = "valuation_history: 回退接口未能构建有效估值序列"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        return merged

    def _normalize_valuation_series(
        self,
        df: pd.DataFrame,
        target_field: str,
        indicator_label: str,
    ) -> pd.DataFrame | None:
        """Normalize one valuation DataFrame into ['trade_date', target_field]."""
        date_col = self._pick_first_existing_column(
            df, ["trade_date", "日期", "date", "交易日期"]
        )
        if date_col is None and len(df.columns) > 0:
            date_col = df.columns[0]
        if date_col is None:
            msg = f"valuation_history: {indicator_label} 缺少日期列"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        candidate_cols = [col for col in df.columns if col != date_col]
        if not candidate_cols:
            msg = f"valuation_history: {indicator_label} 缺少数值列"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        best_col = None
        best_non_na = -1
        for col in candidate_cols:
            non_na = pd.to_numeric(df[col], errors="coerce").notna().sum()
            if non_na > best_non_na:
                best_non_na = non_na
                best_col = col

        if best_col is None or best_non_na <= 0:
            msg = f"valuation_history: {indicator_label} 未找到可解析数值列"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        out = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(df[date_col], errors="coerce"),
                target_field: pd.to_numeric(df[best_col], errors="coerce"),
            }
        )
        out = out.dropna(subset=["trade_date"])
        return out

    @staticmethod
    def _calc_percentile(series: pd.Series, current_value) -> float | None:
        """Compute percentile of current_value among historical series."""
        clean = pd.to_numeric(series, errors="coerce").dropna()
        current_numeric = pd.to_numeric(current_value, errors="coerce")
        if len(clean) < 10 or pd.isna(current_numeric):
            return None
        rank = (clean < float(current_numeric)).sum()
        return round(rank / len(clean) * 100, 1)

    @staticmethod
    def _percentile_description(indicator: str, percentile: float | None) -> str:
        """Generate textual percentile description."""
        if percentile is None:
            return f"{indicator}历史分位数据不足"
        if percentile < 20:
            level = "极低位置（历史底部区域）"
        elif percentile < 40:
            level = "偏低位置"
        elif percentile < 60:
            level = "中等位置"
        elif percentile < 80:
            level = "偏高位置"
        else:
            level = "极高位置（历史顶部区域）"
        return f"{indicator}历史分位{percentile}%，处于{level}"

    def _collect_valuation_vs_industry(self) -> dict | None:
        """主题⑤：行业估值对比。

        stock_zh_valuation_comparison_em 返回同行比较表，列名为：
            代码, 市盈率-TTM, 市净率-MRQ, 市净率-24A 等
        其中目标股通过 "代码" 列定位，行业均值从其余同行行计算。
        """
        upper_symbol = format_symbol(self.symbol, "upper")
        df = self.safe_call(
            "valuation_vs_industry",
            ak.stock_zh_valuation_comparison_em,
            symbol=upper_symbol,
        )
        if df is None:
            return None

        # 找到目标股行（按股票代码匹配）
        stock_row_df = self._safe_filter(df, "代码", self.symbol, "valuation_vs_industry")
        if stock_row_df.empty:
            msg = f"valuation_vs_industry: 代码 '{self.symbol}' 在同行表中未找到"
            self.errors.append(msg)
            logger.warning(msg)
            stock_row: pd.Series | dict = {}
        else:
            stock_row = stock_row_df.iloc[0]

        stock_pe = self._safe_float(stock_row.get("市盈率-TTM") if isinstance(stock_row, pd.Series) else None)
        stock_pb = self._safe_float(stock_row.get("市净率-MRQ") if isinstance(stock_row, pd.Series) else None)

        # 计算行业均值（排除目标股行和代码为空的汇总行）
        industry_avg_pe = None
        industry_median_pe = None
        industry_avg_pb = None
        if "代码" in df.columns:
            peer_df = df[(df["代码"] != self.symbol) & (df["代码"].astype(str).str.strip() != "")]
            if "市盈率-TTM" in peer_df.columns:
                pe_series = pd.to_numeric(peer_df["市盈率-TTM"], errors="coerce").dropna()
                pe_series = pe_series[pe_series > 0]
                if len(pe_series) > 0:
                    industry_avg_pe = round(float(pe_series.mean()), 2)
                    industry_median_pe = round(float(pe_series.median()), 2)
            if "市净率-MRQ" in peer_df.columns:
                pb_series = pd.to_numeric(peer_df["市净率-MRQ"], errors="coerce").dropna()
                pb_series = pb_series[pb_series > 0]
                if len(pb_series) > 0:
                    industry_avg_pb = round(float(pb_series.mean()), 2)

        return {
            "stock_pe": stock_pe,
            "industry_avg_pe": industry_avg_pe,
            "industry_median_pe": industry_median_pe,
            "stock_pb": stock_pb,
            "industry_avg_pb": industry_avg_pb,
            "relative_valuation": self._judge_relative_valuation(stock_pe, industry_avg_pe),
        }

    @staticmethod
    def _judge_relative_valuation(
        stock_pe: float | None, industry_pe: float | None
    ) -> str:
        """Judge stock PE level relative to industry PE."""
        if stock_pe is None or industry_pe is None or stock_pe <= 0 or industry_pe <= 0:
            return "数据不足，无法判断"
        ratio = stock_pe / industry_pe
        if ratio < 0.8:
            return "明显低于行业平均"
        if ratio < 0.95:
            return "略低于行业平均"
        if ratio < 1.05:
            return "接近行业平均"
        if ratio < 1.2:
            return "略高于行业平均"
        return "明显高于行业平均"

    def _collect_fund_flow(self) -> dict | None:
        """主题⑥：个股资金流向。"""
        market = get_market(self.symbol)
        df = self.safe_call(
            "fund_flow",
            ak.stock_individual_fund_flow,
            stock=self.symbol,
            market=market,
        )
        if df is None:
            return None

        if "日期" in df.columns:
            df = (
                df.assign(_flow_date=pd.to_datetime(df["日期"], errors="coerce"))
                .sort_values("_flow_date", ascending=True, na_position="last")
                .drop(columns=["_flow_date"])
            )
        else:
            msg = "fund_flow: 缺少列 '日期'，按原始顺序计算明细与汇总"
            self.errors.append(msg)
            logger.warning(msg)

        recent = df.tail(AKSHARE_FUND_FLOW_DAYS)
        detail = []
        for _, row in recent.iterrows():
            detail.append(
                {
                    "date": self._safe_str(row.get("日期")),
                    "main_net_inflow": self._safe_float(row.get("主力净流入-净额")),
                    "main_net_inflow_pct": self._safe_float(row.get("主力净流入-净占比")),
                }
            )

        summary_5d_window = 5
        summary_10d_window = 10
        main_col = "主力净流入-净额"
        total_5d = None
        total_10d = None
        if main_col in df.columns:
            if len(df) >= summary_5d_window:
                total_5d = self._safe_float(df.tail(summary_5d_window)[main_col].sum())
            else:
                msg = (
                    f"fund_flow: 历史数据不足 {summary_5d_window} 日，"
                    "main_net_inflow_5d_total 置为 None"
                )
                self.errors.append(msg)
                logger.warning(msg)

            if len(df) >= summary_10d_window:
                total_10d = self._safe_float(
                    df.tail(summary_10d_window)[main_col].sum()
                )
            else:
                msg = (
                    f"fund_flow: 历史数据不足 {summary_10d_window} 日，"
                    "main_net_inflow_10d_total 置为 None"
                )
                self.errors.append(msg)
                logger.warning(msg)
        else:
            msg = "fund_flow: 缺少列 '主力净流入-净额'，汇总字段置为 None"
            self.errors.append(msg)
            logger.warning(msg)

        trend = self._judge_fund_flow_trend(total_5d, total_10d)

        return {
            "recent_days": detail,
            "summary": {
                "main_net_inflow_5d_total": total_5d,
                "main_net_inflow_10d_total": total_10d,
                "trend": trend,
            },
        }

    @staticmethod
    def _judge_fund_flow_trend(total_5d: float | None, total_10d: float | None) -> str:
        """Generate flow trend description from 5d/10d aggregates."""
        parts: list[str] = []
        if total_5d is not None:
            direction = "净流入" if total_5d >= 0 else "净流出"
            parts.append(f"近5日主力{direction}")
        if total_10d is not None:
            direction = "净流入" if total_10d >= 0 else "净流出"
            parts.append(f"近10日整体{direction}")
        return "，".join(parts) if parts else "数据不足"

    def _collect_sector_flow(self, industry: str) -> dict | None:
        """主题⑦：板块资金流向。"""
        result: dict = {}

        df_industry = self._safe_call_sector_fund_flow(
            topic="sector_flow_industry",
            legacy_func_name="stock_board_industry_fund_flow_rank_em",
            legacy_cache_key="stock_board_industry_fund_flow_rank_em:今日",
            sector_type="行业资金流",
            fallback_cache_key="stock_sector_fund_flow_rank:行业资金流:今日",
        )
        if df_industry is not None and industry:
            match = self._safe_filter(
                df_industry,
                "名称",
                industry,
                "sector_flow_industry",
                method="eq",
            )
            if match.empty:
                fuzzy_match = self._safe_filter(
                    df_industry,
                    "名称",
                    industry,
                    "sector_flow_industry",
                    method="contains",
                )
                if not fuzzy_match.empty:
                    hit_name = self._safe_str(fuzzy_match.iloc[0].get("名称"))
                    msg = (
                        f"sector_flow_industry: 行业 '{industry}' 未精确命中，"
                        f"回退到包含匹配并命中 '{hit_name}'"
                    )
                    self.errors.append(msg)
                    logger.warning(msg)
                    match = fuzzy_match

            if not match.empty:
                row = match.iloc[0]
                result["industry_name"] = industry

                rank_col = None
                for col in ("排名", "序号", "名次"):
                    if col in df_industry.columns:
                        rank_col = col
                        break

                if rank_col is not None:
                    rank_val = self._safe_float(row.get(rank_col))
                    result["industry_rank"] = int(rank_val) if rank_val is not None else None
                else:
                    pos_df = df_industry.reset_index(drop=True)
                    matched_name = self._safe_str(row.get("名称"))
                    pos_match = self._safe_filter(
                        pos_df,
                        "名称",
                        matched_name,
                        "sector_flow_industry",
                        method="eq",
                    )
                    if pos_match.empty and matched_name:
                        pos_match = self._safe_filter(
                            pos_df,
                            "名称",
                            matched_name,
                            "sector_flow_industry",
                            method="contains",
                        )
                    result["industry_rank"] = (
                        int(pos_match.index[0]) + 1 if not pos_match.empty else None
                    )

                result["industry_net_inflow_today"] = self._safe_float(
                    row.get("今日主力净流入-净额")
                )
            else:
                msg = (
                    f"sector_flow_industry: 行业 '{industry}' 在板块数据中"
                    "精确和模糊匹配均未命中"
                )
                self.errors.append(msg)
                logger.warning(msg)
                result["industry_name"] = industry
                result["industry_rank"] = None
                result["industry_net_inflow_today"] = None

        df_concept = self._safe_call_sector_fund_flow(
            topic="sector_flow_concept",
            legacy_func_name="stock_board_concept_fund_flow_rank_em",
            legacy_cache_key="stock_board_concept_fund_flow_rank_em:今日",
            sector_type="概念资金流",
            fallback_cache_key="stock_sector_fund_flow_rank:概念资金流:今日",
        )
        if df_concept is not None:
            concept_sorted = df_concept
            concept_rank_col = None
            for col in ("排名", "序号", "名次"):
                if col in df_concept.columns:
                    concept_rank_col = col
                    break

            if concept_rank_col is not None:
                concept_sorted = (
                    df_concept.assign(
                        _rank_num=pd.to_numeric(
                            df_concept[concept_rank_col], errors="coerce"
                        )
                    )
                    .sort_values("_rank_num", ascending=True, na_position="last")
                    .drop(columns=["_rank_num"])
                )
            elif "今日主力净流入-净额" in df_concept.columns:
                concept_sorted = (
                    df_concept.assign(
                        _inflow_num=pd.to_numeric(
                            df_concept["今日主力净流入-净额"], errors="coerce"
                        )
                    )
                    .sort_values("_inflow_num", ascending=False, na_position="last")
                    .drop(columns=["_inflow_num"])
                )
            else:
                msg = (
                    "sector_flow_concept: 缺少排序列（排名/序号/名次/今日主力净流入-净额），"
                    "按原始顺序截取 Top5"
                )
                self.errors.append(msg)
                logger.warning(msg)

            top5 = concept_sorted.head(5)
            result["hot_concepts_top5"] = [
                {
                    "name": self._safe_str(row.get("名称")),
                    "net_inflow": self._safe_float(row.get("今日主力净流入-净额")),
                }
                for _, row in top5.iterrows()
            ]

        return result if result else None

    def _safe_call_sector_fund_flow(
        self,
        *,
        topic: str,
        legacy_func_name: str,
        legacy_cache_key: str,
        sector_type: str,
        fallback_cache_key: str,
    ) -> pd.DataFrame | None:
        """Load sector flow with AKShare version compatibility."""
        legacy_func = getattr(ak, legacy_func_name, None)
        if legacy_func is not None:
            return self.safe_call_market_cached(
                legacy_cache_key,
                topic,
                legacy_func,
                indicator="今日",
            )

        fallback_func = getattr(ak, "stock_sector_fund_flow_rank", None)
        if fallback_func is None:
            msg = (
                f"{topic}: 无可用接口（{legacy_func_name} / stock_sector_fund_flow_rank）"
            )
            self.errors.append(msg)
            logger.warning(msg)
            return None

        return self.safe_call_market_cached(
            fallback_cache_key,
            topic,
            fallback_func,
            indicator="今日",
            sector_type=sector_type,
        )

    def _collect_northbound(self) -> dict | None:
        """主题⑧：北向资金持仓。"""
        df = self.safe_call_market_cached(
            "stock_hsgt_hold_stock_em:北向:今日排行",
            "northbound",
            ak.stock_hsgt_hold_stock_em,
            market="北向",
            indicator="今日排行",
        )
        if df is None:
            return None

        row = self._safe_filter(df, "代码", self.symbol, "northbound")
        if row.empty:
            return {
                "held": False,
                "shares_held": None,
                "market_value": None,
                "change_pct": None,
                "note": "未在北向资金持仓名单中找到（可能未持有或披露规则限制）",
            }

        r = row.iloc[0]
        return {
            "held": True,
            "shares_held": self._safe_float(r.get("今日持股-股数")),
            "market_value": self._safe_float(r.get("今日持股-市值")),
            "change_pct": self._safe_float(r.get("今日增持估计-市值增幅")),
            "note": "北向资金披露规则2024年8月后有变化，数据仅供参考",
        }

    def _collect_shareholder_count(self) -> list[dict] | None:
        """主题⑨：股东户数。"""
        df = self.safe_call(
            "shareholder_count",
            ak.stock_zh_a_gdhs_detail_em,
            symbol=self.symbol,
        )
        if df is None:
            return None

        if "股东户数统计截止日" in df.columns:
            df = (
                df.assign(
                    _stat_date=pd.to_datetime(df["股东户数统计截止日"], errors="coerce")
                )
                .sort_values("_stat_date", ascending=False, na_position="last")
                .drop(columns=["_stat_date"])
            )
        else:
            msg = "shareholder_count: 缺少列 '股东户数统计截止日'，按原始顺序截取最近N期"
            self.errors.append(msg)
            logger.warning(msg)

        df = df.head(AKSHARE_SHAREHOLDER_PERIODS)

        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "date": self._safe_str(row.get("股东户数统计截止日")),
                    "count": self._safe_int(row.get("股东户数-本次")),
                    "change_pct": self._safe_float(row.get("股东户数-增减比例")),
                }
            )

        return results

    def _collect_dividend_history(self) -> list[dict] | None:
        """主题⑩：分红历史。"""
        df = self._safe_call_dividend_history_df()
        if df is None:
            return None

        if "年度" in df.columns:
            df = (
                df.assign(
                    _year_num=pd.to_numeric(
                        df["年度"].astype(str).str.extract(r"(\d{4})", expand=False),
                        errors="coerce",
                    )
                )
                .sort_values("_year_num", ascending=False, na_position="last")
                .drop(columns=["_year_num"])
            )
        elif "除权除息日" in df.columns:
            df = (
                df.assign(_ex_date=pd.to_datetime(df["除权除息日"], errors="coerce"))
                .sort_values("_ex_date", ascending=False, na_position="last")
                .drop(columns=["_ex_date"])
            )
        elif "公告日期" in df.columns:
            df = (
                df.assign(_announce_date=pd.to_datetime(df["公告日期"], errors="coerce"))
                .sort_values("_announce_date", ascending=False, na_position="last")
                .drop(columns=["_announce_date"])
            )
        else:
            msg = "dividend_history: 缺少排序列（年度/除权除息日/公告日期），按原始顺序截取"
            self.errors.append(msg)
            logger.warning(msg)

        df = df.head(AKSHARE_DIVIDEND_YEARS)

        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "year": self._safe_str(
                        row.get("年度"),
                        default=self._safe_str(row.get("_derived_year")),
                    ),
                    "dividend_per_share": self._safe_float(
                        row.get("累计股息")
                        if "累计股息" in df.columns
                        else row.get("派息")
                    ),
                    "ex_date": self._safe_str(
                        row.get("除权除息日"),
                        default=self._safe_str(row.get("公告日期")),
                    ),
                }
            )

        return results

    def _safe_call_dividend_history_df(self) -> pd.DataFrame | None:
        """Load dividend history with AKShare compatibility fallback chain."""
        detail_func = getattr(ak, "stock_history_dividend_detail", None)
        if detail_func is not None:
            params = self._get_param_names(detail_func)
            kwargs = {}
            if "symbol" in params:
                kwargs["symbol"] = self.symbol
            if "indicator" in params:
                kwargs["indicator"] = "分红"
            detail_df = self.safe_call("dividend_history_detail", detail_func, **kwargs)
            if detail_df is not None and not detail_df.empty:
                if "年度" not in detail_df.columns and "公告日期" in detail_df.columns:
                    detail_df = detail_df.copy()
                    detail_df["_derived_year"] = (
                        pd.to_datetime(detail_df["公告日期"], errors="coerce")
                        .dt.year.astype("Int64")
                        .astype(str)
                        .replace("<NA>", "")
                    )
                return detail_df

        summary_func = getattr(ak, "stock_history_dividend", None)
        if summary_func is None:
            msg = "dividend_history: 无可用接口（stock_history_dividend_detail / stock_history_dividend）"
            self.errors.append(msg)
            logger.warning(msg)
            return None

        params = self._get_param_names(summary_func)
        kwargs = {}
        if "symbol" in params:
            kwargs["symbol"] = format_symbol(self.symbol, "lower")
        if "indicator" in params:
            kwargs["indicator"] = "分红"

        summary_df = self.safe_call("dividend_history", summary_func, **kwargs)
        if summary_df is None:
            return None

        if "代码" in summary_df.columns:
            row = self._safe_filter(summary_df, "代码", self.symbol, "dividend_history")
            if row.empty:
                msg = f"dividend_history: 全市场分红数据中未找到 {self.symbol}"
                self.errors.append(msg)
                logger.warning(msg)
                return None
            summary_df = row.copy()

        return summary_df

    def _collect_earnings_forecast(self) -> dict | None:
        """主题⑪：业绩预告。"""
        quarter_ends = self._get_recent_quarter_ends(lookback=4)
        had_any_successful_fetch = False

        for qe_date in quarter_ends:
            df = self.safe_call_market_cached(
                f"stock_yjyg_em:{qe_date}",
                "earnings_forecast",
                ak.stock_yjyg_em,
                date=qe_date,
            )
            if df is None:
                continue

            had_any_successful_fetch = True

            row = self._safe_filter(df, "股票代码", self.symbol, "earnings_forecast")
            if row.empty:
                continue

            r = row.iloc[0]
            self.topic_status["earnings_forecast"] = self.STATUS_OK
            return {
                "latest_period": qe_date,
                "forecast_type": self._safe_optional_str(r.get("业绩变动类型")),
                "forecast_range": self._safe_optional_str(r.get("预测内容")),
                "available": True,
            }

        if had_any_successful_fetch:
            logger.info(
                f"earnings_forecast: 最近 {len(quarter_ends)} 个季度均未找到 "
                f"{self.symbol} 的业绩预告（API 正常，该股票无预告）"
            )
            self.topic_status["earnings_forecast"] = self.STATUS_NO_DATA
            return {
                "latest_period": None,
                "forecast_type": None,
                "forecast_range": None,
                "available": False,
            }

        logger.warning(f"earnings_forecast: {len(quarter_ends)} 次 API 调用全部失败")
        return None

    @staticmethod
    def _get_recent_quarter_ends(
        lookback: int = 4,
        today: date | None = None,
        style: Literal["standard", "short"] = "standard",
    ) -> list[str]:
        """Return recent N passed quarter-end dates in reverse chronological order.

        Styles:
          - standard: "20240930"
          - short: "20243" (for institutional holdings)
        """
        if today is None:
            today = date.today()

        # (month, day, short_suffix)
        quarter_ends = [(12, 31, "4"), (9, 30, "3"), (6, 30, "2"), (3, 31, "1")]
        results: list[str] = []
        year = today.year

        while len(results) < lookback:
            for q_month, q_day, q_suffix in quarter_ends:
                qe_date = date(year, q_month, q_day)
                if qe_date <= today:
                    if style == "standard":
                        results.append(f"{year}{q_month:02d}{q_day:02d}")
                    else:
                        results.append(f"{year}{q_suffix}")

                    if len(results) >= lookback:
                        break
            year -= 1

        return results

    def _collect_pledge_ratio(self) -> dict | None:
        """主题⑫：股权质押。"""
        df = self.safe_call_market_cached(
            "stock_gpzy_pledge_ratio_em",
            "pledge_ratio",
            ak.stock_gpzy_pledge_ratio_em,
        )
        if df is None:
            return None

        row = self._safe_filter(df, "股票代码", self.symbol, "pledge_ratio")
        if row.empty:
            return {"ratio_pct": 0.0, "pledged_shares": None, "risk_level": "低"}

        r = row.iloc[0]
        ratio = self._safe_float(r.get("质押比例"))
        risk = self._judge_pledge_risk(ratio)

        return {
            "ratio_pct": ratio,
            "pledged_shares": self._safe_float(r.get("质押股数")),
            "risk_level": risk,
        }

    def _collect_consensus_forecast(self) -> list[dict] | None:
        """主题⑬：一致预期。"""
        df = self.safe_call(
            "consensus_forecast",
            ak.stock_profit_forecast_ths,
            symbol=self.symbol,
        )
        if df is None:
            return None

        # 核心返回字段: 年度, 预测机构数, 均值, 行业平均数
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "year": self._safe_str(row.get("年度")),
                    "inst_count": self._safe_int(row.get("预测机构数")),
                    "net_profit_avg": self._safe_float(row.get("均值")),
                    "industry_avg": self._safe_float(row.get("行业平均数")),
                }
            )
        return results

    def _collect_institutional_holdings(self) -> list[dict] | None:
        """主题⑭：机构持仓详情。"""
        quarters = self._get_recent_quarter_ends(lookback=2, style="short")
        for quarter in quarters:
            df = self.safe_call(
                "institutional_holdings",
                ak.stock_institute_hold_detail,
                stock=self.symbol,
                quarter=quarter,
            )
            if df is not None and not df.empty:
                # 核心返回字段: 持股机构类型, 持股机构简称, 持股比例 (或 最新持股比例)
                ratio_col = self._pick_first_existing_column(
                    df, ["最新持股比例", "持股比例"]
                )
                results: list[dict] = []
                for _, row in df.iterrows():
                    results.append(
                        {
                            "type": self._safe_str(row.get("持股机构类型")),
                            "name": self._safe_str(row.get("持股机构简称")),
                            "ratio": self._safe_float(row.get(ratio_col)) if ratio_col else None,
                        }
                    )
                return results
        return None

    def _collect_business_composition(self) -> list[dict] | None:
        """主题⑮：主营结构。"""
        upper_symbol = format_symbol(self.symbol, "upper")
        df = self.safe_call(
            "business_composition",
            ak.stock_zygc_em,
            symbol=upper_symbol,
        )
        if df is None:
            return None

        # 核心返回字段: 分类类型, 主营构成, 收入比例, 毛利率
        # 优先展示 '按产品分类'
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "type": self._safe_str(row.get("分类类型")),
                    "item": self._safe_str(row.get("主营构成")),
                    "revenue_ratio": self._safe_float(row.get("收入比例")),
                    "gross_margin": self._safe_float(row.get("毛利率")),
                }
            )
        return results

    @staticmethod
    def _judge_pledge_risk(ratio: float | None) -> str:
        """Risk level by pledge ratio."""
        if ratio is None or ratio < 10:
            return "低"
        if ratio < 30:
            return "中"
        if ratio < 50:
            return "高"
        return "极高"

    def collect(self) -> AKShareData:
        """Collect all 15 topics serially and return validated AKShareData."""
        results: dict = {}
        industry = ""

        info = self._safe_collect("company_info", self._collect_company_info)
        if info is not None:
            results["company_info"] = info
            industry = info.get("industry", "")

        quote = self._safe_collect("realtime_quote", self._collect_realtime_quote)
        if quote is not None:
            results["realtime_quote"] = quote

        financial = self._safe_collect(
            "financial_indicators", self._collect_financial_indicators
        )
        if financial is not None:
            results["financial_indicators"] = financial

        valuation = self._safe_collect("valuation_history", self._collect_valuation_history)
        if valuation is not None:
            results["valuation_history"] = valuation

        vs_industry = self._safe_collect(
            "valuation_vs_industry", self._collect_valuation_vs_industry
        )
        if vs_industry is not None:
            results["valuation_vs_industry"] = vs_industry

        fund = self._safe_collect("fund_flow", self._collect_fund_flow)
        if fund is not None:
            results["fund_flow"] = fund

        sector = self._safe_collect("sector_flow", self._collect_sector_flow, industry)
        if sector is not None:
            results["sector_flow"] = sector

        northbound = self._safe_collect("northbound", self._collect_northbound)
        if northbound is not None:
            results["northbound"] = northbound

        shareholders = self._safe_collect(
            "shareholder_count", self._collect_shareholder_count
        )
        if shareholders is not None:
            results["shareholder_count"] = shareholders

        dividends = self._safe_collect("dividend_history", self._collect_dividend_history)
        if dividends is not None:
            results["dividend_history"] = dividends

        forecast = self._safe_collect(
            "earnings_forecast", self._collect_earnings_forecast
        )
        if forecast is not None:
            results["earnings_forecast"] = forecast

        pledge = self._safe_collect("pledge_ratio", self._collect_pledge_ratio)
        if pledge is not None:
            results["pledge_ratio"] = pledge

        consensus = self._safe_collect("consensus_forecast", self._collect_consensus_forecast)
        if consensus is not None:
            results["consensus_forecast"] = consensus

        institutional = self._safe_collect(
            "institutional_holdings", self._collect_institutional_holdings
        )
        if institutional is not None:
            results["institutional_holdings"] = institutional

        business = self._safe_collect(
            "business_composition", self._collect_business_composition
        )
        if business is not None:
            results["business_composition"] = business

        successful = sum(
            1
            for status in self.topic_status.values()
            if status in (self.STATUS_OK, self.STATUS_NO_DATA)
        )
        failed = sum(
            1 for status in self.topic_status.values() if status == self.STATUS_FAILED
        )

        if successful == 0:
            raise AKShareCollectionError(self.symbol, self.errors)

        logger.info(
            f"AKShare collection completed for {self.symbol}: "
            f"{successful}/15 topics succeeded ({failed} failed, {len(self.errors)} errors)"
        )

        return AKShareData(
            meta=AKShareMeta(
                symbol=self.symbol,
                name=self.name,
                query_time=datetime.now().isoformat(),
                data_errors=self.errors,
                successful_topics=successful,
                topic_status=dict(self.topic_status),
            ),
            **results,
        )


def collect_akshare_data(
    symbol: str,
    name: str,
    market_cache: AKShareMarketCache | None = None,
) -> AKShareData:
    """Module A public entrypoint."""
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError(f"Invalid symbol: '{symbol}', expected 6-digit string")

    logger.info(f"[Module A] Starting AKShare data collection for {symbol} ({name})")
    start_time = time.time()
    collector = AKShareCollector(symbol, name, market_cache=market_cache)
    result = collector.collect()
    elapsed = time.time() - start_time
    logger.info(
        f"[Module A] completed for {symbol}: "
        f"{result.meta.successful_topics}/15 topics, {len(result.meta.data_errors)} errors, "
        f"elapsed {elapsed:.1f}s"
    )
    return result
