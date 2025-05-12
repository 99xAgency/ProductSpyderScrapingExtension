import re
from urllib.parse import urlparse

import orjson
from substring_processor import find_parent, fuzzy_search_value

availability_struct = {
    "OutOfStock": "OUT OF STOCK",
    "InStock": "IN STOCK",
    "LimitedAvailability": "IN STOCK",
    "SoldOut": "OUT OF STOCK",
    "in_stock": "IN STOCK",
    "OnlineOnly": "IN STOCK",
    "instock": "IN STOCK",
    "outofstock": "OUT OF STOCK",
}

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
        "meta[property='product:price:currency']",
        "meta[property='og:price:currency']",
        "meta[property='price:currency']",
        "meta[itemprop='priceCurrency']",
        "meta[_itemprop='priceCurrency']",
    ]
)

TITLE_META = ",".join(
    [
        "meta[property='og:title']",
        "meta[property='product:name']",
        "meta[property='product:name']",
        "meta[property='og:title']",
        "meta[property='name']",
        "meta[itemprop='itemOffered']",
        ".wpr-product-title",
    ]
)

IMAGE_META = ",".join(
    [
        "meta[property='og:image']",
        "meta[property='og:image:url']",
        "meta[property='og:image:secure_url']",
        "meta[property='og:image:secure_url']",
        ".woocommerce-product-gallery__image img",
    ]
)

AVAILABILITY_META = ",".join(
    [
        "meta[property='og:availability']",
        "meta[property='availability']",
        "meta[property='product:availability']",
        "meta[property='availability']",
    ]
)


def filter_unique_price_variants(variants):
    unique_prices = set()
    filtered_variants = []

    for variant in variants:
        if variant.get("price") not in unique_prices:
            unique_prices.add(variant.get("price"))
            filtered_variants.append(variant)

    return filtered_variants


def format_resource_url(resource_url, main_url):
    base_url = f"{urlparse(main_url).scheme}://{urlparse(main_url).netloc}"

    if not resource_url:
        return ""

    if resource_url.startswith("http"):
        return resource_url

    if resource_url.startswith("//"):
        return f"https:{resource_url}"

    if resource_url.startswith("/"):
        return f"{base_url}{resource_url}"

    return f"{base_url}/{resource_url}"


def extract_from_gsf_conversion_data(parser, url):
    try:
        script_tags = parser.css("script")

        pattern = r"var gsf_conversion_data = ({.*?});"

        # Process each script tag
        for script in script_tags:
            if script.text():
                # Look for the variable declaration
                match = re.search(pattern, script.text(), re.DOTALL)
                if match:
                    json_str = match.group(1)
                    json_str = json_str.replace("'", '"')
                    json_str = re.sub(r"([{,\s])(\w+)\s*:", r'\1"\2":', json_str)

                    data = orjson.loads(json_str)

                    variants_list = []

                    for product in data["data"]["product_data"]:
                        variant_data = {
                            "name": product.get("name", ""),
                            "variant_id": str(product.get("variant_id", "")),
                            "sku": product.get("sku", ""),
                            "mpn": "",
                            "upc": "",
                            "price": str(product.get("price", "")),
                            "currency": product.get("currency", ""),
                            "availability": "N/A",
                            "url": "",
                            "images": [],
                        }
                        variants_list.append(variant_data)

                    # Nest all variants under 'variants' key
                    formatted_data = {"source": "GSF Conversion Data", "variations": variants_list}

                    return formatted_data

        return None

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return None


def extract_from_ld_json(parser, url):
    js_ld_script = parser.css("script[type='application/ld+json']")
    schema_data = []

    for script in js_ld_script:
        try:
            schema_data.append(orjson.loads(script.text()))
        except orjson.JSONDecodeError:
            pass

    product = find_parent(schema_data, "@type", "Product")

    if not product:
        return None

    offers = product.get("offers", [])

    if not isinstance(offers, list):
        offers = [offers]

    variations = []

    sku = product.get("sku", "")
    mpn = product.get("mpn", "")
    upc = product.get("gtin12") or product.get("gtin13") or product.get("gtin14") or product.get("gtin8") or ""

    name = product.get("name", "")
    image = product.get("image", {})

    fuzzy_search_image = fuzzy_search_value(image, "jpg", "jpeg", "png", "webp")

    images = []

    if fuzzy_search_image:
        images = [format_resource_url(fuzzy_search_image, url)]

    for offer in offers:
        variant_price_specification = offer.get("priceSpecification", {})
        currency = offer.get("priceCurrency", "")

        price = offer.get("price")

        if variant_price_specification:
            if isinstance(variant_price_specification, list):
                variant_price_specification = variant_price_specification[0]
            price = variant_price_specification.get("price")
            currency = variant_price_specification.get("priceCurrency")

        variations.append(
            {
                "name": name,
                "variant_id": offer.get("sku", "") or sku,
                "sku": offer.get("sku", "") or sku,
                "mpn": offer.get("mpn", "") or mpn,
                "upc": offer.get("gtin12") or offer.get("gtin13") or offer.get("gtin14") or offer.get("gtin8") or upc,
                "price": price,
                "currency": currency,
                "availability": availability_struct.get(offer.get("availability", "").split("/")[-1], "N/A"),
                "url": offer.get("url", ""),
                "images": images,
            }
        )

    return {"source": "LD+JSON", "variations": filter_unique_price_variants(variations)}


