# -*- coding: utf-8 -*-

import ccxt
import time
import math
import json

# fetch_ohlcv改良
from datetime import datetime
import calendar

# for logging
import logging

# ###############################################################
# bitmex クラス
# ###############################################################
class BitMEX:

    _symbol = 'BTC/USD'

    _exchange = None

    _logger = None

    #==================================
    # 初期化
    #==================================
    def __init__(self, symbol='BTC/USD', apiKey=None, secret=None, logger=None, use_testnet=False):
        # 取引所オブジェクト(ccxt.bitmex)
        self._exchange = ccxt.bitmex({
            'apiKey': apiKey,
            'secret': secret
        })
        # TestNet利用有無
        if use_testnet == True:
            # for TESTNET
            self._exchange.urls['api'] = self._exchange.urls['test']

        self._symbol = symbol

        self._logger = logger if logger is not None else logging.getLogger(__name__)

    # ##########################################################
    # ヘルパー関数
    # ##########################################################
    # ==========================================================
    # 0.5刻みで切り上げ
    #   param:
    #       price: avgEntryPrice
    # ==========================================================
    def ceil(self, price):
        return math.ceil(price*2)/2

    # ==========================================================
    # 0.5刻みで切り下げ
    #   param:
    #       price: avgEntryPrice
    # ==========================================================
    def floor(self, price):
        return math.floor(price*2)/2

    # ==========================================================
    # 注文更新で使用する orderID, price, leavesQtyを注文から取得
    #   param:
    #       order: order
    #   return:
    #       orderID, price, leavesQty
    # ==========================================================
    def get_amend_params(self, order):
        orderID = order['id']
        price = order['price']
        leavesQty = order['info']['leavesQty']
        return orderID, price, leavesQty

    # ==========================================================
    # 注文削除で使用する orderID を取得する
    #   param:
    #       orders: order配列
    #   return:
    #       orderID（複数ある場合は 'xxxx,yyyy,zzzz'）
    # ==========================================================
    def get_cancel_params(self, orders):
        orderIDs = ''
        for o in orders:
            if orderIDs != '':
                orderIDs += ','
            orderIDs += o['id']
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
            prices.append(o['price'])
        return prices

    # ==========================================================
    # 指定したclOrdIDを含む注文を検索・取得
    #   params:
    #       clOrdID: 'limit_buy', 'limit_sell', 'settle_buy' or 'settle_sell' -> 'settle'だけで決済注文を検索しても良い
    # ==========================================================
    def find_orders(self, open_orders, clOrdID):
        return [order for order in open_orders if 0 < order['info']['clOrdID'].find(clOrdID)]

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
    def open_orders(self, symbol=_symbol):

        orders = None

        try:
            orders = self._exchange.fetch_open_orders(symbol)
            self._logger.debug('■ open orders={}'.format(orders))
        except Exception as e:
            self._logger.error('■ open orders: exception={}'.format(e))
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
        order_id = 'kheir_' + str(round(time.time()))

        try:
            order = self._exchange.create_order(
                symbol=self._symbol, 
                type='limit', 
                side=side, 
                amount=size, 
                price=price, 
                params={
                        'execInst':'ParticipateDoNotInitiate',
                        'clOrdID':'{}_limit_{}'.format(order_id,side)
                    }
            )
            self._logger.debug('■ limit order={}'.format(order))
        except Exception as e:
            self._logger.error('■ limit order: exception={}'.format(e))
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
        order_id = 'kheir_' + str(round(time.time()))

        try:
            order = self._exchange.create_order(
                symbol=self._symbol, 
                type='market', 
                side=side, 
                amount=size,
                params={
                        'clOrdID':'{}_market_{}'.format(order_id,side)
                    }
            )
            self._logger.debug('■ market order={}'.format(order))
        except Exception as e:
            self._logger.error('■ market order: exception={}'.format(e))
            order = None

        return order

    # ==========================================================
    # 決済注文（limit）
    #   param:
    #       side: buy or sell
    #       price: 価格
    #       size: orderロット数
    #   return:
    #       order
    # ==========================================================
    def limit_settle_order(self, side, price, size):

        order = None

        # 注文に設定する「clOrdID」のID情報を作成・取得
        order_id = 'kheir_' + str(round(time.time()))

        try:
            order = self._exchange.create_order(
                symbol=self._symbol, 
                type='limit', 
                side=side, 
                amount=size, 
                price=price,
                params={
                        'execInst':'ReduceOnly,ParticipateDoNotInitiate',
                        'clOrdID':'{}_limit_settle_{}'.format(order_id,side)
                    }
            )
            self._logger.debug('■ limit settle order={}'.format(order))
        except Exception as e:
            self._logger.error('■ limit settle order: exception={}'.format(e))
            order = None

        return order

    # ==========================================================
    # 決済注文（market）
    #   param:
    #       side: buy or sell
    #       size: orderロット数
    #   return:
    #       order
    # ==========================================================
    def market_settle_order(self, side, size):

        order = None

        # 注文に設定する「clOrdID」のID情報を作成・取得
        order_id = 'kheir_' + str(round(time.time()))

        try:
            order = self._exchange.create_order(
                symbol=self._symbol, 
                type='market', 
                side=side, 
                amount=size, 
                params={
                        'execInst':'ReduceOnly',
                        'clOrdID':'{}_market_settle_{}'.format(order_id,side)
                    }
            )
            self._logger.debug('■ market settle order={}'.format(order))
        except Exception as e:
            self._logger.error('■ market settle order: exception={}'.format(e))
            order = None

        return order

    # ==========================================================
    # 注文更新
    #   param:
    #       options: order情報 (注意：数量を変える場合はorderQtyではなく、leavesQty を使う)
    #           orderID, price, leavesQty
    #   return:
    #       order
    # ==========================================================
    def amend_order(self, **options):

        order = None

        try:
            order = self._exchange.privatePutOrder(options)
            self._logger.debug('■ amend order={}'.format(order))
        except Exception as e:
            self._logger.error('■ amend order: exception={}'.format(e))
            order = None
        
        return order

    # ==========================================================
    # 注文キャンセル
    #   param:
    #       options: order情報 (orderID or clOrdID)
    #   return:
    #       order
    # ==========================================================
    def cancel_order(self, **options):

        orders = None

        try:
            orders = self._exchange.privateDeleteOrder(options)
            self._logger.debug('■ cancel orders={}'.format(orders))
        except Exception as e:
            self._logger.error('■ cancel orders: exception={}'.format(e))
            orders = None

        return orders

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
            orders = self._exchange.privateDeleteOrderAll(options)
            self._logger.debug('■ cancel orders={}'.format(orders))
        except Exception as e:
            self._logger.error('■ cancel orders: exception={}'.format(e))
            orders = None

        return orders

    # ==========================================================
    # bulk order 処理
    #       params: order情報
    #   return:
    #       order (注文結果のリスト、失敗の場合はNoneが戻される)
    # ==========================================================
    def bulk_order(self, params):

        # BulkOrder発行
        orders = None

        try:
            orders = self._exchange.privatePostOrderBulk({ 'orders': json.dumps(params) })
            self._logger.debug('■ bulk orders={}'.format(orders))
        except Exception as e:
            self._logger.error('■ bulk orders: exception={}'.format(e))
            orders = None

        return orders

    # ======================================
    # balance
    # ======================================
    def balance(self):
        return self._exchange.fetch_balance()

    # ======================================
    # position
    # ======================================
    def position(self):
        position = self._exchange.private_get_position()
        return position[0] if position is not None else None

    # ======================================
    # ticker
    # ======================================
    def ticker(self, symbol=_symbol):
        return self._exchange.fetch_ticker(
                symbol=symbol   # シンボル
            )

    # ======================================
    # 板情報取得
    # ======================================
    def orderbook(self, symbol=_symbol, limit=100):
        return self._exchange.fetch_order_book(
                symbol=symbol,  # シンボル
                limit=limit     # 取得件数(未指定:100、MAX:500)
            )

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
    def ohlcv(self, symbol=_symbol, timeframe='1m', since=None, limit=None, params={}):
        # timeframe1期間あたりの秒数
        period = {'1m': 1 * 60, '5m': 5 * 60, '1h': 60 * 60, '1d': 24 * 60 * 60}
    
        if timeframe not in period.keys():
            return None
    
        # 未確定の最新時間足のtimestampを取得(ミリ秒)
        now = datetime.utcnow()
        unixtime = calendar.timegm(now.utctimetuple())
        current_timestamp = (unixtime - (unixtime % period[timeframe]) + period[timeframe]) * 1000

        # for DEBUG
        # print('current_timestamp={} : {}'.format(current_timestamp, datetime.fromtimestamp(current_timestamp / 1000)))
    
        # partialフラグ
        is_partial = True
        if 'partial' in params.keys():
            is_partial = params['partial']
    
        # reverseフラグ
        is_reverse = False
        if 'reverse' in params.keys():
            is_reverse = params['reverse']
    
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
                symbol=symbol, 
                timeframe=timeframe, 
                since=since, 
                limit=count, 
                params=params
            )

        # for DEBUG
        # print('ohlcvs={}'.format(datetime.fromtimestamp(ohlcvs[-1][0] / 1000)))
    
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