"""Parquet 本地缓存管理"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import time
import pandas as pd
from loguru import logger


class DataCache:
    """基于 Parquet 的本地数据缓存"""

    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        """生成缓存文件路径，用 MD5 哈希避免 key 冲突"""
        md5 = hashlib.md5(key.encode()).hexdigest()
        # 取 key 中最后一段可读部分作为前缀（去除特殊字符）
        prefix = key.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].replace(":", "_")[:30]
        return self.cache_dir / f"{prefix}_{md5}.parquet"

    def get(self, key: str, max_age_hours: int = 12) -> Optional[pd.DataFrame]:
        """读取缓存，如果过期则返回 None"""
        path = self._cache_path(key)
        if not path.exists():
            return None

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(hours=max_age_hours):
            logger.debug(f"缓存过期: {key}")
            return None

        try:
            df = pd.read_parquet(path)
            logger.debug(f"缓存命中: {key} ({len(df)} 行)")
            return df
        except Exception as e:
            logger.warning(f"读取缓存失败: {key}: {e}")
            return None

    def set(self, key: str, df: pd.DataFrame) -> None:
        """写入缓存"""
        if df.empty:
            return
        path = self._cache_path(key)
        try:
            df.to_parquet(path, index=False)
            logger.debug(f"缓存写入: {key} ({len(df)} 行)")
        except Exception as e:
            logger.warning(f"写入缓存失败: {key}: {e}")

    def get_or_fetch(self, key: str, fetch_func, max_age_hours: int = 12) -> pd.DataFrame:
        """先查缓存，未命中则执行 fetch_func 并缓存结果"""
        cached = self.get(key, max_age_hours)
        if cached is not None:
            return cached

        df = fetch_func()
        if df is not None and not df.empty:
            self.set(key, df)
        return df if df is not None else pd.DataFrame()

    def get_or_fetch_json(self, key: str, fetch_func, max_age_hours: int = 24) -> dict:
        """JSON cache for non-DataFrame data (e.g., earnings).
        Reuses _cache_path() for consistent key hashing, but with .json suffix."""
        parquet_path = self._cache_path(key)
        cache_path = parquet_path.with_suffix(".json")
        if cache_path.exists():
            age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_hours < max_age_hours:
                try:
                    with open(cache_path, encoding="utf-8") as f:
                        data = json.load(f)
                    logger.debug(f"JSON缓存命中: {key}")
                    return data
                except Exception as e:
                    logger.warning(f"读取JSON缓存失败: {key}: {e}")
        data = fetch_func()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
            logger.debug(f"JSON缓存写入: {key}")
        except Exception as e:
            logger.warning(f"写入JSON缓存失败: {key}: {e}")
        return data

    def clear(self, older_than_days: int = 7) -> int:
        """清理过期缓存文件"""
        cleared = 0
        cutoff = datetime.now() - timedelta(days=older_than_days)
        for f in self.cache_dir.glob("*.parquet"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                cleared += 1
        if cleared:
            logger.info(f"清理 {cleared} 个过期缓存文件")
        return cleared
