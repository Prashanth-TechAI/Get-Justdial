# main.py

import time
import os
import csv
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from utils import check_and_click_close_popup, countdown_timer, smooth_scroll_to, human_like_scroll

def get_url_input():
    # Ask the user if they have a URL or need to enter city/keyword
    print("Select an option:")
    print("1. Provide a URL")
    print("2. Enter City/Keyword")
    choice = input("Enter the number of your choice (1 or 2): ").strip()

    if choice == '1':
        url = input("Enter the URL: ").strip()
    elif choice == '2':
        city = input("Enter the city name: ").replace(' ', '-')
        keyword = input("Enter the search keyword: ").replace(' ', '-')
        base_url = "https://www.justdial.com/"
        url = f"{base_url}{city}/{keyword}/"
    else:
        print("Invalid choice. Exiting.")
        exit()

    return url

def get_url_from_file(filename):
    # Read the URL from the specified file
    try:
        with open(filename, 'r') as file:
            url = file.readline().strip()
            if url:
                return url
            else:
                print(f"The file '{filename}' is empty. Exiting.")
                exit()
    except FileNotFoundError:
        print(f"The file '{filename}' does not exist. Exiting.")
        exit()

def scrape_page_data(driver):
    """Extract data from the current page"""
    data = []
    parent_divs = driver.find_elements(By.CLASS_NAME, 'resultbox_info')
    
    if not parent_divs:
        print("No parent divs found on this page.")
        return data
    
    for index, parent_div in enumerate(parent_divs):
        try:
            name = "N/A"
            phone_number = ""
            address = "N/A"
            
            # Extract name
            try:
                name_div = parent_div.find_element(By.CLASS_NAME, 'resultbox_title_anchor')
                name = name_div.text.strip()
            except:
                pass
            
            # Extract phone number (may be empty or "Show Number")
            try:
                phone_div = parent_div.find_element(By.CLASS_NAME, 'callcontent')
                phone_number = phone_div.text.strip()
            except:
                phone_number = ""
            
            # Extract address
            try:
                address_div = parent_div.find_element(By.CLASS_NAME, 'resultbox_address')
                address = address_div.text.strip()
            except:
                pass
            
            # Save record even if phone is missing (as long as name exists)
            if name and name != "N/A":
                data.append({'Name': name, 'Address': address, 'Phone': phone_number})
            else:
                print(f"Skipping parent div {index}: No name found")

        except Exception as e:
            print(f"Error extracting data from listing {index}: {str(e)}")
            continue
    
    return data


def scroll_until_no_more_content(driver, scroll_pause=2, max_no_content_scrolls=5):
    """Scroll until no more new content loads (infinite scroll)"""
    print("Starting infinite scroll to load all results...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    no_new_content_count = 0
    scroll_count = 0
    
    while no_new_content_count < max_no_content_scrolls:
        # Scroll down
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        scroll_count += 1
        
        # Wait for content to load
        time.sleep(scroll_pause)
        
        # Check for popups
        check_and_click_close_popup(driver)
        
        # Check if new content loaded
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height != last_height:
            print(f"Scroll {scroll_count}: New content detected (height: {new_height}px). Continuing...")
            last_height = new_height
            no_new_content_count = 0  # Reset counter when new content loads
        else:
            no_new_content_count += 1
            print(f"Scroll {scroll_count}: No new content ({no_new_content_count}/{max_no_content_scrolls})")
        
        # Also check if we've reached the bottom
        current_position = driver.execute_script("return window.pageYOffset + window.innerHeight")
        if current_position >= new_height - 10:  # Near bottom
            if no_new_content_count >= 2:
                print("Reached bottom with no new content. Stopping scroll.")
                break
    
    # Final scroll to bottom to ensure all content is loaded
    print("Final scroll to bottom...")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    
    # Scroll back to top for data extraction
    print("Scrolling back to top...")
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)
    
    final_height = driver.execute_script("return document.body.scrollHeight")
    print(f"Scrolling completed. Total page height: {final_height}px")
    print(f"Total scrolls performed: {scroll_count}")

