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

function connect() {
  const ws = new WebSocket("ws://127.0.0.1:9999/ws");
  let isConnected = false;

  ws.onopen = function () {
    isConnected = true;
    console.log("Connected to server");
  };

  ws.onmessage = async (e) => {
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

  ws.onclose = function (e) {
    console.log(
      "Socket is closed. Reconnect will be attempted in 1 second.",
      e.reason
    );
    setInterval(function () {
      if (!isConnected) {
        connect();
      }
    }, 1000);
  };

  ws.onerror = function (err) {
    console.log(err);
    ws.close();
  };
}

connect();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "ping") {
    sendResponse("pong");
  }
});
