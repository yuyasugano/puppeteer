# -*- coding: utf-8 -*-
# ==========================================
# Discord
# ==========================================
import requests

# ==========================================
# Discord クラス
#   param:
#       URL: discord webhook url
# ==========================================
class Discord:
    _discord_webhook_url = ''   # discord通知用URL

    # ======================================
    # 初期化
    #   param:
    #       URL: discord webhook url
    # ======================================
    def __init__(self, discord_webhook_url):
        # ----------------------------------
        # discord webhook url設定
        # ----------------------------------
        self._discord_webhook_url = discord_webhook_url

    # ======================================
    # 通知
    #   param:
    #       message: 通知メッセージ
    # ======================================
    def send(self, message):
        if '' != self._discord_webhook_url:
            requests.post(self._discord_webhook_url, data={"content": " " + message + " "})

"""
例：
message += 'BTC\r'
message += '10 BTC'

send(message)

"""