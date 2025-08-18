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


def ensure_screenshots_dir():
    """Ensure the screenshots directory exists"""
    screenshots_dir = "screenshots"
    if not os.path.exists(screenshots_dir):
        os.makedirs(screenshots_dir)
        print(f"Created screenshots directory: {screenshots_dir}")


class URLRequest(BaseModel):
    url: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser
    ensure_screenshots_dir()
    browser = await zd.start(user_data_dir=os.getenv("USER_DATA_DIR"))
    yield
    if browser:
        await browser.stop()


async def wait_for_page_load_simple(tab: zd.Tab, timeout: int = 10) -> bool:
    """
    Simple fallback method to wait for page load without complex JavaScript.
    This is more reliable when the execution context is unstable.
    """
    try:
        if not tab or tab.is_closed():
            return False

        # Wait for a reasonable amount of time for the page to load
        await asyncio.sleep(timeout)
        return True

    except Exception as e:
        print(f"Error in simple page load wait: {e}")
        return False


async def wait_for_page_load(tab: zd.Tab) -> bool:
    try:
        # First check if the tab is still valid
        if not tab or tab.is_closed():
            print("Tab is closed or invalid before starting page load wait")
            return False

        print("Starting complex page load wait...")

        # Wait for network to be idle with timeout and better error handling
        result = await tab.evaluate(
            expression="""
            new Promise((resolve, reject) => {
                // Check if we're still in a valid context
                if (!window || !document) {
                    reject(new Error('Invalid execution context'));
                    return;
                }
                
                let pendingRequests = 0;
                let idleTimer = null;
                let timeoutId = null;
                let isResolved = false;
                
                const cleanup = () => {
                    if (isResolved) return;
                    isResolved = true;
                    if (timeoutId) clearTimeout(timeoutId);
                    if (idleTimer) clearTimeout(idleTimer);
                };
                
                const safeResolve = (value) => {
                    if (!isResolved) {
                        cleanup();
                        resolve(value);
                    }
                };
                
                const safeReject = (error) => {
                    if (!isResolved) {
                        cleanup();
                        reject(error);
                    }
                };
                
                // Set maximum wait time (20 seconds)
                const MAX_WAIT_TIME = 20000;
                timeoutId = setTimeout(() => {
                    console.log('Network timeout reached, resolving...');
                    safeResolve(true);
                }, MAX_WAIT_TIME);
                
                // Monitor fetch requests
                try {
                    const originalFetch = window.fetch;
                    window.fetch = function(...args) {
                        if (!window || !document) {
                            safeReject(new Error('Context destroyed during fetch'));
                            return;
                        }
                        
                        pendingRequests++;
                        return originalFetch.apply(this, args).finally(() => {
                            if (!window || !document) {
                                safeReject(new Error('Context destroyed after fetch'));
                                return;
                            }
                            
                            pendingRequests--;
                            if (pendingRequests === 0) {
                                clearTimeout(idleTimer);
                                idleTimer = setTimeout(() => {
                                    clearTimeout(timeoutId);
                                    safeResolve(true);
                                }, 1500); // Wait 1.5 seconds after last request
                            }
                        });
                    };
                } catch (e) {
                    console.warn('Could not override fetch:', e);
                }
                
                // Monitor XMLHttpRequest
                try {
                    const originalXHROpen = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(...args) {
                        if (!window || !document) {
                            safeReject(new Error('Context destroyed during XHR'));
                            return;
                        }
                        
                        pendingRequests++;
                        this.addEventListener('loadend', () => {
                            if (!window || !document) {
                                safeReject(new Error('Context destroyed after XHR'));
                                return;
                            }
                            
                            pendingRequests--;
                            if (pendingRequests === 0) {
                                clearTimeout(idleTimer);
                                idleTimer = setTimeout(() => {
                                    clearTimeout(timeoutId);
                                    safeResolve(true);
                                }, 1500); // Wait 1.5 seconds after last request
                            }
                        });
                        return originalXHROpen.apply(this, args);
                    };
                } catch (e) {
                    console.warn('Could not override XMLHttpRequest:', e);
                }
                
                // If no requests are made initially, resolve after a short delay
                setTimeout(() => {
                    if (!window || !document) {
                        safeReject(new Error('Context destroyed during initial wait'));
                        return;
                    }
                    
                    if (pendingRequests === 0) {
                        clearTimeout(timeoutId);
                        safeResolve(true);
                    }
                }, 1000);
                
                // Add error handler for unhandled rejections
                window.addEventListener('error', (event) => {
                    safeReject(new Error('Page error: ' + event.message));
                });
                
                // Add unload handler
                window.addEventListener('beforeunload', () => {
                    safeReject(new Error('Page unloading'));
                });
            });
            """,
            await_promise=True,
        )

        print("Complex page load wait completed successfully")
        return True

    except Exception as e:
        print(f"Error waiting for page load: {e}")

        # Check if tab is still valid
        try:
            if tab and not tab.is_closed():
                print("Tab is still valid, will try simple fallback")
                return False
            else:
                print("Tab is closed or invalid")
                return False
        except Exception as check_error:
            print(f"Could not check tab status: {check_error}")
            return False


