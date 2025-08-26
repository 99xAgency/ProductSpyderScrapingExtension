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
    status_code: statusCode[0].result,
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

  const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: 'png',
    quality: 90
  });

  const currentUrl = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.location.href,
  });

  await chrome.tabs.remove(tab.id);

  return {
    screenshot: screenshot,
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
      const { type, url, request_id } = JSON.parse(event.data);
      if (type == "extractHtml") {
        const extractedData = await extractHtml(url);
        this.send(
          JSON.stringify({
            type: "extractHtml",
            result: extractedData,
            request_id,
          })
        );
      } else if (type == "captureScreenshot") {
        const screenshotData = await captureScreenshot(url);
        this.send(
          JSON.stringify({
            type: "captureScreenshot",
            result: screenshotData,
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
