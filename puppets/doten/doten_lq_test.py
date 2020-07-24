# -*- coding: utf-8 -*-
# ==========================================
# ドテン君　サンプル
# ==========================================
import time
from datetime import datetime as dt, timezone as tz, timedelta as delta

import pandas as pd

from puppeteer import Puppeteer


# ==========================================
# Puppet(傀儡) クラス
# ==========================================
class Puppet:

    # ==========================================================
    # 初期化
    #   param:
    #       puppeteer: Puppeteerオブジェクト
    # ==========================================================
    def __init__(self, Puppeteer):
        self._exchange = Puppeteer._exchange  # 取引所オブジェクト(ccxt.liquid)
        self._logger = Puppeteer._logger  # logger
        self._config = Puppeteer._config  # 定義ファイル

    # ==========================================================
    # 売買実行
    #   param:
    #       ticker: Tick情報
    #       orderbook: 板情報
    #       position: ポジション情報
    #       balance: 資産情報
    #       candle: ローソク足
    # ==========================================================
    def run(self, ticker, orderbook, position, balance, candle):
        df = self.__get_candleDF(candle)
        self._logger.info('df: {}'.format(df))

    def __get_candleDF(self, candle):
        df = pd.DataFrame(candle,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True, infer_datetime_format=True) 
        # UNIX時間(ミリ秒)を変換, UTC=TrueでタイムゾーンがUTCに設定される
        # infer_datetime_format=Trueは高速化に寄与するとのこと。
        df = df.set_index('timestamp')

        return df