def extract_from_shopify_analytics(parser, url):
    image_meta = parser.css_first(IMAGE_META)
    availability_meta = parser.css_first(AVAILABILITY_META)

    image = ""
    availability = "N/A"

    if image_meta:
        image = image_meta.attributes.get("content") or image.text()
        image = format_resource_url(image, url)

    if availability_meta:
        availability = availability_meta.attributes.get("content") or availability_meta.text()
        availability = availability_struct.get(availability, "N/A")

    for node in parser.css("script"):
        if node.text() and re.search(r"window.ShopifyAnalytics", node.text()):
            currency_match = re.search(r"window.ShopifyAnalytics.meta.currency = \'(\w+)\';", node.text())
            currency = currency_match.group(1) if currency_match else ""
            match = re.search(r"var meta = ({.*});", node.text(), re.DOTALL)
            if not match:
                return None
            try:
                meta = orjson.loads(match.group(1))
                product = meta.get("product", {})
                variants = product.get("variants", [])
                if not variants:
                    return None
                variants_json_node = parser.css_first("script[data-variants-json]")
                variant_images = {}
                if variants_json_node:
                    variants_data = orjson.loads(variants_json_node.text())
                    for v in variants_data:
                        img = v.get("featured_image")
                        variant_images[str(v["id"])] = img.get("src", "") if isinstance(img, dict) else img or ""
                variations = []
                for variant in variants:
                    variation = {
                        "name": variant.get("name") or product.get("public_title", ""),
                        "variant_id": str(variant.get("id", "")),
                        "sku": variant.get("sku", ""),
                        "mpn": "",
                        "upc": "",
                        "price": "{:.2f}".format(variant.get("price", 0) / 100),
                        "currency": currency,
                        "availability": availability,
                        "url": "",
                        "images": [image],
                    }
                    variations.append(variation)
                return {"source": "Shopify Analytics", "variations": filter_unique_price_variants(variations)}

            except orjson.JSONDecodeError:
                return None
    return None


def extract_from_wpm_data_layer(parser, url):
    script_tags = parser.css("script")

    pattern = r"window\.wpmDataLayer\.products\[\d+\]\s*=\s*({[\s\S]*?});"

    for script in script_tags:
        if script.text():
            script_text = script.text().strip()
            match = re.search(pattern, script_text, re.MULTILINE)
            if match:
                js_str = match.group(1).strip()

                js_str = re.sub(r"([{,\s])(\w+)\s*:", r'\1"\2":', js_str)
                js_str = js_str.replace("'", '"')

                try:
                    data = orjson.loads(js_str)
                except (ValueError, SyntaxError) as e:
                    return None

                variant_data = {
                    "name": data.get("name", ""),
                    "variant_id": data.get("sku", ""),
                    "sku": data.get("sku", ""),
                    "mpn": "",
                    "upc": "",
                    "price": str(data.get("price", "")),
                    "currency": data.get("currency", ""),
                    "availability": "IN STOCK" if data.get("quantity", 0) > 0 else "OUT OF STOCK",
                    "url": "",
                    "images": [],
                }

                return {
                    "source": "WPM Data Layer",
                    "variations": [variant_data],
                }

    return None


def extract_from_bc_data(parser, url):
    script_tags = parser.css("script")

    pattern = r"var\s+BCData\s*=\s*({[\s\S]*?});"

    for script in script_tags:
        if script.text():
            script_text = script.text().strip()

            match = re.search(pattern, script_text, re.MULTILINE)
            if match:
                js_str = match.group(1).strip()

                js_str = re.sub(r"([{,\s])(\w+)\s*:", r'\1"\2":', js_str)
                js_str = js_str.replace("'", '"')

                try:
                    data = orjson.loads(js_str)
                except (ValueError, SyntaxError) as e:
                    return None

                product = data.get("product_attributes", {})

                price_data = product.get("price", {}).get("with_tax", {})
                variant_data = {
                    "name": "",
                    "variant_id": product.get("sku", ""),
                    "sku": product.get("sku", ""),
                    "mpn": product.get("mpn", "") if product.get("mpn") is not None else "",
                    "upc": product.get("upc", "") or product.get("gtin", ""),
                    "price": str(price_data.get("value", "")),
                    "currency": price_data.get("currency", ""),
                    "availability": "IN STOCK" if product.get("instock", False) else "OUT OF STOCK",
                    "url": "",
                    "images": [product.get("image", "")] if product.get("image") else [],
                }

                formatted_data = {"source": "BC Data", "variations": [variant_data]}

                return formatted_data

    return None


