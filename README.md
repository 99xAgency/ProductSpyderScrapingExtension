# Product Spyder Scraping Extension

A Chrome extension for web scraping with random delays. Built with TypeScript and modular design.

## Features

- Scrape multiple websites from a list
- Add random delays between requests to avoid being flagged as a bot
- Extract detailed product information
- Comprehensive data extraction from multiple sources
- TypeScript for type safety and better development experience

## Project Structure

```
├── dist/                 # Compiled JavaScript (after build)
├── src/                  # TypeScript source code
│   ├── extractors/       # Product data extraction modules
│   │   ├── utils.ts      # Shared utility functions
│   │   └── product-extractor.ts # Main extractor implementation
│   ├── types/            # TypeScript type definitions
│   │   └── index.ts      # Shared type interfaces
│   ├── background.ts     # Background script
│   ├── popup.ts          # Popup UI script
│   └── content.ts        # Content script
├── popup.html            # Extension popup UI
├── manifest.json         # Extension manifest
├── package.json          # NPM dependencies
└── tsconfig.json         # TypeScript configuration
```

## Setup

1. Install dependencies:

   ```
   npm install
   ```

2. Build the extension:

   ```
   npm run build
   ```

3. Load the extension in Chrome:
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the project folder

## Usage

1. Click the extension icon in your toolbar
2. Enter the URLs you want to scrape (one per line)
3. Set minimum and maximum delay between requests (in seconds)
4. Click "Start Scraping"

The extension will:

- Open each URL in a tab
- Wait for the page to fully load
- Extract product data using multiple methods
- Add random delays between requests
- Save the scraped data to Chrome's local storage

## Development

For development with auto-rebuilding:

```
npm run watch
```

## Data Extraction

The extension extracts product data from:

- LD+JSON structured data
- Meta tags
- Shopify analytics
- And other sources

It collects:

- Product title
- Price and currency
- SKU, MPN, UPC (when available)
- Availability status
- Product images
- Seller information (when available)
- Variations and offers
