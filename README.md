# Product Spyder Scraping Extension

A Chrome extension for web scraping with advanced bot detection bypass capabilities.

## Features

- Human-like browsing simulation (scrolling, delays, etc.)
- CAPTCHA detection and reporting
- Cookie management
- Custom user agent support
- Configurable timeouts and behavior
- Screenshots of detected CAPTCHAs

## Installation

1. Clone this repository
2. Build the extension:
   ```
   npm install
   npm run build
   ```
3. Load the extension in Chrome:
   - Go to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `dist` directory

## Server Setup

1. Install server dependencies:
   ```
   pip install flask flask-sock gevent
   ```
2. Run the server:
   ```
   python server/app.py
   ```

## Usage

### Basic Usage

The extension connects to the server via WebSocket and waits for scraping instructions. The server exposes an HTTP endpoint for clients to request HTML extraction.

```python
import requests

# List of URLs to scrape
urls = ["https://example.com", "https://example.org"]

# Send request to the server
response = requests.post("http://127.0.0.1:9999/fetch", json=urls)

# Process the response
html_results = response.json()
```

### Advanced Usage with Bot Prevention Bypass

You can customize the scraping behavior to bypass bot prevention:

```python
import requests

# List of URLs to scrape
urls = ["https://example.com", "https://example.org"]

# Configure scraping options
options = {
    "simulateHuman": True,        # Simulate human browsing behavior
    "customUserAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "timeout": 15000,             # 15 seconds timeout
    "handleCaptcha": True,        # Detect and handle CAPTCHAs
    "manageSiteCookies": True     # Manage site cookies
}

# Send request with options
response = requests.post("http://127.0.0.1:9999/fetch",
                        json={"urls": urls, "options": options})

# Process the enhanced response
results = response.json()

# Check for CAPTCHAs
for result in results:
    if result.get("captchaDetected"):
        print(f"CAPTCHA detected on {result['url']}")
        print(f"Type: {result.get('captchaType')}")
        # The screenshot is saved on the server and can be accessed at:
        # http://127.0.0.1:9999/captchas/{result['screenshot']}
```

## Testing

Use the provided test client to verify the functionality:

```
python server/test_client.py
```

## CAPTCHA Handling

When a CAPTCHA is detected:

1. The extension takes a screenshot of the CAPTCHA
2. The server saves the screenshot to the `server/captchas` directory
3. The response includes the CAPTCHA type and a link to the screenshot
4. You can view the screenshots at `http://127.0.0.1:9999/captchas/<filename>`

## Extending

To further enhance the bot prevention bypass:

1. Add more human-like interactions in the `simulateHumanBehavior` function
2. Integrate with external CAPTCHA solving services
3. Implement proxy rotation
4. Add more sophisticated browser fingerprinting techniques
