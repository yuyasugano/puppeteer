# -*- coding: utf-8 -*-

import ccxt
import time
import math
import json

from datetime import datetime
import calendar
import logging

import pandas as pd

# ###############################################################
# liquid class
# ###############################################################
class Liquid:

    SYMBOL = "BTC/USD"
    INFO_SYMBOL = "BTC/USD"
    __NAME = "liquid"  # 取引所名

    # ==================================
    # Initialization
    # ==================================
    def __init__(
        self, symbol=SYMBOL, apiKey=None, secret=None, logger=None):
        # 取引所オブジェクト(ccxt.liquid)
        self._exchange = ccxt.liquid({"apiKey": apiKey, "secret": secret})
        self._symbol = symbol
        self._logger = logger if logger is not None else logging.getLogger(__name__)

        self._logger.info("class Liquid initialized")

    # ===========================================================
    # Destructor
    # ===========================================================
    def __del__(self):
        self._logger.info("class Liquid deleted")

    def __get_error(self, e):
        ret = {"error": {"message": "{}".format(e), "name": "Liquid.__get_error"}}
        return ret

    # ##########################################################
    # ヘルパー関数
    # ##########################################################
    # ==========================================================
    # 0.5刻みで切り上げ
    #   param:
    #       price: avgEntryPrice
    # ==========================================================
    def ceil(self, price):
        return math.ceil(price * 2) / 2

    # ==========================================================
    # 0.5刻みで切り下げ
    #   param:
    #       price: avgEntryPrice
    # ==========================================================
    def floor(self, price):
        return math.floor(price * 2) / 2

    # ##########################################################
    # ccxt関数ラッパー
    # ##########################################################
    # ==========================================================
    # オープンオーダ検索
    #   param:
    #       symbol: シンボル
    #   return:
    #       order
    # ==========================================================
    def open_orders(self, symbol=SYMBOL):

        orders = None

        try:
            orders = self._exchange.fetch_open_orders(symbol)
            self._logger.debug("- open orders={}".format(orders))
        except Exception as e:
            self._logger.error("- open orders: exception={}".format(e))
            orders = None

        return orders

    # ==========================================================
    # 指値注文
    #   param:
    #       side: buy or sell
    #       price: 価格
    #       size: orderロット数
    #   return:
    #       order
    # ==========================================================
    def limit_order(self, side, price, size):

        order = None

        # 注文に設定する「clOrdID」のID情報を作成・取得
        order_id = str(time.time() * 1000)

        try:
            order = self._exchange.create_order(
                symbol=self._symbol,
                type="limit",
                side=side,
                amount=size,
                price=price,
                params={
                    "client_order_id": "{}_limit_{}".format(order_id, side),
                },
            )
            self._logger.debug("- limit order={}".format(order))
        except Exception as e:
            self._logger.error("- limit order: exception={}".format(e))
            order = None

        return order

    # ==========================================================
    # 成行注文
    #   param:
    #       side: buy or sell
    #       size: orderロット数
    #   return:
    #       order
    # ==========================================================
    def market_order(self, side, size):

        order = None

        # 注文に設定する「clOrdID」のID情報を作成・取得
        order_id = str(time.time() * 1000)

        try:
            order = self._exchange.create_order(
                symbol=self._symbol,
                type="market",
                side=side,
                amount=size,
                params={"client_order_id": "{}_market_{}".format(order_id, side)},
            )
            self._logger.debug("- market order={}".format(order))
        except Exception as e:
            self._logger.error("- market order: exception={}".format(e))
            order = None

        return order

    # ==========================================================
    # 注文キャンセル
    #   param:
    #       options: order情報 (orderID or client_order_id)
    #   return:
    #       order
    # ==========================================================
    def cancel_order(self, orderId):

        order = None

        try:
            order = self._exchange.calcel_order(symbol=self._symbol, id=orderId)
            self._logger.debug("- cancel order={}".format(order))
        except Exception as e:
            self._logger.error("- cancel order: exception={}".format(e))
            order = None

        return order

    # ==========================================================
    # 複数注文キャンセル
    #   param:
    #       options: order情報
    #   return:
    #       order
    # ==========================================================
    def cancel_orders(self, **options):

        orders = None

        try:
            orders = self._exchange.fetch_open_orders()
            for i,o in enumerate(orders):
                if orders[i].get('status') == 'live':
                    orderId = orders[i].get('id')
                    self.cancel_order(orderId)
            self._logger.debug("- cancel orders={}".format(orders))
        except Exception as e:
            self._logger.error("- cancel orders: exception={}".format(e))
            orders = None

        return orders

    # ==========================================================
    # ストップ注文
    #   param:
    #       side: buy or sell
    #       size:           サイズ （＋：買い、－：売り）
    #       trigger_price:  トリガー価格
    #   return:
    #       order (注文結果、失敗の場合はNoneが戻される)
    # ==========================================================
    def stop_order(self, side, price, size):

        # 注文に設定する「clOrdID」のID情報を作成・取得
        order_id = str(time.time() * 1000)

        try:
            order = self._exchange.create_order(
                symbol=self._symbol,
                type="stop",
                side=side,
                amount=size,
                price=price,
                params={"client_order_id": "{}_market_{}".format(order_id, side)},
            )
            self._logger.debug("- stop order={}".format(order))
        except Exception as e:
            self._logger.error("- stop order: exception={}".format(e))
            order = None

    # ======================================
    # balance
    # ======================================
    def balance(self):

        _balance = None
        try:
            _balance = self._exchange.fetch_balance()
            self._logger.debug("- balance={}".format(_balance))
        except Exception as e:
            self._logger.error("- balance: exception={}".format(e))
            _balance = None # Noneを戻す

        return _balance

    # ======================================
    # position
    # ======================================
    def position(self):

        _position = None
        try:
            _position = self._exchange.privateGetOrders()
            _position = _position['models']
            self._logger.debug("- position={}".format(_position))
        except Exception as e:
            self._logger.error("- position: exception={}".format(e))
            _position = None # Noneを戻す

        return _position

    # ======================================
    # ticker
    # ======================================
    def ticker(self, symbol=SYMBOL):

        _ticker = None
        try:
            _ticker = self._exchange.fetch_ticker(symbol=symbol)  # シンボル
            self._logger.debug("- ticker={}".format(_ticker))
        except Exception as e:
            self._logger.error("- ticker: exception={}".format(e))
            _ticker = None # Noneを戻す

        return _ticker

    # ======================================
    # 板情報取得
    # ======================================
    def orderbook(self, symbol=SYMBOL, limit=100):

        _orderbook = None
        try:
            _orderbook = self._exchange.fetch_order_book(
                symbol=symbol, limit=limit  # シンボル  # 取得件数(未指定:100、MAX:500)
            )
            self._logger.debug("- orderbook={}".format(_orderbook))
        except Exception as e:
            self._logger.error("- orderbook: exception={}".format(e))
            _orderbook = None # Noneを戻す

        return _orderbook

    # ======================================
    # ccxtのfetch_ohlcv問題に対応するローカル関数
    #  partial問題については、
    #   https://note.mu/nagi7692/n/n5a52e0fa8c28
    #  の記事を参考にした
    #  また、結構な確率でOHLCデータがNoneになってくることがある。
    #
    #  params:
    #       reverse: True(New->Old)、False(Old->New)　未指定時はFlase (注意：sineceを指定せずに、このフラグをTrueにすると最古のデータは2016年頃のデータが取れる)
    #       partial: True(最新の未確定足を含む)、False(含まない)　未指定はTrue　（注意：まだバグっているのか、Falseでも最新足が含まれる）
    # ======================================
    def ohlcv(self, symbol=SYMBOL, timeframe="1m", since=None, limit=None, params={}):
        # timeframe1期間あたりの秒数
        period = {"1m": 1 * 60, "5m": 5 * 60, "1h": 60 * 60, "1d": 24 * 60 * 60}

        if timeframe not in period.keys():
            return None

        # 未確定の最新時間足のtimestampを取得(ミリ秒)
        now = datetime.utcnow()
        unixtime = calendar.timegm(now.utctimetuple())
        current_timestamp = (
            unixtime - (unixtime % period[timeframe])
        ) * 1000  # この値が一つ先の足のデータになっていたので、直近の一番新しい過去の足の時間に調整

        # for DEBUG
        # print('current_timestamp={} : {}'.format(current_timestamp, datetime.fromtimestamp(current_timestamp / 1000)))

        # partialフラグ
        is_partial = True
        if "partial" in params.keys():
            is_partial = params["partial"]

        # reverseフラグ
        is_reverse = False
        if "reverse" in params.keys():
            is_reverse = params["reverse"]

        # 取得件数(未指定は100件)
        fetch_count = 100 if limit is None else limit
        count = fetch_count

        # 取得後に最新足を除外するため、1件多く取得
        if is_partial == False:
            count += 1
        # 取得件数が足りないため、1件多く取得
        if is_reverse == False:
            count += 1
        # 1page最大500件のため、オーバーしている場合、500件に調整
        if count > 500:
            count = 500

        # OHLCVデータ取得
        # 引数：symbol, timeframe='1m', since=None, limit=None, params={}
        ohlcvs = self._exchange.fetch_ohlcv(
            symbol=symbol, timeframe=timeframe, since=since, limit=count, params=params
        )

        # for DEBUG
        # print('ohlcvs_timestamp ={} : {}'.format(ohlcvs[-1][0], datetime.fromtimestamp(ohlcvs[-1][0] / 1000)))

        # partial=Falseの場合、未確定の最新足を除去する
        if is_partial == False:
            if is_reverse == True:
                # 先頭行のtimestampが最新足と一致したら除去
                if ohlcvs[0][0] == current_timestamp:
                    # True(New->Old)なので、最初データを削除する
                    ohlcvs = ohlcvs[1:]
            else:
                # 最終行のtimestampが最新足と一致したら除去
                if ohlcvs[-1][0] == current_timestamp:
                    # False(Old->New)なので、最後データを削除する
                    ohlcvs = ohlcvs[:-1]

        # 取得件数をlimit以下になるように調整
        while len(ohlcvs) > fetch_count:
            if is_reverse == True:
                # True(New->Old)なので、最後データから削除する, sinceが設定されているときは逆
                ohlcvs = ohlcvs[:-1] if since is None else ohlcvs[1:]
            else:
                # False(Old->New)なので、最初データから削除する, sinceが設定されているときは逆
                ohlcvs = ohlcvs[1:] if since is None else ohlcvs[:-1]

        return ohlcvs

    # ==========================================================
    # ローソク足取得(ccxt)
    # ==========================================================
    def to_candleDF(self, candle):
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
        )  # UNIX時間(ミリ秒)を変換, UTC=TrueでタイムゾーンがUTCに設定される, infer_datetime_format=Trueは高速化に寄与するとのこと。
        df = df.set_index("timestamp")

        return df

    # ==========================================================
    # ローソク足の足幅変換
    #   params:
    #       ohlcv: DataFrame (pandas)
    #       resolution: 刻み幅(1m, 3m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 12h, 1d, 3d, 1w, 2w, 1M)
    # ==========================================================
    def change_candleDF(self, ohlcv, resolution="1m"):
        # 参考にしたサイト https://docs.pyq.jp/python/pydata/pandas/resample.html
        """
        -------+------+------
        引数    単位    区切り
        -------+------+------
        AS	    年      年初
        A	    年	    年末
        MS	    月	    月初
        M	    月	    月末
        W	    週	    日曜
        D	    日	    0時
        H	    時	    0分
        T,min	分	    0秒
        S	    秒
        L,ms    ミリ秒
        U,us    マイクロ秒
        N,ns    ナノ秒
        """

        """
        -------+------+------
        関数    説明
        -------+------+------
        min	    最小
        max	    最大
        sum	    合計
        mean	平均
        first	最初の値
        last    最後の値
        interpolate	補間        
        """

        period = {
            "1m": "1T",
            "3m": "3T",
            "5m": "5T",
            "15m": "15T",
            "30m": "30T",
            "1h": "1H",
            "2h": "2H",
            "3h": "3H",
            "4h": "4H",
            "6h": "6H",
            "12h": "12H",
            "1d": "1D",
            "3d": "3D",
            "1w": "1W",
            "2w": "2W",
            "1M": "1M",
        }

        if resolution not in period.keys():
            return None

        # 他の分刻みに直す
        df = (
            ohlcv[["open", "high", "low", "close", "volume"]]
            .resample(period[resolution], label="left", closed="left")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
        )
        # ohlcを再度ohlcに集計するにはaggメソッド

        return df
