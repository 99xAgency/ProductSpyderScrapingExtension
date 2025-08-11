const captureFullPageScreenshot = async (url: string) => {
  console.log(`Capturing screenshot: ${url}`);

  const tab = await chrome.tabs.create({ url });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

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

  // Wait for page to load
  await Promise.race([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: waitForPageLoad,
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 10000)),
  ]);

  // Additional wait for dynamic content
  await new Promise((resolve) => setTimeout(resolve, 3000));

  try {
    // Attach debugger to the tab
    await chrome.debugger.attach({ tabId: tab.id }, "1.3");

    // Get page metrics for full page dimensions
    const metrics = await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Page.getLayoutMetrics"
    ) as any;

    const { width, height } = metrics.contentSize;

    // Set device metrics to capture full page
    await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Emulation.setDeviceMetricsOverride",
      {
        width: Math.ceil(width),
        height: Math.ceil(height),
        deviceScaleFactor: 1,
        mobile: false,
      }
    );

    // Wait a bit for the metrics to apply
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Capture the full page screenshot
    const screenshot = await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Page.captureScreenshot",
      {
        format: "png",
        captureBeyondViewport: true,
      }
    ) as any;

    // Get current URL (in case of redirects)
    const currentUrl = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.location.href,
    });

    // Detach debugger
    await chrome.debugger.detach({ tabId: tab.id });

    // Close the tab
    await chrome.tabs.remove(tab.id);

    // Convert base64 to data URL
    const dataUrl = `data:image/png;base64,${screenshot.data}`;

    return {
      screenshots: [dataUrl],
      url: currentUrl[0].result,
      dimensions: { width: Math.ceil(width), height: Math.ceil(height) },
      segmentCount: 1
    };
  } catch (error) {
    // If debugger fails, fallback to the old method
    console.warn("Debugger method failed, falling back to viewport capture:", error);
    
    // Detach debugger if it's still attached
    try {
      await chrome.debugger.detach({ tabId: tab.id });
    } catch {}

    // Get page dimensions
    const dimensions = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const body = document.body;
        const html = document.documentElement;
        return {
          width: Math.max(
            body.scrollWidth,
            body.offsetWidth,
            html.clientWidth,
            html.scrollWidth,
            html.offsetWidth
          ),
          height: Math.max(
            body.scrollHeight,
            body.offsetHeight,
            html.clientHeight,
            html.scrollHeight,
            html.offsetHeight
          ),
          viewportHeight: window.innerHeight,
          viewportWidth: window.innerWidth
        };
      },
    });

    const { width, height, viewportHeight } = dimensions[0].result as any;
    const screenshots: string[] = [];
    let currentPosition = 0;

    // Capture screenshots in segments
    while (currentPosition < height) {
      // Scroll to position
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (position: number) => {
          window.scrollTo(0, position);
        },
        args: [currentPosition]
      });

      // Wait for scroll to settle
      await new Promise(resolve => setTimeout(resolve, 500));

      // Capture visible area
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId!, {
        format: 'png'
      });
      
      screenshots.push(dataUrl);
      currentPosition += viewportHeight;
    }

    // Get current URL (in case of redirects)
    const currentUrl = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.location.href,
    });

    await chrome.tabs.remove(tab.id);

    return {
      screenshots,
      url: currentUrl[0].result,
      dimensions: { width, height },
      segmentCount: screenshots.length
    };
  }
};

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
        console.log("Received screenshot request");
        let screenshotData = [];
        for (const url of urls) {
          try {
            const result = await captureFullPageScreenshot(url);
            screenshotData.push(result);
          } catch (error) {
            console.error(`Failed to capture screenshot for ${url}:`, error);
            screenshotData.push({
              url,
              error: (error as Error).message,
              screenshots: []
            });
          }
        }
        console.log("Sending screenshot response");
        this.send(
          JSON.stringify({
            type: "captureScreenshot",
            results: screenshotData,
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
