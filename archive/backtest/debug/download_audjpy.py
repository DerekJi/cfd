"""Download AUD_JPY data in batches"""
import sys
import os

# Fix Windows encoding
import codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.data_fetcher import OANDADataFetcher
from oanda_config import OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENVIRONMENT
import pandas as pd
from datetime import datetime, timedelta
import time

def main():
    print("Downloading AUD_JPY data (batch mode)...")
    
    fetcher = OANDADataFetcher(
        api_key=OANDA_API_KEY,
        account_id=OANDA_ACCOUNT_ID,
        environment=OANDA_ENVIRONMENT
    )
    
    # Download in 7-day batches
    start = datetime(2025, 2, 2)
    end = datetime(2026, 2, 11)
    
    all_data = []
    current = start
    batch = 1
    
    while current < end:
        next_date = min(current + timedelta(days=7), end)
        
        print(f"\nBatch {batch}: {current.strftime('%Y-%m-%d')} to {next_date.strftime('%Y-%m-%d')}")
        
        try:
            df = fetcher.fetch_candles(
                instrument='AUD_JPY',
                granularity='M5',
                start_date=current.strftime('%Y-%m-%d'),
                end_date=next_date.strftime('%Y-%m-%d')
            )
            
            if df is not None and not df.empty:
                all_data.append(df)
                print(f"  OK: {len(df)} candles")
            else:
                print(f"  SKIP: No data")
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ERROR: {e}")
        
        current = next_date
        batch += 1
    
    if not all_data:
        print("\nFAILED: No data downloaded")
        return 1
    
    # Merge all data
    print(f"\nMerging {len(all_data)} batches...")
    final_df = pd.concat(all_data, ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['datetime'])
    final_df = final_df.sort_values('datetime')
    
    # Save
    output_file = 'data/AUD_JPY_M5.csv'
    os.makedirs('data', exist_ok=True)
    final_df.to_csv(output_file, index=False)
    
    print(f"\nSUCCESS! Saved to: {output_file}")
    print(f"  Time range: {final_df['datetime'].min()} to {final_df['datetime'].max()}")
    print(f"  Total candles: {len(final_df)}")
    
    return 0

if __name__ == '__main__':
    exit(main())
