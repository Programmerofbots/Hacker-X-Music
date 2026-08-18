import os
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
            <div class="badge">● Online</div>
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


async def start_web_server():
    port = os.getenv("PORT")
    if not port:
        LOGGER("AnonXMusic.server").info(
            "PORT environment variable not set. Skipping web server startup."
        )
        return None

    try:
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(port))
        await site.start()
        LOGGER("AnonXMusic.server").info(
            f"Web server successfully started on 0.0.0.0:{port} (Render / Web Service mode)"
        )
        return runner
    except Exception as err:
        LOGGER("AnonXMusic.server").warning(
            f"Failed to start web server on port {port}: {err}"
        )
        return None
