#!/usr/bin/env python3
"""
Automated Cookie Exporter for Autotrack.nl

This script automatically handles the privacy consent and exports cookies.
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def export_cookies_automated(url, output_file):
    """
    Automatically accept consent and export cookies
    """
    print(f"\n{'='*70}")
    print("AUTOMATED COOKIE EXPORTER FOR AUTOTRACK.NL")
    print(f"{'='*70}\n")
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Initialize driver
    print("Starting Chrome browser...")
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"Error starting Chrome: {e}")
        return False
    
    try:
        # Navigate to the website
        print(f"Navigating to {url}...")
        driver.get(url)
        
        # Wait a bit for page to load
        time.sleep(5)
        
        print("Looking for privacy consent...")
        
        # Try to find and click consent button
        consent_found = False
        
        # Strategy 1: Look for common consent button texts
        button_texts = ['Akkoord', 'Accepteren', 'Alles accepteren', 'Accept', 'Agree', 'Toestaan']
        for button_text in button_texts:
            try:
                print(f"  Trying to find button with text: {button_text}")
                button = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, f"//button[contains(., '{button_text}')]"))
                )
                print(f"  Found button! Clicking...")
                button.click()
                consent_found = True
                print(f"✓ Clicked consent button: {button_text}")
                break
            except:
                continue
        
        # Strategy 2: Try to find iframe and click inside
        if not consent_found:
            print("  Trying to find consent iframe...")
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        for button_text in button_texts:
                            try:
                                button = driver.find_element(By.XPATH, f"//button[contains(., '{button_text}')]")
                                if button.is_displayed():
                                    button.click()
                                    consent_found = True
                                    print(f"✓ Clicked consent button in iframe: {button_text}")
                                    break
                            except:
                                continue
                        driver.switch_to.default_content()
                        if consent_found:
                            break
                    except:
                        driver.switch_to.default_content()
                        continue
            except Exception as e:
                print(f"  No iframe found: {e}")
        
        if not consent_found:
            print("⚠ Could not automatically click consent button")
            print("  Waiting 30 seconds for manual intervention...")
            print("  Please click the consent button in the browser window if it's visible")
            time.sleep(30)
        else:
            # Wait for page to load after consent
            print("Waiting for page to load after consent...")
            time.sleep(10)
        
        # Get all cookies
        cookies = driver.get_cookies()
        
        print(f"\n✓ Found {len(cookies)} cookies!")
        
        # Show important cookies
        important_cookies = []
        for cookie in cookies:
            if any(keyword in cookie['name'].lower() for keyword in ['consent', 'privacy', 'euconsent', 'dpg', 'cmp']):
                important_cookies.append(cookie['name'])
        
        if important_cookies:
            print("\nKey consent-related cookies found:")
            for name in important_cookies:
                print(f"  - {name}")
        else:
            print("\n⚠ WARNING: No obvious consent cookies found!")
            print("  The privacy gate might not have been accepted properly.")
        
        # Save cookies to file
        with open(output_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        print(f"\n✓ Cookies successfully saved to: {output_file}")
        
        # Take a screenshot for debugging
        screenshot_path = "tmp/autotrack_cookie_export.png"
        driver.save_screenshot(screenshot_path)
        print(f"✓ Screenshot saved to: {screenshot_path}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False
        
    finally:
        print("\nClosing browser...")
        driver.quit()
        print("Done!\n")

if __name__ == "__main__":
    import os
    
    # Ensure directories exist
    os.makedirs("cookies", exist_ok=True)
    os.makedirs("tmp", exist_ok=True)
    
    # Export cookies for Autotrack.nl
    success = export_cookies_automated(
        url="https://www.autotrack.nl/aanbod",
        output_file="cookies/autotrack_cookies.json"
    )
    
    if success:
        print("\n" + "="*70)
        print("SUCCESS!")
        print("="*70)
        print("\n1. Cookies have been saved to cookies/autotrack_cookies.json")
        print("2. You can now run the Autotrack scraper")
        print("\nTo run the scraper:")
        print("  python run_scraper.py\n")
    else:
        print("\n" + "="*70)
        print("FAILED - Manual cookie export needed")
        print("="*70)
        print("\nPlease export cookies manually using your browser's developer tools")
        print("See cookies/README.md for instructions\n")
