from flask import Flask, render_template, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

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

def get_all_stocks():
    cached, found = cache_get("all_stocks")
    if found:
        return cached
    result = fetch_github_json("stocks.json")
    if not result.get("error"):
        cache_set("all_stocks", result)
    return result

def get_all_history():
    cached, found = cache_get("all_history")
    if found:
        return cached
    result = fetch_github_json("history.json")
    if not result.get("error"):
        cache_set("all_history", result)
    return result

def get_finmind_industry(stock_id):
    """用 FinMind 抓產業分類"""
    try:
        FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
        params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        res = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=15)
        data = res.json()
        if data["status"] == 200:
            df_info = pd.DataFrame(data["data"])
            match = df_info[df_info["stock_id"] == stock_id]
            if not match.empty:
                return match.iloc[0].get("industry_category", "N/A")
    except:
        pass
    return "N/A"

def get_stock_info(stock_id):
    cache_key = f"stock_{stock_id}"
    cached, found = cache_get(cache_key)
    if found:
        return cached
    try:
        # 從 GitHub 讀財務指標
        all_stocks = get_all_stocks()
        if isinstance(all_stocks, dict) and "error" not in all_stocks:
            stock_per = all_stocks.get(stock_id)
        else:
            stock_per = None

        if not stock_per:
            return {"error": f"查無股票代號 {stock_id}，請確認代號是否正確"}

        name = stock_per.get("name", "")
        pe_ratio = stock_per.get("pe_ratio", "N/A")
        pb_ratio = stock_per.get("pb_ratio", "N/A")
        dividend_yield = stock_per.get("dividend_yield", "N/A")
        fiscal_quarter = stock_per.get("fiscal_quarter", "N/A")
        close = stock_per.get("close", None)

        # 從 GitHub 讀歷史股價
        all_history = get_all_history()
        history = all_history.get(stock_id, {}) if isinstance(all_history, dict) else {}
        dates = history.get("dates", [])
        closes = history.get("closes", [])
        highs = history.get("highs", [])
        lows = history.get("lows", [])

        price = closes[-1] if closes else (float(close) if close and close != "N/A" else None)
        high = highs[-1] if highs else None
        low = lows[-1] if lows else None

        # 產業分類
        industry = get_finmind_industry(stock_id)

        result = {
            "name": name,
            "industry": industry,
            "description": f"{name} 股票代號為 {stock_id}，屬於台灣 {industry} 產業。最新財報季度：{fiscal_quarter}。",
            "price": price,
            "high": high,
            "low": low,
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "dividend_yield": dividend_yield,
            "fiscal_quarter": fiscal_quarter,
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