def extract_from_meta_tags(parser, url):
    currency_meta = parser.css_first(CURRENCY_META)
    price_meta = parser.css_first(PRICE_META)
    title_meta = parser.css_first(TITLE_META)
    image_meta = parser.css_first(IMAGE_META)
    availability_meta = parser.css_first(AVAILABILITY_META)

    price = None
    currency = ""
    images = []
    availability = ""

    if currency_meta:
        currency = currency_meta.attributes.get("content") or currency_meta.text()

    if price_meta:
        price = price_meta.attributes.get("content") or price_meta.text()

    if title_meta:
        title = title_meta.attributes.get("content") or title_meta.text()

    if image_meta:
        image = image_meta.attributes.get("content") or image_meta.text()
        image = format_resource_url(image, url)
        images = [image]

    if availability_meta:
        availability = availability_meta.attributes.get("content") or availability_meta.text
        availability = availability_struct.get(availability, "N/A")

    if not price:
        return None

    return {
        "source": "META TAGS",
        "variations": [
            {
                "name": title,
                "variant_id": "",
                "sku": "",
                "mpn": "",
                "upc": "",
                "price": price,
                "currency": currency,
                "availability": "",
                "images": images,
            }
        ],
    }


def extract_from_gtm_or_ga4(parser, url):
    script_tags = parser.css("script")

    pattern = r"(GTM|GA4)\.updateDataLayerByJson\((.*?)\);"

    for script in script_tags:
        if script.text():
            script_text = script.text().strip()

            match = re.search(pattern, script_text, re.MULTILINE | re.DOTALL)
            if match:
                js_str = match.group(2).strip()

                js_str = re.sub(r"([{,\s])(\w+)\s*:", r'\1"\2":', js_str)
                js_str = js_str.replace("'", '"')

                data = orjson.loads(js_str)

                products = data.get("ecommerce", {}).get("detail", {}).get("products", []) or data.get(
                    "ecommerce", {}
                ).get("items", [])

                variants_list = []

                for product in products:
                    variant_data = {
                        "name": product.get("name", "") or product.get("item_name", ""),
                        "variant_id": product.get("id", "") or product.get("item_id", ""),
                        "sku": product.get("id", "") or product.get("item_id", ""),
                        "mpn": "",
                        "upc": "",
                        "price": str(product.get("price", "")),
                        "currency": product.get("currency", "AUD"),
                        "availability": "N/A",
                        "url": "",
                        "images": [],
                    }
                    variants_list.append(variant_data)

                return {
                    "source": "GTM/GA4 Data Layer",
                    "variations": variants_list,
                }

    return None


def extract_product_info(parser, url):
    results = []
    extractors = [
        extract_from_ld_json,
        extract_from_shopify_analytics,
        extract_from_meta_tags,
        extract_from_gsf_conversion_data,
        extract_from_bc_data,
        extract_from_wpm_data_layer,
        extract_from_gtm_or_ga4,
    ]

    main_variants = []
    highest_count = 0

    for extractor in extractors:
        try:
            result = extractor(parser, url)
            if result:
                results.append(result)

            if result and len(result["variations"]) > highest_count:
                main_variants = result["variations"]
                highest_count = len(result["variations"])
        except Exception:
            pass

    for main_variant in main_variants:
        if not main_variant.get("images"):
            image_meta = parser.css_first(IMAGE_META)
            if image_meta:
                image = image_meta.attributes.get("content") or image_meta.text()
                image = format_resource_url(image, url)
                main_variant["images"] = [image]

        if not main_variant.get("name"):
            title_meta = parser.css_first(TITLE_META)
            title_tag = parser.css_first("title")

            if title_meta:
                title = title_meta.attributes.get("content") or title_meta.text()
            elif title_tag:
                title = title_tag.text()

            main_variant["name"] = title or ""

        if not main_variant.get("currency"):
            currency_meta = parser.css_first(CURRENCY_META)
            if currency_meta:
                main_variant["currency"] = currency_meta.attributes.get("content") or currency_meta.text()

    return {
        "variants": main_variants,
        "sources": results,
    }
