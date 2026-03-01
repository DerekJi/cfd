"""
Oanda REST v20 K线数据获取

两个 Profile (oanda_demo / blue_guardian) 共用同一个数据源。
TradeLocker 不用于获取行情数据（限流风险）。

API 文档: https://developer.oanda.com/rest-live-v20/instrument-ep/
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

# Oanda 环境 URL 映射
OANDA_URLS = {
    'practice': 'https://api-fxpractice.oanda.com',
    'live': 'https://api-fxtrade.oanda.com',
}


class OandaDataProvider:
    """
    Oanda K线数据提供器

    用法:
        provider = OandaDataProvider(api_key="xxx", environment="practice")
        df = provider.get_candles("GBP_USD", count=1000)
    """

    def __init__(self, api_key: str, environment: str = 'practice'):
        """
        Args:
            api_key: Oanda API Key
            environment: 'practice' 或 'live'
        """
        base_url = OANDA_URLS.get(environment)
        if not base_url:
            raise ValueError(f"Unknown environment: {environment}")

        self._base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def get_candles(
        self,
        instrument: str,
        granularity: str = 'M5',
        count: int = 1000,
        price: str = 'M',
    ) -> pd.DataFrame:
        """
        获取K线数据

        Args:
            instrument: 品种名 (Oanda 格式, 如 'GBP_USD')
            granularity: 时间粒度 ('M5', 'H1' 等)
            count: K线数量 (最大 5000)
            price: 价格类型 ('M'=mid, 'B'=bid, 'A'=ask, 'BA'=bid+ask)

        Returns:
            DataFrame: columns = [datetime, open, high, low, close, volume]
        """
        # 自动重试 (处理 Oanda 偶发 502/503)
        last_error = None
        for attempt in range(3):
            try:
                resp = self._client.get(
                    f'/v3/instruments/{instrument}/candles',
                    params={
                        'granularity': granularity,
                        'count': count,
                        'price': price,
                    },
                )
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (502, 503, 504) and attempt < 2:
                    logger.warning(f"Oanda {e.response.status_code}, retry {attempt+1}/2...")
                    time.sleep(2)
                    continue
                raise
        else:
            raise last_error

        data = resp.json()

        candles = data.get('candles', [])
        if not candles:
            logger.warning(f"No candles returned for {instrument}")
            return pd.DataFrame(columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])

        # 只取已完成的K线
        rows = []
        for c in candles:
            if not c.get('complete', False):
                continue
            mid = c.get('mid', {})
            rows.append({
                'datetime': c['time'],
                'open': float(mid.get('o', 0)),
                'high': float(mid.get('h', 0)),
                'low': float(mid.get('l', 0)),
                'close': float(mid.get('c', 0)),
                'volume': int(c.get('volume', 0)),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['datetime'])
        return df

    def get_multi_timeframe(
        self,
        instrument: str,
        granularities: List[str],
        count: int = 200,
        price: str = 'M',
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多个周期的K线数据

        用于半自动策略同时拉取 H1 和 5M 数据。

        Args:
            instrument:    品种名 (Oanda 格式, 如 'EUR_USD')
            granularities: 时间粒度列表, 如 ['H1', 'M5']
            count:         每个周期抓取的K线数量 (默认 200)
            price:         价格类型 ('M'=mid, 'B'=bid, 'A'=ask)

        Returns:
            Dict[granularity, DataFrame]: 每个周期对应的 K 线 DataFrame
            例如: {'H1': df_h1, 'M5': df_m5}
        """
        result: Dict[str, pd.DataFrame] = {}
        for granularity in granularities:
            result[granularity] = self.get_candles(instrument, granularity, count, price)
        return result

    def get_last_completed_candle_time(
        self, instrument: str, granularity: str = 'M5'
    ) -> Optional[datetime]:
        """
        获取最后一根已完成K线的时间

        用于校验K线是否已 finalize。

        Returns:
            datetime (UTC) 或 None
        """
        df = self.get_candles(instrument, granularity, count=2)
        if df.empty:
            return None
        return df.iloc[-1]['datetime'].to_pydatetime()

    def close(self):
        """关闭 HTTP 客户端"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
