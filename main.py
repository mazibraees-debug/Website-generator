from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

load_dotenv(".env")
load_dotenv("../.env")

from ai_generator import generate_website, generate_website_stream  # noqa: E402
from validator import ValidationError  # noqa: E402

app = FastAPI(title="AI Website Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    current_files: Optional[dict[str, str]] = None


class GenerateResponse(BaseModel):
    files: dict[str, str]


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Website Generator Running</h1>")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    try:
        files = generate_website(req.prompt, req.current_files)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Generated code safe nahi tha: {e}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    return GenerateResponse(files=files)


@app.post("/generate/stream")
def generate_stream(req: GenerateRequest):
    """Streaming endpoint — returns SSE events with real-time AI output chunks."""
    return StreamingResponse(
        generate_website_stream(req.prompt, req.current_files),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
