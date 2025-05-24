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

  const simulateHumanScrolling = () => {
    return new Promise((resolve) => {
      const scrollHeight = document.documentElement.scrollHeight;
      const viewportHeight = window.innerHeight;
      let currentScroll = 0;

      const scroll = () => {
        if (currentScroll >= scrollHeight - viewportHeight) {
          resolve(null);
          return;
        }

        // Random scroll amount between 100 and 400 pixels
        const scrollAmount = Math.floor(Math.random() * 300) + 100;
        currentScroll += scrollAmount;

        // Ensure we don't scroll past the bottom
        currentScroll = Math.min(currentScroll, scrollHeight - viewportHeight);

        window.scrollTo({
          top: currentScroll,
          behavior: "smooth",
        });

        // Random pause between 500ms and 2000ms
        const pause = Math.floor(Math.random() * 1500) + 500;
        setTimeout(scroll, pause);
      };

      // Start scrolling
      scroll();
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

  // Add human-like scrolling behavior
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => simulateHumanScrolling(),
  });

  const html = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.documentElement.outerHTML,
  });

  await chrome.tabs.remove(tab.id);

  return html[0].result;
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
          JSON.stringify({ type: "extractHtml", htmls: mergedData, request_id })
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
