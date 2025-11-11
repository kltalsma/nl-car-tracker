# Cookie Files for Bypassing Privacy Gates

This directory contains cookie files used to bypass DPG Media privacy consent gates on Autotrack.nl and Gaspedaal.nl.

## How to Export Cookies from Chrome

### Method 1: Using EditThisCookie Extension (Recommended)

1. **Install EditThisCookie extension:**
   - Go to Chrome Web Store
   - Search for "EditThisCookie"
   - Install the extension

2. **Visit the website and accept consent:**
   - Go to https://www.autotrack.nl (or https://www.gaspedaal.nl)
   - Accept the privacy consent when prompted
   - Make sure you can see the actual car listings

3. **Export cookies:**
   - Click the EditThisCookie icon in your browser toolbar
   - Click the "Export" button (looks like a download icon)
   - The cookies will be copied to your clipboard in JSON format

4. **Save cookies to file:**
   - Paste the cookies into `autotrack_cookies.json` (for Autotrack)
   - Or paste into `gaspedaal_cookies.json` (for Gaspedaal)

### Method 2: Using Browser DevTools

1. **Visit the website and accept consent:**
   - Go to https://www.autotrack.nl
   - Accept the privacy consent
   - Make sure you can see car listings

2. **Open DevTools:**
   - Press F12 or right-click and select "Inspect"
   - Go to the "Application" tab
   - In the left sidebar, expand "Cookies"
   - Click on "https://www.autotrack.nl"

3. **Export cookies manually:**
   - You'll see all cookies for the domain
   - Look for cookies related to consent/privacy (e.g., cookies with names containing "consent", "privacy", etc.)
   - Copy them into the JSON format shown below

## Cookie File Format

The cookie file should be a JSON array of cookie objects:

```json
[
  {
    "name": "cookie_name",
    "value": "cookie_value",
    "domain": ".autotrack.nl",
    "path": "/",
    "expires": 1735689600,
    "httpOnly": false,
    "secure": true
  }
]
```

## Important Cookies to Look For

When exporting cookies, make sure to include cookies with names like:
- `euconsent-v2` (main consent cookie)
- `_ga`, `_gid` (Google Analytics)
- Any cookies with "privacy", "consent", or "dpg" in the name

## Files

- `autotrack_cookies.json` - Cookies for autotrack.nl (DPG Media network)
- `gaspedaal_cookies.json` - Cookies for gaspedaal.nl (same DPG Media network, may share cookies)

## Notes

- Cookies may expire after a certain period (usually a few months to a year)
- If the scraper starts hitting privacy gates again, re-export fresh cookies
- The same cookies may work for both Autotrack and Gaspedaal (same network)
