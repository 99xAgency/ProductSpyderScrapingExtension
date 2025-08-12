const extractHtml = async (url: string) => {
  const waitForPageLoad = () => {
    return new Promise((resolve) => {
      if (document.readyState === "complete") {
        resolve(null);
      } else {
        document.addEventListener("readystatechange", () => {
          if (document.readyState === "complete") {
            resolve(null);
          }
        });
      }
    });
  };

  const getStatusCode = (originalUrl: string) => {
    return new Promise((resolve) => {
      const currentUrl = window.location.href;
      if (currentUrl !== originalUrl) {
        resolve(301);
      }
      const entries: any = window.performance.getEntries();
      if (entries.length > 0) {
        resolve(entries[0].responseStatus || 200);
      } else {
        resolve(200);
      }
    });
  };

  console.log(`Processing: ${url}`);

  const tab = await chrome.tabs.create({ url });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

  await Promise.race([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: waitForPageLoad,
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 10000)),
  ]);

  await new Promise((resolve) => setTimeout(resolve, 3000));

  const html = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.documentElement.outerHTML,
  });

  const statusCode = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: getStatusCode,
    args: [url],
  });

  const currentUrl = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.location.href,
  });

  await chrome.tabs.remove(tab.id);

  return {
    html: html[0].result,
    statusCode: statusCode[0].result,
    url: currentUrl[0].result,
  };
};

const captureScreenshot = async (url: string) => {
  const waitForPageLoad = () => {
    return new Promise((resolve) => {
      if (document.readyState === "complete") {
        resolve(null);
      } else {
        document.addEventListener("readystatechange", () => {
          if (document.readyState === "complete") {
            resolve(null);
          }
        });
      }
    });
  };

  const getPageDimensions = () => {
    return {
      width: Math.max(
        document.documentElement.scrollWidth,
        document.body.scrollWidth,
        document.documentElement.offsetWidth,
        document.body.offsetWidth,
        document.documentElement.clientWidth
      ),
      height: Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight,
        document.documentElement.offsetHeight,
        document.body.offsetHeight,
        document.documentElement.clientHeight
      ),
    };
  };

  console.log(`Capturing screenshot for: ${url}`);

  const tab = await chrome.tabs.create({ url });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

  await Promise.race([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: waitForPageLoad,
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 10000)),
  ]);

  await new Promise((resolve) => setTimeout(resolve, 3000));

  // Get page dimensions
  const dimensions = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: getPageDimensions,
  });

  const { width, height } = dimensions[0].result || {
    width: 1920,
    height: 1080,
  };

  // Capture the screenshot
  const screenshot = await chrome.tabs.captureVisibleTab(tab.id, {
    format: "png",
    quality: 100,
  });

  // If the page is larger than the viewport, we need to capture it in parts
  let fullScreenshot = screenshot;

  if (height > 800) {
    // If page height is greater than typical viewport
    // For now, we'll capture the visible area
    // In a more advanced implementation, you could scroll and stitch multiple screenshots
    console.log("Page is taller than viewport, capturing visible area only");
  }

  const currentUrl = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.location.href,
  });

  await chrome.tabs.remove(tab.id);

  return {
    screenshot: fullScreenshot,
    dimensions: { width, height },
    url: currentUrl[0].result,
  };
};

class WebSocketManager {
  url: string;
  ws: WebSocket | null;
  reconnectDelay: number;

  constructor(url: string) {
    this.url = url;
    this.ws = null;
    this.reconnectDelay = 1000;
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log("WebSocket connected");
    };

    this.ws.onmessage = async (event) => {
      const { type, urls, request_id } = JSON.parse(event.data);
      if (type == "extractHtml") {
        console.log("Received extractHtml request");
        let mergedData = [];
        for (const url of urls) {
          mergedData.push(await extractHtml(url));
        }
        console.log("Sending extractHtml response");
        this.send(
          JSON.stringify({
            type: "extractHtml",
            results: mergedData,
            request_id,
          })
        );
      } else if (type == "captureScreenshot") {
        console.log("Received captureScreenshot request");
        let mergedData = [];
        for (const url of urls) {
          mergedData.push(await captureScreenshot(url));
        }
        console.log("Sending captureScreenshot response");
        this.send(
          JSON.stringify({
            type: "captureScreenshot",
            results: mergedData,
            request_id,
          })
        );
      }
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    this.ws.onclose = () => {
      console.log(`Reconnecting in ${this.reconnectDelay}ms...`);
      setTimeout(() => {
        this.connect();
      }, this.reconnectDelay);
    };
  }

  send(data: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    } else {
      console.warn("WebSocket not connected");
    }
  }

  close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

new WebSocketManager("ws://127.0.0.1:9999/ws");

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "ping") {
    sendResponse("pong");
  }
});
