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
    now = datetime.now()
    start = 0 if now.hour >= 15 else 1
    for i in range(start, 8):
        d = now - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return now.strftime("%Y%m%d")

def fetch_twse_institutional(date):
    url = f"https://www.twse.com.tw/fund/T86?response=json&date={date}&selectType=ALLBUT0999"
    try:
        res = requests.get(url, timeout=15, verify=False)
        data = res.json()
        if data.get("stat") == "OK":
            return data
    except:
        pass
    return None

def get_stock_id_list():
    cached, found = cache_get("stock_id_list")
    if found:
        return cached
    try:
        params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        res = requests.get(FINMIND_URL, params=params, timeout=15)
        data = res.json()
        df_info = pd.DataFrame(data["data"])[["stock_id", "stock_name", "industry_category"]]
        exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
                   "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
        result = df_info[~df_info["industry_category"].isin(exclude)]
        cache_set("stock_id_list", result)
        return result
    except:
        return pd.DataFrame(columns=["stock_id", "stock_name", "industry_category"])

def get_institutional_investors():
    cached, found = cache_get("institutional")
    if found:
        return cached
    try:
        date = get_latest_trade_date()
        data = fetch_twse_institutional(date)

        if not data:
            for i in range(1, 6):
                d = datetime.strptime(date, "%Y%m%d") - timedelta(days=i)
                if d.weekday() < 5:
                    data = fetch_twse_institutional(d.strftime("%Y%m%d"))
                    date = d.strftime("%Y%m%d")
                    if data:
                        break

        if not data:
            return {"error": "暫時無法取得資料，請稍後再試"}

        df = pd.DataFrame(data["data"], columns=data["fields"])
        df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
        df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)

        df_info = get_stock_id_list()
        stock_only = df_info["stock_id"].tolist()
        df = df[df["證券代號"].isin(stock_only)]

        top10_buy = df.nlargest(10, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]].rename(
            columns={"三大法人買賣超股數": "三大法人合計"}).to_dict("records")
        top10_sell = df.nsmallest(10, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]].rename(
            columns={"三大法人買賣超股數": "三大法人合計"}).to_dict("records")

        result = {"buy": top10_buy, "sell": top10_sell, "date": date}
        cache_set("institutional", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_industry_institutional():
    cached, found = cache_get("industry")
    if found:
        return cached
    try:
        date = get_latest_trade_date()
        data = fetch_twse_institutional(date)

        if not data:
            for i in range(1, 6):
                d = datetime.strptime(date, "%Y%m%d") - timedelta(days=i)
                if d.weekday() < 5:
                    data = fetch_twse_institutional(d.strftime("%Y%m%d"))
                    if data:
                        break

        if not data:
            return {"error": "暫時無法取得資料，請稍後再試"}

        df = pd.DataFrame(data["data"], columns=data["fields"])
        df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
        df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)

        df_info = get_stock_id_list()
        df_merged = pd.merge(df, df_info, left_on="證券代號", right_on="stock_id", how="inner")

        result = {}
        for industry, group in df_merged.groupby("industry_category"):
            top5 = group.nlargest(5, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]]
            result[industry] = [{"證券名稱": r["證券名稱"], "三大法人買賣超股數": r["三大法人買賣超股數"]} for _, r in top5.iterrows()]

        cache_set("industry", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_weekly_institutional():
    cached, found = cache_get("weekly")
    if found:
        return cached
    try:
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())

        df_info = get_stock_id_list()
        stock_only = df_info["stock_id"].tolist()

        all_df = []
        dates = []
        for i in range(5):
            d = monday + timedelta(days=i)
            if d > today or d.weekday() >= 5:
                continue
            date_str = d.strftime("%Y%m%d")
            data = fetch_twse_institutional(date_str)
            if not data:
                continue
            df = pd.DataFrame(data["data"], columns=data["fields"])
            df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
            df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)
            df = df[df["證券代號"].isin(stock_only)]
            all_df.append(df)
            dates.append(date_str)

        if not all_df:
            return {"error": "本週尚無資料"}

        combined = pd.concat(all_df)
        weekly = combined.groupby("證券名稱")["三大法人買賣超股數"].sum().reset_index()
        weekly.columns = ["股票名稱", "週合計買賣超"]

        top10_buy = weekly.nlargest(10, "週合計買賣超").to_dict("records")
        top10_sell = weekly.nsmallest(10, "週合計買賣超").to_dict("records")

        result = {"buy": top10_buy, "sell": top10_sell, "dates": dates}
        cache_set("weekly", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_stock_info(stock_id):
    cache_key = f"stock_{stock_id}"
    cached, found = cache_get(cache_key)
    if found:
        return cached
    try:
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

        date = get_latest_trade_date()
        price_url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date}&stockNo={stock_id}"
        price_res = requests.get(price_url, timeout=15, verify=False)
        price_data = price_res.json()

        price = None
        high = None
        low = None
        if price_data.get("stat") == "OK" and price_data.get("data"):
            latest = price_data["data"][-1]
            try:
                price = float(latest[6].replace(",", ""))
                high = float(latest[4].replace(",", ""))
                low = float(latest[5].replace(",", ""))
            except:
                pass

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
