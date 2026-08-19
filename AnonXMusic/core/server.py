import asyncio
import os
import aiohttp
from aiohttp import web

from ..logging import LOGGER

routes = web.RouteTableDef()


@routes.get("/")
async def root_route_handler(request):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hacker-X-Music Status</title>
        <style>
            body {
                background: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .card {
                background: #1e293b;
                padding: 30px 40px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                text-align: center;
                border: 1px solid #334155;
            }
            h1 { color: #38bdf8; margin-bottom: 10px; }
            p { color: #94a3b8; font-size: 16px; margin: 8px 0; }
            .badge {
                display: inline-block;
                background: #22c55e;
                color: #ffffff;
                padding: 6px 16px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 14px;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⚡ HACKER X MUSIC ⚡</h1>
            <p>Telegram Music Bot is Alive & Running smoothly.</p>
            <div class="badge">● Online 24/7</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html")


@routes.get("/health")
@routes.get("/ping")
async def health_check(request):
    return web.json_response(
        {
            "status": "healthy",
            "service": "Hacker-X-Music",
            "state": "running",
        }
    )


async def _keep_alive_task(port: int):
    # Wait for the bot & web server to finish initialization
    await asyncio.sleep(20)

    url = (
        os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("KEEP_ALIVE_URL")
        or os.getenv("APP_URL")
    )
    if not url:
        url = f"http://127.0.0.1:{port}"

    LOGGER("AnonXMusic.keep_alive").info(f"Keep-Alive ping loop active for: {url}")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    LOGGER("AnonXMusic.keep_alive").info(
                        f"Keep-alive ping sent to {url} [Status: {resp.status}]"
                    )
            except Exception as e:
                LOGGER("AnonXMusic.keep_alive").warning(
                    f"Keep-alive ping failed for {url}: {e}"
                )
            await asyncio.sleep(300)  # Ping every 5 minutes (300 seconds)


async def start_web_server():
    port_str = os.getenv("PORT")
    if not port_str:
        if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL"):
            port_str = "10000"
        else:
            LOGGER("AnonXMusic.server").info(
                "PORT environment variable not set. Skipping web server startup."
            )
            return None

    try:
        port = int(port_str)
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        LOGGER("AnonXMusic.server").info(
            f"Web server successfully started on 0.0.0.0:{port} (Render / Web Service mode)"
        )

        # Start keep-alive loop in background
        asyncio.create_task(_keep_alive_task(port))

        return runner
    except Exception as err:
        LOGGER("AnonXMusic.server").warning(
            f"Failed to start web server on port {port_str}: {err}"
        )
        return None
