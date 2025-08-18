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
        # First wait for basic DOM readiness
        await tab.evaluate(
            expression="""
            new Promise((resolve) => {
                if (document.readyState === 'complete' && document.body) {
                    resolve(true);
                } else {
                    window.addEventListener('load', () => resolve(true));
                }
            });
            """,
            await_promise=True,
        )

        # Then wait for content to stabilize (no new elements for 2 seconds)
        await tab.evaluate(
            expression="""
            new Promise((resolve) => {
                let lastElementCount = document.body.children.length;
                let stableCount = 0;
                let checkInterval;
                let timeoutId;
                
                // Set maximum wait time (15 seconds)
                timeoutId = setTimeout(() => {
                    clearInterval(checkInterval);
                    console.log('Timeout reached, resolving...');
                    resolve(true);
                }, 15000);
                
                checkInterval = setInterval(() => {
                    const currentElementCount = document.body.children.length;
                    
                    if (currentElementCount === lastElementCount) {
                        stableCount++;
                        if (stableCount >= 4) { // 2 seconds (4 * 500ms)
                            clearInterval(checkInterval);
                            clearTimeout(timeoutId);
                            resolve(true);
                        }
                    } else {
                        stableCount = 0;
                        lastElementCount = currentElementCount;
                    }
                }, 500);
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
