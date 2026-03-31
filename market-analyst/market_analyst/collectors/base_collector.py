"""数据收集器基类"""
import time
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np
import pandas as pd
from loguru import logger


class BaseCollector(ABC):
    """数据收集器基类，提供统一接口和重试逻辑"""

    def __init__(self, name: str, max_retries: int = 3, retry_delay: float = 2.0):
        self.name = name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logger.bind(collector=name)

    @abstractmethod
    def _fetch_data(self, symbols: list, lookback_days: int) -> pd.DataFrame:
        """子类实现具体的数据获取逻辑

        返回 DataFrame 列：symbol, name, sector, market, date, open, high, low, close, volume
        """
        pass

    def collect(self, symbols: list, lookback_days: int = 60) -> pd.DataFrame:
        """带重试的数据收集"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"第 {attempt}/{self.max_retries} 次尝试收集数据...")
                df = self._fetch_data(symbols, lookback_days)
                if df is not None and not df.empty:
                    self.logger.info(f"成功收集 {len(df)} 条数据，覆盖 {df['symbol'].nunique()} 个标的")
                    return df
                else:
                    self.logger.warning("返回空数据")
                    last_error = ValueError("Empty data returned")
            except Exception as e:
                last_error = e
                self.logger.warning(f"第 {attempt} 次尝试失败: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        self.logger.error(f"所有 {self.max_retries} 次尝试均失败: {last_error}")
        return pd.DataFrame()

    @staticmethod
    def validate_dataframe(df: pd.DataFrame, drop_bad_rows: bool = True) -> bool:
        """验证 DataFrame 格式和数据质量

        Args:
            df: 待验证的 DataFrame
            drop_bad_rows: 是否就地删除不合格行（默认 True）

        Returns:
            True 如果 DataFrame 基本有效（可能已过滤掉坏行）
        """
        required_columns = ['symbol', 'name', 'sector', 'market', 'date', 'close']
        if df.empty:
            return False
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            logger.warning(f"缺少列: {missing}")
            return False

        # --- 数值列 NaN/Inf 检查 ---
        numeric_cols = [c for c in ['close', 'high', 'low', 'open', 'volume'] if c in df.columns]
        for col in numeric_cols:
            nan_count = df[col].isna().sum()
            inf_count = np.isinf(df[col]).sum() if df[col].dtype.kind == 'f' else 0
            if nan_count > 0:
                logger.warning(f"列 '{col}' 含 {nan_count} 个 NaN 值")
            if inf_count > 0:
                logger.warning(f"列 '{col}' 含 {inf_count} 个 Inf 值")

        bad_mask = pd.Series(False, index=df.index)

        # --- high >= low 检查 ---
        if 'high' in df.columns and 'low' in df.columns:
            hl_bad = df['high'] < df['low']
            hl_count = hl_bad.sum()
            if hl_count > 0:
                logger.warning(f"{hl_count} 行 high < low，数据异常")
                bad_mask |= hl_bad

        # --- close 在 [low, high] 范围内 ---
        if all(c in df.columns for c in ['close', 'low', 'high']):
            cl_bad = (df['close'] < df['low']) | (df['close'] > df['high'])
            # 只对 high >= low 的行检查（避免与上面重复）
            cl_bad = cl_bad & ~bad_mask
            cl_count = cl_bad.sum()
            if cl_count > 0:
                logger.warning(f"{cl_count} 行 close 不在 [low, high] 范围内")
                bad_mask |= cl_bad

        # --- 重复 (symbol, date) 检查 ---
        if 'symbol' in df.columns and 'date' in df.columns:
            dup_mask = df.duplicated(subset=['symbol', 'date'], keep='first')
            dup_count = dup_mask.sum()
            if dup_count > 0:
                logger.warning(f"{dup_count} 行重复 (symbol, date) 组合")
                bad_mask |= dup_mask

        # --- 按需删除坏行 ---
        if drop_bad_rows and bad_mask.any():
            total_bad = bad_mask.sum()
            logger.warning(f"过滤掉 {total_bad} 行异常数据")
            df.drop(df.index[bad_mask], inplace=True)

        return not df.empty
