import asyncio
import argparse
import sys
import time
from pathlib import Path
import httpx

OUTPUT_FILE = Path(__file__).resolve().parent.parent / "proxies.txt"

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies.txt",
]

TEST_URL = "https://httpbin.org/ip"
TIMEOUT = 8
MAX_WORKERS = 50
MAX_PROXIES = 200

async def fetch_proxy_list(url, client):
    try:
        resp = await client.get(url, timeout=15)
        if resp.status_code == 200:
            lines = resp.text.strip().splitlines()
            proxies = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("http"):
                    line = f"http://{line}"
                proxies.append(line)
            label = url.split("/")[-3] + "/" + url.split("/")[-1]
            print(f"  OK {label}: {len(proxies)} proxies")
            return proxies
    except Exception as e:
        print(f"  FAIL {url}: {e}")
    return []

async def test_proxy(proxy):
    try:
        async with httpx.AsyncClient(
            proxies={"http://": proxy, "https://": proxy},
            follow_redirects=True,
            timeout=TIMEOUT,
        ) as c:
            resp = await c.get(TEST_URL)
            if resp.status_code == 200:
                return proxy
    except Exception:
        pass
    return None

async def main(args):
    print("Fetching proxy lists from GitHub...")
    t0 = time.time()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [fetch_proxy_list(url, client) for url in PROXY_SOURCES]
        results = await asyncio.gather(*tasks)

    all_proxies = list(set(p for batch in results for p in batch))
    print(f"Total unique proxies: {len(all_proxies)}")

    if args.quick:
        OUTPUT_FILE.write_text("\n".join(all_proxies[:MAX_PROXIES]) + "\n", encoding="utf-8")
        print(f"Quick mode: saved {min(len(all_proxies), MAX_PROXIES)} proxies to {OUTPUT_FILE}")
        return

    to_test = all_proxies[:args.test] if args.test else all_proxies[:MAX_PROXIES]
    print(f"Testing {len(to_test)} proxies (concurrency={MAX_WORKERS})...")

    sem = asyncio.Semaphore(MAX_WORKERS)

    async def bounded(proxy):
        async with sem:
            return await test_proxy(proxy)

    test_results = await asyncio.gather(*[bounded(p) for p in to_test])
    working = [p for p in test_results if p]

    if not working:
        print("No working proxies found. Try again later (lists refresh hourly).")
        sys.exit(1)

    OUTPUT_FILE.write_text("\n".join(working) + "\n", encoding="utf-8")
    elapsed = time.time() - t0
    print(f"{len(working)}/{len(to_test)} proxies alive ({elapsed:.1f}s)")
    print(f"Saved to: {OUTPUT_FILE}")
    print("")
    print("Next steps:")
    print("  1. Set PROXY_ENABLED=true in your .env file")
    print("  2. Run: .\\venv\\Scripts\\python.exe main.py scrape --portal ixigo -r BOM-DEL -d 2026-09-10")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--test", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(args))
