import base64
import io
import json
import os
import queue
import threading
import uuid
from datetime import datetime

import requests
from flask import Flask, jsonify, request
from flask_sock import Sock
from gevent import monkey
from gevent.pywsgi import WSGIServer
from PIL import Image

monkey.patch_all()

app = Flask(__name__)
sock = Sock(app)

# Create screenshots directory if it doesn't exist
SCREENSHOTS_DIR = "screenshots"
if not os.path.exists(SCREENSHOTS_DIR):
    os.makedirs(SCREENSHOTS_DIR)

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


@app.route("/screenshot", methods=["POST"])
def capture_screenshot():
    print("Capturing screenshot")

    data = request.json
    urls = data.get("urls", [])

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    # Create a unique request ID
    request_id = str(uuid.uuid4())

    # Create a queue for this specific request
    with response_lock:
        response_queues[request_id] = queue.Queue()

    successfull_send = 0
    for client in client_list[:]:  # Create a copy of the list to safely iterate
        print("Sending screenshot request to client")
        try:
            client.send(json.dumps({"type": "captureScreenshot", "urls": urls, "request_id": request_id}))
            successfull_send += 1
        except Exception:
            print("Removing client")
            if client in client_list:
                client_list.remove(client)

    print(f"Successfully sent screenshot request to {successfull_send} clients")

    if successfull_send == 0:
        # Clean up the queue if no clients are available
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]
        return jsonify({"error": "No client available"}), 500

    print(f"Waiting for screenshot data for request {request_id}")

    try:
        # Wait for response with timeout
        with response_lock:
            response_queue = response_queues[request_id]

        parsed_data = response_queue.get(timeout=300)

        # Process screenshots and save them to files
        processed_results = []
        for result in parsed_data["results"]:
            if "screenshot" in result and result["screenshot"]:
                # Generate filename with timestamp and URL hash
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                url_hash = str(hash(result["url"]))[-8:]  # Last 8 chars of hash
                filename = f"screenshot_{timestamp}_{url_hash}.png"
                filepath = os.path.join(SCREENSHOTS_DIR, filename)

                # Remove the data URL prefix if present
                screenshot_data = result["screenshot"]
                if screenshot_data.startswith("data:image/png;base64,"):
                    screenshot_data = screenshot_data.split(",")[1]

                try:
                    # Decode base64 and save as image
                    image_data = base64.b64decode(screenshot_data)
                    image = Image.open(io.BytesIO(image_data))
                    image.save(filepath)

                    processed_results.append(
                        {"filename": filename, "dimensions": result.get("dimensions", {}), "url": result["url"]}
                    )
                    print(f"Saved screenshot: {filename}")
                except Exception as e:
                    print(f"Error saving screenshot: {e}")
                    processed_results.append({"error": f"Failed to save screenshot: {str(e)}", "url": result["url"]})
            else:
                processed_results.append({"error": "No screenshot data received", "url": result["url"]})

        return jsonify(processed_results)

    except queue.Empty:
        return jsonify({"error": "Screenshot request timed out"}), 504

    finally:
        # Clean up the queue after processing
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]


if __name__ == "__main__":
    WSGIServer(("127.0.0.1", 9999), app).serve_forever()
