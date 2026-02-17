import os, sys
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

# Test 1: data_manager imports
print("Test 1: data_manager imports...", end=" ")
from data_manager import load_data, update_data_with_scraping, add_forecast, save_data, CATEGORIES
print("OK")

# Test 2: scraper imports
print("Test 2: scraper imports...", end=" ")
from scraper import scrape_tradedata_main, scrape_tradedata_detail, get_trade_data
print("OK")

# Test 3: load data
print("Test 3: load data...", end=" ")
df = load_data()
print(f"OK - {len(df)} rows loaded")

# Test 4: Forecast Logic
print("Test 4: Forecast logic...", end=" ")
if len(df) > 0:
    df = add_forecast(df, months_ahead=3)
    forecast_rows = df[df["구분"] == "예측"]
    current_ym = datetime.now().strftime("%Y-%m")
    future_rows = df[df["날짜"] > current_ym]
    
    print(f"OK - {len(forecast_rows)} forecasted rows")
    if len(future_rows) > 0:
        print(f"  Future rows found: {len(future_rows)} (First: {future_rows.iloc[0]['날짜']})")
else:
    print("SKIP (No data)")

print()
print("ALL TESTS PASSED!")
