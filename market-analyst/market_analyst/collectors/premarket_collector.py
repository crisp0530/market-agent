"""盘前/盘后数据收集器 — 通过 yfinance ticker.info 获取实时盘前报价

只对 T1/T4 极端标的 + 用户自定义 watchlist 拉取盘前数据，
避免对全部 87 个标的调用（太慢）。
"""
import yfinance as yf
import pandas as pd
from loguru import logger


class PremarketCollector:
    """收集盘前/盘后价格数据"""

    def __init__(self, config: dict = None):
        pm_cfg = (config or {}).get("premarket", {})
        self.enabled = pm_cfg.get("enabled", True)
        # 用户自定义关注列表（始终拉取盘前数据）
        self.watchlist = pm_cfg.get("watchlist", [])

    def collect(self, strength_df: pd.DataFrame) -> pd.DataFrame:
        """
        对 T1/T4 标的 + watchlist 拉取盘前数据，合并到 strength_df。
        新增列：pm_price, pm_change_pct, pm_gap（盘前价相对收盘价的 gap%）
        """
        if not self.enabled:
            logger.info("盘前数据: 已禁用")
            return strength_df

        # 确定需要查询的标的
        targets = set()

        # T1/T4 美股标的（A股没有盘前交易）
        if not strength_df.empty:
            extreme = strength_df[
                (strength_df["tier"].isin(["T1", "T4"])) &
                (strength_df["market"] == "us")
            ]
            targets.update(extreme["symbol"].tolist())

        # 全局指标中的美股期货（VIX 等不一定有盘前）
        global_us = strength_df[
            (strength_df["market"] == "global") &
            (strength_df["symbol"].str.match(r'^[A-Z]'))
        ]
        targets.update(global_us["symbol"].tolist())

        # 用户 watchlist
        for item in self.watchlist:
            targets.add(item)

        if not targets:
            return strength_df

        logger.info(f"盘前数据: 查询 {len(targets)} 个标的...")

        results = []
        for symbol in targets:
            data = self._fetch_premarket(symbol)
            if data:
                results.append(data)

        if not results:
            logger.info("盘前数据: 无盘前报价（可能非盘前时段）")
            return strength_df

        pm_df = pd.DataFrame(results)
        logger.info(f"盘前数据: 获取 {len(pm_df)} 个标的")

        # 清除已有的 pm_ 列
        existing = [c for c in strength_df.columns if c.startswith("pm_")]
        if existing:
            strength_df = strength_df.drop(columns=existing)

        # 合并已有标的的盘前数据
        result = strength_df.merge(pm_df, on="symbol", how="left")

        # watchlist 中不在 strength_df 里的标的，作为独立行追加
        existing_symbols = set(result["symbol"].tolist())
        extra_rows = []
        for _, pm_row in pm_df.iterrows():
            if pm_row["symbol"] not in existing_symbols:
                # 补充基本信息
                extra = {
                    "symbol": pm_row["symbol"],
                    "name": pm_row["symbol"],
                    "market": "watchlist",
                    "close": pm_row.get("pm_price", 0) / (1 + pm_row.get("pm_gap", 0) / 100) if pm_row.get("pm_gap", 0) != 0 else pm_row.get("pm_price", 0),
                    "tier": "—",
                    "composite_score": 0,
                    "pm_price": pm_row["pm_price"],
                    "pm_change_pct": pm_row["pm_change_pct"],
                    "pm_gap": pm_row["pm_gap"],
                }
                # 尝试从 yfinance 拿名称
                try:
                    import yfinance as yf
                    info = yf.Ticker(pm_row["symbol"]).info
                    extra["name"] = info.get("shortName", pm_row["symbol"])
                    extra["close"] = info.get("previousClose", extra["close"])
                except (ValueError, KeyError, Exception):
                    # yfinance 没有专用异常类，保留 Exception 兜底
                    pass
                extra_rows.append(extra)

        if extra_rows:
            extra_df = pd.DataFrame(extra_rows)
            result = pd.concat([result, extra_df], ignore_index=True)
            logger.info(f"  watchlist 新增: {[r['symbol'] for r in extra_rows]}")

        return result

    @staticmethod
    def _fetch_premarket(symbol: str) -> dict | None:
        """通过 yfinance ticker.info 获取单个标的的盘前数据"""
        try:
            # yfinance 需要特定格式
            yf_symbol = symbol
            # 全局指标的特殊符号转换
            if symbol == "GC=F" or symbol == "CL=F":
                yf_symbol = symbol  # 期货直接用
            elif symbol.startswith("^"):
                yf_symbol = symbol  # 指数直接用

            t = yf.Ticker(yf_symbol)
            info = t.info

            pm_price = info.get("preMarketPrice")
            pm_change_pct = info.get("preMarketChangePercent")
            prev_close = info.get("previousClose")
            reg_price = info.get("regularMarketPrice")

            if pm_price is None:
                return None

            # 计算盘前 gap（盘前价 vs 昨收）
            base_price = reg_price or prev_close or 0
            pm_gap = ((pm_price / base_price) - 1) * 100 if base_price > 0 else 0

            return {
                "symbol": symbol,
                "pm_price": round(pm_price, 4),
                "pm_change_pct": round(pm_change_pct, 2) if pm_change_pct else round(pm_gap, 2),
                "pm_gap": round(pm_gap, 2),
            }

        except (ValueError, KeyError, Exception) as e:
            # yfinance 没有专用异常类，保留 Exception 兜底
            logger.debug(f"盘前查询 {symbol} 失败: {e}")
            return None
