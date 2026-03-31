from flask import Flask, render_template, jsonify, request
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

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

        return {"buy": top10_buy, "sell": top10_sell}
    except Exception as e:
        return {"error": str(e)}

def get_industry_institutional():
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

        url2 = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockInfo", "token": ""}
        res2 = requests.get(url2, params=params)
        data2 = res2.json()
        df_info = pd.DataFrame(data2["data"])[["stock_id", "industry_category"]]

        df_merged = pd.merge(df_fund, df_info, left_on="證券代號", right_on="stock_id", how="left")

        exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
                   "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
        df_merged = df_merged[~df_merged["industry_category"].isin(exclude)]
        df_merged = df_merged.dropna(subset=["industry_category"])

        result = {}
        for industry, group in df_merged.groupby("industry_category"):
            top5 = group.nlargest(5, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]]
            result[industry] = top5.to_dict("records")

        return result
    except Exception as e:
        return {"error": str(e)}

def get_stock_info(stock_id):
    try:
        ticker = yf.Ticker(f"{stock_id}.TW")
        info = ticker.info
        fast = ticker.fast_info
        return {
            "name": info.get("longName", ""),
            "industry": info.get("industry", ""),
            "description": info.get("longBusinessSummary", "暫無資料"),
            "price": fast.last_price,
            "pe_ratio": info.get("trailingPE", "N/A"),
            "pb_ratio": info.get("priceToBook", "N/A"),
            "roe": info.get("returnOnEquity", "N/A"),
            "roa": info.get("returnOnAssets", "N/A"),
            "revenue_growth": info.get("revenueGrowth", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
        }
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

@app.route("/api/stock/<stock_id>")
def api_stock(stock_id):
    return jsonify(get_stock_info(stock_id))

if __name__ == "__main__":
    app.run(debug=True)
