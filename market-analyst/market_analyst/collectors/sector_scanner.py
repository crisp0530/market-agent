"""板块→个股钻取扫描器 — 基于 T1/T2 热门板块，向下筛选放量异动个股

从 strength_df 的梯队排名中识别热门板块（T1/T2），
映射到 TradingView 的 Sector 分类，扫描板块内放量+技术面有看点的个股。
同时扫描全市场大幅异动个股（>8% 涨跌）。
支持美股和A股两个市场。
"""
from typing import Optional
import pandas as pd
from loguru import logger

try:
    from tvscreener import Market, StockField, StockScreener
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

# ETF symbol → TradingView Sector 映射
ETF_TO_TV_SECTOR = {
    # 美股板块 ETF → TV Sector
    "XLE": "Energy Minerals",
    "XLK": "Electronic Technology",
    "XLF": "Finance",
    "XLV": "Health Technology",
    "XLI": "Producer Manufacturing",
    "XLP": "Consumer Non-Durables",
    "XLY": "Retail Trade",
    "XLU": "Utilities",
    "XLB": "Non-Energy Minerals",
    "XLRE": "Finance",
    "XLC": "Technology Services",
    "SMH": "Electronic Technology",
    "SOXX": "Electronic Technology",
    "IGV": "Technology Services",
    "HACK": "Technology Services",
    "CLOU": "Technology Services",
    "BOTZ": "Electronic Technology",
    "USO": "Energy Minerals",
    "GLD": "Non-Energy Minerals",
    "TAN": "Electronic Technology",
    "LIT": "Non-Energy Minerals",
    "JETS": "Transportation",
    "XBI": "Health Technology",
    "DBA": "Process Industries",
    "ARKK": "Technology Services",
}

# A股 ETF symbol → TradingView Sector 映射
CN_ETF_TO_TV_SECTOR = {
    "512480": "Electronic Technology",    # 半导体ETF
    "515030": "Consumer Durables",        # 新能源车ETF
    "516160": "Utilities",                # 新能源ETF
    "512880": "Finance",                  # 证券ETF
    "512800": "Finance",                  # 银行ETF
    "512010": "Health Technology",        # 医药ETF
    "512170": "Health Technology",        # 医疗ETF
    "515790": "Electronic Technology",    # 光伏ETF
    "512660": "Electronic Technology",    # 军工ETF
    "512200": "Finance",                  # 房地产ETF
    "515050": "Communications",           # 5GETF
    "159869": "Technology Services",      # 游戏ETF
    "562500": "Electronic Technology",    # 机器人ETF
    "159819": "Technology Services",      # 人工智能ETF
    "512690": "Consumer Non-Durables",    # 酒ETF
    "515210": "Non-Energy Minerals",      # 钢铁ETF
    "516950": "Producer Manufacturing",   # 基建ETF
    "512400": "Non-Energy Minerals",      # 有色金属ETF
    "159766": "Consumer Services",        # 旅游ETF
    "515880": "Communications",           # 通信ETF
    "512980": "Technology Services",      # 传媒ETF
    "515170": "Consumer Non-Durables",    # 食品饮料ETF
    "512580": "Industrial Services",      # 环保ETF
    "516110": "Consumer Durables",        # 汽车ETF
    "159870": "Process Industries",       # 化工ETF
    "515220": "Energy Minerals",          # 煤炭ETF
    "159611": "Utilities",                # 电力ETF
    "159985": "Process Industries",       # 豆粕ETF
    "159980": "Non-Energy Minerals",      # 有色ETF
}


