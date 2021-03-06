#!/usr/bin/python3
# -*- coding: utf-8 -*-

# sudo pip install websocket-client==0.47
# version指定
import websocket

# thred操作
import threading

# for datetime,time関連
from datetime import datetime, timedelta, timezone
import dateutil.parser
import time

# json操作
import json

# for logging
import logging
import traceback

# import urllibだけだとエラーになる
import urllib.parse

# for instrument
import math

import pandas as pd

# for signature
import hmac, hashlib

# sqlite
import sqlite3

# for logging
import logging
from logging import getLogger, StreamHandler, Formatter

# listのコピー
import copy

# サポートクラス
# 板情報
from exchanges.websocket.orderbook import OrderBook

# 注文情報
from exchanges.websocket.order import Order


# ###############################################################
# Naive implementation of connecting to BitMEX websocket for streaming realtime data.
# The Marketmaker still interacts with this as if it were a REST Endpoint, but now it can get
# much more realtime data without polling the hell out of the API.
#
# The Websocket offers a bunch of data as raw properties right on the object.
# On connect, it synchronously asks for a push of all this data then returns.
# Right after, the MM can start using its data. It will be updated in realtime, so the MM can
# poll really often if it wants.
# ###############################################################
class BitMEXWebsocket:

    # Don't grow a table larger than this amount. Helps cap memory usage.
    MAX_TABLE_LEN = 1000
    # order bookの最大保持数
    MAX_ORDERBOOK_LEN = 100
    # ローソク足の刻み幅
    CANDLE_RANGE = 5
    MAX_CANDLE_LEN = int(3600 / CANDLE_RANGE)  # 1h分

    # 長期間ポジションが無いと、positionのPartialでNULLデータが取得される。
    INIT_POSITION = {
        "account": 1,
        "avgCostPrice": None,
        "avgEntryPrice": None,
        "bankruptPrice": None,
        "breakEvenPrice": None,
        "commission": 0.00075,
        "crossMargin": True,
        "currency": "XBt",
        "currentComm": 0,
        "currentCost": 0,
        "currentQty": 0,
        "currentTimestamp": "2019-01-01T00:00:00.000Z",
        "deleveragePercentile": None,
        "execBuyCost": 0,
        "execBuyQty": 0,
        "execComm": 0,
        "execCost": 0,
        "execQty": 0,
        "execSellCost": 0,
        "execSellQty": 0,
        "foreignNotional": 0,
        "grossExecCost": 0,
        "grossOpenCost": 0,
        "grossOpenPremium": 0,
        "homeNotional": 0,
        "indicativeTax": 0,
        "indicativeTaxRate": 0,
        "initMargin": 0,
        "initMarginReq": 0.01,
        "isOpen": False,
        "lastPrice": None,
        "lastValue": 0,
        "leverage": 100,
        "liquidationPrice": None,
        "longBankrupt": 0,
        "maintMargin": 0,
        "maintMarginReq": 0.005,
        "marginCallPrice": None,
        "markPrice": None,
        "markValue": 0,
        "openOrderBuyCost": 0,
        "openOrderBuyPremium": 0,
        "openOrderBuyQty": 0,
        "openOrderSellCost": 0,
        "openOrderSellPremium": 0,
        "openOrderSellQty": 0,
        "openingComm": 0,
        "openingCost": 0,
        "openingQty": 0,
        "openingTimestamp": "2019-01-01T00:00:00.000Z",
        "posAllowance": 0,
        "posComm": 0,
        "posCost": 0,
        "posCost2": 0,
        "posCross": 0,
        "posInit": 0,
        "posLoss": 0,
        "posMaint": 0,
        "posMargin": 0,
        "posState": "",
        "prevClosePrice": 0,
        "prevRealisedPnl": 0,
        "prevUnrealisedPnl": 0,
        "quoteCurrency": "USD",
        "realisedCost": 0,
        "realisedGrossPnl": 0,
        "realisedPnl": 0,
        "realisedTax": 0,
        "rebalancedPnl": 0,
        "riskLimit": 10000000000,
        "riskValue": 0,
        "sessionMargin": 0,
        "shortBankrupt": 0,
        "simpleCost": None,
        "simplePnl": None,
        "simplePnlPcnt": None,
        "simpleQty": None,
        "simpleValue": None,
        "symbol": "XBTUSD",
        "targetExcessMargin": 0,
        "taxBase": 0,
        "taxableMargin": 0,
        "timestamp": "2019-01-01T00:00:00.000Z",
        "underlying": "XBT",
        "unrealisedCost": 0,
        "unrealisedGrossPnl": 0,
        "unrealisedPnl": 0,
        "unrealisedPnlPcnt": 0,
        "unrealisedRoePcnt": 0,
        "unrealisedTax": 0,
        "varMargin": 0,
    }

    # ===========================================================
    # コンストラクタ
    # ===========================================================
    def __init__(
        self,
        endpoint,
        symbol="XBTUSD",
        api_key=None,
        api_secret=None,
        logger=None,
        use_timemark=False,
    ):
        """Connect to the websocket and initialize data stores."""
        # -------------------------------------------------------
        # logger
        # -------------------------------------------------------
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.logger.info("BitMEXWebsocket constructor")

        # -------------------------------------------------------
        # endpoint, symbol
        # -------------------------------------------------------
        self.endpoint = endpoint
        self.symbol = symbol

        # -------------------------------------------------------
        # apikey,secret
        # -------------------------------------------------------
        if api_key is not None and api_secret is None:
            raise ValueError("api_secret is required if api_key is provided")
        if api_key is None and api_secret is not None:
            raise ValueError("api_key is required if api_secret is provided")

        self.api_key = api_key
        self.api_secret = api_secret

        # -------------------------------------------------------
        # timezone, timestamp
        # -------------------------------------------------------
        self._tz = timezone.utc
        self._ts = datetime.now(self._tz).timestamp()

        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 0  # まだ何もしていない状態

        # -------------------------------------------------------
        # 時間計測するかどうか
        # -------------------------------------------------------
        self._use_timemark = use_timemark

        # -------------------------------------------------------
        # Threadのロック用オブジェクト
        # -------------------------------------------------------
        self._lock = threading.Lock()

        # -------------------------------------------------------
        # ローカル変数 設定
        # -------------------------------------------------------
        self.__initialize_params()

        # -------------------------------------------------------
        # websocket初期化、スレッド生成
        # -------------------------------------------------------
        # We can subscribe right in the connection querystring, so let's build that.
        # Subscribe to all pertinent endpoints
        wsURL = self.__get_url()
        self.logger.info("Connecting to %s" % wsURL)
        self.__connect(wsURL, symbol)
        self.logger.info("Connected to WS.")

        # -------------------------------------------------------
        # 各メッセージの「partial」が到着するまで待機
        # -------------------------------------------------------
        # apikeyが必要無いもの
        # -------------------------------------------------------
        self.__wait_for_symbol(symbol)
        # -------------------------------------------------------
        # tickerがinstrumentの情報を使用するため
        # -------------------------------------------------------
        time.sleep(0.1)
        self.instrument()
        # -------------------------------------------------------
        # apikeyを持つもの
        # -------------------------------------------------------
        if api_key:
            self.__wait_for_account()
        self.logger.info("Got all market data. Starting.")

    # ===========================================================
    # デストラクタ
    # ===========================================================
    def __del__(self):
        self.logger.info("BitMEXWebsocket destructor")
        if not self.exited:
            # クロースずる
            self.exit()

    # ###########################################################
    # public methods
    # ###########################################################
    def reconnect(self):
        self.logger.info("websocket reconnect(): start")

        # -------------------------------------------------------
        # 終了処理が未実施だったら終了処理を実行
        # -------------------------------------------------------
        if not self.exited:
            self.exit()

        # -------------------------------------------------------
        # ローカル変数 再設定開始
        # -------------------------------------------------------
        self.__initialize_params()

        # -------------------------------------------------------
        # websocket初期化、スレッド生成
        # 各メッセージの「partial」が到着するまで待機
        # -------------------------------------------------------
        try:
            # We can subscribe right in the connection querystring, so let's build that.
            # Subscribe to all pertinent endpoints
            wsURL = self.__get_url()
            self.logger.info("Connecting to %s" % wsURL)
            self.__connect(wsURL, self.symbol)
            self.logger.info("Connected to WS.")
            # ---------------------------------------------------
            # apikeyが必要無いもの
            # ---------------------------------------------------
            self.__wait_for_symbol(self.symbol)
            # ---------------------------------------------------
            # tickerがinstrumentの情報を使用するため
            # ---------------------------------------------------
            time.sleep(0.1)
            self.instrument()
            # ---------------------------------------------------
            # apikeyを持つもの
            # ---------------------------------------------------
            if self.api_key:
                self.__wait_for_account()
            self.logger.info("Got all market data. Starting.")
        except Exception as e:
            self.logger.error("websocket reconnect() : error = {}".format(e))

    # ===========================================================
    # 終了
    # ===========================================================
    def exit(self):
        """Call this to exit - will close websocket."""
        self.exited = True
        # for DEBUG
        time.sleep(1)

        # -------------------------------------------------------
        # websocketのクローズ
        # -------------------------------------------------------
        try:
            # websokectクローズ
            if self.ws:
                self.ws.keep_running = False  # 永遠に実行中をやめる
                # ソケットクローズ
                if self.ws.sock and self.ws.sock.connected:
                    self.ws.close()
                    self.logger.info("websocket exit() socket closed")
                    time.sleep(1)
        except Exception as e:
            self.logger.error("websocket exit() socket close: error = {}".format(e))
        finally:
            # self.ws = None
            pass

        # -------------------------------------------------------
        # websocket スレッドの終了
        # -------------------------------------------------------
        try:
            # スレッド終了
            self.__wst_thread_exit()
        except Exception as e:
            self.logger.error(
                "websocket exit() websocket thread exit : error = {}".format(e)
            )
        finally:
            # self.wst = None     # reconnect の再帰に備えてクリアしない
            pass

        # -------------------------------------------------------
        # check candle スレッドの終了
        # -------------------------------------------------------
        try:
            # スレッド終了
            self.__check_candle_thread_exit()
        except Exception as e:
            self.logger.error(
                "websocket exit() check candle thread exit : error = {}".format(e)
            )
        finally:
            # self._check_candle_thread = None   # reconnect の再帰に備えてクリアしない
            pass

        # -------------------------------------------------------
        # DBクローズ
        # -------------------------------------------------------
        try:
            # db close
            self._db.close()
            # db用オブジェクトの削除
            del self._orderbook
            del self._order
        except Exception as e:
            self.logger.error("websocket exit() db close : error = {}".format(e))
        finally:
            self._db = None
            self._orderbook = None
            self._order = None

    # ===========================================================
    # 強制終了の通知がONか？(__on_errorで設定される)
    # ===========================================================
    def is_force_exit(self):
        return self.__force_exit

    # ===========================================================
    # quote, trade, execution は追記型
    # ===========================================================
    # quotes
    # ===========================================================
    def quotes(self):
        """Get recent quotes."""
        self.__thread_lock()
        quote = self.data["quote"][:]
        self.__thread_unlock()
        return quote

    # ===========================================================
    # trades
    # ===========================================================
    def trades(self):
        """Get recent trades."""
        self.__thread_lock()
        trade = self.data["trade"][:]
        self.__thread_unlock()
        return trade

    # ===========================================================
    # executions
    # ===========================================================
    def executions(self):
        """Get recent executions."""
        self.__thread_lock()
        execution = self.data["execution"][:]
        self.__thread_unlock()
        return execution

    # ===========================================================
    # margin(funds), position, instrument は更新型
    # ===========================================================
    # funds (margin)
    # ===========================================================
    def funds(self):
        """Get your margin details."""
        self.__thread_lock()
        margin = copy.copy(self.data["margin"])
        self.__thread_unlock()
        return margin

    # ===========================================================
    # position
    # ===========================================================
    def position(self):
        """ Get your position details."""
        self.__thread_lock()
        pos = copy.copy(self.data["position"])
        self.__thread_unlock()
        return pos

    # ===========================================================
    # instrument
    # ===========================================================
    def instrument(self):
        """Get the raw instrument data for this symbol."""
        # Turn the 'tickSize' into 'tickLog' for use in rounding
        instrument = self.data["instrument"]
        instrument["tickLog"] = int(math.fabs(math.log10(instrument["tickSize"])))
        return instrument

    # ===========================================================
    # tickerはquote,trade,instrumentから作成された合成型
    # ===========================================================
    # ticker
    # ===========================================================
    def ticker(self):
        """Return a ticker object. Generated from quote and trade."""
        self.__thread_lock()
        lastQuote = self.data["quote"][-1]
        lastTrade = self.data["trade"][-1]
        ticker = {
            "last": lastTrade["price"],
            "bid": lastQuote["bidPrice"],
            "ask": lastQuote["askPrice"],
            "mid": (
                float(lastQuote["bidPrice"] or 0) + float(lastQuote["askPrice"] or 0)
            )
            / 2,
        }

        # The instrument has a tickSize. Use it to round values.
        instrument = self.data["instrument"]
        self.__thread_unlock()
        return {
            k: round(float(v or 0), instrument["tickLog"]) for k, v in ticker.items()
        }

    # ===========================================================
    # orders, orderbook はDB型(partial, insert, update, delete)
    # ===========================================================
    # open orders
    # ===========================================================
    def open_orders(self, clOrdIDPrefix=None):
        """Get all your open orders."""
        self.__thread_lock()
        # orders = self.data['order']
        orders = self._order.get_orders()
        self.__thread_unlock()
        if clOrdIDPrefix is None:
            # Filter to only open orders (leavesQty > 0) and those that we actually placed
            return [o for o in orders if o["leavesQty"] > 0]
        else:
            # Filter to only open orders (leavesQty > 0) and those that we actually placed
            return [
                o
                for o in orders
                if str(o["clOrdID"]).startswith(clOrdIDPrefix) and o["leavesQty"] > 0
            ]

    # ===========================================================
    # market depth (orderbook)
    # ===========================================================
    def orderbook(self):
        """Get market depth (orderbook). Returns all levels."""
        # return self.data['orderBookL2']
        self.__thread_lock()
        book = self._orderbook.get_orderbook(BitMEXWebsocket.MAX_ORDERBOOK_LEN)
        self.__thread_unlock()

        # もし、orderbookの内容が壊れて、bidとaskの整合性が崩れたたら例外を発行する
        bid = book["bids"][0]["price"]
        ask = book["asks"][0]["price"]
        if bid >= ask:
            raise Exception("orderbook: bid({}) >= ask({})".format(bid, ask))

        return book

    # ===========================================================
    # candle
    #   params:
    #       type: 0, 1  # 0: 未確定含まない, 1: 未確定含む
    # ===========================================================
    def candle(self, type=0):
        self.__thread_lock()
        if type == 0:
            candle = self._candle[:-1]
        else:
            candle = self._candle[:]
        self.__thread_unlock()
        return candle

    # ==========================================================
    # ヘルパー関数
    # ==========================================================
    # 注文更新で使用する orderID, price, leavesQtyを注文から取得
    #   param:
    #       order: order
    #   return:
    #       orderID, price, leavesQty
    # ==========================================================
    def get_amend_params(self, order):
        orderID = order["orderID"]
        price = order["price"]
        leavesQty = order["leavesQty"]
        return orderID, price, leavesQty

    # ==========================================================
    # 注文削除で使用する orderID を取得する
    #   param:
    #       orders: order配列
    #   return:
    #       orderID（複数ある場合は 'xxxx,yyyy,zzzz'）
    # ==========================================================
    def get_cancel_params(self, orders):
        orderIDs = ""
        for o in orders:
            if orderIDs != "":
                orderIDs += ","
            orderIDs += o["orderID"]
        return orderIDs

    # ==========================================================
    # 注文価格配列を order から取得する
    #   param:
    #       orders: order配列
    #   return:
    #       price list
    # ==========================================================
    def get_price_list(self, orders):
        prices = []
        for o in orders:
            prices.append(o["price"])
        return prices

    # ==========================================================
    # 指定したclOrdIDを含む注文を検索・取得
    #   params:
    #       clOrdID: 'limit_buy', 'limit_sell', 'settle_buy' or 'settle_sell' -> 'settle'だけで決済注文を検索しても良い
    # ==========================================================
    def find_orders(self, open_orders, clOrdID):
        return [order for order in open_orders if 0 < order["clOrdID"].find(clOrdID)]

    # ==========================================================
    # candleデータフレーム作成
    #   param:
    #       candle: 5秒足配列　[['timestamp','open','high','low','close','volume','buy','sell'], [], [], ,,,,]
    #   return:
    #       df: pandas.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'buy', 'sell'])
    # ==========================================================
    def to_candleDF(self, candle):
        # ------------------------------------------------------
        # DataFrame作成
        # ------------------------------------------------------
        # df = pd.DataFrame(ws.candle()[-ws.MAX_CANDLE_LEN:])
        # df = df.loc[:, ['timestamp','open','high','low','close','volume','buy','sell']]
        # ↑ 上記の記述は冗長なので書き直した
        df = pd.DataFrame(
            candle,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "buy",
                "sell",
            ],
        )
        # ------------------------------------------------------
        # 日時データをDataFrameのインデックスにする
        #   candleのtimestampデータがUNIXTIME(秒)なので、unit='s'を指定する。（ミリ秒なら 'ms'を指定する）
        # ------------------------------------------------------
        df["timestamp"] = pd.to_datetime(
            df["timestamp"], unit="s", infer_datetime_format=True
        )  # infer_datetime_format=Trueは高速化に寄与するとのこと。
        df = df.set_index("timestamp")
        # ------------------------------------------------------
        # timezone を変更する。
        #   tz_convert('Asia/Tokyo')    local-PC:OK,    AWS Cloud9: NG
        #   tz_convert(None)            AWS Cloud9: OK
        #   tz_localize(None)           AWS Cloud9: OK
        # 考慮の末、tz_localize(None)を採用した。
        # ------------------------------------------------------
        # df.index = df.index.tz_convert('Asia/Tokyo')   # local-PC: OK, AWS Cloud9: NG
        # df.index = df.index.tz_convert(None)           # AWS Cloud9: OK
        df.index = df.index.tz_localize(None)  # AWS Cloud9: OK
        # ------------------------------------------------------
        # 一つでも欠損値(NaN)がある行は削除する
        # ------------------------------------------------------
        count_all = len(df)
        df_notnan = df.dropna(how="any")
        count_notNaN = len(df_notnan)
        # ------------------------------------------------------
        if count_all != count_notNaN:
            self.logger.warning(
                "candle data include NaN, all={}, NaN={}".format(
                    count_all, count_all - count_notNaN
                )
            )
            return df_notnan
        else:
            return df

    # ==========================================================
    # ローソク足の足幅変換
    #   params:
    #       ohlcv: pandas.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'buy', 'sell'])
    #       resolution: 刻み幅(10s, 15s, 30s)
    # ==========================================================
    def change_candleDF(self, ohlcv, resolution="10s"):
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

        period = {"10s": "10S", "15s": "15S", "30s": "30S"}

        if resolution not in period.keys():
            return None

        # 他の秒刻みに直す
        df = (
            ohlcv[["open", "high", "low", "close", "volume", "buy", "sell"]]
            .resample(period[resolution], label="left", closed="left")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "buy": "sum",
                    "sell": "sum",
                }
            )
        )
        # ohlcを再度ohlcに集計するにはaggメソッド

        return df

    # ###########################################################
    # local Methods
    # ###########################################################

    # ===========================================================
    # ローカル変数の初期化
    #   プログラムで変更される可能性のあるデータ
    # ===========================================================
    def __initialize_params(self):
        # メッセージデータ
        self.data = {}
        # 本クラスを終了させるときにONにするフラグ
        self.exited = False
        # socket側からerror通知を受けた時ONにする。外部プログラムからこのフラグを見て reconnect するかどうかを決める
        self.__force_exit = False

        # candle
        self._candle = []
        """
            candleデータの構造
            {
                'timestamp': round(datetime.utcnow().timestamp()),
                'open': 0,
                'high': 0,
                'low': 0,
                'close': 0,
                'volume': 0,
                'buy': 0,
                'sell':0
            }
        """

        # sqlite3 (in memory database)
        self._db = sqlite3.connect(
            database=":memory:",  # in memory
            isolation_level="EXCLUSIVE",  # 開始時にEXCLUSIVEロックを取得する
            check_same_thread=False,  # 他のスレッドからの突入を許す
        )

        # orderbook クラス作成
        self._orderbook = OrderBook(self._db, self.logger)
        # order クラス作成
        self._order = Order(self._db, self.logger)

        # 高速化のため、各処理の処理時間を格納するtimemarkを作成
        self.timemark = {}
        self.timemark["partial"] = 0
        self.timemark["insert"] = 0
        self.timemark["update"] = 0
        self.timemark["delete"] = 0
        self.timemark["count"] = 0

        self.__initialize_timemark("execution")
        self.__initialize_timemark("order")
        self.__initialize_timemark("position")
        self.__initialize_timemark("quote")
        self.__initialize_timemark("trade")
        self.__initialize_timemark("margin")
        self.__initialize_timemark("instrument")
        self.__initialize_timemark("orderBookL2")

    # ===========================================================
    # timemarkテーブルの初期化
    # ===========================================================
    def __initialize_timemark(self, table):
        self.timemark[table] = {}
        self.timemark[table]["partial"] = 0
        self.timemark[table]["insert"] = 0
        self.timemark[table]["update"] = 0
        self.timemark[table]["delete"] = 0
        self.timemark[table]["count"] = 0

    # ===========================================================
    # websocket thread終了
    # ===========================================================
    def __wst_thread_exit(self):
        # スレッドを終了させようとしても終了しないことが多数ある。最終的にsocketがクローズされると終了しているので、タイムアウトしたらそのまま処理を終えるようにする。
        self.wst.join(timeout=3)  # この値が妥当かどうか検討する
        """
        # websocket thread
        while self.wst.is_alive():
            self.wst.join(timeout=3) # この値が妥当かどうか検討する
            if self.wst.is_alive() == True:
                self.logger.warning('websocket thread {} still alive'.format(self.wst))
            else:
                self.logger.info("websocket thread is ended.")
        """

    # ===========================================================
    # check candle thread終了
    # ===========================================================
    def __check_candle_thread_exit(self):
        # スレッドを終了させようとしても終了しないことが多数ある。最終的にsocketがクローズされると終了しているので、タイムアウトしたらそのまま処理を終えるようにする。
        self._check_candle_thread.join(timeout=3)  # この値が妥当かどうか検討する
        """
        # check candle thread
        while self._check_candle_thread.is_alive():
            if self._check_candle_thread.is_alive() == True:
                self.logger.warning('check candle thread {} still alive'.format(self._check_candle_thread))
            else:
                self.logger.info("check candle thread is ended.")
        """

    # ===========================================================
    # Lock取得
    # ===========================================================
    def __thread_lock(self):
        _count = 0
        while self._lock.acquire(blocking=True, timeout=1) == False:
            _count += 1
            if _count > 3:
                self.logger.error("lock acquire: timeout")
                return False
        return True

    # ===========================================================
    # Lock解放
    # ===========================================================
    def __thread_unlock(self):
        try:
            self._lock.release()
        except Exception as e:
            self.logger.error("lock release: {}".format(e))
            return False
        return True

    # ===========================================================
    # websocket 接続
    # ===========================================================
    def __connect(self, wsURL, symbol):
        """Connect to the websocket in a thread."""
        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 0
        # -------------------------------------------------------
        # websocket
        # -------------------------------------------------------
        self.ws = websocket.WebSocketApp(
            wsURL,
            on_message=self.__on_message,
            on_close=self.__on_close,
            on_open=self.__on_open,
            on_error=self.__on_error,
            header=self.__get_auth(),
        )
        self.ws.keep_running = True  # 実行中を保持する
        self.logger.debug("Started websocket connection")

        # -------------------------------------------------------
        # websocket スレッド
        # -------------------------------------------------------
        self.wst = threading.Thread(target=lambda: self.ws.run_forever())
        self.wst.daemon = True  # mainスレッドが終わったときにサブスレッドも終了する
        self.wst.start()
        self.logger.debug("Started websocket thread")

        # -------------------------------------------------------
        # ローソク足チェックスレッド
        # -------------------------------------------------------
        self._check_candle_thread = threading.Thread(
            target=self.__check_candle, args=("check_candle",)
        )
        self._check_candle_thread.daemon = True
        self._check_candle_thread.start()
        self.logger.debug("Started check candle thread")

        # -------------------------------------------------------
        # Wait for connect before continuing
        # -------------------------------------------------------
        conn_timeout = 5
        while not self.ws.sock or not self.ws.sock.connected and conn_timeout:
            time.sleep(1)
            conn_timeout -= 1
        if not conn_timeout:
            self.logger.error("Couldn't connect to WS! Exiting.")
            # 別スレッドから終了処理をしているので大丈夫
            self.exit()
            raise websocket.WebSocketTimeoutException(
                "Couldn't connect to WS! Exiting."
            )

        # -------------------------------------------------------
        # コネクション確立
        # -------------------------------------------------------
        self.logger.info("Started websocket & threads")

    # ===========================================================
    # nonce作成
    # ===========================================================
    def __generate_nonce(self):
        return int(round(time.time() * 3600))

    # ===========================================================
    # Generates an API signature.
    # A signature is HMAC_SHA256(secret, verb + path + nonce + data), hex encoded.
    # Verb must be uppercased, url is relative, nonce must be an increasing 64-bit integer
    # and the data, if present, must be JSON without whitespace between keys.
    #
    # For example, in psuedocode (and in real code below):
    #
    # verb=POST
    # url=/api/v1/order
    # nonce=1416993995705
    # data={"symbol":"XBTZ14","quantity":1,"price":395.01}
    # signature = HEX(HMAC_SHA256(secret, 'POST/api/v1/order1416993995705{"symbol":"XBTZ14","quantity":1,"price":395.01}'))
    # ===========================================================
    def __generate_signature(self, secret, verb, url, nonce, data):
        """Generate a request signature compatible with BitMEX."""
        # Parse the url so we can remove the base and extract just the path.
        parsedURL = urllib.parse.urlparse(url)
        path = parsedURL.path
        if parsedURL.query:
            path = path + "?" + parsedURL.query

        # print "Computing HMAC: %s" % verb + path + str(nonce) + data
        message = (verb + path + str(nonce) + data).encode("utf-8")

        signature = hmac.new(
            secret.encode("utf-8"), message, digestmod=hashlib.sha256
        ).hexdigest()
        return signature

    # ===========================================================
    # 認証
    # ===========================================================
    def __get_auth(self):
        """Return auth headers. Will use API time.time() if present in settings."""
        if self.api_key:
            self.logger.info("Authenticating with API Key.")
            # To auth to the WS using an API key, we generate a signature of a nonce and
            # the WS API endpoint.
            expires = self.__generate_nonce()
            return [
                "api-expires: " + str(expires),
                "api-signature: "
                + self.__generate_signature(
                    self.api_secret, "GET", "/realtime", expires, ""
                ),
                "api-key:" + self.api_key,
            ]
        else:
            self.logger.info("Not authenticating.")
            return []

    # ===========================================================
    # 接続URL取得
    # ===========================================================
    def __get_url(self):
        """
        Generate a connection URL. We can define subscriptions right in the querystring.
        Most subscription topics are scoped by the symbol we're listening to.
        """

        # You can sub to orderBookL2 for all levels, or orderBook10 for top 10 levels & save bandwidth
        """
        取得するtable
            execution
            order
            position
            quote
            trade
            margin
            instrument
            orderBookL2
        """
        symbolSubs = [
            "execution",
            "instrument",
            "order",
            "orderBookL2",
            "position",
            "quote",
            "trade",
        ]
        genericSubs = ["margin"]

        subscriptions = [sub + ":" + self.symbol for sub in symbolSubs]
        subscriptions += genericSubs

        urlParts = list(urllib.parse.urlparse(self.endpoint))
        urlParts[0] = urlParts[0].replace("http", "ws")
        urlParts[2] = "/realtime?subscribe={}".format(",".join(subscriptions))
        return urllib.parse.urlunparse(urlParts)

    # ===========================================================
    # アカウント待ち
    # ===========================================================
    def __wait_for_account(self):
        """On subscribe, this data will come down. Wait for it."""
        # -------------------------------------------------------
        # Wait for the time.time() to show up from the ws
        # -------------------------------------------------------
        wait_timeout = 600
        while (
            not {"margin", "position", "order", "execution"} <= set(self.data)
            and wait_timeout
        ):
            time.sleep(0.1)
            wait_timeout -= 1
        if not wait_timeout:
            self.logger.error("Couldn't wait [margin][position][order][execution].")
            # 別スレッドから終了処理をしているので大丈夫
            self.exit()
            raise websocket.WebSocketTimeoutException(
                "Couldn't wait [margin][position][order][execution]."
            )

    # ===========================================================
    # シンボル待ち
    # ===========================================================
    def __wait_for_symbol(self, symbol):
        """On subscribe, this data will come down. Wait for it."""
        # -------------------------------------------------------
        # order, orderBookL2はself.dataを使わなくすると、待ち処理でロックしてしまうので、とりあえずこのまま置いておく。
        # -------------------------------------------------------
        wait_timeout = 600
        while not {"instrument", "trade", "quote", "orderBookL2"} <= set(self.data):
            time.sleep(0.1)
            wait_timeout -= 1
        if not wait_timeout:
            self.logger.error("Couldn't wait [instrument][trade][quote][orderBookL2].")
            # 別スレッドから終了処理をしているので大丈夫
            self.exit()
            raise websocket.WebSocketTimeoutException(
                "Couldn't wait [instrument][trade][quote][orderBookL2]."
            )

    # ===========================================================
    # コマンド送信（現在未使用）
    # ===========================================================
    def __send_command(self, command, args=None):
        """Send a raw command."""
        if args is None:
            args = []
        self.ws.send(json.dumps({"op": command, "args": args}))

    # ===========================================================
    # メッセージ受信部
    # ===========================================================
    def __on_message(self, ws, message):
        """Handler for parsing WS messages."""
        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 4
        # 時刻のタイムスタンプを更新
        self._ts = datetime.now(self._tz).timestamp()
        #
        message = json.loads(message)
        self.logger.debug(json.dumps(message))

        table = message["table"] if "table" in message else None
        action = message["action"] if "action" in message else None
        try:
            # ---------------------------------------------------
            # subscribe
            # ---------------------------------------------------
            if "subscribe" in message:
                self.logger.debug("Subscribed to %s." % message["subscribe"])
            # ---------------------------------------------------
            # action
            # ---------------------------------------------------
            elif action:

                """
                - この３つはただ追記するのみなので配列 [] で追記
                  - quote　		Partial		Insert								ただ追記するのみ
                  - trade		Partial		Insert								ただ追記するのみ
                  - execution	Partial		Insert								ただ追記するのみ

                - この３つは辞書型 {} で登録・更新
                  - margin　	Partial					Update					一つのデータを更新しつづける→辞書型のUpdateが使える？
                  - position　	Partial					Update					一つのデータを更新しつづける→辞書型のUpdateが使える？
                  - instrument　Partial					Update					一つのデータを更新しつづける→辞書型のUpdateが使える？

                - この２つはDB化が必要
                  - order  		Partial		Insert		Update 					Data部の形が変わる。数が増減する
                  - orderBookL2	Partial		Insert		Update		Delete 		Data部の形が変わる。数が増減する
                """

                # Lock
                self.__thread_lock()

                if table not in self.data:
                    if table in ["orderBookL2"]:
                        # DB に 登録(partial)・挿入(insert)・更新(update)・削除(delete)
                        self.data[table] = {}
                    elif table in ["order"]:
                        # DB に 登録(partial)・挿入(insert)・更新(update)
                        self.data[table] = {}
                    elif table in ["instrument", "margin", "position"]:
                        # 辞書型 {} で登録(partial)・更新(update)
                        self.data[table] = {}
                    elif table in ["execution", "trade", "quote"]:
                        # 配列 [] で登録(partial)・挿入(insert)
                        self.data[table] = []

                # unLock
                self.__thread_unlock()

                # There are four possible actions from the WS:
                # 'partial' - full table image
                # 'insert'  - new row
                # 'update'  - update row
                # 'delete'  - delete row

                # -----------------------------------------------
                # partial
                # -----------------------------------------------
                if action == "partial":

                    self.logger.info("Received [%s]: partial" % table)

                    # 処理時間計測開始
                    start = time.time()

                    # Lock
                    self.__thread_lock()

                    try:
                        # partial
                        if table in ["orderBookL2"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)・削除(delete)
                            # orderbook取得
                            self._orderbook.replace(message["data"])
                        elif table in ["order"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)
                            # order取得
                            orders = [o for o in message["data"] if o["leavesQty"] > 0]
                            self._order.replace(orders)
                        elif table in ["instrument", "margin", "position"]:
                            # 辞書型 {} で登録(partial)・更新(update)
                            if table == "position" and len(message["data"]) == 0:
                                self.logger.warning(
                                    "position partial data is nothing. force DEFAULT"
                                )
                                self.data[table].update(BitMEXWebsocket.INIT_POSITION)
                            else:
                                self.data[table].update(message["data"][0])
                        elif table in ["execution", "trade", "quote"]:
                            # 配列 [] で登録(partial)・挿入(insert)
                            self.data[table] = message["data"]
                            # ----------------------------------------
                            # candle
                            # ----------------------------------------
                            if table == "trade":
                                self.__init_candle_data(self.data[table])
                    except Exception as e:
                        self.logger.error("Exception {} partial {}".format(table, e))

                    # unLock
                    self.__thread_unlock()

                    # 処理時間計測終了・登録
                    end = time.time()
                    if self._use_timemark:
                        self.timemark["partial"] += end - start
                        self.timemark["count"] += 1
                        self.timemark[table]["partial"] += end - start
                        self.timemark[table]["count"] += 1

                # -----------------------------------------------
                # insert
                # -----------------------------------------------
                elif action == "insert":

                    self.logger.debug("%s: inserting %s" % (table, message["data"]))

                    # 処理時間計測開始
                    start = time.time()

                    # Lock
                    self.__thread_lock()

                    try:
                        # insert
                        if table in ["orderBookL2"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)・削除(delete)
                            # orderbook取得
                            self._orderbook.replace(message["data"])
                        elif table in ["order"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)
                            # order取得
                            orders = [o for o in message["data"] if o["leavesQty"] > 0]
                            self._order.replace(orders)
                        elif table in ["execution", "trade", "quote"]:
                            # 配列 [] で登録(partial)・挿入(insert)
                            self.data[table] += message["data"]
                            if len(self.data[table]) > (
                                BitMEXWebsocket.MAX_TABLE_LEN * 1.5
                            ):
                                self.data[table] = self.data[table][
                                    -BitMEXWebsocket.MAX_TABLE_LEN :
                                ]
                            # ----------------------------------------
                            # candle
                            # ----------------------------------------
                            if table == "trade":
                                for trade in message["data"]:
                                    self.__update_candle_data(trade)
                        elif table in ["instrument", "margin", "position"]:
                            # dataは来ないはず
                            self.logger.error(
                                "insert event occured table: {}".format(table)
                            )
                    except Exception as e:
                        self.logger.error("Exception {} insert {}".format(table, e))

                    # unLock
                    self.__thread_unlock()

                    # 処理時間計測終了・登録
                    end = time.time()
                    if self._use_timemark:
                        self.timemark["insert"] += end - start
                        self.timemark["count"] += 1
                        self.timemark[table]["insert"] += end - start
                        self.timemark[table]["count"] += 1

                # -----------------------------------------------
                # update
                # -----------------------------------------------
                elif action == "update":

                    self.logger.debug("%s: updating %s" % (table, message["data"]))

                    # 処理時間計測開始
                    start = time.time()

                    # Lock
                    self.__thread_lock()

                    try:
                        # update
                        if table in ["orderBookL2"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)・削除(delete)
                            # orderbook取得
                            self._orderbook.update(message["data"])
                        elif table in ["order"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)
                            # order取得
                            update_order = []
                            delete_order = []
                            for order in message["data"]:
                                if "leavesQty" in order:  # leavesQtyを持っているデータ
                                    if order["leavesQty"] <= 0:
                                        # 削除対象
                                        delete_order.append(order)
                                    else:
                                        update_order.append(order)
                                else:
                                    update_order.append(order)
                            # orderを更新
                            for o in update_order:
                                # order情報をUpdate
                                order = self._order.select(o["orderID"])
                                if len(order) != 0:
                                    # orderはdeleteが通知されないかわりに update で leavesQty = 0 の通知をもって delete としているが、
                                    # ごく稀に leavesQty = 0 の通知の後、update が再び通知されることがあるが、
                                    # その後すぐに leavesQty = 0 が再度通知されるので問題ない。DBに存在しない update は無視することとする。
                                    order[0].update(o)
                                    self._order.replace(order)
                                else:
                                    # for DEBUG
                                    self.logger.debug(
                                        "{}, {}, {}, {}".format(
                                            table,
                                            action,
                                            o["orderID"],
                                            "already deleted",
                                        )
                                    )
                            # キャンセルや約定済みorderを削除
                            if len(delete_order) != 0:
                                self._order.delete(delete_order)
                        elif table in ["instrument", "margin", "position"]:
                            # 辞書型 {} で登録(partial)・更新(update)
                            self.data[table].update(message["data"][0])
                        elif table in ["execution", "trade", "quote"]:
                            # dataは来ないはず
                            self.logger.error(
                                "update event occured table: {}".format(table)
                            )
                    except Exception as e:
                        self.logger.error("Exception {} update {}".format(table, e))

                    # unLock
                    self.__thread_unlock()

                    # 処理時間計測終了・登録
                    end = time.time()
                    if self._use_timemark:
                        self.timemark["update"] += end - start
                        self.timemark["count"] += 1
                        self.timemark[table]["update"] += end - start
                        self.timemark[table]["count"] += 1

                # -----------------------------------------------
                # delete
                # -----------------------------------------------
                elif action == "delete":

                    self.logger.debug("%s: deleting %s" % (table, message["data"]))

                    # 処理時間計測開始
                    start = time.time()

                    # Lock
                    self.__thread_lock()

                    try:
                        # delete
                        if table in ["orderBookL2"]:
                            # DB に 登録(partial)・挿入(insert)・更新(update)・削除(delete)
                            # orderbook取得
                            self._orderbook.delete(message["data"])
                        elif table in [
                            "execution",
                            "instrument",
                            "trade",
                            "quote",
                            "margin",
                            "position",
                            "order",
                        ]:
                            # dataは来ないはず
                            self.logger.error(
                                "delete event occured table: {}".format(table)
                            )
                    except Exception as e:
                        self.logger.error("Exception {} delete {}".format(table, e))

                    # unLock
                    self.__thread_unlock()

                    # 処理時間計測終了・登録
                    end = time.time()
                    if self._use_timemark:
                        self.timemark["delete"] += end - start
                        self.timemark["count"] += 1
                        self.timemark[table]["delete"] += end - start
                        self.timemark[table]["count"] += 1

                # -----------------------------------------------
                # Unknown action は無視する
                # -----------------------------------------------
                else:
                    # raise Exception("Unknown action: %s" % action)
                    self.logger.error("Unknown action {}".format(action))
        except:
            self.logger.error(traceback.format_exc())

    # ===========================================================
    # エラー受信部
    # ===========================================================
    def __on_error(self, ws, error):
        """Called on fatal websocket errors. We exit on these."""
        self.logger.error("websocket: __on_error() : %s" % error)
        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 3
        #
        if not self.exited:
            # 強制終了フラグをONにする（このフラグがたったときにはすでにsock.connectedがOFFかもしれないが）
            self.__force_exit = True
            # 例外をスロー
            raise websocket.WebSocketException(error)

    # ===========================================================
    # オープン受信部
    # ===========================================================
    def __on_open(self, ws):
        """Called when the WS opens."""
        self.logger.info("websocket: __on_open()")
        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 1

    # ===========================================================
    # クローズ受信部
    # ===========================================================
    def __on_close(self, ws):
        """Called on websocket close."""
        self.logger.info("websocket: __on_close()")
        # -------------------------------------------------------
        # websocket status
        #   0:  initial
        #   1:  open
        #   2:  close
        #   3:  error
        #   4:  message
        # -------------------------------------------------------
        self._ws_status = 2

    # ===========================================================
    # ローソク足の収集開始
    # ===========================================================
    def __init_candle_data(self, trades):
        # ローソク足の最初のタイムスタンプを作成
        ts = round(dateutil.parser.parse(trades[0]["timestamp"]).timestamp())
        mark_ts = ts - ts % BitMEXWebsocket.CANDLE_RANGE
        self.logger.debug("ローソク足開始時刻 {}".format(mark_ts))

        # 最初のデータ
        self._candle.append(
            {
                "timestamp": mark_ts,
                "open": trades[0]["price"],
                "high": trades[0]["price"],
                "low": trades[0]["price"],
                "close": trades[0]["price"],
                "volume": trades[0]["size"],
                "buy": trades[0]["size"] if trades[0]["side"] == "Buy" else 0,
                "sell": trades[0]["size"] if trades[0]["side"] == "Sell" else 0,
            }
        )

        if len(trades) > 1:
            # data部が複数
            for trade in trades[1:]:
                self.__update_candle_data(trade)

    # ===========================================================
    # ローソク足のデータを更新する
    # ===========================================================
    def __update_candle_data(self, trade):
        ts = round(dateutil.parser.parse(trade["timestamp"]).timestamp())
        # 最後のcandle足
        last_candle = self._candle[-1]
        mark_ts = last_candle["timestamp"]
        """
        # for DEBUG
        print('■ mark_ts {} ,ts {}, diff {} :判定 {}, {}'.format(
                mark_ts, 
                ts, 
                ts - mark_ts,
                (mark_ts < ts <= (mark_ts + BitMEXWebsocket.CANDLE_RANGE)),
                ((mark_ts + BitMEXWebsocket.CANDLE_RANGE) < ts)
            ))
        """
        # 開始日時からRANGE内に収まっていたら、既存のcandleを更新する
        if mark_ts < ts <= (mark_ts + BitMEXWebsocket.CANDLE_RANGE):
            # timestamp, openは更新しない
            last_candle["high"] = max(last_candle["high"], trade["price"])
            last_candle["low"] = min(last_candle["low"], trade["price"])
            last_candle["close"] = trade["price"]
            last_candle["volume"] += trade["size"]
            last_candle["buy"] += trade["size"] if trade["side"] == "Buy" else 0
            last_candle["sell"] += trade["size"] if trade["side"] == "Sell" else 0
        # 次の時間帯になっていたら、新しいcandleを作る
        elif (mark_ts + BitMEXWebsocket.CANDLE_RANGE) < ts:
            # mark_tsを更新
            mark_ts = mark_ts + BitMEXWebsocket.CANDLE_RANGE
            # 新しいcandleを作成
            self._candle.append(
                {
                    "timestamp": mark_ts,
                    "open": last_candle["close"],  # 一つ前のcloseデータを今回のopenに設定
                    "high": trade["price"],
                    "low": trade["price"],
                    "close": trade["price"],
                    "volume": trade["size"],
                    "buy": trade["size"] if trade["side"] == "Buy" else 0,
                    "sell": trade["size"] if trade["side"] == "Sell" else 0,
                }
            )

    # ===========================================================
    # ローソク足の不足分データが無いかどうかをチェックする
    # ===========================================================
    def __check_candle(self, args):
        # エリア設定待ち
        while "trade" not in self.data:
            time.sleep(1)
        # データの格納待ち
        while len(self.trades()) == 0:
            time.sleep(1)

        # UTC = timezone.utc    # でも良かったみたい
        UTC = timezone(timedelta(hours=0), name="UTC")

        # socketが接続されている間だけ処理する
        while self.ws.sock and self.ws.sock.connected:
            # candle生成時間の半分だけ待つ
            time.sleep(BitMEXWebsocket.CANDLE_RANGE / 2)

            # Lock
            self.__thread_lock()

            try:
                # 現在時刻(UTC)のtimestamp
                ts = round(datetime.now(UTC).timestamp())
                # 最後のcandle足
                last_candle = self._candle[-1]
                mark_ts = last_candle["timestamp"]
                """
                # for DEBUG
                print('● mark_ts {} ,ts {}, diff {} :判定 {}, {}'.format(
                        mark_ts, 
                        ts, 
                        ts - mark_ts,
                        (mark_ts < ts <= (mark_ts + BitMEXWebsocket.CANDLE_RANGE)),
                        ((mark_ts + BitMEXWebsocket.CANDLE_RANGE) < ts)
                    ))
                """
                # 次の時間帯になっていたら、新しいcandle(空)を作る
                if (mark_ts + BitMEXWebsocket.CANDLE_RANGE) < ts:
                    # mark_tsを更新
                    mark_ts = mark_ts + BitMEXWebsocket.CANDLE_RANGE
                    # 新しいcandleを作成
                    self._candle.append(
                        {
                            "timestamp": mark_ts,
                            "open": last_candle["close"],
                            "high": last_candle["close"],
                            "low": last_candle["close"],
                            "close": last_candle["close"],
                            "volume": 0,
                            "buy": 0,
                            "sell": 0,
                        }
                    )

                # 最大サイズ調整
                if len(self._candle) > (BitMEXWebsocket.MAX_CANDLE_LEN * 1.5):
                    self._candle = self._candle[-BitMEXWebsocket.MAX_CANDLE_LEN :]
            except Exception as e:
                self.logger.error("check candle thread Exception {}".format(e))
            finally:
                pass

            # unLock
            self.__thread_unlock()


