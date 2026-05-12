from flask import Flask, render_template, jsonify
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

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

def get_latest_trade_date():
    """取得最近的交易日"""
    today = datetime.now()
    # 如果是週末往回找
    for i in range(7):
        d = today - timedelta(days=i)
        if d.weekday() < 5:  # 週一到週五
            return d.strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d")

def get_prev_trade_date():
    """取得前一個交易日"""
    today = datetime.now()
    for i in range(1, 8):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime("%Y-%m-%d")
    return (today - timedelta(days=1)).strftime("%Y-%m-%d")

def get_institutional_investors():
    """取得三大法人買賣超前十名"""
    cached, found = cache_get("institutional")
    if found:
        return cached
    try:
        # 盤中用前一日，盤後用當日
        now = datetime.now()
        if now.hour < 15:
            date = get_prev_trade_date()
        else:
            date = get_latest_trade_date()

        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "start_date": date,
            "end_date": date,
            "token": FINMIND_TOKEN
        }
        res = requests.get(FINMIND_URL, params=params, timeout=15)
        data = res.json()

        if data["status"] != 200 or not data["data"]:
            # 嘗試前一日
            date = get_prev_trade_date()
            params["start_date"] = date
            params["end_date"] = date
            res = requests.get(FINMIND_URL, params=params, timeout=15)
            data = res.json()

        if data["status"] != 200 or not data["data"]:
            return {"error": f"資料取得失敗：{data.get('msg', '未知錯誤')}"}

        df = pd.DataFrame(data["data"])

        # 三大法人合計
        df_total = df.groupby("stock_id").agg(
            買超=("buy", "sum"),
            賣超=("sell", "sum"),
            股票名稱=("stock_id", "first")
        ).reset_index()

        # 抓股票名稱
        info_params = {
            "dataset": "TaiwanStockInfo",
            "token": FINMIND_TOKEN
        }
        info_res = requests.get(FINMIND_URL, params=info_params, timeout=15)
        info_data = info_res.json()
        df_info = pd.DataFrame(info_data["data"])[["stock_id", "stock_name", "industry_category"]]

        # 過濾ETF
        exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
                   "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
        df_info = df_info[~df_info["industry_category"].isin(exclude)]

        df_total = pd.merge(df_total, df_info, left_on="stock_id", right_on="stock_id", how="inner")
        df_total["合計"] = df_total["買超"] - df_total["賣超"]

        top10_buy = df_total.nlargest(10, "合計")[["stock_name", "合計"]].rename(
            columns={"stock_name": "股票名稱", "合計": "三大法人合計"}).to_dict("records")
        top10_sell = df_total.nsmallest(10, "合計")[["stock_name", "合計"]].rename(
            columns={"stock_name": "股票名稱", "合計": "三大法人合計"}).to_dict("records")

        result = {"buy": top10_buy, "sell": top10_sell, "date": date}
        cache_set("institutional", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_industry_institutional():
    """取得各產業三大法人前五名"""
    cached, found = cache_get("industry")
    if found:
        return cached
    try:
        now = datetime.now()
        if now.hour < 15:
            date = get_prev_trade_date()
        else:
            date = get_latest_trade_date()

        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "start_date": date,
            "end_date": date,
            "token": FINMIND_TOKEN
        }
        res = requests.get(FINMIND_URL, params=params, timeout=15)
        data = res.json()

        if data["status"] != 200 or not data["data"]:
            date = get_prev_trade_date()
            params["start_date"] = date
            params["end_date"] = date
            res = requests.get(FINMIND_URL, params=params, timeout=15)
            data = res.json()

        if data["status"] != 200 or not data["data"]:
            return {"error": "資料取得失敗"}

        df = pd.DataFrame(data["data"])
        df_total = df.groupby("stock_id").agg(
            買超=("buy", "sum"),
            賣超=("sell", "sum")
        ).reset_index()
        df_total["合計"] = df_total["買超"] - df_total["賣超"]

        info_params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        info_res = requests.get(FINMIND_URL, params=info_params, timeout=15)
        info_data = info_res.json()
        df_info = pd.DataFrame(info_data["data"])[["stock_id", "stock_name", "industry_category"]]

        exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
                   "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
        df_info = df_info[~df_info["industry_category"].isin(exclude)]

        df_merged = pd.merge(df_total, df_info, on="stock_id", how="inner")

        result = {}
        for industry, group in df_merged.groupby("industry_category"):
            top5 = group.nlargest(5, "合計")[["stock_name", "合計"]]
            result[industry] = [{"證券名稱": r["stock_name"], "三大法人買賣超股數": r["合計"]} for _, r in top5.iterrows()]

        cache_set("industry", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_weekly_institutional():
    """取得本週三大法人買賣超彙總"""
    cached, found = cache_get("weekly")
    if found:
        return cached
    try:
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        start_date = monday.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "start_date": start_date,
            "end_date": end_date,
            "token": FINMIND_TOKEN
        }
        res = requests.get(FINMIND_URL, params=params, timeout=20)
        data = res.json()

        if data["status"] != 200 or not data["data"]:
            return {"error": "本週尚無資料"}

        df = pd.DataFrame(data["data"])

        info_params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        info_res = requests.get(FINMIND_URL, params=info_params, timeout=15)
        info_data = info_res.json()
        df_info = pd.DataFrame(info_data["data"])[["stock_id", "stock_name", "industry_category"]]

        exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
                   "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
        df_info = df_info[~df_info["industry_category"].isin(exclude)]
        stock_only = df_info["stock_id"].tolist()

        df = df[df["stock_id"].isin(stock_only)]
        df_total = df.groupby("stock_id").agg(
            買超=("buy", "sum"),
            賣超=("sell", "sum")
        ).reset_index()
        df_total["週合計"] = df_total["買超"] - df_total["賣超"]

        df_total = pd.merge(df_total, df_info[["stock_id", "stock_name"]], on="stock_id", how="inner")

        dates = []
        for i in range(5):
            d = monday + timedelta(days=i)
            if d <= today and d.weekday() < 5:
                dates.append(d.strftime("%Y%m%d"))

        top10_buy = df_total.nlargest(10, "週合計")[["stock_name", "週合計"]].rename(
            columns={"stock_name": "股票名稱", "週合計": "週合計買賣超"}).to_dict("records")
        top10_sell = df_total.nsmallest(10, "週合計")[["stock_name", "週合計"]].rename(
            columns={"stock_name": "股票名稱", "週合計": "週合計買賣超"}).to_dict("records")

        result = {"buy": top10_buy, "sell": top10_sell, "dates": dates}
        cache_set("weekly", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_stock_info(stock_id):
    """取得個股詳細資料"""
    cache_key = f"stock_{stock_id}"
    cached, found = cache_get(cache_key)
    if found:
        return cached
    try:
        # 基本資料
        info_params = {
            "dataset": "TaiwanStockInfo",
            "stock_id": stock_id,
            "token": FINMIND_TOKEN
        }
        info_res = requests.get(FINMIND_URL, params=info_params, timeout=15)
        info_data = info_res.json()

        if info_data["status"] != 200 or not info_data["data"]:
            return {"error": "查無此股票代號"}

        stock_info = info_data["data"][0]

        # 最新股價
        date = get_latest_trade_date()
        price_params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": date,
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

        # 財務資料
        fin_params = {
            "dataset": "TaiwanStockFinancialStatements",
            "data_id": stock_id,
            "start_date": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            "token": FINMIND_TOKEN
        }
        fin_res = requests.get(FINMIND_URL, params=fin_params, timeout=15)
        fin_data = fin_res.json()

        pe_ratio = "N/A"
        pb_ratio = "N/A"
        roe = "N/A"
        roa = "N/A"

        if fin_data["status"] == 200 and fin_data["data"]:
            df_fin = pd.DataFrame(fin_data["data"])
            if "per" in df_fin.columns:
                pe_ratio = df_fin["per"].dropna().iloc[-1] if not df_fin["per"].dropna().empty else "N/A"
            if "pbr" in df_fin.columns:
                pb_ratio = df_fin["pbr"].dropna().iloc[-1] if not df_fin["pbr"].dropna().empty else "N/A"

        result = {
            "name": stock_info.get("stock_name", ""),
            "industry": stock_info.get("industry_category", ""),
            "description": f"{stock_info.get('stock_name', '')} 屬於 {stock_info.get('industry_category', '')} 產業，股票代號為 {stock_id}。",
            "price": price,
            "high": high,
            "low": low,
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "roe": roe,
            "roa": roa,
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
