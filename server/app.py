import base64
import io
import json
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_sock import Sock
from gevent import monkey
from gevent.pywsgi import WSGIServer
from PIL import Image

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


def process_screenshot(result):
    """Process screenshot segments and stitch them together if needed."""
    if not result.get("screenshots"):
        return None
    
    screenshots = result["screenshots"]
    segments_info = result.get("segments", [])
    dimensions = result.get("dimensions", {})
    
    # If we only have one screenshot, return it directly
    if len(screenshots) == 1:
        img_data = screenshots[0].split(",")[1]
        img_bytes = base64.b64decode(img_data)
        return Image.open(io.BytesIO(img_bytes))
    
    # Multiple segments - need to stitch them together
    full_width = dimensions.get("width", 0)
    full_height = dimensions.get("height", 0)
    
    if not full_width or not full_height:
        # Fallback: return the first segment if dimensions are missing
        img_data = screenshots[0].split(",")[1]
        img_bytes = base64.b64decode(img_data)
        return Image.open(io.BytesIO(img_bytes))
    
    # Create a new image with the full dimensions
    stitched_image = Image.new("RGB", (full_width, full_height), color="white")
    
    # Paste each segment into the correct position
    for i, screenshot_data in enumerate(screenshots):
        # Get segment info
        if i < len(segments_info):
            segment = segments_info[i]
            x = segment.get("x", 0)
            y = segment.get("y", 0)
        else:
            # Fallback if segment info is missing
            x = 0
            y = 0
        
        # Decode and paste the segment
        img_data = screenshot_data.split(",")[1]
        img_bytes = base64.b64decode(img_data)
        segment_img = Image.open(io.BytesIO(img_bytes))
        
        stitched_image.paste(segment_img, (x, y))
    
    return stitched_image


@app.route("/screenshot", methods=["POST"])
def capture_screenshot():
    """Capture full page screenshots of the provided URLs."""
    print("Capturing screenshots")

    urls = request.json

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    # Create screenshots directory if it doesn't exist
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)

    # Create a unique request ID
    request_id = str(uuid.uuid4())

    # Create a queue for this specific request
    with response_lock:
        response_queues[request_id] = queue.Queue()

    successful_send = 0
    for client in client_list[:]:
        print("Sending screenshot request to client")
        try:
            client.send(json.dumps({"type": "captureScreenshot", "urls": urls, "request_id": request_id}))
            successful_send += 1
        except Exception:
            print("Removing client")
            if client in client_list:
                client_list.remove(client)

    print(f"Successfully sent to {successful_send} clients")

    if successful_send == 0:
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

        # Process the screenshot results
        results = []
        for result in parsed_data["results"]:
            if "error" in result:
                results.append({"url": result["url"], "error": result["error"]})
            else:
                # Process the screenshot (handles both single and multi-segment)
                screenshot_image = process_screenshot(result)

                if screenshot_image:
                    # Generate filename
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"screenshot_{timestamp}_{uuid.uuid4().hex[:8]}.png"
                    filepath = screenshots_dir / filename

                    # Save the image
                    screenshot_image.save(filepath, "PNG")

                    results.append(
                        {
                            "url": result["url"],
                            "filename": filename,
                            "path": str(filepath),
                            "dimensions": result["dimensions"],
                        }
                    )
                else:
                    results.append({"url": result["url"], "error": "Failed to process screenshot"})

        return jsonify({"screenshots": results})

    except queue.Empty:
        return jsonify({"error": "Request timed out"}), 504

    finally:
        # Clean up the queue after processing
        with response_lock:
            if request_id in response_queues:
                del response_queues[request_id]


@app.route("/screenshots/<filename>", methods=["GET"])
def serve_screenshot(filename):
    """Serve a screenshot file."""
    screenshots_dir = Path("screenshots")
    filepath = screenshots_dir / filename

    if not filepath.exists():
        return jsonify({"error": "Screenshot not found"}), 404

    return send_file(filepath, mimetype="image/png")


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
