"""热门板块个股扫描 — 基于 market-analyst 的板块信号，向下钻取到个股"""
from tvscreener import Market, StockField, StockScreener


def scan_sector(label, sector, min_cap=10e9, min_rel_vol=1.3):
    """扫描指定板块的放量个股"""
    ss = StockScreener()
    ss.set_markets(Market.AMERICA)
    ss.set_range(0, 100)
    ss.select(
        StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
        StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
        StockField.CHAIKIN_MONEY_FLOW_20, StockField.MACD_HIST,
        StockField.MARKET_CAPITALIZATION, StockField.INDUSTRY,
        StockField.AVERAGE_VOLUME_30_DAY,
    )
    if sector:
        ss.where(StockField.SECTOR == sector)
    ss.where(StockField.MARKET_CAPITALIZATION > min_cap)
    ss.where(StockField.RELATIVE_VOLUME > min_rel_vol)
    ss.where(StockField.AVERAGE_VOLUME_30_DAY > 500000)
    df = ss.get()

    if df.empty:
        print(f"\n=== {label} === 无结果")
        return

    # 过滤 OTC
    df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]
    df = df.sort_values("Relative Volume", ascending=False)

    print(f"\n=== {label} === {len(df)} 只")
    print(f"  {'代码':10s} {'价格':>8s} {'涨跌%':>7s} {'相对量':>5s} {'RSI':>5s} {'CMF':>7s}  {'MACD柱':>7s}  {'市值B':>5s}  行业")
    print("  " + "-" * 90)
    for _, r in df.head(10).iterrows():
        sym = str(r.get("Symbol", "")).split(":")[-1]
        cap_b = r.get("Market Capitalization", 0) / 1e9
        print(
            f"  {sym:10s} ${r.get('Price', 0):7.2f} {r.get('Change %', 0):+6.2f}% "
            f"{r.get('Relative Volume', 0):5.2f} {r.get('Relative Strength Index (14)', 0):5.1f} "
            f"{r.get('Chaikin Money Flow (20)', 0):+6.3f}  {r.get('MACD Hist', 0):+6.3f}  "
            f"{cap_b:5.1f}B  {str(r.get('Industry', '?'))[:20]}"
        )


def scan_big_movers():
    """全市场暴涨暴跌扫描"""
    for direction, label, op in [("up", "暴涨(>8%)", 8), ("down", "暴跌(<-8%)", -8)]:
        ss = StockScreener()
        ss.set_markets(Market.AMERICA)
        ss.set_range(0, 50)
        ss.select(
            StockField.NAME, StockField.PRICE, StockField.CHANGE_PERCENT,
            StockField.RELATIVE_VOLUME, StockField.RELATIVE_STRENGTH_INDEX_14,
            StockField.CHAIKIN_MONEY_FLOW_20,
            StockField.MARKET_CAPITALIZATION, StockField.SECTOR, StockField.INDUSTRY,
            StockField.AVERAGE_VOLUME_30_DAY,
        )
        ss.where(StockField.MARKET_CAPITALIZATION > 5_000_000_000)
        ss.where(StockField.AVERAGE_VOLUME_30_DAY > 500000)
        if direction == "up":
            ss.where(StockField.CHANGE_PERCENT > op)
        else:
            ss.where(StockField.CHANGE_PERCENT < op)
        df = ss.get()

        if df.empty:
            print(f"\n=== 全市场{label} === 无结果")
            continue

        df = df[~df["Symbol"].str.contains("OTC|GREY", na=False)]
        asc = direction == "down"
        df = df.sort_values("Change %", ascending=asc)

        print(f"\n=== 全市场{label} (市值>5B) === {len(df)} 只")
        print(f"  {'代码':10s} {'价格':>8s} {'涨跌%':>7s} {'相对量':>5s} {'RSI':>5s} {'CMF':>7s}  {'市值B':>5s}  板块/行业")
        print("  " + "-" * 85)
        for _, r in df.head(15).iterrows():
            sym = str(r.get("Symbol", "")).split(":")[-1]
            cap_b = r.get("Market Capitalization", 0) / 1e9
            sect = str(r.get("Sector", "?"))[:12]
            ind = str(r.get("Industry", "?"))[:15]
            print(
                f"  {sym:10s} ${r.get('Price', 0):7.2f} {r.get('Change %', 0):+6.2f}% "
                f"{r.get('Relative Volume', 0):5.2f} {r.get('Relative Strength Index (14)', 0):5.1f} "
                f"{r.get('Chaikin Money Flow (20)', 0):+6.3f}  {cap_b:5.1f}B  {sect}/{ind}"
            )


if __name__ == "__main__":
    # 基于今日 market-analyst T1/T2 板块向下钻取
    scan_sector("能源板块 — 放量异动", "Energy Minerals", min_cap=10e9, min_rel_vol=1.3)
    scan_sector("软件/云 — 逆势放量", "Technology Services", min_cap=10e9, min_rel_vol=1.3)
    scan_sector("半导体 — 放量反弹", "Electronic Technology", min_cap=10e9, min_rel_vol=1.3)

    # 全市场大幅异动
    scan_big_movers()
