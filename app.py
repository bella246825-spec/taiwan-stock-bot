from flask import Flask, render_template, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
import time
import twstock

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
        params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        res = requests.get(FINMIND_URL, params=params, timeout=15)
        data = res.json()

        if data["status"] != 200 or not data["data"]:
            return {"error": "查無此股票代號"}

        df_info = pd.DataFrame(data["data"])
        match = df_info[df_info["stock_id"] == stock_id]
        if match.empty:
            return {"error": f"查無股票代號 {stock_id}"}
        stock_info = match.iloc[0].to_dict()

        # 財務指標用證交所 OpenAPI
        per_res = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d", timeout=15)
        per_data = per_res.json()
        stock_per = next((d for d in per_data if d.get("Code") == stock_id), None)

        pe_ratio = stock_per.get("PEratio", "N/A") if stock_per else "N/A"
        pb_ratio = stock_per.get("PBratio", "N/A") if stock_per else "N/A"
        dividend_yield = stock_per.get("DividendYield", "N/A") if stock_per else "N/A"
        close_price = stock_per.get("ClosePrice", None) if stock_per else None

        # 歷史股價用 twstock
        stock_obj = twstock.Stock(stock_id)
        dates = [d.strftime("%Y-%m-%d") for d in stock_obj.date]
        closes = stock_obj.close
        highs = stock_obj.high
        lows = stock_obj.low

        price = closes[-1] if closes else None
        high = highs[-1] if highs else None
        low = lows[-1] if lows else None

        result = {
            "name": stock_info.get("stock_name", ""),
            "industry": stock_info.get("industry_category", ""),
            "description": f"{stock_info.get('stock_name', '')} 屬於台灣 {stock_info.get('industry_category', '')} 產業，股票代號為 {stock_id}。",
            "price": float(close_price) if close_price else price,
            "high": high,
            "low": low,
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "dividend_yield": dividend_yield,
            "history_dates": dates,
            "history_closes": closes,
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
