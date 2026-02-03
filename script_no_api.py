"""
Google Maps Scraper (Phone Extraction Version)
Clicks into each business to extract phone numbers.
"""

import os
import time
import json
import random
import re
import pandas as pd
import logging
from datetime import datetime

# Try undetected_chromedriver first, fallback to regular selenium
try:
    import undetected_chromedriver as uc
    USE_UNDETECTED = True
except ImportError:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    USE_UNDETECTED = False

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

import argparse

# Parse arguments first to set up paths
parser = argparse.ArgumentParser()
parser.add_argument("--owner_id", type=str, default=None, help="Owner ID for isolation")
parser.add_argument("--log_file", type=str, default="log_no_api.log", help="Path to log file")
parser.add_argument("--output_dir", type=str, default=".", help="Directory for results")
args, _ = parser.parse_known_args()

# --- Configuration ---
LOG_FILE = args.log_file
OUTPUT_DIR = args.output_dir
MAX_SCROLL_ATTEMPTS = 25
SCROLL_PAUSE_MIN = 1.0
SCROLL_PAUSE_MAX = 2.5
CLICK_PAUSE_MIN = 1.5
CLICK_PAUSE_MAX = 3.0

# Stable XPath selectors
SELECTORS = {
    "feed": "//div[@role='feed']",
    "place_link": "//a[contains(@href, '/maps/place/')]",
    "back_button": "//button[@aria-label='Back']",
    # Phone selectors (multiple fallbacks)
    "phone_button": "//button[contains(@aria-label, 'Phone:') or contains(@data-tooltip, 'Copy phone number')]",
    "phone_link": "//a[starts-with(@href, 'tel:')]",
    "phone_text": "//*[contains(text(), '+62') or contains(text(), '021') or contains(text(), '08')]",
}

# Phone regex patterns for Indonesia
PHONE_PATTERNS = [
    r'\+62[\d\s\-]{9,15}',
    r'62[\d\s\-]{9,15}',
    r'0[8|2|3|7][\d\s\-]{8,13}',
]

# Setup Logging
def setup_logging():
    logger = logging.getLogger("maps_scraper")
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Ensure directory exists for log file
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

def load_config():
    try:
        with open("env_parameters.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Config file not found.")
        return {}

def init_driver(headless=False):
    """Initialize browser with stealth options"""
    
    if USE_UNDETECTED:
        logger.info("Using undetected-chromedriver for stealth...")
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=id-ID")
        
        if headless:
            options.add_argument("--headless=new")
        
        driver = uc.Chrome(options=options)
    else:
        logger.info("Using regular selenium...")
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=id-ID")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        if headless:
            options.add_argument("--headless=new")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def random_delay(min_s=SCROLL_PAUSE_MIN, max_s=SCROLL_PAUSE_MAX):
    """Random delay to mimic human behavior"""
    time.sleep(random.uniform(min_s, max_s))

def extract_phone_from_text(text):
    """Extract Indonesian phone number from text"""
    for pattern in PHONE_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            # Clean and return first match
            phone = re.sub(r'[\s\-]', '', matches[0])
            return phone
    return None

def scroll_feed(driver, max_attempts=MAX_SCROLL_ATTEMPTS, target_count=50):
    """Scroll the results feed to load more items"""
    logger.info("Looking for results feed...")
    
    try:
        wait = WebDriverWait(driver, 15)
        
        # Try multiple selector strategies
        feed = None
        for selector in [SELECTORS["feed"], "//div[@role='main']//div[contains(@class, 'scrollable')]"]:
            try:
                feed = wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                break
            except:
                continue
        
        if not feed:
            logger.warning("Could not find scrollable feed")
            return False
        
        logger.info(f"Starting scroll (max {max_attempts}, target {target_count})...")
        
        last_count = 0
        no_change_count = 0
        
        for i in range(max_attempts):
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
            random_delay()
            
            items = driver.find_elements(By.XPATH, SELECTORS["place_link"])
            current_count = len(items)
            
            logger.info(f"  Scroll {i+1}: {current_count} items")
            
            if current_count >= target_count:
                break
            
            if current_count == last_count:
                no_change_count += 1
                if no_change_count >= 3:
                    break
            else:
                no_change_count = 0
            
            last_count = current_count
            
        return True
        
    except Exception as e:
        logger.warning(f"Scroll error: {e}")
        return False

def get_phone_from_detail(driver):
    """Extract phone number from business detail page"""
    try:
        # Wait for detail page to load
        time.sleep(1)
        
        # Method 1: Look for phone button with aria-label
        try:
            phone_buttons = driver.find_elements(By.XPATH, SELECTORS["phone_button"])
            for btn in phone_buttons:
                label = btn.get_attribute("aria-label") or ""
                phone = extract_phone_from_text(label)
                if phone:
                    return phone
        except:
            pass
        
        # Method 2: Look for tel: links
        try:
            tel_links = driver.find_elements(By.XPATH, SELECTORS["phone_link"])
            for link in tel_links:
                href = link.get_attribute("href") or ""
                if href.startswith("tel:"):
                    phone = href.replace("tel:", "").strip()
                    phone = re.sub(r'[\s\-]', '', phone)
                    if len(phone) >= 10:
                        return phone
        except:
            pass
        
        # Method 3: Search page source for phone patterns
        try:
            page_source = driver.page_source
            phone = extract_phone_from_text(page_source)
            if phone:
                return phone
        except:
            pass
        
        return None
        
    except Exception as e:
        logger.debug(f"Phone extraction error: {e}")
        return None

