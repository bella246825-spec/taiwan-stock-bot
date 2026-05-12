from flask import Flask, render_template, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
import time
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
GITHUB_RAW = "https://raw.githubusercontent.com/bella246825-spec/taiwan-stock-bot/main/data"

_cache = {}
CACHE_TTL = 300

def cache_get(key):
    if key in _cache:
        value, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return value, True
    return None, False

def cache_set(key, value):
    _cache[key] = (value, time.time())

def fetch_github_json(filename):
    """從 GitHub 讀取 JSON 檔案"""
    try:
        res = requests.get(f"{GITHUB_RAW}/{filename}", timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

def get_institutional_investors():
    cached, found = cache_get("institutional")
    if found:
        return cached
    result = fetch_github_json("institutional.json")
    if not result.get("error"):
        cache_set("institutional", result)
    return result

def get_industry_institutional():
    cached, found = cache_get("industry")
    if found:
        return cached
    result = fetch_github_json("industry.json")
    if not result.get("error"):
        cache_set("industry", result)
    return result

def get_weekly_institutional():
    cached, found = cache_get("weekly")
    if found:
        return cached
    result = fetch_github_json("weekly.json")
    if not result.get("error"):
        cache_set("weekly", result)
    return result

def get_stock_info(stock_id):
    cache_key = f"stock_{stock_id}"
    cached, found = cache_get(cache_key)
    if found:
        return cached
    try:
        # 基本資料用 FinMind
        params = {
            "dataset": "TaiwanStockInfo",
            "stock_id": stock_id,
            "token": FINMIND_TOKEN
        }
        res = requests.get(FINMIND_URL, params=params, timeout=15)
        data = res.json()

        if data["status"] != 200 or not data["data"]:
            return {"error": "查無此股票代號"}

        stock_info = data["data"][0]

        # 股價用 FinMind
        today = datetime.now()
        start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        price_params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": FINMIND_TOKEN
        }
        price_res = requests.get(FINMIND_URL, params=price_params, timeout=15)
        price_data = price_res.json()

        price = None
        high = None
        low = None
        if price_data["status"] == 200 and price_data["data"]:
            latest = price_data["data"][-1]
            price = latest.get("close")
            high = latest.get("max")
            low = latest.get("min")

        result = {
            "name": stock_info.get("stock_name", ""),
            "industry": stock_info.get("industry_category", ""),
            "description": f"{stock_info.get('stock_name', '')} 屬於台灣 {stock_info.get('industry_category', '')} 產業，股票代號為 {stock_id}。",
            "price": price,
            "high": high,
            "low": low,
            "pe_ratio": "N/A",
            "pb_ratio": "N/A",
            "roe": "N/A",
            "roa": "N/A",
            "market_cap": "N/A",
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/institutional")
def api_institutional():
    return jsonify(get_institutional_investors())

@app.route("/api/industry")
def api_industry():
    return jsonify(get_industry_institutional())

@app.route("/api/weekly")
def api_weekly():
    return jsonify(get_weekly_institutional())

@app.route("/api/stock/<stock_id>")
def api_stock(stock_id):
    return jsonify(get_stock_info(stock_id))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
