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

browser_pool = []
browser_semaphore = None


class URLRequest(BaseModel):
    url: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser_pool, browser_semaphore
    
    # Create 2 browser instances
    browser_semaphore = asyncio.Semaphore(2)
    for i in range(2):
        browser = await zd.start(user_data_dir=os.getenv("USER_DATA_DIR"))
        browser_pool.append(browser)
    
    yield
    
    # Clean up browsers
    for browser in browser_pool:
        if browser:
            await browser.stop()
    browser_pool.clear()


async def get_browser():
    """Get an available browser from the pool"""
    await browser_semaphore.acquire()
    try:
        # Return the first available browser (simple round-robin)
        return browser_pool[len(browser_pool) - browser_semaphore._value - 1]
    except IndexError:
        # Fallback to first browser if calculation fails
        return browser_pool[0]


def release_browser():
    """Release a browser back to the pool"""
    browser_semaphore.release()


async def wait_for_page_load(tab: zd.Tab) -> bool:
    try:
        # Wait for initial page load
        await tab.evaluate(
            expression="""
            new Promise((resolve) => {
                if (document.readyState === 'complete') {
                    resolve(true);
                } else {
                    window.addEventListener('load', () => resolve(true));
                }
            });
            """,
            await_promise=True,
        )

        await asyncio.sleep(5)

        return True

    except Exception as e:
        print(f"Error waiting for page load: {e}")
        # Fallback: wait a bit more and return
        await asyncio.sleep(3)
        return False


app = FastAPI(lifespan=lifespan)


@app.post("/fetch")
async def extract(request: URLRequest):
    url = request.url
    tab = None
    browser = None

    try:
        browser = await get_browser()
        tab = await browser.get(url, new_tab=True)

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
        if browser:
            release_browser()


@app.post("/screenshot")
async def screenshot(request: URLRequest):
    url = request.url
    tab = None
    browser = None

    try:
        browser = await get_browser()
        tab = await browser.get(url, new_tab=True)

        await wait_for_page_load(tab)

        file_name = f"screenshot_{str(uuid4()).split('-')[0]}.png"

        await tab.save_screenshot(f"screenshots/{file_name}")

        return {"message": "Screenshot saved", "path": f"{file_name}"}

    except Exception:
        return ""

    finally:
        if tab:
            await tab.close()
        if browser:
            release_browser()


@app.get("/screenshots/{file_name}")
async def screenshots(file_name: str):
    return FileResponse(f"screenshots/{file_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9999)
