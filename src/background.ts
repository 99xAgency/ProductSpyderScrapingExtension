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

  const html = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.documentElement.outerHTML,
  });

  await chrome.tabs.remove(tab.id);

  return html[0].result;
};

let ws = new WebSocket("ws://127.0.0.1:9999/ws");
let isConnected = false;

const onOpen = () => {
  isConnected = true;
  console.log("Connected to server");
};

const onMessage = async (e: MessageEvent) => {
  const { type, urls, request_id } = JSON.parse(e.data);
  if (type == "extractHtml") {
    console.log("Received extractHtml request");
    let mergedData = [];
    for (const url of urls) {
      mergedData.push(await extractHtml(url));
    }
    console.log("Sending extractHtml response");
    ws.send(
      JSON.stringify({ type: "extractHtml", htmls: mergedData, request_id })
    );
  }
};

const onClose = () => {
  isConnected = false;
  console.log("Socket is closed. Reconnect will be attempted in 1 second.");
  setInterval(() => {
    if (!isConnected) {
      ws.close();
      ws = new WebSocket("ws://127.0.0.1:9999/ws");
      ws.onopen = onOpen;
      ws.onmessage = onMessage;
      ws.onclose = onClose;
    }
  }, 1000);
};

ws.onopen = onOpen;
ws.onmessage = onMessage;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "ping") {
    sendResponse("pong");
  }
});
