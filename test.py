import asyncio

import requests
from curl_cffi.requests import AsyncSession


async def main():
    async with AsyncSession() as session:
        data = {"url": "https://www.kayaks2fish.com/2.8m-nextgen-fishing-kayak-bora-bora-sydney"}
        tasks = [session.post("http://127.0.0.1:9999/screenshot", json=data) for _ in range(2)]

        responses = await asyncio.gather(*tasks)
        print(responses[1].text)


if __name__ == "__main__":
    asyncio.run(main())
