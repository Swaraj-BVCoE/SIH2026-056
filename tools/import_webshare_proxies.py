"""
tools/import_webshare_proxies.py
Converts Webshare.io proxy list to proxies.txt

Webshare format:  ip:port:username:password
Output format:    http://username:password@ip:port

Usage:
    python tools/import_webshare_proxies.py webshare_list.txt
"""
import sys
from pathlib import Path

OUTPUT_FILE = Path(__file__).resolve().parent.parent / "proxies.txt"

def convert_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(":")
    if len(parts) == 4:
        ip, port, user, password = parts
        return f"http://{user}:{password}@{ip}:{port}"
    elif line.startswith("http"):
        return line
    return None

def main():
    if len(sys.argv) > 1:
        lines = Path(sys.argv[1]).read_text().strip().splitlines()
    else:
        print("Paste Webshare proxy list (Ctrl+Z to finish):")
        lines = sys.stdin.read().strip().splitlines()

    converted = [r for line in lines if (r := convert_line(line))]
    if not converted:
        print("No valid proxies found. Expected: ip:port:username:password")
        sys.exit(1)

    OUTPUT_FILE.write_text("\n".join(converted) + "\n")
    print(f"Saved {len(converted)} proxies to {OUTPUT_FILE}")
    print("Next: set PROXY_ENABLED=true in .env, then re-run scraper")

if __name__ == "__main__":
    main()
