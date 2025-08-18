import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import zendriver as zd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

browser = None


class URLRequest(BaseModel):
    url: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser
    browser = await zd.start(user_data_dir=os.getenv("USER_DATA_DIR"))
    yield
    if browser:
        await browser.stop()


async def wait_for_page_load(tab: zd.Tab) -> bool:
    try:
        # Wait for network to be idle with timeout
        await tab.evaluate(
            expression="""
            new Promise((resolve) => {
                let pendingRequests = 0;
                let idleTimer = null;
                let timeoutId = null;
                
                // Set maximum wait time (12 seconds)
                const MAX_WAIT_TIME = 20000;
                timeoutId = setTimeout(() => {
                    console.log('Network timeout reached, resolving...');
                    resolve(true);
                }, MAX_WAIT_TIME);
                
                // Monitor fetch requests
                const originalFetch = window.fetch;
                window.fetch = function(...args) {
                    pendingRequests++;
                    return originalFetch.apply(this, args).finally(() => {
                        pendingRequests--;
                        if (pendingRequests === 0) {
                            clearTimeout(idleTimer);
                            idleTimer = setTimeout(() => {
                                clearTimeout(timeoutId);
                                resolve(true);
                            }, 1500); // Wait 1.5 seconds after last request
                        }
                    });
                };
                
                // Monitor XMLHttpRequest
                const originalXHROpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(...args) {
                    pendingRequests++;
                    this.addEventListener('loadend', () => {
                        pendingRequests--;
                        if (pendingRequests === 0) {
                            clearTimeout(idleTimer);
                            idleTimer = setTimeout(() => {
                                clearTimeout(timeoutId);
                                resolve(true);
                            }, 1500); // Wait 1.5 seconds after last request
                        }
                    });
                    return originalXHROpen.apply(this, args);
                };
                
                // If no requests are made initially, resolve after a short delay
                setTimeout(() => {
                    if (pendingRequests === 0) {
                        clearTimeout(timeoutId);
                        resolve(true);
                    }
                }, 1000);
            });
            """,
            await_promise=True,
        )

        return True

    except Exception as e:
        print(f"Error waiting for page load: {e}")
        # Fallback: wait a bit and return
        await asyncio.sleep(3)
        return False


app = FastAPI(lifespan=lifespan)


@app.post("/fetch")
async def extract(request: URLRequest):
    url = request.url
    tab = None

    try:
        tab = await browser.get(url, new_tab=True)

        await asyncio.sleep(1)

        await wait_for_page_load(tab)

        url = await tab.evaluate("window.location.href")
        status_code = 200
        source_code = await tab.evaluate("document.documentElement.outerHTML")

        return {"status_code": status_code, "url": url, "html": source_code}

    except Exception:
        return ""

    finally:
        if tab:
            await tab.close()


@app.post("/screenshot")
async def screenshot(request: URLRequest):
    url = request.url
    tab = None

    try:
        tab = await browser.get(url, new_tab=True)

        await asyncio.sleep(1)

        await wait_for_page_load(tab)

        file_name = f"screenshot_{str(uuid4()).split('-')[0]}.png"

        await tab.save_screenshot(f"screenshots/{file_name}")

        return {"message": "Screenshot saved", "path": f"{file_name}"}

    except Exception:
        return ""

    finally:
        if tab:
            await tab.close()


@app.get("/screenshots/{file_name}")
async def screenshots(file_name: str):
    return FileResponse(f"screenshots/{file_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9999)
