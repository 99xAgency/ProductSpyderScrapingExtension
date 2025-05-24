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

  console.log(`Processing: ${url}`);

  const tab = await chrome.tabs.create({ url });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

  await Promise.race([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => waitForPageLoad(),
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 6000)),
  ]);

  await new Promise((resolve) => setTimeout(resolve, 3000));

  const html = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.documentElement.outerHTML,
  });

  const statusCode = await new Promise<number>((resolve) => {
    let isRedirected = false;

    const redirectListener = (
      details: chrome.webRequest.WebResponseHeadersDetails
    ) => {
      if (details.url === url) {
        isRedirected = true;
        chrome.webRequest.onBeforeRedirect.removeListener(redirectListener);
      }
    };

    chrome.webRequest.onBeforeRedirect.addListener(redirectListener, {
      urls: [url],
    });

    const listener = (details: chrome.webRequest.WebResponseCacheDetails) => {
      if (details.url === url) {
        chrome.webRequest.onCompleted.removeListener(listener);
        chrome.webRequest.onBeforeRedirect.removeListener(redirectListener);
        resolve(isRedirected ? 301 : details.statusCode);
      }
    };

    chrome.webRequest.onCompleted.addListener(listener, { urls: [url] });
    setTimeout(() => resolve(isRedirected ? 301 : 200), 10000);
  });

  await chrome.tabs.remove(tab.id);

  return {
    html: html[0].result,
    statusCode,
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