app = FastAPI(lifespan=lifespan)


@app.post("/fetch")
async def extract(request: URLRequest):
    url = request.url
    tab = None

    try:
        tab = await browser.get(url, new_tab=True)

        await asyncio.sleep(1)

        # Wait for page load and handle failures
        page_loaded = await wait_for_page_load(tab)
        if not page_loaded:
            print(f"Failed to wait for page load on {url}, trying simple fallback...")
            # Try the simple fallback method
            page_loaded = await wait_for_page_load_simple(tab, timeout=5)
            if not page_loaded:
                print(f"Both page load methods failed for {url}")
                # Still try to get the content, but with a shorter wait
                await asyncio.sleep(2)

        # Check if tab is still valid before proceeding
        if not tab or tab.is_closed():
            return {"error": "Tab was closed before content could be extracted"}

        url = await tab.evaluate("window.location.href")
        status_code = 200
        source_code = await tab.evaluate("document.documentElement.outerHTML")

        return {"status_code": status_code, "url": url, "html": source_code}

    except Exception as e:
        print(f"Error in fetch endpoint: {e}")
        return {"error": str(e)}

    finally:
        if tab:
            try:
                await tab.close()
            except Exception as e:
                print(f"Error closing tab: {e}")


@app.post("/screenshot")
async def screenshot(request: URLRequest):
    url = request.url
    tab = None

    try:
        tab = await browser.get(url, new_tab=True)

        await asyncio.sleep(1)

        # Wait for page load and handle failures
        page_loaded = await wait_for_page_load(tab)
        if not page_loaded:
            print(f"Failed to wait for page load on {url}, trying simple fallback...")
            # Try the simple fallback method
            page_loaded = await wait_for_page_load_simple(tab, timeout=5)
            if not page_loaded:
                print(f"Both page load methods failed for {url}")
                # Still try to take screenshot, but with a shorter wait
                await asyncio.sleep(2)

        # Check if tab is still valid before proceeding
        if not tab or tab.is_closed():
            return {"error": "Tab was closed before screenshot could be taken"}

        file_name = f"screenshot_{str(uuid4()).split('-')[0]}.png"

        await tab.save_screenshot(f"screenshots/{file_name}")

        return {"message": "Screenshot saved", "path": f"{file_name}"}

    except Exception as e:
        print(f"Error in screenshot endpoint: {e}")
        return {"error": str(e)}

    finally:
        if tab:
            try:
                await tab.close()
            except Exception as e:
                print(f"Error closing tab: {e}")


@app.get("/screenshots/{file_name}")
async def screenshots(file_name: str):
    return FileResponse(f"screenshots/{file_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9999)