class SectorScanner:
    """板块→个股钻取扫描"""

    def __init__(self, config: dict = None):
        scan_cfg = (config or {}).get("sector_scan", {})
        self.enabled = scan_cfg.get("enabled", True) and TV_AVAILABLE
        # 美股参数
        self.min_cap = scan_cfg.get("min_market_cap", 5e9)
        self.min_rel_vol = scan_cfg.get("min_relative_volume", 1.3)
        self.min_avg_vol = scan_cfg.get("min_avg_volume", 500000)
        self.big_move_threshold = scan_cfg.get("big_move_threshold", 8)
        self.max_per_sector = scan_cfg.get("max_per_sector", 8)
        # A股参数（市值门槛更低，涨跌幅限制不同）
        cn_cfg = scan_cfg.get("cn", {})
        self.cn_min_cap = cn_cfg.get("min_market_cap", 5e9)       # 50亿人民币
        self.cn_min_rel_vol = cn_cfg.get("min_relative_volume", 1.0)
        self.cn_min_avg_vol = cn_cfg.get("min_avg_volume", 100000)
        self.cn_big_move_threshold = cn_cfg.get("big_move_threshold", 5)  # A股涨跌停10%
        # tvscreener 查询行数限制
        self.sector_scan_limit = scan_cfg.get("sector_scan_limit", 50)
        self.big_mover_scan_limit = scan_cfg.get("big_mover_scan_limit", 30)
        self.max_big_movers = scan_cfg.get("max_big_movers", 10)

    def scan(self, strength_df: pd.DataFrame) -> dict:
        """
        扫描热门板块个股 + 全市场异动。
        返回: {
            "sector_picks": [{"sector": ..., "stocks": [...]}],
            "big_movers_up": [...],
            "big_movers_down": [...]
        }
        """
        if not self.enabled:
            logger.info("板块扫描: 不可用")
            return {"sector_picks": [], "big_movers_up": [], "big_movers_down": []}

        result = {
            "sector_picks": [],
            "big_movers_up": [],
            "big_movers_down": [],
        }

        # 1. 美股: 从 T1/T2 ETF 提取热门板块
        us_hot = self._identify_hot_sectors(strength_df, "us", ETF_TO_TV_SECTOR)
        logger.info(f"板块扫描(美股): 识别到 {len(us_hot)} 个热门板块")

        for sector_name, tv_sector, source_etfs in us_hot:
            stocks = self._scan_sector(tv_sector, Market.AMERICA, self.min_cap, self.min_rel_vol, self.min_avg_vol)
            if stocks:
                result["sector_picks"].append({
                    "sector": sector_name,
                    "market": "us",
                    "tv_sector": tv_sector,
                    "source_etfs": source_etfs,
                    "stocks": stocks[:self.max_per_sector],
                })

        # 2. A股: 从 T1/T2 ETF 提取热门板块
        cn_hot = self._identify_hot_sectors(strength_df, "cn", CN_ETF_TO_TV_SECTOR)
        logger.info(f"板块扫描(A股): 识别到 {len(cn_hot)} 个热门板块")

        for sector_name, tv_sector, source_etfs in cn_hot:
            stocks = self._scan_sector(tv_sector, Market.CHINA, self.cn_min_cap, self.cn_min_rel_vol, self.cn_min_avg_vol)
            if stocks:
                result["sector_picks"].append({
                    "sector": sector_name,
                    "market": "cn",
                    "tv_sector": tv_sector,
                    "source_etfs": source_etfs,
                    "stocks": stocks[:self.max_per_sector],
                })

        # 3. 全市场大幅异动（美股 + A股）
        result["big_movers_up"] = self._scan_big_movers("up", Market.AMERICA, self.min_cap, self.min_avg_vol, self.big_move_threshold)
        result["big_movers_down"] = self._scan_big_movers("down", Market.AMERICA, self.min_cap, self.min_avg_vol, self.big_move_threshold)
        result["cn_big_movers_up"] = self._scan_big_movers("up", Market.CHINA, self.cn_min_cap, self.cn_min_avg_vol, self.cn_big_move_threshold)
        result["cn_big_movers_down"] = self._scan_big_movers("down", Market.CHINA, self.cn_min_cap, self.cn_min_avg_vol, self.cn_big_move_threshold)

        total = sum(len(s["stocks"]) for s in result["sector_picks"])
        us_movers = len(result["big_movers_up"]) + len(result["big_movers_down"])
        cn_movers = len(result["cn_big_movers_up"]) + len(result["cn_big_movers_down"])
        logger.info(
            f"板块扫描完成: {total} 只板块个股 + "
            f"美股异动 {us_movers} 只 + A股异动 {cn_movers} 只"
        )

        return result

    def _identify_hot_sectors(self, strength_df: pd.DataFrame, market: str, sector_map: dict) -> list:
        """从 T1/T2 ETF 识别热门 TradingView 板块"""
        hot = strength_df[
            (strength_df["market"] == market) &
            (strength_df["tier"].isin(["T1", "T2"]))
        ]

        # 去重：同一个 TV Sector 只扫一次
        seen_sectors = {}
        for _, row in hot.iterrows():
            symbol = row["symbol"]
            tv_sector = sector_map.get(symbol)
            if tv_sector and tv_sector not in seen_sectors:
                seen_sectors[tv_sector] = {
                    "name": row["name"],
                    "etfs": [symbol],
                }
            elif tv_sector and tv_sector in seen_sectors:
                seen_sectors[tv_sector]["etfs"].append(symbol)

        return [
            (info["name"], sector, info["etfs"])
            for sector, info in seen_sectors.items()
        ]

    def _scan_sector(self, tv_sector: str, tv_market=None, min_cap: float = 5e9, min_rel_vol: float = 1.3, min_avg_vol: float = 500000) -> list:
        """扫描指定板块的放量个股"""
        if tv_market is None:
            tv_market = Market.AMERICA
        try:
            ss = StockScreener()
            ss.set_markets(tv_market)
            ss.set_range(0, self.sector_scan_limit)
            ss.select(
                StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
                StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
                StockField.CHAIKIN_MONEY_FLOW_20, StockField.MACD_HIST,
                StockField.MARKET_CAPITALIZATION, StockField.INDUSTRY,
                StockField.AVERAGE_VOLUME_30_DAY,
            )
            ss.where(StockField.SECTOR == tv_sector)
            ss.where(StockField.MARKET_CAPITALIZATION > min_cap)
            ss.where(StockField.RELATIVE_VOLUME > min_rel_vol)
            ss.where(StockField.AVERAGE_VOLUME_30_DAY > min_avg_vol)
            df = ss.get()

            if df.empty:
                return []

            df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]
            df = df.sort_values("Relative Volume", ascending=False)

            is_cn = (tv_market == Market.CHINA)
            stocks = []
            for _, r in df.head(self.max_per_sector).iterrows():
                stocks.append(self._row_to_dict(r, is_cn=is_cn))
            return stocks

        except (ValueError, KeyError, ConnectionError, Exception) as e:
            # tvscreener 网络请求或数据解析都可能失败，保留 Exception 兜底
            logger.debug(f"板块扫描 {tv_sector} 失败: {e}")
            return []

    def _scan_big_movers(self, direction: str, tv_market=None, min_cap: float = 5e9, min_avg_vol: float = 500000, threshold: float = 8) -> list:
        """全市场暴涨/暴跌扫描"""
        if tv_market is None:
            tv_market = Market.AMERICA
        try:
            ss = StockScreener()
            ss.set_markets(tv_market)
            ss.set_range(0, self.big_mover_scan_limit)
            ss.select(
                StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
                StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
                StockField.CHAIKIN_MONEY_FLOW_20,
                StockField.MARKET_CAPITALIZATION, StockField.SECTOR, StockField.INDUSTRY,
                StockField.AVERAGE_VOLUME_30_DAY,
            )
            ss.where(StockField.MARKET_CAPITALIZATION > min_cap)
            ss.where(StockField.AVERAGE_VOLUME_30_DAY > min_avg_vol)

            if direction == "up":
                ss.where(StockField.CHANGE_PERCENT > threshold)
            else:
                ss.where(StockField.CHANGE_PERCENT < -threshold)

            df = ss.get()
            if df.empty:
                return []

            df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]
            asc = direction == "down"
            df = df.sort_values("Change %", ascending=asc)

            is_cn = (tv_market == Market.CHINA)
            return [self._row_to_dict(r, is_cn=is_cn) for _, r in df.head(self.max_big_movers).iterrows()]

        except (ValueError, KeyError, ConnectionError, Exception) as e:
            # tvscreener 网络请求或数据解析都可能失败，保留 Exception 兜底
            logger.debug(f"全市场异动扫描失败: {e}")
            return []

    @staticmethod
    def _row_to_dict(r, is_cn: bool = False) -> dict:
        sym = str(r.get("Symbol", "")).split(":")[-1]
        cap = float(r.get("Market Capitalization", 0))
        # A股市值单位用亿人民币，美股用 Billion USD
        cap_display = round(cap / 1e8, 1) if is_cn else round(cap / 1e9, 1)
        return {
            "symbol": sym,
            "name": r.get("Name", sym),
            "price": round(float(r.get("Price", 0)), 2),
            "change_pct": round(float(r.get("Change %", 0)), 2),
            "rel_volume": round(float(r.get("Relative Volume", 0)), 2),
            "rsi": round(float(r.get("Relative Strength Index (14)", 0)), 1),
            "cmf": round(float(r.get("Chaikin Money Flow (20)", 0)), 3),
            "macd_hist": round(float(r.get("MACD Hist", 0)), 3),
            "market_cap_b": cap_display,
            "market_cap_unit": "亿" if is_cn else "B",
            "sector": str(r.get("Sector", "")),
            "industry": str(r.get("Industry", "")),
        }
