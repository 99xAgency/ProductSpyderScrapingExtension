from curl_cffi import requests
from extractors import extract_from_meta_tags
from selectolax.lexbor import LexborHTMLParser


def main():
    with open("power.html", "r") as f:
        resp = f.read()

    parser = LexborHTMLParser(resp)
    url = "https://www.powerland.com.au/beefeater-signature-3000e-5-burner-built-in-lpg-bbq-black-enamel-bs19952"

    extracted_data = extract_from_meta_tags(parser, url)

    if extracted_data:
        print(extracted_data)
    else:
        print("No data extracted")


if __name__ == "__main__":
    main()
