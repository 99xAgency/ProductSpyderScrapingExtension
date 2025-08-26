import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4
import time
import logging

import zendriver as zd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

browser = None
browser_lock = asyncio.Lock()
last_browser_restart = 0
BROWSER_RESTART_COOLDOWN = 10
PAGE_LOAD_TIMEOUT = 30
EVALUATE_TIMEOUT = 10


class URLRequest(BaseModel):
    url: str


async def start_browser():
    """Start or restart the browser instance."""
    global browser, last_browser_restart
    try:
        if browser:
            logger.info("Stopping existing browser instance...")
            try:
                await browser.stop()
            except Exception as e:
                logger.warning(f"Error stopping browser: {e}")
        
        logger.info("Starting new browser instance...")
        browser = await zd.start(user_data_dir=os.getenv("USER_DATA_DIR"))
        last_browser_restart = time.time()
        logger.info("Browser started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        return False


async def check_browser_health():
    """Check if browser is responsive."""
    global browser
    if not browser:
        return False
    
    test_tab = None
    try:
        test_tab = await asyncio.wait_for(
            browser.get("about:blank", new_tab=True),
            timeout=5
        )
        await asyncio.wait_for(
            test_tab.evaluate("1 + 1"),
            timeout=2
        )
        return True
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Browser health check failed: {e}")
        return False
    finally:
        if test_tab:
            try:
                await asyncio.wait_for(test_tab.close(), timeout=2)
            except:
                pass


async def kill_stuck_tab(tab):
    """Force kill a stuck tab."""
    try:
        await asyncio.wait_for(tab.evaluate("window.stop()"), timeout=1)
    except:
        pass
    try:
        await asyncio.wait_for(tab.close(), timeout=2)
    except:
        logger.warning("Failed to close stuck tab gracefully")


async def ensure_browser_healthy():
    """Ensure browser is healthy, restart if needed."""
    global browser, last_browser_restart
    
    async with browser_lock:
        if await check_browser_health():
            return True
        
        current_time = time.time()
        if current_time - last_browser_restart < BROWSER_RESTART_COOLDOWN:
            logger.warning("Browser restart cooldown active")
            return False
        
        logger.info("Browser unhealthy, attempting restart...")
        return await start_browser()


async def periodic_health_check():
    """Periodically check browser health and restart if needed."""
    while True:
        await asyncio.sleep(60)
        try:
            if not await check_browser_health():
                logger.warning("Periodic health check failed, restarting browser...")
                await ensure_browser_healthy()
        except Exception as e:
            logger.error(f"Error in periodic health check: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser
    await start_browser()
    
    health_check_task = asyncio.create_task(periodic_health_check())
    
    yield
    
    health_check_task.cancel()
    try:
        await health_check_task
    except asyncio.CancelledError:
        pass
    
    if browser:
        await browser.stop()


async def wait_for_page_load(tab: zd.Tab, timeout: int = PAGE_LOAD_TIMEOUT) -> bool:
    try:
        await asyncio.wait_for(
            tab.evaluate(
                expression="""
                new Promise((resolve) => {
                    if (document.readyState === 'complete') {
                        resolve(true);
                    } else {
                        const timeout = setTimeout(() => resolve(false), 25000);
                        window.addEventListener('load', () => {
                            clearTimeout(timeout);
                            resolve(true);
                        });
                    }
                });
                """,
                await_promise=True,
            ),
            timeout=timeout
        )
        
        await asyncio.sleep(2)
        return True

    except asyncio.TimeoutError:
        logger.warning(f"Page load timeout after {timeout} seconds")
        return False
    except Exception as e:
        logger.error(f"Error waiting for page load: {e}")
        return False


app = FastAPI(lifespan=lifespan)


@app.post("/fetch")
async def extract(request: URLRequest):
    url = request.url
    max_retries = 2
    
    for attempt in range(max_retries):
        tab = None
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt} for URL: {url}")
                if not await ensure_browser_healthy():
                    logger.error("Failed to ensure browser health")
                    continue
            
            tab = await asyncio.wait_for(
                browser.get(url, new_tab=True),
                timeout=10
            )
            await wait_for_page_load(tab)
            
            url = await asyncio.wait_for(
                tab.evaluate("window.location.href"),
                timeout=EVALUATE_TIMEOUT
            )
            status_code = 200
            source_code = await asyncio.wait_for(
                tab.evaluate("document.documentElement.outerHTML"),
                timeout=EVALUATE_TIMEOUT
            )
            
            return {"status_code": status_code, "url": url, "html": source_code}
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url} (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                return {"status_code": 500, "url": url, "html": "", "error": "Page load timeout"}
        except Exception as e:
            logger.error(f"Error fetching {url} (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                return {"status_code": 500, "url": url, "html": "", "error": str(e)}
        
        finally:
            if tab:
                try:
                    await asyncio.wait_for(tab.close(), timeout=3)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Error closing tab: {e}")
                    try:
                        await tab.evaluate("window.stop()")
                    except:
                        pass


@app.post("/screenshot")
async def screenshot(request: URLRequest):
    url = request.url
    max_retries = 2
    
    for attempt in range(max_retries):
        tab = None
        try:
            if attempt > 0:
                logger.info(f"Retry attempt {attempt} for screenshot: {url}")
                if not await ensure_browser_healthy():
                    logger.error("Failed to ensure browser health")
                    continue
            
            tab = await asyncio.wait_for(
                browser.get(url, new_tab=True),
                timeout=10
            )
            await wait_for_page_load(tab)
            
            file_name = f"screenshot_{str(uuid4()).split('-')[0]}.png"
            await asyncio.wait_for(
                tab.save_screenshot(f"screenshots/{file_name}"),
                timeout=10
            )
            
            return {"message": "Screenshot saved", "path": f"{file_name}"}
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout taking screenshot of {url} (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                return {"message": "Failed to take screenshot", "error": "Screenshot timeout"}
        except Exception as e:
            logger.error(f"Error taking screenshot of {url} (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                return {"message": "Failed to take screenshot", "error": str(e)}
        
        finally:
            if tab:
                try:
                    await asyncio.wait_for(tab.close(), timeout=3)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Error closing tab: {e}")
                    try:
                        await tab.evaluate("window.stop()")
                    except:
                        pass


@app.get("/health")
async def health_check():
    """Health check endpoint that also checks browser status."""
    is_healthy = await check_browser_health()
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "browser_alive": browser is not None,
        "browser_responsive": is_healthy
    }


@app.post("/reload-browser")
async def reload_browser():
    """Manually trigger browser reload."""
    success = await ensure_browser_healthy()
    return {
        "status": "success" if success else "failed",
        "message": "Browser reloaded successfully" if success else "Failed to reload browser"
    }


@app.get("/screenshots/{file_name}")
async def screenshots(file_name: str):
    return FileResponse(f"screenshots/{file_name}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9999)
