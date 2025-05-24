const extractHtml = async (url: string) => {
  let customUserAgent =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36";

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

  const simulateHumanBehavior = () => {
    // Simulate scrolling and mouse movements
    return new Promise((resolve) => {
      let scrolls = 0;
      const maxScrolls = Math.floor(Math.random() * 5) + 3; // Random number of scrolls between 3-7

      const scroll = () => {
        if (scrolls >= maxScrolls) {
          resolve(null);
          return;
        }

        const scrollAmount = Math.floor(Math.random() * 400) + 100; // Random scroll between 100-500px
        window.scrollBy(0, scrollAmount);
        scrolls++;

        // Random delay between scrolls (500-2000ms)
        setTimeout(scroll, Math.floor(Math.random() * 1500) + 500);
      };

      // Initial delay before starting to scroll (1000-3000ms)
      setTimeout(scroll, Math.floor(Math.random() * 2000) + 1000);
    });
  };

  const handleCaptchas = () => {
    // Basic detection of common CAPTCHA patterns
    return new Promise((resolve) => {
      // Check for common CAPTCHA elements
      const hasCaptcha =
        document.querySelector('iframe[src*="recaptcha"]') ||
        document.querySelector('iframe[src*="captcha"]') ||
        document.querySelector(".g-recaptcha") ||
        document.querySelector('[class*="captcha"]') ||
        document.querySelector('[class*="robot"]') ||
        document.querySelector('[id*="captcha"]');

      if (hasCaptcha) {
        console.log("CAPTCHA detected");

        // Attempt to find the container of the CAPTCHA
        const captchaElement =
          document.querySelector('iframe[src*="recaptcha"]')?.parentElement ||
          document.querySelector('iframe[src*="captcha"]')?.parentElement ||
          document.querySelector(".g-recaptcha") ||
          document.querySelector('[class*="captcha"]') ||
          document.querySelector('[id*="captcha"]');

        if (captchaElement) {
          // Scroll to the CAPTCHA element to make it visible
          captchaElement.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
        }

        // Wait a bit for any animations to complete
        setTimeout(() => {
          resolve({
            hasCaptcha: true,
            captchaType: determineCaptchaType(),
          });
        }, 1000);
      } else {
        resolve({
          hasCaptcha: false,
        });
      }
    });
  };

  const determineCaptchaType = () => {
    if (
      document.querySelector('iframe[src*="recaptcha"]') ||
      document.querySelector(".g-recaptcha")
    ) {
      return "reCAPTCHA";
    } else if (
      document.querySelector('iframe[src*="hcaptcha"]') ||
      document.querySelector(".h-captcha")
    ) {
      return "hCaptcha";
    } else if (
      document.querySelector('iframe[src*="cloudflare"]') ||
      document.querySelector("#cf-challenge-container")
    ) {
      return "Cloudflare";
    } else {
      return "Unknown";
    }
  };

  console.log(`Processing: ${url}`);

  const tab = await chrome.tabs.create({
    url,
  });

  if (!tab.id) {
    throw new Error("Failed to create tab");
  }

  // Set custom user agent if specified
  if (customUserAgent) {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (userAgent) => {
        Object.defineProperty(navigator, "userAgent", {
          get: function () {
            return userAgent;
          },
        });
      },
      args: [customUserAgent],
    });
  }

  // Wait for page to load with timeout
  await Promise.race([
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => waitForPageLoad(),
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 6000)),
  ]);

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => simulateHumanBehavior(),
  });

  const captchaResult = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => handleCaptchas(),
  });

  interface CaptchaResult {
    hasCaptcha: boolean;
    captchaType?: string;
  }

  // If a captcha was detected, take a screenshot
  const result = captchaResult[0].result as CaptchaResult;

  if (result.hasCaptcha) {
    console.log(`CAPTCHA detected: ${result.captchaType}`);
    return "";
  }

  await new Promise((resolve) =>
    setTimeout(resolve, Math.floor(Math.random() * 2000) + 1000)
  );

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
      const data = JSON.parse(event.data);
      const { type, request_id } = data;

      if (type == "extractHtml") {
        console.log("Received extractHtml request");

        const { urls } = data;
        let mergedData = [];

        // Extract options with de
        for (const url of urls) {
          try {
            const result = await extractHtml(url);
            mergedData.push(result);
          } catch (error: any) {
            console.error(`Error extracting HTML from ${url}:`, error);
            mergedData.push("");
          }
        }

        console.log("Sending extractHtml response");
        this.send(
          JSON.stringify({
            type: "extractHtml",
            htmls: mergedData,
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