# ###############################################################
# テスト
# ###############################################################
if __name__ == "__main__":

    # -------------------------------------------
    # テストクラス
    # -------------------------------------------
    class Test:

        USE_TESTNET = True
        SYMBOL = "XBTUSD"
        APIKEY = ""
        SECRET = ""

        def __init__(self, logger):
            # loggerオブジェクトの宣言
            self.logger = logger
            # loggerのログレベル設定(ハンドラに渡すエラーメッセージのレベル)
            self.logger.setLevel(logging.INFO)  # ※ここはConfigで設定可能にする
            # Formatterの生成
            formatter = Formatter(
                fmt="%(asctime)s, %(levelname)-8s, %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            # console handlerの生成・追加
            stream_handler = StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

            # WebSocket API接続用オブジェクトを生成
            self.ws = BitMEXWebsocket(
                endpoint="wss://www.bitmex.com/realtime"
                if Test.USE_TESTNET is False
                else "wss://testnet.bitmex.com/realtime",
                symbol=Test.SYMBOL,
                api_key=Test.APIKEY,
                api_secret=Test.SECRET,
                logger=self.logger,
                use_timemark=False,
            )
            # instrumentメソッドを一度呼び出さないとエラーを吐くので追加(内部的にget_tickerがこの情報を使用するため)
            # self.ws.instrument()

            # 例外発生のカウント
            self.count = 0

        def run(self):
            # websocket start
            while (
                self.ws.ws.sock
                and self.ws.ws.sock.connected
                and not self.ws.is_force_exit()
            ):
                pass
                """
                # for DEBUG
                book = self.ws.orderbook()
                self.logger.info('orderbook bids[0] {}'.format(book['bids'][0]))
                time.sleep(0.1)
                # ダミーの例外を発生させる
                self.count += 1
                if self.count > 3:
                    raise Exception('Unknown')
                """

        def reconnect(self):
            self.count = 0
            self.ws.reconnect()

        def exit(self):
            self.ws.exit()
            del self.ws

    # -------------------------------------------
    #  空クラス
    # -------------------------------------------
    class T:
        def __init__(self):
            print("init")

        def __del__(self):
            print("del")

        def run(self):
            print("run")
            # for DEBUG
            # raise Exception('exception run')

        def exit(self):
            print("exit")

    # -------------------------------------------
    # 実行
    # -------------------------------------------
    logger = getLogger("test")
    t = Test(logger=logger)
    while True:
        try:
            print("- inmemorydb_bitmex_websocket debug start -")
            t.run()
        except Exception as e:
            print("loop {}, object {}, socket {}".format(e, t, t.ws))
        finally:
            t.reconnect()
            time.sleep(5)
            print("- inmemorydb_bitmex_websocket restart -")
