import json
import queue
import threading
import uuid

from flask import Flask, jsonify, request
from flask_sock import Sock
from gevent import monkey
from gevent.pywsgi import WSGIServer

monkey.patch_all()

app = Flask(__name__)
sock = Sock(app)


client_list = []
response_queues = {}
response_lock = threading.Lock()


@sock.route("/ws")
def echo(sock):
    client_list.append(sock)
    while True:
        try:
            data = sock.receive()
            parsed_data = json.loads(data)

            if "request_id" in parsed_data:
                request_id = parsed_data["request_id"]
                with response_lock:
                    if request_id in response_queues:
                        response_queues[request_id].put(parsed_data)
        except Exception as e:
            print(f"Error with websocket: {e}")
            if sock in client_list:
                client_list.remove(sock)
            break


@app.route("/fetch", methods=["POST"])
def extract_data():
    print("Extracting data")

    urls = request.json

    # Create a unique request ID
    request_id = str(uuid.uuid4())

    # Create a queue for this specific request
    with response_lock:
        response_queues[request_id] = queue.Queue()

    successfull_send = 0
    for client in client_list[:]:  # Create a copy of the list to safely iterate
        print("Sending to client")
        try:
            client.send(json.dumps({"type": "extractHtml", "urls": urls, "request_id": request_id}))
            successfull_send += 1
        except Exception:
            print("Removing client")
            if client in client_list:
                client_list.remove(client)

    print(f"Successfully sent to {successfull_send} clients")

    if successfull_send == 0:
        # Clean up the queue if no clients are available
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]
        return jsonify({"error": "No client available"}), 500

    print(f"Waiting for data for request {request_id}")

    try:
        # Wait for response with timeout
        with response_lock:
            response_queue = response_queues[request_id]

        parsed_data = response_queue.get(timeout=300)

        return jsonify(parsed_data["results"])

    except queue.Empty:
        return jsonify({"error": "Request timed out"}), 504

    finally:
        # Clean up the queue after processing
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]


if __name__ == "__main__":
    WSGIServer(("127.0.0.1", 9999), app).serve_forever()
