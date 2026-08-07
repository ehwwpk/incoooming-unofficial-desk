from pathlib import Path

from fastapi.templating import Jinja2Templates

WEB_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=WEB_ROOT / "templates")
