import json
import queue
import threading

from custom_extractors import EXTRACTOR_DICT
from flask import Flask, jsonify, request
from flask_sock import Sock
from gevent import monkey
from gevent.pywsgi import WSGIServer
from selectolax.lexbor import LexborHTMLParser
from substring_processor import extract_domain_name

from extractors import extract_product_info

monkey.patch_all()

app = Flask(__name__)
sock = Sock(app)


client_list = []
data_queue = queue.Queue()

extract_data_lock = threading.Lock()


@sock.route("/ws")
def echo(sock):
    client_list.append(sock)
    while True:
        data = sock.receive()
        data_queue.put((sock, data))


@app.route("/extract-data", methods=["POST"])
def extract_data():
    print("Extracting data")

    urls = request.json
    successfull_send = 0
    for client in client_list:
        print("Sending to client")
        try:
            client.send(json.dumps({"type": "extractHtml", "urls": urls}))
            successfull_send += 1
        except Exception:
            print("Removing client")
            client_list.remove(client)

    print(f"Successfully sent to {successfull_send} clients")

    if successfull_send == 0:
        return jsonify({"error": "No client available"}), 500

    print("Waiting for data")

    _, data = data_queue.get(timeout=300)
    print(data)

    parsed_data = json.loads(data)

    product_info = []

    for url, html in zip(urls, parsed_data["htmls"]):
        domain = extract_domain_name(url)
        extractor = extract_product_info
        if domain in EXTRACTOR_DICT:
            extractor = EXTRACTOR_DICT[domain]
        parser = LexborHTMLParser(html)
        product_info.append(extractor(parser, url))

    return jsonify(product_info)


if __name__ == "__main__":
    WSGIServer(("127.0.0.1", 9999), app).serve_forever()
