const captureFullPageScreenshot = async (url: string) => {
  console.log(`Capturing screenshot: ${url}`);

  const tab = await chrome.tabs.create({ url, active: false });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

  const waitForPageLoad = () => {
    return new Promise((resolve) => {
      if (document.readyState === "complete") {
        resolve(null);
      } else {
        const handler = () => {
          if (document.readyState === "complete") {
            document.removeEventListener("readystatechange", handler);
            resolve(null);
          }
        };
        document.addEventListener("readystatechange", handler);
      }
    });
  };

  try {
    // Wait for page to load
    await Promise.race([
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: waitForPageLoad,
      }),
      new Promise((resolve) => setTimeout(() => resolve(null), 15000)),
    ]);

    // Additional wait for dynamic content to render
    await new Promise((resolve) => setTimeout(resolve, 3000));

    // Attach debugger to the tab
    await chrome.debugger.attach({ tabId: tab.id }, "1.3");

    // Enable necessary domains
    await chrome.debugger.sendCommand({ tabId: tab.id }, "Page.enable");
    await chrome.debugger.sendCommand({ tabId: tab.id }, "Runtime.enable");
    await chrome.debugger.sendCommand({ tabId: tab.id }, "DOM.enable");

    // Wait for page to be fully loaded
    await chrome.debugger.sendCommand({ tabId: tab.id }, "Page.loadEventFired");

    // Get page metrics for full page dimensions
    const metrics = await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Page.getLayoutMetrics"
    ) as any;

    const { width, height } = metrics.contentSize;
    const viewportWidth = Math.ceil(width);
    const viewportHeight = Math.ceil(height);

    console.log(`Page dimensions: ${viewportWidth}x${viewportHeight}`);

    // Set device metrics to capture full page
    await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Emulation.setDeviceMetricsOverride",
      {
        width: viewportWidth,
        height: viewportHeight,
        deviceScaleFactor: 1,
        mobile: false,
        screenWidth: viewportWidth,
        screenHeight: viewportHeight,
        positionX: 0,
        positionY: 0,
        dontSetVisibleSize: false,
        screenOrientation: {
          type: "portraitPrimary",
          angle: 0
        }
      }
    );

    // Wait for the viewport change to take effect
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Force a layout update
    await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Page.setDocumentContent",
      {
        frameId: (await chrome.debugger.sendCommand({ tabId: tab.id }, "Page.getFrameTree") as any).frameTree.frame.id,
        html: await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => document.documentElement.outerHTML,
        }).then(r => r[0].result)
      }
    ).catch(() => {}); // Ignore if this fails

    // Capture the full page screenshot
    const screenshot = await chrome.debugger.sendCommand(
      { tabId: tab.id },
      "Page.captureScreenshot",
      {
        format: "png",
        quality: 100,
        captureBeyondViewport: true,
        fromSurface: true,
        clip: {
          x: 0,
          y: 0,
          width: viewportWidth,
          height: viewportHeight,
          scale: 1
        }
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
      dimensions: { width: viewportWidth, height: viewportHeight },
      segmentCount: 1
    };
  } catch (error) {
    console.error("Screenshot capture failed:", error);
    
    // Ensure cleanup
    try {
      await chrome.debugger.detach({ tabId: tab.id });
    } catch {}
    
    try {
      await chrome.tabs.remove(tab.id);
    } catch {}

    throw new Error(`Failed to capture screenshot: ${(error as Error).message}`);
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
