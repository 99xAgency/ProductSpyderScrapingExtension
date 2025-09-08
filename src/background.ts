const extractHtml = async (url: string, maxTimeout: number = 30000) => {
  const waitForPageLoad = () => {
    return new Promise((resolve) => {
      if (document.readyState === "complete") {
        resolve(null);
      } else {
        const listener = () => {
          if (document.readyState === "complete") {
            document.removeEventListener("readystatechange", listener);
            resolve(null);
          }
        };
        document.addEventListener("readystatechange", listener);
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

  let createdTab: chrome.tabs.Tab | undefined;
  let timeoutId: NodeJS.Timeout | undefined;
  
  try {
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error(`Operation timed out after ${maxTimeout}ms`));
      }, maxTimeout);
    });

    const extractPromise = async () => {
      const tab = await chrome.tabs.create({ url });
      createdTab = tab;

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

      return {
        html: html[0].result,
        status_code: statusCode[0].result,
        url: currentUrl[0].result,
      };
    };

    const result = await Promise.race([extractPromise(), timeoutPromise]);
    return result;
  } catch (error) {
    console.error(`Error extracting HTML from ${url}:`, error);
    throw error;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    if (createdTab?.id) {
      const tabId = createdTab.id;
      try {
        await chrome.tabs.remove(tabId);
        console.log(`Tab ${tabId} closed successfully`);
      } catch (removeError) {
        console.error(`Failed to close tab ${tabId}:`, removeError);
        try {
          const existingTab = await chrome.tabs.get(tabId);
          if (existingTab) {
            await chrome.tabs.remove(tabId);
          }
        } catch (retryError) {
          console.error(`Retry failed to close tab ${tabId}:`, retryError);
        }
      }
    }
  }
};

const captureScreenshot = async (url: string, maxTimeout: number = 30000) => {
  const waitForPageLoad = () => {
    return new Promise((resolve) => {
      if (document.readyState === "complete") {
        resolve(null);
      } else {
        const listener = () => {
          if (document.readyState === "complete") {
            document.removeEventListener("readystatechange", listener);
            resolve(null);
          }
        };
        document.addEventListener("readystatechange", listener);
      }
    });
  };

  console.log(`Capturing screenshot for: ${url}`);

  let createdTab: chrome.tabs.Tab | undefined;
  let timeoutId: NodeJS.Timeout | undefined;
  
  try {
    const timeoutPromise = new Promise((_, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error(`Operation timed out after ${maxTimeout}ms`));
      }, maxTimeout);
    });

    const capturePromise = async () => {
      const tab = await chrome.tabs.create({ url });
      createdTab = tab;

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

      return {
        screenshot: screenshot,
        url: currentUrl[0].result,
      };
    };

    const result = await Promise.race([capturePromise(), timeoutPromise]);
    return result;
  } catch (error) {
    console.error(`Error capturing screenshot from ${url}:`, error);
    throw error;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    if (createdTab?.id) {
      const tabId = createdTab.id;
      try {
        await chrome.tabs.remove(tabId);
        console.log(`Tab ${tabId} closed successfully`);
      } catch (removeError) {
        console.error(`Failed to close tab ${tabId}:`, removeError);
        try {
          const existingTab = await chrome.tabs.get(tabId);
          if (existingTab) {
            await chrome.tabs.remove(tabId);
          }
        } catch (retryError) {
          console.error(`Retry failed to close tab ${tabId}:`, retryError);
        }
      }
    }
  }
};

class WebSocketManager {
  url: string;
  ws: WebSocket | null;
  reconnectDelay: number;
  activeTabs: Set<number>;

  constructor(url: string) {
    this.url = url;
    this.ws = null;
    this.reconnectDelay = 1000;
    this.activeTabs = new Set();
    this.connect();
    this.setupTabCleanup();
  }

  setupTabCleanup() {
    setInterval(async () => {
      if (this.activeTabs.size > 0) {
        console.log(`Checking ${this.activeTabs.size} active tabs for cleanup`);
        for (const tabId of this.activeTabs) {
          try {
            await chrome.tabs.get(tabId);
          } catch (error) {
            console.log(`Tab ${tabId} no longer exists, removing from tracking`);
            this.activeTabs.delete(tabId);
          }
        }
      }
    }, 30000);
  }

  async cleanupAllTabs() {
    console.log(`Cleaning up ${this.activeTabs.size} active tabs`);
    for (const tabId of this.activeTabs) {
      try {
        await chrome.tabs.remove(tabId);
        console.log(`Cleaned up tab ${tabId}`);
      } catch (error) {
        console.error(`Failed to cleanup tab ${tabId}:`, error);
      }
    }
    this.activeTabs.clear();
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log("WebSocket connected");
    };

    this.ws.onmessage = async (event) => {
      try {
        const { type, url, request_id } = JSON.parse(event.data);
        
        if (type == "extractHtml") {
          try {
            const extractedData = await extractHtml(url);
            this.send(
              JSON.stringify({
                type: "extractHtml",
                result: extractedData,
                request_id,
              })
            );
          } catch (error) {
            console.error(`Failed to extract HTML for ${url}:`, error);
            this.send(
              JSON.stringify({
                type: "extractHtml",
                result: { error: String(error) },
                request_id,
              })
            );
          }
        } else if (type == "captureScreenshot") {
          try {
            const screenshotData = await captureScreenshot(url);
            this.send(
              JSON.stringify({
                type: "captureScreenshot",
                result: screenshotData,
                request_id,
              })
            );
          } catch (error) {
            console.error(`Failed to capture screenshot for ${url}:`, error);
            this.send(
              JSON.stringify({
                type: "captureScreenshot",
                result: { error: String(error) },
                request_id,
              })
            );
          }
        }
      } catch (error) {
        console.error("Error processing WebSocket message:", error);
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

chrome.runtime.onMessage.addListener((message, _, sendResponse) => {
  if (message.action === "ping") {
    sendResponse("pong");
  }
});