def run_single_scrape(city: str, keyword: str) -> str:
    """
    Programmatic entrypoint for scraping one city + one keyword.
    Returns the path to the generated CSV file.
    """
    # Build JustDial URL from city + keyword
    base_url = "https://www.justdial.com/"
    city_formatted = city.replace(" ", "-").replace("–", "-").replace("/", "-").lower()
    keyword_formatted = keyword.replace(" ", "-").lower()
    url = f"{base_url}{city_formatted}/{keyword_formatted}/"

    # Set up Chrome options (same as in __main__ block)
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

    # Ensure output folder exists
    os.makedirs("Scrapped", exist_ok=True)
    csv_filename = os.path.join("Scrapped", f"{city_formatted}_{keyword_formatted}.csv")

    try:
        driver.get(url)
        print("Opened URL:", url)

        # Handle 'Maybe Later' popup if present
        time.sleep(5)
        try:
            maybe_later_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "maybelater"))
            )
            if maybe_later_button.is_displayed():
                maybe_later_button.click()
                print("Clicked 'Maybe Later' button.")
        except Exception:
            pass

        # Scroll and load all results
        print("\nStarting to scroll and load all results...")
        scroll_until_no_more_content(driver, scroll_pause=2, max_no_content_scrolls=5)

        # Extract data
        print("\nExtracting data from all loaded results...")
        all_data = scrape_page_data(driver)

        if all_data:
            with open(csv_filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Name", "Address", "Phone"])
                writer.writeheader()
                writer.writerows(all_data)
            print(f"Saved {len(all_data)} records to {csv_filename}")
        else:
            print("No data extracted; CSV will be empty or not created.")

        return csv_filename
    finally:
        driver.quit()

# Main execution - only runs when script is executed directly, not when imported
if __name__ == "__main__":
    # Get the URL from temp_url.txt if it exists
    if os.path.exists('temp_url.txt'):
        url = get_url_from_file('temp_url.txt')
    else:
        # Use the original URL fetching method if temp_url.txt does not exist
        url = get_url_input()

    # Set up Chrome options
    chrome_options = Options()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    # Set up WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Hide WebDriver signature
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # Ensure the 'Scrapped' folder exists
    os.makedirs('Scrapped', exist_ok=True)

    # Get CSV filename
    csv_filename = os.path.join('Scrapped', f"{url.split('/')[-2]}.csv")

    # Initialize CSV file with header
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Name', 'Address', 'Phone']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

    try:
        driver.get(url)
        print("Opened URL:", url)
        print(f"\n{'='*60}")
        print("JustDial Infinite Scroll Scraper")
        print(f"{'='*60}")

        # Check for 'Maybe Later' popup and click it if found
        time.sleep(5)
        try:
            maybe_later_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'maybelater'))
            )
            if maybe_later_button.is_displayed():
                maybe_later_button.click()
                print("Clicked 'Maybe Later' button.")
        except Exception as e:
            print(f"Maybe Later popup not found or failed to click: {str(e)}")

        # Scroll until all content is loaded (infinite scroll)
        print("\nStarting to scroll and load all results...")
        scroll_until_no_more_content(driver, scroll_pause=2, max_no_content_scrolls=5)
        
        # Extract all data from the page
        print("\nExtracting data from all loaded results...")
        all_data = scrape_page_data(driver)
        
        if all_data:
            # Save all data to CSV
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['Name', 'Address', 'Phone'])
                writer.writeheader()
                writer.writerows(all_data)
            
            total_records = len(all_data)
            print(f"\n{'='*60}")
            print(f"Scraping completed!")
            print(f"Total records extracted: {total_records}")
            print(f"Data saved to: {csv_filename}")
            print(f"{'='*60}")
        else:
            print(f"\n{'='*60}")
            print("⚠ No data found on the page.")
            print("Please check:")
            print("1. The URL is correct")
            print("2. The page structure hasn't changed")
            print("3. You have internet connection")
            print(f"{'='*60}")

    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Print script completion message
        print("\nScript execution completed.")
        
        # Wait for 3 seconds
        time.sleep(3)
        
        # Remove page_source.html and stop.txt files
        if os.path.exists('page_source.html'):
            os.remove('page_source.html')
        if os.path.exists('stop.txt'):
            os.remove('stop.txt')
        if os.path.exists('error_log.txt'):
            os.remove('error_log.txt')
        print("Deleted Logs")
        
        driver.quit()
        
