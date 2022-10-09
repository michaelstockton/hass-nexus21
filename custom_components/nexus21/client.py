#!/usr/bin/env python3

import aiohttp
import asyncio

from api import Nexus21IPModule


async def fetch(client):
    upper = Nexus21IPModule("192.168.0.39", session=client)
    lower = Nexus21IPModule("192.168.0.40", session=client)
    return await asyncio.gather(
        upper.close(),
        lower.close(),
    )


async def main():
    async with aiohttp.ClientSession() as client:
        responses = await fetch(client)
        #for r in responses:
        #    print(r.status)


if __name__ == "__main__":
    asyncio.run(main())
