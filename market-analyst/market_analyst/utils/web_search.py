"""Web search verification for anomalies."""

import os
from loguru import logger


class WebSearcher:
    """Use Tavily (preferred) or DuckDuckGo to verify anomalies."""

    def __init__(self, config: dict):
        ws_config = config.get("web_search", {})
        self.enabled = ws_config.get("enabled", True)
        self.max_verify = ws_config.get("max_anomalies_to_verify", 5)
        self.provider = ws_config.get("provider", "tavily")  # tavily / duckduckgo

    def verify_anomalies(self, anomalies: list) -> list:
        if not self.enabled:
            return []

        high_anomalies = [a for a in anomalies if a.get("severity") == "high"][: self.max_verify]
        if not high_anomalies:
            return []

        results = []
        for anomaly in high_anomalies:
            query = self._build_query(anomaly)
            anomaly_key = f"{anomaly['type']}:{','.join(anomaly.get('symbols', []))}"
            try:
                if self.provider == "tavily":
                    search_results = self._search_tavily(query)
                else:
                    search_results = self._search_ddg(query)

                results.append(
                    {
                        "query": query,
                        "anomaly_key": anomaly_key,
                        "results": search_results,
                    }
                )
                logger.debug(f"Web search verified: {query} -> {len(search_results)} results")

            except Exception as e:
                logger.warning(f"Search failed '{query}': {e}")
                results.append(
                    {
                        "query": query,
                        "anomaly_key": anomaly_key,
                        "anomaly_type": anomaly.get("type", "unknown"),
                        "results": [],
                        "error": str(e),
                    }
                )

        return results

    def _search_tavily(self, query: str) -> list:
        from tavily import TavilyClient

        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            logger.warning("TAVILY_API_KEY not set, fallback to DuckDuckGo")
            return self._search_ddg(query)

        client = TavilyClient(api_key=api_key)
        resp = client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
        )

        results = []
        if resp.get("answer"):
            results.append(
                {
                    "title": "AI summary",
                    "url": "",
                    "snippet": resp["answer"],
                }
            )

        for r in resp.get("results", [])[:3]:
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],
                }
            )

        return results

    def _search_ddg(self, query: str) -> list:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            try:
                from ddgs import DDGS
            except ImportError:
                logger.warning("duckduckgo-search/ddgs is not installed")
                return []

        ddgs = DDGS()
        raw = list(ddgs.text(query, max_results=3))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]

    def _build_query(self, anomaly: dict) -> str:
        symbols = anomaly.get("symbols", [])
        atype = anomaly.get("type", "")

        if atype == "zscore":
            sym = symbols[0] if symbols else ""
            return f"{sym} ETF price movement today"
        if atype == "divergence":
            return "VIX QQQ divergence market analysis"
        if atype == "cross_market":
            return "US dollar gold correlation breakdown"
        if atype == "tier_jump":
            sym = symbols[0] if symbols else ""
            return f"{sym} ETF sudden move reason"
        if atype == "clustering":
            market = anomaly.get("data", {}).get("market", "")
            return f"{'US' if market == 'us' else 'China A-share'} market breadth extreme"

        return f"market anomaly {' '.join(symbols[:2])}"
