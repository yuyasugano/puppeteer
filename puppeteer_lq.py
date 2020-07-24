# -*- coding: utf-8 -*-
# ==========================================
# システムモジュール
# ==========================================
import sys
import ccxt
import time
from importlib import machinery
import json
import pprint

# ログのライブラリ
import logging
from logging import getLogger, StreamHandler, Formatter
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from os.path import splitext, basename

# fetch_ohlcv改良
from datetime import datetime, timedelta, timezone
import calendar

# liquid wrapper
from exchanges.ccxt.liquid import Liquid

# ==========================================
# Puppeteer module
# ==========================================
from modules.discord import Discord  # Discord class
from modules.balance import Balance  # Balance class
from modules.heartbeat import Heartbeat  # Heartbeat class
from modules.candle import Candle  # Candle class

# ==========================================
# python pupeteer <実行ファイルのフルパス> <実行定義JSONファイルのフルパス>
# ==========================================
args = sys.argv


# ==========================================
# Puppeteer class
# ==========================================
class Puppeteer:

    # ======================================
    # 初期化
    #   param:
    #       args: Puppeteer起動時の引数
    # ======================================
    def __init__(self, args):
        # ----------------------------------
        # timezone,timestamp
        # ----------------------------------
        self._tz = timezone.utc
        self._ts = datetime.now(self._tz).timestamp()
        # ----------------------------------
        # loggerの設定
        # ----------------------------------
        # logファイル名を抜き出す
        base, ext = splitext(basename(args[1]))  # 引数チェックをする前に引数を使っているけど、Loggerを先に作りたい。
        # loggerオブジェクトの宣言
        logger = getLogger("puppeteer")
        # loggerのログレベル設定(ハンドラに渡すエラーメッセージのレベル)
        logger.setLevel(logging.INFO)  # ※ここはConfigで設定可能にする
        # Formatterの生成
        formatter = Formatter(
            fmt="%(asctime)s, %(levelname)-8s, %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        # console handlerの生成・追加
        stream_handler = StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        # file handlerの生成・追加
        timedrotating_handler = TimedRotatingFileHandler(
            filename="logs/{}.log".format(base),  # logファイル名
            when="D",  # 1日を指定
            interval=1,  # 間隔
            backupCount=7,  # 7日間保持
            encoding="UTF-8",  # UTF-8
        )
        timedrotating_handler.setFormatter(formatter)
        logger.addHandler(timedrotating_handler)
        self._logger = logger
        # ----------------------------------
        # 資産状況通知loggerの設定
        # ----------------------------------
        self._balanceLogName = base + "-balance"  # ログ名称
        # balance格納用ログ
        # loggerオブジェクトの宣言
        balanceLogger = getLogger("balanceLogger")
        # loggerのログレベル設定(ハンドラに渡すエラーメッセージのレベル)
        balanceLogger.setLevel(logging.DEBUG)  # 絶対にログを出すので
        # Formatterの生成
        formatter = Formatter(fmt="%(message)s")
        # file handlerの生成・追加
        rotating_handler = RotatingFileHandler(
            filename="logs/" + self._balanceLogName + ".log",  # logファイル名
            maxBytes=10 * 1000 * 1000,  # 10MBを指定
            backupCount=7,  # 7個保持
            encoding="UTF-8",  # UTF-8
        )
        rotating_handler.setFormatter(formatter)
        balanceLogger.addHandler(rotating_handler)
        self._balanceLogger = balanceLogger  # balanceデータ格納ロガー
        # ----------------------------------
        # Augment validation
        # ----------------------------------
        if len(args) != 3:
            self._logger.error("argument length != 3")
            exit()
        # ----------------------------------
        # 定義ファイルのロード
        # ----------------------------------
        with open(args[2], "r") as f:
            jsonData = json.load(f)
            self._config = jsonData
            # print(json.dumps(jsonData, sort_keys = True, indent = 4))
        # ----------------------------------
        # ログレベルの設定（デフォルトはINFO）
        # ----------------------------------
        if "LOG_LEVEL" in self._config:
            if self._config["LOG_LEVEL"] in [
                "CRITICAL",
                "ERROR",
                "WARNING",
                "INFO",
                "DEBUG",
            ]:
                self._logger.setLevel(eval("logging." + self._config["LOG_LEVEL"]))
        # ------------------------------
        # liquid wrapper
        # ------------------------------
        self._ccxt = Liquid(
            symbol=self._config["SYMBOL"],
            apiKey=self._config["APIKEY"],
            secret=self._config["SECRET"],
            logger=self._logger
        )
        # ------------------------------
        # 取引所オブジェクト
        # ------------------------------
        self._exchange = self._ccxt._exchange
        # ----------------------------------
        # Discord生成
        # ----------------------------------
        self._discord = Discord(self._config["DISCORD_WEBHOOK_URL"])
        # ------------------------------
        # 資産状況通知を使うか
        # ------------------------------
        if "USE_SEND_BALANCE" not in self._config:
            self._config["USE_SEND_BALANCE"] = False
        # ------------------------------
        # マルチタイムフレームを使うかどうか
        # ------------------------------
        if "MULTI_TIMEFRAME_CANDLE_SPAN_LIST" not in self._config:
            self._config["MULTI_TIMEFRAME_CANDLE_SPAN_LIST"] = []

        # ------------------------------
        # マルチタイムフレーム ローソク足オブジェクト
        # ------------------------------
        self._candle = (
            Candle(self)
            if len(self._config["MULTI_TIMEFRAME_CANDLE_SPAN_LIST"]) != 0
            else None
        )

        # ----------------------------------
        # ストラテジのロードと生成
        # ----------------------------------
        module = machinery.SourceFileLoader("Puppet", args[1]).load_module()
        self._Puppet = module.Puppet(self)
        # ----------------------------------
        # 起動メッセージ
        # ----------------------------------
        message = "Liquid puppet has been initialized. Puppet={}, Config={}, Currency pair={}, Tick interval={}(sec)".format(
            args[1], args[2], self._config["SYMBOL"], self._config["INTERVAL"]
        )
        self._logger.info(message)
        self._discord.send(message)

if __name__ == "__main__":
    def start():
        puppeteer = Puppeteer(args=args)
        balance = Balance(puppeteer) if puppeteer._config["USE_SEND_BALANCE"] else None
        while True:
            try:
                run(Puppeteer=puppeteer)
            except KeyboardInterrupt:
                puppeteer._logger.info("Keyboard Interruption detected: Process exited")
                puppeteer._discord.send("Keyboard Interruption detected: Process exited")
                # cancel orders if exit
                if len(puppeteer._ccxt.open_orders()):
                    puppeteer._ccxt.cancel_orders()
                    puppeteer._logger.info("Keyboard Interruption detected: Orders cancelled")
                    puppeteer._discord.send("Keyboard Interruption detected: Orders cancelled")
                    time.sleep(1)
                exit()
            except Exception as e:
                puppeteer._logger.error("Exception occurred: Restart the process".format(e))
                puppeteer._discord.send("Exception occurred: Restart the process".format(e))
                time.sleep(5)

    def run(Puppeteer):
        while True:
            # ----------------------------------
            # timestamp更新
            # ----------------------------------
            Puppeteer._ts = datetime.now(Puppeteer._tz).timestamp()
            # ----------------------------------
            # 引数の初期化
            # ----------------------------------
            ticker, orderbook, position, balance, candle = None, None, None, None, None
            # ----------------------------------
            # 処理開始
            # ----------------------------------
            start = time.time()
            try:
                # ------------------------------
                # ローソク足情報取得
                # ローカル関数を使用
                # ------------------------------
                candle = (
                    Puppeteer._ccxt.ohlcv(
                        symbol=Puppeteer._config["SYMBOL"],  # シンボル
                        timeframe=Puppeteer._config["CANDLE"][
                            "TIMEFRAME"
                        ],  # timeframe= 1m 5m 1h 1d
                        since=Puppeteer._config["CANDLE"][
                            "SINCE"
                        ],  # データ取得開始時刻(Unix Timeミリ秒)
                        limit=Puppeteer._config["CANDLE"][
                            "LIMIT"
                        ],  # 取得件数(未指定:100、MAX:500)
                        params={
                            "reverse": Puppeteer._config["CANDLE"][
                                "REVERSE"
                            ],  # True(New->Old)、False(Old->New)　未指定時はFlase (注意：sineceを指定せずに、このフラグをTrueにすると最古のデータは2016年頃のデータが取れる)
                            "partial": Puppeteer._config["CANDLE"][
                                "PARTIAL"
                            ],  # True(最新の未確定足を含む)、False(含まない)　未指定はTrue　（注意：まだバグっているのか、Falseでも最新足が含まれる）
                        },
                    )
                    if Puppeteer._config["USE"]["CANDLE"] == True
                    else None
                )
                # ------------------------------
                # 資産状況の取得
                # ------------------------------
                balance = (
                    Puppeteer._ccxt.balance()
                    if Puppeteer._config["USE"]["BALANCE"] == True
                    else None
                )
                print('BTC balance: {}'.format(balance['info'][2]['balance']))
                # ------------------------------
                # ポジション取得
                # ------------------------------
                position = (
                    Puppeteer._ccxt.position()
                    if Puppeteer._config["USE"]["POSITION"] == True
                    else None
                )
                print('position: {}'.format(position['models']))
                # ------------------------------
                # ticker取得
                # ------------------------------
                ticker = (
                    Puppeteer._ccxt.ticker(symbol=Puppeteer._config["SYMBOL"])  # シンボル
                    if Puppeteer._config["USE"]["TICKER"] == True
                    else None
                )
                print('last price: {}'.format(ticker['last']))
                # ------------------------------
                # 板情報取得
                # ------------------------------
                orderbook = (
                    Puppeteer._ccxt.orderbook(
                        symbol=Puppeteer._config["SYMBOL"],  # シンボル
                        limit=Puppeteer._config["ORDERBOOK"][
                            "LIMIT"
                        ],  # 取得件数(未指定:100、MAX:500)
                    )
                    if Puppeteer._config["USE"]["ORDERBOOK"] == True
                    else None
                )
                print('bid: {}, ask: {}'.format(orderbook['bids'][0][0], orderbook['asks'][0][0]))
            except Exception as e:
                # liquidオブジェクトの実行で例外が発生したが、再起動はしないで処理を継続する
                Puppeteer._logger.error(
                    "Puppeteer.run() liquid Exception: {}".format(e)
                )
                # 処理時間がINTERVALよりも長かったらワーニングを出す
                elapsed_time = time.time() - start
                if elapsed_time > Puppeteer._config["INTERVAL"]:
                    Puppeteer._logger.warning(
                        "elapsed_time={} over interval time={}".format(
                            elapsed_time, Puppeteer._config["INTERVAL"]
                        )
                    )
                continue
            # ----------------------------------
            # ストラテジ呼び出し
            # ----------------------------------
            Puppeteer._Puppet.run(ticker, orderbook, position, balance, candle)
            # ----------------------------------
            # 処理終了
            # ----------------------------------
            elapsed_time = time.time() - start
            # ----------------------------------
            # 上記までで消費された秒数だけ差し引いてスリープする
            # ----------------------------------
            interval = Puppeteer._config["INTERVAL"]
            diff = interval - elapsed_time
            if diff > 0:
                time.sleep(diff)
            else:
                time.sleep(1)
                Puppeteer._logger.warning(
                    "elapsed_time={} over interval time={}".format(
                        elapsed_time, interval
                    )
                )
    start()
