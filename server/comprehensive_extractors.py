import re

import orjson
from selectolax.lexbor import LexborHTMLParser

# Define selectors for various product metadata elements
PRICE_META = ",".join(
    [
        "[itemprop='price']",
        "meta[property='product:price:amount']",
        "meta[property='og:price:amount']",
        "div[data-orignal-price]",
        "span.ProductMeta__Price",
        ".woocommerce-Price-amount",
    ]
)

CURRENCY_META = ",".join(
    [
        "meta[property='og:price:currency']",
        "meta[property='product:price:currency']",
        "meta[itemprop='priceCurrency']",
        "meta[_itemprop='priceCurrency']",
    ]
)

TITLE_META = ",".join(
    [
        "meta[property='og:title']",
        "meta[property='product:name']",
        "meta[itemprop='itemOffered']",
        ".wpr-product-title",
    ]
)

IMAGE_META = ",".join(
    [
        "meta[property='og:image']",
        "meta[property='og:image:url']",
        "meta[property='og:image:secure_url']",
        ".woocommerce-product-gallery__image img",
        "img[itemprop='image']",
    ]
)

AVAILABILITY_META = ",".join(
    [
        "meta[property='og:availability']",
        "meta[property='product:availability']",
    ]
)

SKU_META = ",".join(
    [
        "meta[itemprop='sku']",
        "meta[property='product:retailer_item_id']",
    ]
)


def extract_skus(parser: LexborHTMLParser) -> dict | None:
    """
    Extract SKU information from HTML using various selectors and patterns

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Dictionary containing all found SKUs or None if not found
    """
    result = {"skus": []}

    # 1. Extract SKU from span with class="productsku"
    productsku_span = parser.css_first("span.productsku")
    if productsku_span:
        sku_value = productsku_span.text().strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 2. Extract SKU from hidden input field
    sku_input = parser.css_first('input[name="sku"]')
    if sku_input:
        sku_value = sku_input.attributes.get("value", "").strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 3. Extract SKU from span with class="sku" inside sku_wrapper
    sku_span = parser.css_first("span.sku_wrapper span.sku")
    if sku_span:
        sku_value = sku_span.text().strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 4. Extract SKU from meta with itemprop="sku"
    sku_meta = parser.css_first('meta[itemprop="sku"]')
    if sku_meta:
        sku_value = sku_meta.attributes.get("content", "").strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 5. Extract SKU from span with class="js-variant-sku"
    variant_sku_span = parser.css_first("span.js-variant-sku")
    if variant_sku_span:
        sku_value = variant_sku_span.text().strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 6. Extract SKU from meta with property="product:retailer_item_id"
    retailer_item_meta = parser.css_first('meta[property="product:retailer_item_id"]')
    if retailer_item_meta:
        sku_value = retailer_item_meta.attributes.get("content", "").strip()
        if sku_value:
            result["skus"].append(sku_value)

    # 7. Extract model as potential SKU
    model_p = parser.css_first('p[itemprop="model"]')
    if model_p:
        model_value = model_p.text().strip()
        if model_value:
            result["skus"].append(model_value)

    # 8. Extract GTIN-13 as related identifier
    gtin13_p = parser.css_first('p[itemprop="gtin13"]')
    if gtin13_p:
        gtin_value = gtin13_p.text().strip()
        if gtin_value:
            result["gtin13"] = gtin_value

    # Determine primary SKU (using a simple heuristic)
    if result["skus"]:
        # Prioritize retailer_item_id
        retailer_item_meta = parser.css_first('meta[property="product:retailer_item_id"]')
        if retailer_item_meta:
            sku_value = retailer_item_meta.attributes.get("content", "").strip()
            if sku_value:
                result["primary_sku"] = sku_value

        # If no retailer_item_id, use meta itemprop="sku"
        if "primary_sku" not in result:
            sku_meta = parser.css_first('meta[itemprop="sku"]')
            if sku_meta:
                sku_value = sku_meta.attributes.get("content", "").strip()
                if sku_value:
                    result["primary_sku"] = sku_value

        # If still no primary SKU, use the first one found
        if "primary_sku" not in result and result["skus"]:
            result["primary_sku"] = result["skus"][0]

    return result if result["skus"] else None


