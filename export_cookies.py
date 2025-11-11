#!/usr/bin/env python3
"""
Cookie Exporter for Autotrack.nl

This script opens a Chrome browser window where you can manually accept the privacy consent.
After you accept, it will automatically export the cookies to a JSON file.

Usage:
    python export_cookies.py
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def export_cookies(url, output_file):
    """
    Open a browser window, let user accept consent, then export cookies
    """
    print(f"\n{'='*70}")
    print("COOKIE EXPORTER FOR AUTOTRACK.NL")
    print(f"{'='*70}\n")
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Initialize driver
    print("Starting Chrome browser...")
    try:
        # Try to use ChromeDriverManager
        driver_path = ChromeDriverManager().install()
        # Fix for ARM64 Mac - find actual chromedriver binary
        import os
        if os.path.isdir(driver_path):
            # If path is a directory, find the chromedriver binary inside
            for file in os.listdir(driver_path):
                if file == 'chromedriver':
                    driver_path = os.path.join(driver_path, file)
                    break
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error with ChromeDriverManager: {e}")
        print("Trying without service specification...")
        driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to the website
        print(f"\nNavigating to {url}...")
        driver.get(url)
        
        # Wait for user to accept consent
        print("\n" + "="*70)
        print("MANUAL STEP REQUIRED:")
        print("="*70)
        print("\n1. The browser window has opened")
        print("2. ACCEPT the privacy consent when it appears")
        print("3. Wait for the page to load and show car listings")
        print("4. Come back to this terminal and press ENTER when done\n")
        print("="*70 + "\n")
        
        input("Press ENTER after you've accepted the consent and can see the listings...")
        
        # Give it a moment to ensure cookies are set
        time.sleep(2)
        
        # Get all cookies
        cookies = driver.get_cookies()
        
        print(f"\nFound {len(cookies)} cookies!")
        print("\nKey cookies found:")
        for cookie in cookies:
            if any(keyword in cookie['name'].lower() for keyword in ['consent', 'privacy', 'euconsent', 'dpg']):
                print(f"  - {cookie['name']}")
        
        # Save cookies to file
        with open(output_file, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        print(f"\n✓ Cookies successfully saved to: {output_file}")
        print(f"\nYou can now run the Autotrack scraper!\n")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        
    finally:
        print("\nClosing browser...")
        driver.quit()
        print("Done!\n")

if __name__ == "__main__":
    # Export cookies for Autotrack.nl
    export_cookies(
        url="https://www.autotrack.nl",
        output_file="cookies/autotrack_cookies.json"
    )
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("\n1. The cookies have been saved to cookies/autotrack_cookies.json")
    print("2. You can now run the Autotrack scraper")
    print("3. The scraper will automatically load these cookies")
    print("\nTo run the scraper:")
    print("  python run_scraper.py\n")
