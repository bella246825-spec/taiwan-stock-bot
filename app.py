from flask import Flask, render_template, jsonify, request
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3
import os
import time
from deep_translator import GoogleTranslator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

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

def get_stock_id_list():
    cached, found = cache_get("stock_id_list")
    if found:
        return cached
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo", "token": ""}
    res = requests.get(url, params=params)
    data = res.json()
    df_info = pd.DataFrame(data["data"])[["stock_id", "industry_category"]]
    exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
               "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
    result = df_info[~df_info["industry_category"].isin(exclude)]
    cache_set("stock_id_list", result)
    return result

def get_stock_price(stock_id):
    try:
        ticker = yf.Ticker(f"{stock_id}.TW")
        info = ticker.fast_info
        return {
            "price": info.last_price,
            "high": info.day_high,
            "low": info.day_low,
        }
    except Exception as e:
        return {"error": str(e)}

def get_institutional_investors():
    cached, found = cache_get("institutional")
    if found:
        return cached
    try:
        today = datetime.now().strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={today}&selectType=ALLBUT0999&response=json"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        data = res.json()

        if data.get("stat") != "OK":
            return {"error": "資料尚未更新，請於收盤後 17:00 後再試"}

        df = pd.DataFrame(data["data"], columns=data["fields"])
        df = df[["證券名稱", "外陸資買賣超股數(不含外資自營商)", "投信買賣超股數", "自營商買賣超股數", "三大法人買賣超股數"]]
        df.columns = ["股票名稱", "外資", "投信", "自營商", "三大法人合計"]

        for col in ["外資", "投信", "自營商", "三大法人合計"]:
            df[col] = df[col].str.replace(",", "").astype(float)

        top10_buy = df.nlargest(10, "三大法人合計")[["股票名稱", "三大法人合計"]].to_dict("records")
        top10_sell = df.nsmallest(10, "三大法人合計")[["股票名稱", "三大法人合計"]].to_dict("records")

        result = {"buy": top10_buy, "sell": top10_sell}
        cache_set("institutional", result)
        return result
    except Exception as e:
        return {"error": str(e)}

def get_industry_institutional():
    cached, found = cache_get("industry")
    if found:
        return cached
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={yesterday}&selectType=ALLBUT0999&response=json"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10, verify=False)
        data = res.json()

        if data.get("stat") != "OK":
            return {"error": "資料尚未更新"}

        df_fund = pd.DataFrame(data["data"], columns=data["fields"])
        df_fund = df_fund[["證券代號", "證券名稱", "三大法人買賣超股數"]]
        df_fund["三大法人買賣超股數"] = df_fund["三大法人買賣超股數"].str.replace(",", "").astype(float)

        df_info = get_stock_id_list()
        df_merged = pd.merge(df_fund, df_info, left_on="證券代號", right_on="stock_id", how="left")
        df_merged = df_merged.dropna(subset=["industry_category"])

        result = {}
        for industry, group in df_merged.groupby("industry_category"):
            top5 = group.nlargest(5, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]]
            result[industry] = top5.to_dict("records")

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
        dates = []
        for i in range(5):
            d = monday + timedelta(days=i)
            if d <= today:
                dates.append(d.strftime("%Y%m%d"))

        df_info = get_stock_id_list()
        stock_only = df_info["stock_id"].tolist()

        all_df = []
        for date in dates:
            url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALLBUT0999&response=json"
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=10, verify=False)
            data = res.json()
            if data.get("stat") != "OK":
                continue
            df = pd.DataFrame(data["data"], columns=data["fields"])
            df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
            df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)
            df = df[df["證券代號"].isin(stock_only)]
            all_df.append(df)

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
        time.sleep(1)
        ticker = yf.Ticker(f"{stock_id}.TW")
        info = ticker.info
        fast = ticker.fast_info

        description_en = info.get("longBusinessSummary", "")
        description_zh = "暫無簡介資料"
        if description_en:
            try:
                description_zh = GoogleTranslator(source="en", target="zh-TW").translate(description_en)
            except:
                description_zh = description_en

        result = {
            "name": info.get("longName", ""),
            "industry": info.get("industry", ""),
            "description": description_zh,
            "price": fast.last_price,
            "pe_ratio": info.get("trailingPE", "N/A"),
            "pb_ratio": info.get("priceToBook", "N/A"),
            "roe": info.get("returnOnEquity", "N/A"),
            "roa": info.get("returnOnAssets", "N/A"),
            "revenue_growth": info.get("revenueGrowth", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/price/<stock_id>")
def api_price(stock_id):
    return jsonify(get_stock_price(stock_id))

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
