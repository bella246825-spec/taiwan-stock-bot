import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta

def get_latest_trade_date():
    today = datetime.now()
    for i in range(7):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return today.strftime("%Y%m%d")

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
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo", "token": ""}
    res = requests.get(url, params=params, timeout=15)
    data = res.json()
    df_info = pd.DataFrame(data["data"])[["stock_id", "stock_name", "industry_category"]]
    exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券",
               "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
    return df_info[~df_info["industry_category"].isin(exclude)]

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已儲存 {path}")

def fetch_institutional():
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
        print("❌ 三大法人資料抓取失敗")
        return

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

    save_json("data/institutional.
