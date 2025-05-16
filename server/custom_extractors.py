import re

from curl_cffi import requests
from extractors import extract_product_info
from price_parser import Price
from selectolax.lexbor import LexborHTMLParser


def get_text_or_none(element):
    if element:
        return element.text()
    return None


# Marketplace extractors


def dicksmith_extractor(parser: LexborHTMLParser, url: str):
    product_info = extract_product_info(parser, url)
    seller_a = parser.css_first("a[data-discover='true']")
    if seller_a:
        product_info["seller"] = seller_a.text()
    return product_info


def amazon_extractor(parser: LexborHTMLParser, url: str):
    product_info = {
        "sources": [],
        "variants": [],
    }

    price = get_text_or_none(parser.css_first("span.priceToPay"))
    seller = get_text_or_none(parser.css_first("a#sellerProfileTriggerId"))
    image = parser.css_first("img#landingImage").attributes.get("src")
    title = get_text_or_none(parser.css_first("span#productTitle")).strip()
    currency = ""
    availability = ""

    if price:
        parsed_price = Price.fromstring(price)
        price = parsed_price.amount_float

    product = {
        "price": price,
        "currency": currency,
        "availability": availability,
        "images": [image],
        "title": title,
        "mpn": "",
        "sku": "",
        "upc": "",
        "variant_id": "",
        "url": url,
    }

    product_info["variants"].append(product)
    product_info["sources"].append(
        {
            "source": "Amazon",
            "variations": [product],
        }
    )
    product_info["seller"] = seller

    return product_info


def ebay_extractor(parser, url):
    product_info = extract_product_info(parser, url)
    seller = get_text_or_none(parser.css_first(".x-sellercard-atf__info__about-seller a"))
    product_info["seller"] = seller
    return product_info


def kogan_extractor(parser, url):
    product_info = extract_product_info(parser, url)
    seller = get_text_or_none(parser.css_first("div._1wK-K a"))
    product_info["seller"] = seller
    return product_info


def mydeal_extractor(parser: LexborHTMLParser, url: str):
    product_info = extract_product_info(parser, url)
    regex = re.compile(r'"sellerName": \'(.*?)\',')
    regex_result = regex.search(parser.html)
    if regex_result:
        product_info["seller"] = regex_result.group(1)
    return product_info


def bunnings_extractor(parser: LexborHTMLParser, url: str):
    product_info = extract_product_info(parser, url)
    seller = parser.css_first("a[data-locator='sellerName']")
    if seller:
        product_info["seller"] = seller.text()
    return product_info


# Custom Extractors


def bcf_extractor(parser: LexborHTMLParser, url: str):
    product_info = extract_product_info(parser, url)
    last_part_of_url = url.split("/")[-1]
    product_id = last_part_of_url.split(".")[0]

    try:
        response = requests.get(
            f"https://apps.bazaarvoice.com/api/data/products.json?passkey=caiXwE96iTtmnYMqwqEvrNnPXXaLiIYEReuQk3eGoGfPc&locale=en_AU&allowMissing=true&apiVersion=5.4&filter=id:{product_id}"
        )
        response.raise_for_status()
        data = response.json()
        product_info["gtin"] = data["Results"][0]["EANs"][0]
    except Exception:
        pass

    return product_info


def chsmith_extractor(parser: LexborHTMLParser, url: str):
    product_info = extract_product_info(parser, url)
    specs_tr = parser.css_matches("#product-attribute-specs-table tr")
    for tr in specs_tr:
        key = tr.css_first("th").text()
        value = tr.css_first("td").text()
        product_info[key] = value
    return product_info


EXTRACTOR_DICT = {
    "dicksmith": dicksmith_extractor,
    "amazon": amazon_extractor,
    "ebay": ebay_extractor,
    "kogan": kogan_extractor,
    "mydeal": mydeal_extractor,
    "bunnings": bunnings_extractor,
    "bcf": bcf_extractor,
    "chsmith": chsmith_extractor,
}
