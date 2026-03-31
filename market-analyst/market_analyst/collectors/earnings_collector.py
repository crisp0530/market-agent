"""Financial data collector for earnings analysis. Wraps akshare (CN) and yfinance (US)."""
from __future__ import annotations

import pandas as pd
from loguru import logger


class EarningsCollector:
    """Collect structured earnings data for a single stock.

    Unlike other collectors (which return DataFrames of OHLCV), this returns
    a structured dict since financial statement data is not OHLCV-shaped.
    """

    def __init__(self, config: dict):
        cfg = config.get("earnings", {})
        self.reduction_days = cfg.get("reduction_alert_days", 90)
        self.pledge_alert = cfg.get("pledge_alert_ratio", 50)

    def collect(self, symbol: str, market: str = "cn") -> dict:
        """Collect earnings data for a stock.

        Returns:
            {
                "financials": [{"quarter": str, "revenue": float, "net_profit": float,
                                "revenue_yoy": float|None, "profit_yoy": float|None}],
                "forecast": {"consensus_profit": float|None},
                "risks": {"is_st": bool, "reductions": list, "pledge_ratio": float|None},
                "meta": {"name": str, "currency": str}
            }
        """
        if market == "cn":
            return self._collect_cn(symbol)
        else:
            return self._collect_us(symbol)

    def _collect_cn(self, symbol: str) -> dict:
        financials_df = self._fetch_cn_financials(symbol)
        financials = self._parse_cn_financials(financials_df)
        forecast = self._fetch_cn_forecast(symbol)
        risks = self._fetch_cn_risks(symbol)
        return {
            "financials": financials,
            "forecast": {"consensus_profit": forecast},
            "risks": risks,
            "meta": {"name": symbol, "currency": "CNY"},
        }

    def _collect_us(self, symbol: str) -> dict:
        financials = self._fetch_us_financials(symbol)
        forecast = self._fetch_us_forecast(symbol)
        risks = self._fetch_us_risks(symbol)
        return {
            "financials": financials,
            "forecast": {"consensus_profit": forecast},
            "risks": risks,
            "meta": {"name": symbol, "currency": "USD"},
        }

    def _fetch_cn_financials(self, symbol: str) -> pd.DataFrame:
        """Fetch A-share financial data via akshare."""
        try:
            import akshare as ak
            df = ak.stock_financial_analysis_indicator(symbol=symbol)
            return df.head(8) if not df.empty else pd.DataFrame()
        except Exception as e:
            logger.warning(f"Failed to fetch CN financials for {symbol}: {e}")
            return pd.DataFrame()

    def _parse_cn_financials(self, df: pd.DataFrame) -> list[dict]:
        if df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            period = str(row.get("报告期", ""))
            quarter = self._period_to_quarter(period)
            revenue = float(row.get("营业总收入", 0)) / 1e8
            profit = float(row.get("净利润", 0)) / 1e8
            results.append({
                "quarter": quarter,
                "revenue": round(revenue, 2),
                "net_profit": round(profit, 2),
                "revenue_yoy": None,
                "profit_yoy": None,
            })
        return results

    def _fetch_cn_forecast(self, symbol: str) -> float | None:
        """Fetch analyst consensus forecast via akshare."""
        try:
            import akshare as ak
            df = ak.stock_profit_forecast_em(symbol=symbol)
            if not df.empty and "预测净利润均值" in df.columns:
                return float(df.iloc[0]["预测净利润均值"])
        except Exception as e:
            logger.debug(f"No CN forecast for {symbol}: {e}")
        return None

    def _fetch_cn_risks(self, symbol: str) -> dict:
        """Fetch ST status, insider reductions, pledge ratio."""
        risks: dict = {"is_st": False, "reductions": [], "pledge_ratio": None}
        try:
            import akshare as ak
            try:
                st_df = ak.stock_zh_a_st_em()
                if not st_df.empty and symbol in st_df["代码"].values:
                    risks["is_st"] = True
            except Exception:
                pass

            try:
                from datetime import datetime, timedelta
                for days_back in range(0, 6):
                    try_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
                    try:
                        pledge_df = ak.stock_gpzy_pledge_ratio_em(date=try_date)
                        if not pledge_df.empty:
                            code_col = [c for c in pledge_df.columns if "代码" in c or "股票代码" in c]
                            if code_col:
                                row = pledge_df[pledge_df[code_col[0]] == symbol]
                                if not row.empty:
                                    ratio_col = [c for c in pledge_df.columns if "质押比例" in c]
                                    if ratio_col:
                                        risks["pledge_ratio"] = float(row.iloc[0][ratio_col[0]])
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            try:
                from datetime import datetime, timedelta
                df = ak.stock_hold_management_detail_em()
                if not df.empty:
                    code_col = [c for c in df.columns if "代码" in c or "股票代码" in c]
                    if code_col:
                        filtered = df[df[code_col[0]] == symbol]
                        if not filtered.empty:
                            # Filter by reduction_days to avoid stale records
                            date_col = [c for c in filtered.columns if "日期" in c or "变动日期" in c]
                            if date_col:
                                try:
                                    cutoff = (datetime.now() - timedelta(days=self.reduction_days)).strftime("%Y-%m-%d")
                                    filtered = filtered[filtered[date_col[0]].astype(str) >= cutoff]
                                except Exception:
                                    pass
                            if not filtered.empty:
                                risks["reductions"] = filtered.head(5).to_dict("records")
            except Exception:
                pass

        except ImportError:
            logger.warning("akshare not installed")
        return risks

    def _fetch_us_financials(self, symbol: str) -> list[dict]:
        """Fetch US financial data via yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            qf = ticker.quarterly_financials
            if qf is None or qf.empty:
                return []
            results = []
            for col in qf.columns[:8]:
                quarter = self._period_to_quarter(str(col.date()) if hasattr(col, "date") else str(col))
                revenue = float(qf.loc["Total Revenue", col]) / 1e8 if "Total Revenue" in qf.index else 0
                profit = float(qf.loc["Net Income", col]) / 1e8 if "Net Income" in qf.index else 0
                results.append({
                    "quarter": quarter,
                    "revenue": round(revenue, 2),
                    "net_profit": round(profit, 2),
                    "revenue_yoy": None,
                    "profit_yoy": None,
                })
            return results
        except Exception as e:
            logger.warning(f"Failed to fetch US financials for {symbol}: {e}")
            return []

    def _fetch_us_forecast(self, symbol: str) -> float | None:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            est = ticker.earnings_estimate
            if est is not None and not est.empty:
                return float(est.iloc[0].get("avg", 0))
        except Exception:
            pass
        return None

    def _fetch_us_risks(self, symbol: str) -> dict:
        risks: dict = {"reductions": []}
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            insiders = ticker.insider_transactions
            if insiders is not None and not insiders.empty:
                sales = insiders[insiders.get("Text", "").str.contains("Sale", case=False, na=False)]
                risks["reductions"] = sales.head(5).to_dict("records") if not sales.empty else []
        except Exception:
            pass
        return risks

    @staticmethod
    def _period_to_quarter(period: str) -> str:
        """Convert date string to quarter label like '2025Q4'."""
        try:
            if "-" in period:
                parts = period.split("-")
                year = parts[0]
                month = int(parts[1])
            else:
                return period
            q = (month - 1) // 3 + 1
            return f"{year}Q{q}"
        except Exception:
            return period