def go_back_to_list(driver):
    """Navigate back to the results list"""
    try:
        # Method 1: Click back button
        try:
            back_btn = driver.find_element(By.XPATH, SELECTORS["back_button"])
            back_btn.click()
            time.sleep(1)
            return True
        except:
            pass
        
        # Method 2: Press Escape
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
            return True
        except:
            pass
        
        # Method 3: Browser back
        driver.back()
        time.sleep(1)
        return True
        
    except:
        return False

def extract_places_with_phones(driver, max_places=50):
    """Extract places by clicking into each one to get phone"""
    logger.info(f"Extracting up to {max_places} places with phone numbers...")
    
    results = []
    processed_names = set()
    
    try:
        # Get all place links
        items = driver.find_elements(By.XPATH, SELECTORS["place_link"])
        logger.info(f"Found {len(items)} place links to process")
        
        for idx, item in enumerate(items[:max_places]):
            try:
                name = item.get_attribute("aria-label")
                
                if not name or name in processed_names:
                    continue
                
                processed_names.add(name)
                logger.info(f"[{idx+1}/{min(len(items), max_places)}] Processing: {name[:40]}...")
                
                # Scroll item into view
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                random_delay(0.5, 1.0)
                
                # Click to open detail
                try:
                    item.click()
                except:
                    driver.execute_script("arguments[0].click();", item)
                
                random_delay(CLICK_PAUSE_MIN, CLICK_PAUSE_MAX)
                
                # Extract phone from detail page
                phone = get_phone_from_detail(driver)
                
                place = {
                    "name": name.strip(),
                    "phone": phone or "",
                    "source": "GMaps Scrape"
                }
                
                results.append(place)
                
                if phone:
                    logger.info(f"   ✓ Found phone: {phone}")
                else:
                    logger.info(f"   ✗ No phone found")
                
                # Go back to list
                go_back_to_list(driver)
                random_delay(0.5, 1.0)
                
                # Re-fetch items (DOM might have changed)
                items = driver.find_elements(By.XPATH, SELECTORS["place_link"])
                
            except Exception as e:
                logger.debug(f"Error processing item: {e}")
                go_back_to_list(driver)
                continue
        
        logger.info(f"Extracted {len(results)} places, {sum(1 for r in results if r['phone'])} with phones")
        return results
        
    except Exception as e:
        logger.error(f"Extract error: {e}")
        return results

def save_results(results, search_phrase):
    """Save results to CSV"""
    if not results:
        logger.warning("No results to save")
        return None
    
    df = pd.DataFrame(results)
    
    folder_name = search_phrase.lower().replace(" ", "_")[:50]
    
    # Use global OUTPUT_DIR 
    full_output_path = os.path.join(OUTPUT_DIR, folder_name)
    os.makedirs(full_output_path, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(full_output_path, f"results_{timestamp}.csv")
    
    df.to_csv(output_file, index=False)
    logger.info(f"Saved {len(results)} results to: {output_file}")
    
    # Also save only with phones
    with_phones = df[df['phone'] != '']
    if len(with_phones) > 0:
        phones_file = os.path.join(full_output_path, f"phones_only_{timestamp}.csv")
        with_phones.to_csv(phones_file, index=False)
        logger.info(f"Saved {len(with_phones)} with phones to: {phones_file}")
    
    return output_file

def main():
    logger.info("=" * 50)
    logger.info("Starting Google Maps Scraper (Phone Extraction)")
    logger.info("=" * 50)
    
    config = load_config()
    search_phrase = config.get("search_phrase", "Coffee Shop Jakarta")
    
    headless = config.get("HEADLESS", False)
    target_count = config.get("MAX_RESULTS", 30)  # Lower default for phone extraction
    
    driver = None
    
    try:
        driver = init_driver(headless=headless)
        
        url = f"https://www.google.com/maps/search/{search_phrase.replace(' ', '+')}"
        logger.info(f"Navigating to: {url}")
        driver.get(url)
        
        logger.info("Waiting for page load...")
        time.sleep(5)
        
        # Handle consent dialog
        try:
            consent_button = driver.find_element(By.XPATH, "//button[contains(., 'Accept all') or contains(., 'Terima semua')]")
            consent_button.click()
            time.sleep(2)
        except:
            pass
        
        # Scroll to load results
        scroll_feed(driver, target_count=target_count)
        
        # Extract with phone numbers
        results = extract_places_with_phones(driver, max_places=target_count)
        
        # Save results
        if results:
            save_results(results, search_phrase)
            
            phones_found = sum(1 for r in results if r['phone'])
            logger.info(f"\n{'='*50}")
            logger.info(f"DONE: {len(results)} places, {phones_found} with phone numbers")
            logger.info(f"{'='*50}")
        else:
            logger.warning("No places extracted")
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            driver.quit()
            logger.info("Browser closed")

if __name__ == "__main__":
    main()
