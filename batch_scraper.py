# batch_scraper.py

import json
import os
import time
from main import (
    scrape_page_data, scroll_until_no_more_content, 
    check_and_click_close_popup
)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import csv

def load_json_file(filename, key=None):
    """Load data from JSON file - handles both array and object formats"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # If it's a list, return it directly
            if isinstance(data, list):
                return data
            
            # If it's a dict and key is provided, return that key's value
            if isinstance(data, dict) and key:
                return data.get(key, [])
            
            # If it's a dict without key, try common keys
            if isinstance(data, dict):
                # Try common keys
                for common_key in ['cities', 'searches', 'keywords', 'data']:
                    if common_key in data:
                        return data[common_key]
                # If no common key found, return empty list
                return []
            
            return data
    except FileNotFoundError:
        print(f"Error: {filename} not found!")
        return []
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filename}: {e}")
        return []

def scrape_city_keyword(driver, city, keyword, base_url="https://www.justdial.com/"):
    """Scrape data for a specific city and keyword combination"""
    # Format city and keyword for URL (handle spaces, special chars)
    city_formatted = city.replace(' ', '-').replace('–', '-').replace('/', '-').lower()
    keyword_formatted = keyword.replace(' ', '-').lower()
    url = f"{base_url}{city_formatted}/{keyword_formatted}/"
    
    print(f"\n{'='*80}")
    print(f"Processing: {city.upper()} - {keyword.upper()}")
    print(f"URL: {url}")
    print(f"{'='*80}")
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # Handle popup
        try:
            maybe_later_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'maybelater'))
            )
            if maybe_later_button.is_displayed():
                maybe_later_button.click()
                print("Clicked 'Maybe Later' button.")
        except:
            pass
        
        # Scroll to load all content
        print("\nStarting to scroll and load all results...")
        scroll_until_no_more_content(driver, scroll_pause=2, max_no_content_scrolls=5)
        
        # Extract data
        print("\nExtracting data from all loaded results...")
        all_data = scrape_page_data(driver)
        
        return all_data
        
    except Exception as e:
        print(f"Error scraping {city} - {keyword}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def append_data_to_csv(data, city, keyword, output_dir='Scrapped', is_first_write=False):
    """Append scraped data to CSV file (one file per keyword, all cities combined)"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filename: keyword.csv (sanitize for filesystem)
    keyword_safe = keyword.replace(' ', '_').replace('/', '_').replace('-', '_').lower()
    filename = f"{keyword_safe}.csv"
    csv_path = os.path.join(output_dir, filename)
    
    if data:
        # Add city column to each record
        data_with_city = []
        for record in data:
            record_with_city = record.copy()
            record_with_city['City'] = city
            data_with_city.append(record_with_city)
        
        # Write mode: 'w' for first write (create new file), 'a' for append
        mode = 'w' if is_first_write else 'a'
        with open(csv_path, mode, newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Name', 'Address', 'Phone', 'City']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header only if it's the first write
            if is_first_write:
                writer.writeheader()
            
            writer.writerows(data_with_city)
        
        print(f"✓ Added {len(data)} records from {city} to {filename}")
        return len(data)
    else:
        print(f"⚠ No data to save for {city} - {keyword}")
        return 0

def main():
    """Main batch processing function"""
    print("="*80)
    print("JustDial Batch Scraper - All Cities & Keywords")
    print("="*80)
    
    # Load cities and keywords from JSON files
    cities = load_json_file('cities.json', key='cities')
    keywords = load_json_file('searchs.json', key='searches')
    
    if not cities:
        print("Error: No cities found in cities.json")
        print("Make sure the file has format: {\"cities\": [...]} or just [...]")
        return
    
    if not keywords:
        print("Error: No keywords found in searchs.json")
        print("Make sure the file has format: {\"searches\": [...]} or just [...]")
        return
    
    print(f"\nLoaded {len(cities)} cities and {len(keywords)} keywords")
    print(f"Total combinations: {len(cities) * len(keywords)}")
    
    # Show first few cities and keywords
    print(f"\nSample cities: {', '.join(cities[:5])}...")
    print(f"Keywords: {', '.join(keywords)}")
    
    # Ask for confirmation
    response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Cancelled.")
        return
    
    # Setup Chrome driver
    chrome_options = Options()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Statistics
    total_combinations = len(cities) * len(keywords)
    processed = 0
    total_records = 0
    failed = []
    successful = []
    
    try:
        # Process each keyword, and for each keyword process all cities
        for keyword_idx, keyword in enumerate(keywords, 1):
            print(f"\n{'#'*80}")
            print(f"# KEYWORD {keyword_idx}/{len(keywords)}: {keyword.upper()}")
            print(f"# Processing all cities for this keyword...")
            print(f"{'#'*80}")
            
            keyword_records = 0
            is_first_city = True
            
            for city_idx, city in enumerate(cities, 1):
                processed += 1
                print(f"\n[{processed}/{total_combinations}] Keyword: {keyword} | City: {city} ({city_idx}/{len(cities)})")
                
                # Scrape data
                data = scrape_city_keyword(driver, city, keyword)
                
                # Append data to keyword CSV file
                records_count = append_data_to_csv(data, city, keyword, is_first_write=is_first_city)
                total_records += records_count
                keyword_records += records_count
                
                if records_count > 0:
                    successful.append(f"{city} - {keyword} ({records_count} records)")
                    print(f"✓ Successfully scraped {records_count} records")
                else:
                    failed.append(f"{city} - {keyword}")
                    print(f"✗ No records found")
                
                # Mark that we've written at least once
                if is_first_city and records_count > 0:
                    is_first_city = False
                
                # Small delay between requests to avoid rate limiting
                if processed < total_combinations:  # Don't wait after last one
                    time.sleep(3)
            
            # Summary for this keyword
            keyword_safe = keyword.replace(' ', '_').replace('/', '_').replace('-', '_').lower()
            print(f"\n{'='*80}")
            print(f"Completed keyword '{keyword}'")
            print(f"Total records for {keyword}: {keyword_records}")
            print(f"Saved to: Scrapped/{keyword_safe}.csv")
            print(f"{'='*80}")
            
            # Extra delay after completing all cities for a keyword
            if keyword_idx < len(keywords):
                print(f"\nMoving to next keyword...")
                time.sleep(2)
        
        # Print summary
        print(f"\n{'='*80}")
        print("BATCH PROCESSING COMPLETED!")
        print(f"{'='*80}")
        print(f"Total combinations processed: {processed}")
        print(f"Total records extracted: {total_records}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        
        if successful:
            print(f"\nFirst 10 successful combinations:")
            for s in successful[:10]:
                print(f"  ✓ {s}")
        
        if failed:
            print(f"\nFailed combinations ({len(failed)}):")
            for f in failed[:20]:  # Show first 20
                print(f"  ✗ {f}")
            if len(failed) > 20:
                print(f"  ... and {len(failed) - 20} more")
        
        print(f"{'='*80}")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user.")
        print(f"Processed {processed}/{total_combinations} combinations")
        print(f"Total records extracted: {total_records}")
        
        # Calculate which keyword and city we were on
        if processed > 0:
            keyword_idx = (processed - 1) // len(cities)
            city_idx = (processed - 1) % len(cities)
            if keyword_idx < len(keywords) and city_idx < len(cities):
                print(f"\nLast processed: {keywords[keyword_idx]} - {cities[city_idx]}")
        
        print(f"\nTo resume, you can modify cities.json to start from where you left off.")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        print("\nBrowser closed.")

if __name__ == "__main__":
    main()