def extract_gtm4wp_product_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract GTM4WP product data from hidden input fields

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted GTM4WP product data as a dictionary or None if not found
    """
    # Find input with name="gtm4wp_product_data"
    input_tag = parser.css_first('input[name="gtm4wp_product_data"]')

    if not input_tag:
        return None

    # Get the value attribute which contains JSON data
    json_str = input_tag.attributes.get("value", "")

    if not json_str:
        return None

    try:
        # Parse the JSON string
        product_data = orjson.loads(json_str)
        return {"gtm4wp_product": product_data}
    except orjson.JSONDecodeError as e:
        print(f"Failed to parse GTM4WP product data JSON: {e}")
        print(f"JSON string: {json_str}")

    return None


def extract_drip_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Drip tracking data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Drip data as a dictionary or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    for script in script_tags:
        script_text = script.text()
        if script_text and "_dcq" in script_text and "_dcq.push" in script_text and "recordProductView" in script_text:
            # Extract the Drip account ID
            account_id_match = re.search(r'dc\.src\s*=\s*"https://tag\.getdrip\.com/(\d+)\.js"', script_text)
            account_id = account_id_match.group(1) if account_id_match else None

            # Extract key product information directly using regex patterns
            # Product ID
            id_match = re.search(r"id:\s*(\d+)", script_text)
            product_id = int(id_match.group(1)) if id_match else None

            # Product title
            title_match = re.search(r'title:\s*"([^"]+)"', script_text)
            title = title_match.group(1) if title_match else None

            # Product handle/slug
            handle_match = re.search(r'handle:\s*"([^"]+)"', script_text)
            handle = handle_match.group(1) if handle_match else None

            # Product price
            price_match = re.search(r"price:\s*(\d+)", script_text)
            price = int(price_match.group(1)) if price_match else None

            # Product availability
            available_match = re.search(r"available:\s*(true|false)", script_text)
            available = available_match.group(1) == "true" if available_match else None

            # Product vendor
            vendor_match = re.search(r'vendor:\s*"([^"]+)"', script_text)
            vendor = vendor_match.group(1) if vendor_match else None

            # Product type
            type_match = re.search(r'type:\s*"([^"]+)"', script_text)
            product_type = type_match.group(1) if type_match else None

            # Currency (usually at the end of the array)
            currency_match = re.search(r'_dcq\.push\(\s*\[[^\]]*\],\s*\[[^\]]*\],\s*"([A-Z]{3})"', script_text)
            currency = currency_match.group(1) if currency_match else None

            # URL path
            url_match = re.search(r'_dcq\.push\(\s*\[[^\]]*\],\s*\[[^\]]*\],\s*"[A-Z]{3}",\s*"([^"]+)"', script_text)
            url_path = url_match.group(1) if url_match else None

            # Extract product tags if available
            tags = []
            tags_match = re.search(r"tags:\s*\[(.*?)\]", script_text, re.DOTALL)
            if tags_match:
                tags_text = tags_match.group(1)
                tag_items = re.findall(r'"([^"]+)"', tags_text)
                tags = tag_items if tag_items else []

            # Construct the result dictionary
            result = {
                "drip": {
                    "account_id": account_id,
                    "product_view": {
                        "id": product_id,
                        "title": title,
                        "handle": handle,
                        "price": price,
                        "available": available,
                        "vendor": vendor,
                        "type": product_type,
                        "tags": tags,
                    },
                    "currency": currency,
                    "url_path": url_path,
                }
            }

            # Remove None values
            result["drip"]["product_view"] = {k: v for k, v in result["drip"]["product_view"].items() if v is not None}
            result["drip"] = {k: v for k, v in result["drip"].items() if v is not None}

            # Only return if we have at least some product data
            if result["drip"]["product_view"]:
                return result

    return None


def extract_gsf_conversion_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract gsf_conversion_data from HTML using selectolax

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted gsf_conversion_data as a dictionary
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for the script tag containing gsf_conversion_data
    for script in script_tags:
        script_text = script.text()
        if script_text and re.search(r"var\s+gsf_conversion_data\s*=", script_text):
            # Extract the gsf_conversion_data assignment using regex
            match = re.search(r"var\s+gsf_conversion_data\s*=\s*(\{.*?\});", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Replace single quotes with double quotes
                json_str = json_str.replace("'", '"')
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)

                try:
                    # Parse the JSON string
                    data = orjson.loads(json_str)
                    return data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_shopify_analytics_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract ShopifyAnalytics data from HTML using selectolax

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted ShopifyAnalytics data as a dictionary
    """
    # Find all script tags
    script_tags = parser.css("script")

    for script in script_tags:
        script_text = script.text()
        if script_text and "window.ShopifyAnalytics" in script_text:
            # Extract the meta object which contains product data
            meta_match = re.search(r"var\s+meta\s*=\s*(\{.*?\});\s*for", script_text, re.DOTALL)
            if meta_match:
                # Get the JSON string for meta object
                json_str = meta_match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Replace single quotes with double quotes
                json_str = json_str.replace("'", '"')
                # Fix backslashes in strings (like "gid:\/\/")
                json_str = re.sub(r"\\/", "/", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)

                try:
                    # Parse the JSON string
                    meta_data = orjson.loads(json_str)

                    # Also extract the currency if available
                    currency_match = re.search(r'window\.ShopifyAnalytics\.meta\.currency\s*=\s*"([^"]+)"', script_text)
                    if currency_match:
                        # Add currency to the meta data
                        meta_data["currency"] = currency_match.group(1)

                    return meta_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse ShopifyAnalytics JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_variants_json(parser: LexborHTMLParser) -> dict | None:
    """
    Extract product variants JSON data from HTML script tag with data-variants-json attribute
    and from textarea elements with data-variant-json and data-current-variant-json attributes

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Dictionary containing variants and current_variant information or None if not found
    """
    result = {}

    # Look for script tag with data-variants-json attribute
    script_tag = parser.css_first("script[data-variants-json]")
    if script_tag:
        # Get the JSON content
        json_data = script_tag.text()
        if json_data:
            try:
                # Parse the JSON directly as it should already be valid JSON
                variants = orjson.loads(json_data)
                result["variants"] = variants
            except orjson.JSONDecodeError as e:
                print(f"Failed to parse variants JSON from script tag: {e}")

    # Find textarea with data-variant-json attribute
    variants_textarea = parser.css_first("textarea[data-variant-json]")
    if variants_textarea:
        variants_json = variants_textarea.text().strip()
        if variants_json:
            try:
                variants_data = orjson.loads(variants_json)
                # Only add if we don't already have variants from script tag
                if "variants" not in result:
                    result["variants"] = variants_data
            except orjson.JSONDecodeError as e:
                print(f"Failed to parse data-variant-json: {e}")

    # Find textarea with data-current-variant-json attribute
    current_variant_textarea = parser.css_first("textarea[data-current-variant-json]")
    if current_variant_textarea:
        current_variant_json = current_variant_textarea.text().strip()
        if current_variant_json:
            try:
                current_variant_data = orjson.loads(current_variant_json)
                result["current_variant"] = current_variant_data
            except orjson.JSONDecodeError as e:
                print(f"Failed to parse data-current-variant-json: {e}")

    return result if result else None


