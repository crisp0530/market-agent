import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def sample_raw_df():
    """Generate realistic market data for testing."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='B')
    symbols = ['SPY', 'QQQ', 'GLD', 'TLT', '^VIX']
    rows = []
    for symbol in symbols:
        base_price = {'SPY': 500, 'QQQ': 450, 'GLD': 200, 'TLT': 90, '^VIX': 18}[symbol]
        np.random.seed(hash(symbol) % 2**31)
        prices = base_price * (1 + np.random.randn(len(dates)).cumsum() * 0.01)
        for i, date in enumerate(dates):
            p = prices[i]
            rows.append({
                'symbol': symbol,
                'name': symbol,
                'date': date.strftime('%Y-%m-%d'),
                'open': round(p * 0.999, 2),
                'high': round(p * 1.005, 2),
                'low': round(p * 0.995, 2),
                'close': round(p, 2),
                'volume': int(np.random.uniform(1e6, 1e8)),
                'market': 'us' if symbol != '^VIX' else 'global',
                'sector': 'equity' if symbol in ('SPY', 'QQQ') else (
                    'commodity' if symbol == 'GLD' else (
                        'bond' if symbol == 'TLT' else 'volatility'
                    )
                ),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_stock_df_hot_money():
    """Simulated hot-money stock: high turnover, high volatility, limit-ups."""
    np.random.seed(100)
    dates = pd.bdate_range(end="2026-03-27", periods=60)
    base = 20.0
    daily_returns = np.random.randn(60) * 0.04
    daily_returns[10] = 0.10
    daily_returns[25] = 0.098
    closes = base * np.cumprod(1 + daily_returns)

    return pd.DataFrame({
        "symbol": "301234",
        "name": "游资概念股",
        "market": "cn",
        "sector": "Technology",
        "date": dates.strftime("%Y-%m-%d").tolist(),
        "open": closes * (1 - np.abs(np.random.randn(60)) * 0.01),
        "high": closes * (1 + np.abs(np.random.randn(60)) * 0.03),
        "low": closes * (1 - np.abs(np.random.randn(60)) * 0.03),
        "close": closes,
        "volume": np.random.randint(5_000_000, 50_000_000, 60).astype(float),
    })


@pytest.fixture
def sample_stock_df_institutional():
    """Simulated institutional stock: low turnover, stable, large cap."""
    np.random.seed(200)
    dates = pd.bdate_range(end="2026-03-27", periods=60)
    base = 1800.0
    closes = base + np.cumsum(np.random.randn(60) * 5)

    return pd.DataFrame({
        "symbol": "600519",
        "name": "贵州茅台",
        "market": "cn",
        "sector": "Consumer Staples",
        "date": dates.strftime("%Y-%m-%d").tolist(),
        "open": closes - np.random.rand(60) * 2,
        "high": closes + np.random.rand(60) * 8,
        "low": closes - np.random.rand(60) * 8,
        "close": closes,
        "volume": np.random.randint(50_000, 200_000, 60).astype(float),
    })


@pytest.fixture
def sample_characterization_config():
    return {
        "characterization": {
            "turnover_high_threshold": 8.0,
            "turnover_low_threshold": 3.0,
            "market_cap_small": 200,
            "market_cap_large": 500,
            "hot_money_threshold": 65,
            "institutional_threshold": 65,
            "weights": {
                "turnover": 0.25,
                "volatility": 0.20,
                "volume_pattern": 0.20,
                "limit_up_freq": 0.15,
                "institutional_holding": 0.10,
                "market_cap": 0.10,
            },
        }
    }


@pytest.fixture
def sample_config():
    return {
        'strength': {
            'roc_period': 20,
            'lookback_days': 60,
            'tiers': {'T1': 80, 'T2': 60, 'T3': 40},
            'weights': {'roc_5d': 0.5, 'roc_20d': 0.3, 'roc_60d': 0.2},
        },
        'anomaly': {
            'zscore_threshold': 2.0,
            'tier_jump_days': 20,
            'cluster_threshold': 0.4,
            'momentum_reversal_threshold': 3.0,
        }
    }
