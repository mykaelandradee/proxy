import os
import sys
from urllib.parse import urlsplit, urlunsplit

from fastapi import Query
from fastapi.responses import JSONResponse
import aiohttp

sys.path.insert(0, "/mediaflow_proxy")

from mediaflow_proxy.main import app

# Move the catch-all static mount behind this diagnostic route.
static_route = app.router.routes.pop()

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
IPTV_UA = "IPTVSmartersPro/3.0.0"


def safe_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


async def probe(session, url, *, range_header=None, ua=DEFAULT_UA, allow_redirects=True):
    headers = {"User-Agent": ua}
    if range_header is not None:
        headers["Range"] = range_header
    try:
        async with session.get(url, headers=headers, allow_redirects=allow_redirects) as r:
            body = await r.content.read(160)
            location = r.headers.get("Location")
            return {
                "status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "content_length": r.headers.get("Content-Length"),
                "server": r.headers.get("Server"),
                "location": safe_url(location) if location else None,
                "final_url": safe_url(str(r.url)),
                "body_prefix": body.decode("utf-8", errors="replace")[:160],
                "error": None,
            }
    except Exception as exc:
        return {
            "status": None,
            "content_type": None,
            "content_length": None,
            "server": None,
            "location": None,
            "final_url": None,
            "body_prefix": None,
            "error": type(exc).__name__ + ": " + str(exc)[:160],
        }


@app.get("/diagnostic/upstream")
async def diagnostic(url: str = Query(..., description="Provider stream URL")):
    timeout = aiohttp.ClientTimeout(total=15, sock_read=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tests = {
            "no_range_chrome_follow": await probe(session, url, range_header=None, ua=DEFAULT_UA, allow_redirects=True),
            "range_chrome_follow": await probe(session, url, range_header="bytes=0-", ua=DEFAULT_UA, allow_redirects=True),
            "no_range_iptv_follow": await probe(session, url, range_header=None, ua=IPTV_UA, allow_redirects=True),
            "range_iptv_follow": await probe(session, url, range_header="bytes=0-", ua=IPTV_UA, allow_redirects=True),
            "no_range_chrome_manual": await probe(session, url, range_header=None, ua=DEFAULT_UA, allow_redirects=False),
        }
    return JSONResponse({"target": safe_url(url), "tests": tests})


app.router.routes.append(static_route)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8888")))
