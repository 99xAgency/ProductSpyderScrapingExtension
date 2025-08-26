if (window.location.href.includes("google.com")) {
  setInterval(() => {
    chrome.runtime.sendMessage({
      action: "ping",
    });
  }, 10000);
}