def extract_bc_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract BCData product information from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: BCData product information or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing BCData
    for script in script_tags:
        script_text = script.text()
        if script_text and "BCData" in script_text:
            # Extract the BCData assignment using regex
            match = re.search(r"var\s+BCData\s*=\s*(\{.*?\});", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                try:
                    # BCData should already be valid JSON, parse directly
                    bc_data = orjson.loads(json_str)
                    return bc_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse BCData JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_wpm_data_layer(parser: LexborHTMLParser) -> dict | None:
    """
    Extract wpmDataLayer product information from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: wpmDataLayer product information or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing wpmDataLayer
    for script in script_tags:
        script_text = script.text()
        if script_text and "wpmDataLayer" in script_text:
            # Try two different patterns for wpmDataLayer

            # Pattern 1: Direct assignment to window.wpmDataLayer.products[id]
            match = re.search(r"window\.wpmDataLayer\.products\[(\d+)\]\s*=\s*(\{.*?\});", script_text, re.DOTALL)
            if match:
                product_id = match.group(1)
                json_str = match.group(2)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)

                try:
                    # Parse the JSON string
                    product_data = orjson.loads(json_str)

                    # Create a structure similar to the original JavaScript object
                    wpm_data = {"products": {product_id: product_data}}

                    return wpm_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse wpmDataLayer JSON: {e}")
                    print(f"JSON string: {json_str}")

            # Pattern 2: Assignment through initialization
            match = re.search(
                r"\(window\.wpmDataLayer\s*=.*?\)\.products\s*=.*?window\.wpmDataLayer\.products\[(\d+)\]\s*=\s*(\{.*?\});",
                script_text,
                re.DOTALL,
            )
            if match:
                product_id = match.group(1)
                json_str = match.group(2)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle array values
                json_str = json_str.replace("'", '"')

                try:
                    # Parse the JSON string
                    product_data = orjson.loads(json_str)

                    # Create a structure similar to the original JavaScript object
                    wpm_data = {"products": {product_id: product_data}}

                    return wpm_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse wpmDataLayer JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_gtm_datalayer(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Google Tag Manager dataLayer information from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: GTM dataLayer information or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing dataLayer.push
    for script in script_tags:
        script_text = script.text()
        if script_text and "dataLayer.push" in script_text:
            # Extract the dataLayer.push call using regex
            match = re.search(r"dataLayer\.push\((\{.*?\})\);", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle null values
                json_str = json_str.replace("null", "null")

                try:
                    # Parse the JSON string
                    datalayer_data = orjson.loads(json_str)
                    return datalayer_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse GTM dataLayer JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_gtm_update_datalayer(parser: LexborHTMLParser) -> dict | None:
    """
    Extract GTM.updateDataLayerByJson information from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: GTM.updateDataLayerByJson information or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing GTM.updateDataLayerByJson
    for script in script_tags:
        script_text = script.text()
        if script_text and "GTM.updateDataLayerByJson" in script_text:
            # Extract the GTM.updateDataLayerByJson call using regex
            match = re.search(r"GTM\.updateDataLayerByJson\((\{.*?\})\);", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle null values
                json_str = json_str.replace("null", "null")

                try:
                    # Parse the JSON string
                    update_datalayer_data = orjson.loads(json_str)
                    return update_datalayer_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse GTM.updateDataLayerByJson JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_ga4_update_datalayer(parser: LexborHTMLParser) -> dict | None:
    """
    Extract GA4.updateDataLayerByJson information from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: GA4.updateDataLayerByJson information or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing GA4.updateDataLayerByJson
    for script in script_tags:
        script_text = script.text()
        if script_text and "GA4.updateDataLayerByJson" in script_text:
            # Extract the GA4.updateDataLayerByJson call using regex
            match = re.search(r"GA4\.updateDataLayerByJson\((\{.*?\})\);", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle null values
                json_str = json_str.replace("null", "null")

                try:
                    # Parse the JSON string
                    ga4_data = orjson.loads(json_str)
                    return ga4_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse GA4.updateDataLayerByJson JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_gtag_event_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract gtag event data from HTML script tags, focusing on product view_item events

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Product information from gtag event calls or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing gtag event calls
    for script in script_tags:
        script_text = script.text()
        if script_text and 'gtag("event"' in script_text:
            # Focus on view_item event for product data
            view_item_match = re.search(r'gtag\("event",\s*"view_item",\s*(\{.*?\})\);', script_text, re.DOTALL)
            if view_item_match:
                # Get the JSON string
                json_str = view_item_match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Replace template literals with their content
                json_str = re.sub(r"`([^`]*)`", r'"\1"', json_str)
                # Handle parseFloat calls
                json_str = re.sub(r'parseFloat\("(\d+(?:\.\d+)?)"\)', r"\1", json_str)
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)

                try:
                    # Parse the JSON string
                    gtag_data = orjson.loads(json_str)
                    return {"view_item": gtag_data}
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse gtag event JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_shopify_web_pixels_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Shopify Web Pixels Manager product data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Product information from Shopify Web Pixels Manager or None if not found
    """
    # Find script tag with id="web-pixels-manager-setup"
    script_tag = parser.css_first("script#web-pixels-manager-setup")

    if not script_tag:
        return None

    script_text = script_tag.text()

    # Extract the product data from the function arguments
    # Look for the productVariants section in the IIFE arguments
    product_variants_match = re.search(r"productVariants:\s*(\[.*?\])", script_text, re.DOTALL)

    # Look for the product_viewed event data in the pageEvents function
    product_viewed_match = re.search(r'publish\("product_viewed",\s*(\{.*?\})\)', script_text, re.DOTALL)

    # Look for shop information - use a more specific pattern to capture the entire shop object
    shop_match = re.search(
        r'shop:\s*(\{[^{]*"name":[^{]*"paymentSettings":\s*\{[^{]*\}[^{]*\})', script_text, re.DOTALL
    )

    result = {}

    # Process productVariants if found
    if product_variants_match:
        variants_str = product_variants_match.group(1)
        # Clean up the JSON string
        variants_str = re.sub(r",\s*([}\]])", r"\1", variants_str)
        variants_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', variants_str)
        variants_str = variants_str.replace("'", '"')
        variants_str = re.sub(r'\\([/"])', r"\1", variants_str)

        try:
            # Parse the variants JSON
            variants_data = orjson.loads(variants_str)
            result["product_variants"] = variants_data
        except orjson.JSONDecodeError as e:
            print(f"Failed to parse Shopify Web Pixels productVariants JSON: {e}")
            print(f"JSON string: {variants_str}")

    # Process product_viewed event if found
    if product_viewed_match:
        product_viewed_str = product_viewed_match.group(1)
        # Clean up the JSON string
        product_viewed_str = re.sub(r",\s*([}\]])", r"\1", product_viewed_str)
        product_viewed_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', product_viewed_str)
        product_viewed_str = product_viewed_str.replace("'", '"')
        product_viewed_str = re.sub(r'\\([/"])', r"\1", product_viewed_str)

        try:
            # Parse the product_viewed JSON
            product_viewed_data = orjson.loads(product_viewed_str)
            result["product_viewed"] = product_viewed_data
        except orjson.JSONDecodeError as e:
            print(f"Failed to parse Shopify Web Pixels product_viewed JSON: {e}")
            print(f"JSON string: {product_viewed_str}")

    # Process shop information if found
    if shop_match:
        shop_str = shop_match.group(1)
        # Clean up the JSON string
        shop_str = re.sub(r",\s*([}\]])", r"\1", shop_str)
        shop_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', shop_str)
        shop_str = shop_str.replace("'", '"')
        shop_str = re.sub(r'\\([/"])', r"\1", shop_str)
        shop_str = re.sub(r"\\\\/", r"/", shop_str)  # Handle escaped forward slashes

        try:
            # Parse the shop JSON
            shop_data = orjson.loads(shop_str)
            result["shop"] = shop_data
        except orjson.JSONDecodeError as e:
            # If we still have issues, just extract the key information manually
            name_match = re.search(r'"name":\s*"([^"]+)"', shop_str)
            currency_match = re.search(r'"currencyCode":\s*"([^"]+)"', shop_str)

            shop_data = {}
            if name_match:
                shop_data["name"] = name_match.group(1)
            if currency_match:
                shop_data["currency"] = currency_match.group(1)

            if shop_data:
                result["shop"] = shop_data

    return result if result else None


def extract_og_meta_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Open Graph and product metadata from HTML meta tags and other selectors

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Structured metadata from Open Graph and product meta tags
    """
    # Find all meta tags with og: or product: prefix in their property
    meta_tags = parser.css('meta[property^="og:"], meta[property^="product:"]')

    # Initialize data structure to hold extracted information
    result_data = {"og": {}, "product": {}, "structured": {}}

    # Process Open Graph and product meta tags
    if meta_tags:
        for meta in meta_tags:
            # Get property and content attributes
            prop = meta.attributes.get("property", "")
            content = meta.attributes.get("content", "")

            if not prop or not content:
                continue

            # Split property into namespace and name parts
            parts = prop.split(":")
            namespace = parts[0]

            if namespace == "og":
                # Handle nested properties like og:image:width
                if len(parts) > 2:
                    # Create nested structure for properties with multiple colons
                    if parts[1] not in result_data["og"]:
                        result_data["og"][parts[1]] = {}

                    if len(parts) == 3:
                        # Make sure parts[1] is a dictionary not a string
                        if not isinstance(result_data["og"][parts[1]], dict):
                            result_data["og"][parts[1]] = {}
                        result_data["og"][parts[1]][parts[2]] = content
                    elif len(parts) == 4:
                        if not isinstance(result_data["og"][parts[1]], dict):
                            result_data["og"][parts[1]] = {}
                        if parts[2] not in result_data["og"][parts[1]]:
                            result_data["og"][parts[1]][parts[2]] = {}
                        result_data["og"][parts[1]][parts[2]][parts[3]] = content
                else:
                    # Simple property like og:title
                    result_data["og"][parts[1]] = content

            elif namespace == "product":
                # Handle nested product properties like product:price:amount
                if len(parts) > 2:
                    # Create nested structure for properties with multiple colons
                    if parts[1] not in result_data["product"]:
                        result_data["product"][parts[1]] = {}

                    if len(parts) == 3:
                        # Make sure parts[1] is a dictionary not a string
                        if not isinstance(result_data["product"][parts[1]], dict):
                            result_data["product"][parts[1]] = {}
                        result_data["product"][parts[1]][parts[2]] = content
                else:
                    # Simple property
                    result_data["product"][parts[1]] = content

    # Convert price to numeric value if it exists
    if (
        "price" in result_data["product"]
        and isinstance(result_data["product"]["price"], dict)
        and "amount" in result_data["product"]["price"]
    ):
        try:
            result_data["product"]["price"]["amount"] = float(result_data["product"]["price"]["amount"])
        except (ValueError, TypeError):
            pass

    # Extract structured data using various selectors
    structured_data = {}

    # Extract price
    price_elements = parser.css(PRICE_META)
    if price_elements:
        for element in price_elements:
            price_text = None
            if element.tag == "meta":
                price_text = element.attributes.get("content", "")
            else:
                price_text = element.text().strip()

            if price_text:
                # Clean up price text and convert to float if possible
                price_text = re.sub(r"[^\d.,]", "", price_text)
                price_text = price_text.replace(",", ".")
                try:
                    structured_data["price"] = float(price_text)
                    break
                except (ValueError, TypeError):
                    pass

    # Extract currency
    currency_elements = parser.css(CURRENCY_META)
    if currency_elements:
        for element in currency_elements:
            if element.tag == "meta":
                currency = element.attributes.get("content", "")
                if currency:
                    structured_data["currency"] = currency
                    break

    # Extract title
    title_elements = parser.css(TITLE_META)
    if title_elements:
        for element in title_elements:
            title = None
            if element.tag == "meta":
                title = element.attributes.get("content", "")
            else:
                title = element.text().strip()

            if title:
                structured_data["title"] = title
                break

    # Extract image URLs
    image_elements = parser.css(IMAGE_META)
    if image_elements:
        image_urls = []
        for element in image_elements:
            image_url = None
            if element.tag == "meta":
                image_url = element.attributes.get("content", "")
            elif element.tag == "img":
                # Check for src or data-src attribute
                image_url = element.attributes.get("src") or element.attributes.get("data-src")

            if image_url and image_url not in image_urls:
                image_urls.append(image_url)

        if image_urls:
            structured_data["images"] = image_urls

    # Extract availability
    availability_elements = parser.css(AVAILABILITY_META)
    if availability_elements:
        for element in availability_elements:
            if element.tag == "meta":
                availability = element.attributes.get("content", "")
                if availability:
                    structured_data["availability"] = availability
                    break

    # Extract SKU
    sku_elements = parser.css(SKU_META)
    if sku_elements:
        for element in sku_elements:
            if element.tag == "meta":
                sku = element.attributes.get("content", "")
                if sku:
                    structured_data["sku"] = sku
                    break

    # Add structured data to the result
    if structured_data:
        result_data["structured"] = structured_data

    # Only return if we have any data
    if result_data["og"] or result_data["product"] or result_data["structured"]:
        return result_data

    return None


def extract_facebook_pixel_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Facebook Pixel data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Facebook Pixel data as a dictionary or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing fbq tracking code
    for script in script_tags:
        script_text = script.text()

        # Check for Facebook Pixel code
        if script_text and "fbq" in script_text and "ViewContent" in script_text:
            # Approach with direct string extraction rather than trying to parse the entire JS code
            try:
                # Extract content values directly with regex for each field
                content_name = re.search(r'content_name:\s*"([^"]+)"', script_text)
                content_ids = re.search(r"content_ids:\s*\'(\[[^\]]+\])\'", script_text)
                content_type = re.search(r'content_type:\s*"([^"]+)"', script_text)
                contents = re.search(r"contents:\s*\'(\[{[^}]+}\])\'", script_text)
                content_category = re.search(r'content_category:\s*"([^"]+)"', script_text)
                value = re.search(r'value:\s*"([^"]+)"', script_text)
                currency = re.search(r'currency:\s*"([^"]+)"', script_text)
                event_id = re.search(r'eventID:\s*"([^"]+)"', script_text)
                source = re.search(r'source:\s*"([^"]+)"', script_text)
                version = re.search(r'version:\s*"([^"]+)"', script_text)
                plugin_version = re.search(r'pluginVersion:\s*"([^"]+)"', script_text)

                # Build the result data
                result = {"content": {}}

                if source and source.group(1):
                    result["content"]["source"] = source.group(1)

                if version and version.group(1):
                    result["content"]["version"] = version.group(1)

                if plugin_version and plugin_version.group(1):
                    result["content"]["plugin_version"] = plugin_version.group(1)

                if content_name and content_name.group(1):
                    result["content"]["content_name"] = content_name.group(1)

                if content_type and content_type.group(1):
                    result["content"]["content_type"] = content_type.group(1)

                if content_category and content_category.group(1):
                    result["content"]["content_category"] = content_category.group(1)

                if value and value.group(1):
                    try:
                        result["content"]["value"] = float(value.group(1))
                    except ValueError:
                        result["content"]["value"] = value.group(1)

                if currency and currency.group(1):
                    result["content"]["currency"] = currency.group(1)

                # Handle JSON strings in content_ids and contents
                if content_ids and content_ids.group(1):
                    try:
                        result["content"]["content_ids"] = orjson.loads(content_ids.group(1))
                    except orjson.JSONDecodeError:
                        result["content"]["content_ids"] = content_ids.group(1)

                if contents and contents.group(1):
                    try:
                        result["content"]["contents"] = orjson.loads(contents.group(1))
                    except orjson.JSONDecodeError:
                        result["content"]["contents"] = contents.group(1)

                # Add event data
                if event_id and event_id.group(1):
                    result["event"] = {"event_id": event_id.group(1)}

                return result
            except Exception as e:
                print(f"Error extracting Facebook Pixel data: {e}")

    return None


def extract_json_ld_data(parser: LexborHTMLParser) -> list | None:
    """
    Extract JSON-LD structured data from script tags with type="application/ld+json"

    Args:
        parser: LexborHTMLParser instance

    Returns:
        list: List of parsed JSON-LD objects or None if not found
    """
    # Find all script tags with type="application/ld+json"
    script_tags = parser.css('script[type="application/ld+json"]')

    if not script_tags:
        return None

    json_ld_data = []

    for script in script_tags:
        script_text = script.text()
        if not script_text:
            continue

        try:
            # Parse the JSON directly
            data = orjson.loads(script_text)
            json_ld_data.append(data)
        except orjson.JSONDecodeError as e:
            print(f"Failed to parse JSON-LD: {e}")
            print(f"JSON string: {script_text}")

    return json_ld_data if json_ld_data else None


def extract_product_from_json_ld(json_ld_data: list) -> dict | None:
    """
    Extract product information from JSON-LD data

    Args:
        json_ld_data: List of JSON-LD objects

    Returns:
        dict: Structured product information extracted from JSON-LD data
    """
    if not json_ld_data:
        return None

    product_info = {
        "name": None,
        "description": None,
        "price": None,
        "currency": None,
        "sku": None,
        "mpn": None,
        "gtin": None,
        "brand": None,
        "images": [],
        "availability": None,
        "offers": [],
    }

    for json_ld in json_ld_data:
        # Handle @graph structure (multiple items in one JSON-LD)
        if "@graph" in json_ld:
            for item in json_ld["@graph"]:
                if item.get("@type") == "Product":
                    _extract_product_data(item, product_info)
        # Handle direct product
        elif json_ld.get("@type") == "Product":
            _extract_product_data(json_ld, product_info)

    # Remove empty fields
    product_info = {k: v for k, v in product_info.items() if v}

    return product_info if product_info else None


def _extract_product_data(product_data: dict, product_info: dict) -> None:
    """
    Helper function to extract product data from a JSON-LD Product object

    Args:
        product_data: JSON-LD Product object
        product_info: Dictionary to update with extracted information
    """
    # Extract basic product info
    if "name" in product_data and not product_info["name"]:
        product_info["name"] = product_data["name"]

    if "description" in product_data and not product_info["description"]:
        product_info["description"] = product_data["description"]

    if "sku" in product_data and not product_info["sku"]:
        product_info["sku"] = product_data["sku"]

    if "mpn" in product_data and not product_info["mpn"]:
        product_info["mpn"] = product_data["mpn"]

    # Extract GTIN (could be gtin8, gtin12, gtin13, gtin14)
    for gtin_type in ["gtin", "gtin8", "gtin12", "gtin13", "gtin14"]:
        if gtin_type in product_data and not product_info["gtin"]:
            product_info["gtin"] = product_data[gtin_type]

    # Extract brand information
    if "brand" in product_data and not product_info["brand"]:
        if isinstance(product_data["brand"], dict):
            product_info["brand"] = product_data["brand"].get("name")
        else:
            product_info["brand"] = product_data["brand"]

    # Extract image information
    if "image" in product_data:
        if isinstance(product_data["image"], list):
            for img in product_data["image"]:
                if isinstance(img, dict) and "url" in img:
                    if img["url"] not in product_info["images"]:
                        product_info["images"].append(img["url"])
                elif isinstance(img, str) and img not in product_info["images"]:
                    product_info["images"].append(img)
        elif isinstance(product_data["image"], dict) and "url" in product_data["image"]:
            if product_data["image"]["url"] not in product_info["images"]:
                product_info["images"].append(product_data["image"]["url"])
        elif isinstance(product_data["image"], str) and product_data["image"] not in product_info["images"]:
            product_info["images"].append(product_data["image"])

    # Extract offers
    if "offers" in product_data:
        if isinstance(product_data["offers"], list):
            for offer in product_data["offers"]:
                _extract_offer_data(offer, product_info)
        else:
            _extract_offer_data(product_data["offers"], product_info)


def _extract_offer_data(offer: dict, product_info: dict) -> None:
    """
    Helper function to extract offer data from a JSON-LD Offer object

    Args:
        offer: JSON-LD Offer object
        product_info: Dictionary to update with extracted information
    """
    # Create simplified offer object
    offer_data = {}

    # Extract price information
    if "price" in offer:
        try:
            offer_data["price"] = float(offer["price"])
            if not product_info["price"]:
                product_info["price"] = float(offer["price"])
        except (ValueError, TypeError):
            offer_data["price"] = offer["price"]
            if not product_info["price"]:
                product_info["price"] = offer["price"]

    # Extract currency
    if "priceCurrency" in offer:
        offer_data["currency"] = offer["priceCurrency"]
        if not product_info["currency"]:
            product_info["currency"] = offer["priceCurrency"]

    # Extract availability
    if "availability" in offer:
        availability = offer["availability"]
        # Convert schema.org URL to simple string
        if "schema.org" in availability:
            availability = availability.split("/")[-1]
        offer_data["availability"] = availability
        if not product_info["availability"]:
            product_info["availability"] = availability

    # Add other offer details
    if "priceValidUntil" in offer:
        offer_data["validUntil"] = offer["priceValidUntil"]

    if "itemCondition" in offer:
        condition = offer["itemCondition"]
        # Convert schema.org URL to simple string
        if "schema.org" in condition:
            condition = condition.split("/")[-1]
        offer_data["condition"] = condition

    # Add offer to product offers list if it has content
    if offer_data:
        product_info["offers"].append(offer_data)


def extract_dmpt_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Dynamic Marketing Platform tracker (dmPt) data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted dmPt product tracking data or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing dmPt tracking code
    for script in script_tags:
        script_text = script.text()

        # Check for dmPt initialization and product tracking
        if script_text and "dmPt" in script_text and "viewed_product" in script_text:
            try:
                # Extract the profile ID and domain
                profile_match = re.search(r"window\.dmPt\('create',\s*'([^']+)',\s*'([^']+)'", script_text)

                # Extract the viewed product data
                product_match = re.search(r"var\s+viewed_product\s*=\s*(\{.*?\});", script_text, re.DOTALL)

                result = {"dmpt": {}}

                # Add profile information if found
                if profile_match:
                    result["dmpt"]["profile_id"] = profile_match.group(1)
                    result["dmpt"]["domain"] = profile_match.group(2)

                # Process product data if found
                if product_match:
                    product_json = product_match.group(1)

                    # Clean up the JSON string
                    # Remove trailing commas (which are valid in JS but not in JSON)
                    product_json = re.sub(r",\s*([}\]])", r"\1", product_json)
                    # Convert JS property names (without quotes) to JSON property names (with quotes)
                    product_json = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', product_json)
                    # Handle escaped slashes in URLs
                    product_json = product_json.replace('\\"', '"')

                    try:
                        # Parse the product JSON
                        product_data = orjson.loads(product_json)
                        result["dmpt"]["viewed_product"] = product_data
                    except orjson.JSONDecodeError as e:
                        print(f"Failed to parse dmPt viewed_product JSON: {e}")
                        print(f"JSON string: {product_json}")

                return result if result["dmpt"] else None

            except Exception as e:
                print(f"Error extracting dmPt data: {e}")

    return None


def extract_klaviyo_viewed_product(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Klaviyo viewed_product data from HTML using selectolax

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Klaviyo viewed_product data as a dictionary
    """
    # Find the script tag with id="viewed_product"
    script_tag = parser.css_first("script#viewed_product")

    if script_tag:
        script_text = script_tag.text()
        if script_text and "var item" in script_text:
            # Extract the item data using regex
            match = re.search(r"var\s+item\s*=\s*(\{[^;]*?\});", script_text, re.DOTALL)
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Replace single quotes with double quotes
                json_str = json_str.replace("'", '"')
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle escaped sequences
                json_str = json_str.replace("\\u0026", "&")

                try:
                    # Parse the JSON string
                    data = orjson.loads(json_str)
                    return data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse Klaviyo JSON: {e}")
                    print(f"JSON string: {json_str}")

    return None


def extract_drip_product_view(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Drip recordProductView data from HTML using selectolax

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Drip recordProductView data as a dictionary
    """
    # Find all script tags
    script_tags = parser.css("script[type='text/javascript']")

    for script in script_tags:
        script_text = script.text()
        if script_text and "_dcq.push" in script_text and "recordProductView" in script_text:
            # Extract the recordProductView data using regex
            match = re.search(
                r"_dcq\.push\s*\(\s*\[\s*\"recordProductView\"\s*,\s*(\{.*?\})\s*\]", script_text, re.DOTALL
            )
            if match:
                # Get the JSON string
                json_str = match.group(1)

                # Clean up the JSON string
                # Remove trailing commas (which are valid in JS but not in JSON)
                json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
                # Replace single quotes with double quotes
                json_str = json_str.replace("'", '"')
                # Convert JS property names (without quotes) to JSON property names (with quotes)
                json_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', json_str)
                # Handle HTML entities in strings
                json_str = (
                    json_str.replace("\\u003c", "<")
                    .replace("\\u003e", ">")
                    .replace("\\u003cli", "<li")
                    .replace("\\u003cul", "<ul")
                    .replace("\\u003c/li", "</li")
                    .replace("\\u003c/ul", "</ul")
                )

                try:
                    # Parse the JSON string
                    data = orjson.loads(json_str)
                    return data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse Drip JSON: {e}")
                    print(f"JSON string: {json_str}")

                    # Try a more aggressive approach to clean the JSON if the first attempt failed
                    try:
                        # Remove all escaped HTML tags that might cause issues
                        clean_json = re.sub(r'\\u003c[^"]+\\u003e', "", json_str)
                        data = orjson.loads(clean_json)
                        return data
                    except orjson.JSONDecodeError:
                        print(f"Failed to parse cleaned Drip JSON")

    return None


def extract_rivo_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Rivo product and shop data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Rivo data as a dictionary or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing window.Rivo initialization
    for script in script_tags:
        script_text = script.text()
        if script_text and "window.Rivo" in script_text:
            result = {"rivo": {}}

            # Extract shop information
            shop_match = re.search(r"window\.Rivo\.common\.shop\s*=\s*(\{.*?\});", script_text, re.DOTALL)
            if shop_match:
                shop_str = shop_match.group(1)

                # Clean up the JSON string
                shop_str = re.sub(r",\s*([}\]])", r"\1", shop_str)
                shop_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', shop_str)
                shop_str = shop_str.replace("'", '"')

                try:
                    shop_data = orjson.loads(shop_str)
                    result["rivo"]["shop"] = shop_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse Rivo shop JSON: {e}")
                    print(f"JSON string: {shop_str}")

            # Extract template information
            template_match = re.search(r'window\.Rivo\.common\.template\s*=\s*"([^"]+)"', script_text)
            if template_match:
                result["rivo"]["template"] = template_match.group(1)

            # Extract product information for product template
            if template_match and template_match.group(1) == "product":
                product_match = re.search(r"window\.Rivo\.common\.product\s*=\s*(\{.*?\});", script_text, re.DOTALL)
                if product_match:
                    product_str = product_match.group(1)

                    # Clean up the JSON string
                    product_str = re.sub(r",\s*([}\]])", r"\1", product_str)
                    product_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', product_str)
                    product_str = product_str.replace("'", '"')

                    try:
                        product_data = orjson.loads(product_str)
                        result["rivo"]["product"] = product_data
                    except orjson.JSONDecodeError as e:
                        print(f"Failed to parse Rivo product JSON: {e}")
                        print(f"JSON string: {product_str}")

            # Extract vapid_public_key if available
            vapid_key_match = re.search(r'window\.Rivo\.common\.vapid_public_key\s*=\s*"([^"]+)"', script_text)
            if vapid_key_match:
                result["rivo"]["vapid_public_key"] = vapid_key_match.group(1)

            # Check if we have any data in the result
            if len(result["rivo"]) > 0:
                return result

    return None


def extract_shopify_tracking_events(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Shopify tracking events data from analytics script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Shopify tracking events data or None if not found
    """
    # Find script tag with class="analytics"
    script_tag = parser.css_first("script.analytics")

    if not script_tag:
        return None

    script_text = script_tag.text()

    if not script_text or "ShopifyAnalytics.lib.track" not in script_text:
        return None

    result = {"tracking_events": []}

    # Extract all tracking events
    track_calls = re.finditer(r'ShopifyAnalytics\.lib\.track\(\s*"([^"]+)",\s*(\{[^}]+\})', script_text, re.DOTALL)

    for match in track_calls:
        event_name = match.group(1)
        event_data_str = match.group(2)

        # Clean up the JSON string
        # Remove trailing commas
        event_data_str = re.sub(r",\s*([}\]])", r"\1", event_data_str)
        # Convert JS property names to JSON format
        event_data_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', event_data_str)
        # Replace single quotes with double quotes
        event_data_str = event_data_str.replace("'", '"')
        # Handle escaped characters
        event_data_str = re.sub(r"\\([/])", r"\1", event_data_str)

        try:
            event_data = orjson.loads(event_data_str)
            result["tracking_events"].append({"name": event_name, "data": event_data})
        except orjson.JSONDecodeError as e:
            print(f"Failed to parse Shopify tracking event JSON: {e}")
            print(f"JSON string: {event_data_str}")

    # Extract shop information
    shop_id_match = re.search(r"shopId:\s*(\d+)", script_text)
    theme_id_match = re.search(r"themeId:\s*(\d+)", script_text)
    currency_match = re.search(r'currency:\s*"([^"]+)"', script_text)

    if shop_id_match:
        result["shop_id"] = int(shop_id_match.group(1))

    if theme_id_match:
        result["theme_id"] = int(theme_id_match.group(1))

    if currency_match:
        result["currency"] = currency_match.group(1)

    return result if result["tracking_events"] else None


def extract_afterpay_data(parser: LexborHTMLParser) -> dict | None:
    """
    Extract Afterpay configuration and product data from HTML script tags

    Args:
        parser: LexborHTMLParser instance

    Returns:
        dict: Extracted Afterpay data as a dictionary or None if not found
    """
    # Find all script tags
    script_tags = parser.css("script")

    # Look for script tag containing Afterpay variables
    for script in script_tags:
        script_text = script.text()
        if script_text and "afterpay_shop_currency" in script_text:
            result = {"afterpay": {}}

            # Extract shop data
            shop_currency_match = re.search(r'var\s+afterpay_shop_currency\s*=\s*"([^"]+)"', script_text)
            if shop_currency_match:
                result["afterpay"]["shop_currency"] = shop_currency_match.group(1)

            cart_currency_match = re.search(r'var\s+afterpay_cart_currency\s*=\s*"([^"]+)"', script_text)
            if cart_currency_match:
                result["afterpay"]["cart_currency"] = cart_currency_match.group(1)

            money_format_match = re.search(r'var\s+afterpay_shop_money_format\s*=\s*"([^"]+)"', script_text)
            if money_format_match:
                result["afterpay"]["shop_money_format"] = money_format_match.group(1)

            domain_match = re.search(r'var\s+afterpay_shop_permanent_domain\s*=\s*"([^"]+)"', script_text)
            if domain_match:
                result["afterpay"]["shop_permanent_domain"] = domain_match.group(1)

            theme_match = re.search(r'var\s+afterpay_theme_name\s*=\s*"([^"]+)"', script_text)
            if theme_match:
                result["afterpay"]["theme_name"] = theme_match.group(1)

            js_version_match = re.search(r'var\s+afterpay_js_snippet_version\s*=\s*"([^"]+)"', script_text)
            if js_version_match:
                result["afterpay"]["js_snippet_version"] = js_version_match.group(1)

            # Extract product data
            product_match = re.search(r"var\s+afterpay_product\s*=\s*(\{.*?\});", script_text, re.DOTALL)
            if product_match:
                product_str = product_match.group(1)

                # Clean up the JSON string
                product_str = re.sub(r",\s*([}\]])", r"\1", product_str)
                product_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', product_str)

                try:
                    product_data = orjson.loads(product_str)
                    result["afterpay"]["product"] = product_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse Afterpay product JSON: {e}")
                    print(f"JSON string: {product_str}")

            # Extract current variant data
            current_variant_match = re.search(
                r"var\s+afterpay_current_variant\s*=\s*(\{.*?\});", script_text, re.DOTALL
            )
            if current_variant_match:
                variant_str = current_variant_match.group(1)

                # Clean up the JSON string
                variant_str = re.sub(r",\s*([}\]])", r"\1", variant_str)
                variant_str = re.sub(r"([{,])\s*([a-zA-Z0-9_]+)\s*:", r'\1"\2":', variant_str)

                try:
                    variant_data = orjson.loads(variant_str)
                    result["afterpay"]["current_variant"] = variant_data
                except orjson.JSONDecodeError as e:
                    print(f"Failed to parse Afterpay current variant JSON: {e}")
                    print(f"JSON string: {variant_str}")

            # Extract cart total price
            cart_total_match = re.search(r"var\s+afterpay_cart_total_price\s*=\s*(\d+)", script_text)
            if cart_total_match:
                result["afterpay"]["cart_total_price"] = int(cart_total_match.group(1))

            return result

    return None


def extract_page_info(parser: LexborHTMLParser) -> dict | None:
    extractor_dict = {
        "drip_data": extract_drip_data,
        "gsf_data": extract_gsf_conversion_data,
        "shopify_data": extract_shopify_analytics_data,
        "variants_data": extract_variants_json,
        "bc_data": extract_bc_data,
        "wpm_data": extract_wpm_data_layer,
        "gtm_data": extract_gtm_datalayer,
        "gtm_update_data": extract_gtm_update_datalayer,
        "ga4_update_data": extract_ga4_update_datalayer,
        "gtag_data": extract_gtag_event_data,
        "shopify_web_pixels_data": extract_shopify_web_pixels_data,
        "og_data": extract_og_meta_data,
        "fb_pixel_data": extract_facebook_pixel_data,
        "json_ld_data": extract_json_ld_data,
        "json_ld_product": extract_product_from_json_ld,
        "dmpt_data": extract_dmpt_data,
        "klaviyo_viewed_product": extract_klaviyo_viewed_product,
        "drip_product_view": extract_drip_product_view,
        "rivo_data": extract_rivo_data,
        "shopify_tracking_events": extract_shopify_tracking_events,
        "afterpay_data": extract_afterpay_data,
        "gtm4wp_data": extract_gtm4wp_product_data,
        "sku_data": extract_skus,
    }

    result = {}

    for key, extractor in extractor_dict.items():
        data = extractor(parser)
        if data:
            result[key] = data

    return result
