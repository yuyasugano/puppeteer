# -*- coding: utf-8 -*-
# ==========================================
# Discord
# ==========================================
import requests
import time
from datetime import datetime

# thred操作
import threading

# csv reader として利用
import pandas as pd

# グラフ保存用
import matplotlib as mpl
import matplotlib as plt
import matplotlib.dates as mdates

plt.use("Agg")

# from puppeteer import Puppeteer


# ==============================================================
# Balance クラス
#   param:
#       puppeteer: Puppeteerオブジェクト
# ==============================================================
class Balance:

    # ==========================================================
    # 初期化
    #   param:
    #       puppeteer: Puppeteerオブジェクト
    # ==========================================================
    def __init__(self, Puppeteer):
        self._exchange = Puppeteer._exchange  # 取引所オブジェクト
        self._logger = Puppeteer._logger  # logger
        self._config = Puppeteer._config  # 定義ファイル
        if hasattr(Puppeteer, '_ws'):
            self._ws = Puppeteer._ws  # websocket
        else:
            self._ws = None
        self._ccxt = Puppeteer._ccxt  # ccxt wrapper object
        self._discord = Puppeteer._discord  # discord
        self._balanceLogger = Puppeteer._balanceLogger  # 資産通知用ロガー

        # neither websocket nor balance true then warn a user
        '''
        if not self._config["USE_WEBSOCKET"] and not self._config["USE"]["BALANCE"]:
            self._logger.warning(
                "balance output is None. because [not websocket] and [not use balance]"
            )
        '''

        # ログファイル名
        self._balanceLogName = Puppeteer._balanceLogName  # ログファイル名

        self._loop_sec = 60  # ループ時間（秒）

        # すでにあるwalletBalanceファイルを読み込む
        self._walletBalance = 0
        try:
            # walletBalanceファイルを読み込み
            df = pd.read_csv(
                filepath_or_buffer="logs/" + self._balanceLogName + ".log",  # logファイル名
                names=("datetime", "balance", "diff"),  # カラム名
                encoding="UTF-8",  # エンコーディング
                sep=",",  # セパレータ（csv形式なので、「,」）
            )
            # 読み込みに成功したら、最終行のbalanceデータを取り出し、前回値に設定する
            self._walletBalance = df["balance"].values[-1]
        except:
            # ファイルが存在しない
            pass

        # -------------------------------------------------------
        # 資産状況通知スレッド
        # -------------------------------------------------------
        self._send_balance_thread = threading.Thread(
            target=self.__run, args=("check_balance",)
        )
        self._send_balance_thread.daemon = True
        self._send_balance_thread.start()
        self._logger.debug("Started check balance thread")

    # ===========================================================
    # デストラクタ
    # ===========================================================
    def __del__(self):
        self._send_balance_thread.join(timeout=3)

    # ==========================================================
    # balanceデータ
    # ==========================================================
    def balance(self):
        # if self._config["USE_WEBSOCKET"]:
        walletBalance=0.0
        if self._ws is not None:
            # websocket 有効
            if self._ccxt.__class__.__name__ == 'liquid':
                # add liquid websocket code if needed
                walletBalance
            elif self._ccxt.__class__.__name__ == 'bitmex':
                walletBalance = self._ws.funds()["walletBalance"] * 0.00000001
            else:
                walletBalance=0.0
        else:
            # websocket 無効
            balance = (
                self._exchange.fetch_balance()
                if self._config["USE"]["BALANCE"] == True
                else 0
            )
            if self._ccxt.__class__.__name__ == 'liquid':
                walletBalance = float(balance["info"][0]["balance"])
            elif self._ccxt.__class__.__name__ == 'bitmex':
                walletBalance = balance["info"][0]["walletBalance"] * 0.00000001
            else:
                walletBalance=0.0
        return walletBalance

    # ==========================================================
    # run
    # ==========================================================
    def __run(self, args):
        while True:
            # 開始
            start = time.time()

            try:
                # ------------------------------------------------------
                # 今回の資産状況
                # ------------------------------------------------------
                walletBalance = self.balance()
                # ------------------------------------------------------
                # 変化有り
                # ------------------------------------------------------
                if self._walletBalance != walletBalance:
                    # --------------------------------------------------
                    # 前回との差分
                    # --------------------------------------------------
                    diff = walletBalance - (
                        self._walletBalance
                        if self._walletBalance != 0
                        else walletBalance
                    )
                    # --------------------------------------------------
                    # 次回用に保存
                    # --------------------------------------------------
                    self._walletBalance = walletBalance

                    # --------------------------------------------------
                    #         time, balance, diff
                    # --------------------------------------------------
                    message = "{}, {}, {}".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "{:.8f}".format(self._walletBalance),
                        "{:.8f}".format(diff),
                    )
                    # --------------------------------------------------
                    # walletBalanceファイルに情報を保存
                    # --------------------------------------------------
                    self._balanceLogger.info(message)
                    time.sleep(1)

                    # --------------------------------------------------
                    # walletBalanceファイルを読み込み
                    # --------------------------------------------------
                    df = pd.read_csv(
                        filepath_or_buffer="logs/"
                        + self._balanceLogName
                        + ".log",  # logファイル名
                        header=None,  # ヘッダー無し
                        names=("datetime", "balance", "diff"),  # カラム名
                        encoding="UTF-8",  # エンコーディング
                        sep=",",  # セパレータ（csv形式なので、「,」）
                        index_col="datetime",  # 先頭列をインデックスに
                        parse_dates=True,  # indexをDatetime型に
                    )
                    # --------------------------------------------------
                    # balanceグラフを出力
                    # --------------------------------------------------
                    # print(df)
                    df.plot(y="balance")
                    plt.pyplot.gca().xaxis.set_major_formatter(
                        mdates.DateFormatter("%m/%d %H:%M")
                    )
                    plt.pyplot.xticks(rotation=45)
                    plt.pyplot.savefig("logs/" + self._balanceLogName + ".png")
                    # plt.pyplot.show()
                    plt.pyplot.close()
                    time.sleep(1)

                    # --------------------------------------------------
                    # discord通知
                    #         time, balance, diff
                    # --------------------------------------------------
                    message = "{}: balane={}, diff={}".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "{:.8f}".format(self._walletBalance),
                        "{:.8f}".format(diff),
                    )
                    # --------------------------------------------------
                    self._discord.send(
                        message=message,
                        fileName="logs/" + self._balanceLogName + ".png",
                    )
            except Exception as e:
                self._logger.error("balance module send Exception: {}".format(e))

            # 終了
            end = time.time()
            elapsed_time = end - start

            # ---------------------------------------------------
            # 時間調整
            # ---------------------------------------------------
            if elapsed_time >= self._loop_sec:
                # それほど時間を消費することはないと思うが、念のため
                self._logger.warning(
                    "balance send thread: use time {}".format(elapsed_time)
                )
            else:
                time.sleep(self._loop_sec - elapsed_time)
