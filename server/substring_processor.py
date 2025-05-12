import re
from urllib.parse import urlparse


def find_keys(data, target_key):
    results = []

    if isinstance(data, dict):
        if target_key in data:
            results.append(data[target_key])
        for value in data.values():
            results.extend(find_keys(value, target_key))

    elif isinstance(data, (list, tuple)):
        for item in data:
            results.extend(find_keys(item, target_key))

    return results


def remove_query_parameters(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"


def extract_domain_name(url):
    pattern = r"(?:(?:https?:)?\/\/)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

    match = re.search(pattern, url)
    if match:
        domain_parts = match.group(1).split(".")
        if len(domain_parts) > 2:
            return domain_parts[-3]
        return domain_parts[-2]
    return None


def extract_country_code(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    country_code = domain.split(".")[-1]
    return country_code


def find_parent(json_obj, target_key, target_value):
    """
    This function will find the parent object of the target key-value pair in a nested JSON object.
    {
        "name": "Random",
        "age": 30,
        "product": {
            "type": "electronics",
            "price": 200,
        }
    }

    find_parent(json_obj, "price", 200) => {"type": "electronics", "price": 200}
    """

    if isinstance(json_obj, dict):
        if target_key in json_obj and json_obj[target_key] == target_value:
            return json_obj
        else:
            for key, value in json_obj.items():
                result = find_parent(value, target_key, target_value)
                if result is not None:
                    return result
    elif isinstance(json_obj, list):
        for item in json_obj:
            result = find_parent(item, target_key, target_value)
            if result is not None:
                return result

    return None


def fuzzy_search_value(item, *target):
    """
    Finds a susbsting in a nested JSON object.
    """

    if isinstance(item, dict):
        for key, value in item.items():
            if isinstance(value, (dict, list, tuple)):
                result = fuzzy_search_value(value, *target)
                if result is not None:
                    return result
            elif isinstance(value, str) and any(t in value for t in target):
                return value

    elif isinstance(item, (list, tuple)):
        for i, value in enumerate(item):
            if isinstance(value, (dict, list, tuple)):
                result = fuzzy_search_value(value, *target)
                if result is not None:
                    return result
            elif isinstance(value, str) and any(t in value for t in target):
                return value

    return None


def get_origin_url(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"
