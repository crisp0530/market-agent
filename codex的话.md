只剩一个明确的落点问题了，设计文档本身基本过关，卡在实现计划代码片段。

实现计划里的 mcp_server.py 示例直接调用了 StockDiagnostor()，但没有导入。
2026-03-30-retail-investor-features-completion.md (line 2188) 到 2026-03-30-retail-investor-features-completion.md (line 2188) 的 get_trade_signal 代码块里，diag = StockDiagnostor().diagnose(stock_df) 前没有 from market_analyst.processors.stock_diagnostor import StockDiagnostor。
2026-03-30-retail-investor-features-completion.md (line 2290) 到 2026-03-30-retail-investor-features-completion.md (line 2290) 的 get_trading_strategies 代码块同样缺这个 import。
修改建议：在两个代码片段里都显式补上该 import。
这轮里，上次指出的 API 名、fallback、sector_correlation、_get_market_overview_impl 调用方式和 get_or_fetch_json 示例问题都已经修掉了。

补完这一个点后，我这边就会给 APPROVED。