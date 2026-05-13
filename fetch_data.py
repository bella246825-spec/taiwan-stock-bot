import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

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
    exclude = ["ETF", "ETN", "受益證券", "存託憑證", "Index", "大盤", "所有證券", "上櫃ETF", "上櫃指數股票型基金(ETF)", "指數投資證券(ETN)", "創新板股票", "創新版股票"]
    return df_info[~df_info["industry_category"].isin(exclude)]

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已儲存 {path}")

def fetch_institutional():
    print("抓取三大法人資料...")
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
        print("三大法人資料抓取失敗")
        return
    df = pd.DataFrame(data["data"], columns=data["fields"])
    df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
    df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)
    df_info = get_stock_id_list()
    stock_only = df_info["stock_id"].tolist()
    df = df[df["證券代號"].isin(stock_only)]
    df["證券名稱"] = df["證券名稱"].str.strip()
    top10_buy = df.nlargest(10, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]].rename(columns={"三大法人買賣超股數": "三大法人合計"}).to_dict("records")
    top10_sell = df.nsmallest(10, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]].rename(columns={"三大法人買賣超股數": "三大法人合計"}).to_dict("records")
    save_json("data/institutional.json", {"buy": top10_buy, "sell": top10_sell, "date": date})

def fetch_industry():
    print("抓取產業分類資料...")
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
        print("產業資料抓取失敗")
        return
    df = pd.DataFrame(data["data"], columns=data["fields"])
    df = df[["證券代號", "證券名稱", "三大法人買賣超股數"]]
    df["三大法人買賣超股數"] = df["三大法人買賣超股數"].str.replace(",", "").astype(float)
    df_info = get_stock_id_list()
    df_merged = pd.merge(df, df_info, left_on="證券代號", right_on="stock_id", how="inner")
    df_merged["證券名稱"] = df_merged["證券名稱"].str.strip()
    result = {}
    for industry, group in df_merged.groupby("industry_category"):
        top5 = group.nlargest(5, "三大法人買賣超股數")[["證券名稱", "三大法人買賣超股數"]]
        result[industry] = [{"證券名稱": r["證券名稱"], "三大法人買賣超股數": r["三大法人買賣超股數"]} for _, r in top5.iterrows()]
    save_json("data/industry.json", result)

def fetch_weekly():
    print("抓取週彙總資料...")
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
        df["證券名稱"] = df["證券名稱"].str.strip()
        all_df.append(df)
        dates.append(date_str)
    if not all_df:
        print("週彙總資料抓取失敗")
        return
    combined = pd.concat(all_df)
    weekly = combined.groupby("證券名稱")["三大法人買賣超股數"].sum().reset_index()
    weekly.columns = ["股票名稱", "週合計買賣超"]
    top10_buy = weekly.nlargest(10, "週合計買賣超").to_dict("records")
    top10_sell = weekly.nsmallest(10, "週合計買賣超").to_dict("records")
    save_json("data/weekly.json", {"buy": top10_buy, "sell": top10_sell, "dates": dates})

if __name__ == "__main__":
    print("開始抓取資料...")
    fetch_institutional()
    fetch_industry()
    fetch_weekly()
    print("全部完成！")
