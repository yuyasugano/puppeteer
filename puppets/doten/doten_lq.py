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

        # ------------------------------------------------------
        # candle in DataFrame object
        # ------------------------------------------------------
        df = self.__get_candleDF(candle)

        range_mean = self.__calc_range_mean(
            df[:-1], self._config["RANGE_MEAN_NUM"]
        )  # 直近の足は未確定足だから計算に渡さない

        doten = self.__calc_doten(
            df.iloc[-1], range_mean, self._config["DOTEN_K"]
        )
        self._logger.info('doten: {}'.format(doten))

        if doten == "buy":
            # self.__market_order("buy", self.__config["LOT"])
            print("Doten signaled for bid: {}".format(self._config["LOT"]))
        elif doten == "sell":
            # self.__market_order("sell", self.__config["LOT"])
            print("Doten signeled for ask: {}".format(self._config["LOT"]))

    # ==========================================================
    # ローソク足 DataFrame 取得
    # ==========================================================
    def __get_candleDF(self, candle):
        # -----------------------------------------------
        # Pandasのデータフレームに
        # -----------------------------------------------
        df = pd.DataFrame(
            candle, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        # -----------------------------------------------
        # 日時データをDataFrameのインデックスにする
        # -----------------------------------------------
        df["timestamp"] = pd.to_datetime(
            df["timestamp"], unit="ms", utc=True, infer_datetime_format=True
        )
        # UNIX時間(ミリ秒)を変換, UTC=TrueでタイムゾーンがUTCに設定される
        # infer_datetime_format=Trueは高速化に寄与するとのこと。
        df = df.set_index("timestamp")

        return df

    # ==========================================================
    # RANGE計算
    # ==========================================================
    def __calc_range_mean(self, df, range_mean_num):
        diff = 0
        for index, row in df[-range_mean_num:].iterrows():
            diff += row["high"] - row["low"]
        return diff/range_mean_num

    # ==========================================================
    # ドテン計算
    # ==========================================================
    def __calc_doten(self, last, range_mean, k):
        ret = "none"
        if last["high"] > (last["open"] + range_mean * k):
            ret = "buy"
        elif last["low"] < (last["open"] - range_mean * k):
            ret = "sell"
        return ret

    # ==========================================================
    # 成行注文
    #   param:
    #       side: buy or sell
    #       size: orderロット数
    #   return:
    #       order
    # ==========================================================
    def __market_order(self, side, size):

        order = None

        try:
            order = self._exchange.create_order(
                self._config["SYMBOL"], type="market", side=side, amount=size
            )
            self._logger.debug("- market order={}".format(order))
        except Exception as e:
            self._logger.error("- market order: exception={}".format(e))
            order = None

        return order
