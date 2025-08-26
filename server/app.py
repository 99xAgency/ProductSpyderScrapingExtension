import base64
import json
import os
import queue
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, send_file
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

    url = request.json["url"]

    # Create a unique request ID
    request_id = str(uuid.uuid4())

    # Create a queue for this specific request
    with response_lock:
        response_queues[request_id] = queue.Queue()

    successfull_send = 0
    for client in client_list[:]:  # Create a copy of the list to safely iterate
        print("Sending to client")
        try:
            client.send(json.dumps({"type": "extractHtml", "url": url, "request_id": request_id}))
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

        return jsonify(parsed_data["result"])

    except queue.Empty:
        return jsonify({"error": "Request timed out"}), 504

    finally:
        # Clean up the queue after processing
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]


@app.route("/screenshot", methods=["POST"])
def take_screenshot():
    print("Taking screenshot")

    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Create a unique request ID
    request_id = str(uuid.uuid4())

    # Create a queue for this specific request
    with response_lock:
        response_queues[request_id] = queue.Queue()

    successful_send = 0
    for client in client_list[:]:  # Create a copy of the list to safely iterate
        print("Sending screenshot request to client")
        try:
            client.send(json.dumps({"type": "captureScreenshot", "url": url, "request_id": request_id}))
            successful_send += 1
        except Exception:
            print("Removing client")
            if client in client_list:
                client_list.remove(client)

    print(f"Successfully sent to {successful_send} clients")

    if successful_send == 0:
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

        # Save screenshot to file
        result = parsed_data.get("result", {})
        if "screenshot" in result:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}_{request_id[:8]}.png"
            filepath = os.path.join("screenshots", filename)

            # Create screenshots directory if it doesn't exist
            screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)

            # Create full path
            full_path = os.path.join(screenshots_dir, filename)

            # Decode base64 image and save
            try:
                # Remove data:image/png;base64, prefix if present
                image_data = result["screenshot"]
                if image_data.startswith("data:image"):
                    image_data = image_data.split(",")[1]

                with open(full_path, "wb") as f:
                    f.write(base64.b64decode(image_data))

                return jsonify({
                    "success": True, 
                    "screenshot_path": filepath, 
                    "filename": filename, 
                    "url": result.get("url", url)
                })
            except Exception as e:
                return jsonify({"error": f"Failed to save screenshot: {str(e)}"}), 500
        else:
            return jsonify({"error": "No screenshot data received"}), 500

    except queue.Empty:
        return jsonify({"error": "Screenshot request timed out"}), 504

    finally:
        # Clean up the queue after processing
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]


@app.route("/screenshot/<filename>", methods=["GET"])
def get_screenshot(filename):
    try:
        screenshot_path = os.path.join(os.path.dirname(__file__), "screenshots", filename)
        if os.path.exists(screenshot_path):
            return send_file(screenshot_path, mimetype="image/png")
        else:
            return jsonify({"error": "Screenshot not found"}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve screenshot: {str(e)}"}), 500


@app.route("/screenshots", methods=["GET"])
def list_screenshots():
    try:
        screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if not os.path.exists(screenshots_dir):
            return jsonify({"screenshots": []})

        screenshots = []
        for filename in os.listdir(screenshots_dir):
            if filename.endswith(".png"):
                filepath = os.path.join(screenshots_dir, filename)
                file_stats = os.stat(filepath)
                screenshots.append(
                    {
                        "filename": filename,
                        "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                        "size": file_stats.st_size,
                    }
                )

        # Sort by creation time, newest first
        screenshots.sort(key=lambda x: x["created"], reverse=True)
        return jsonify({"screenshots": screenshots})
    except Exception as e:
        return jsonify({"error": f"Failed to list screenshots: {str(e)}"}), 500


if __name__ == "__main__":
    WSGIServer(("127.0.0.1", 9999), app).serve_forever()
