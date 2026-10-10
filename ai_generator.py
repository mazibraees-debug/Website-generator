import json
import os
import re
from typing import Generator
import httpx

from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv(".env")
load_dotenv("../.env")

from prompts import SYSTEM_PROMPT, build_user_message
from validator import ValidationError, validate_files

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        load_dotenv(".env")
        load_dotenv("../.env")
        key = os.getenv("OPENROUTER_API_KEY", "")
    return key


def _get_candidate_models() -> list[str]:
    primary = os.getenv("MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b:free")
    candidates = [
        primary,
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3.5-lightning:free",
        "liquid/lfm-2.5-2.6b:free",
        "cohere/north-mini-code:free",
    ]
    # Remove duplicates while preserving order
    return list(dict.fromkeys(candidates))



def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AI ne valid JSON nahi diya")
    return json.loads(text[start : end + 1])


def generate_website(prompt: str, current_files: dict | None = None) -> dict[str, str]:
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY set nahi hai. Kripya .env file check karein.")

    user_message = build_user_message(prompt, current_files)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "AI Website Generator",
    }

    last_error: Exception | None = None
    candidate_models = _get_candidate_models()

    # Try models with automatic fallback
    for model_choice in candidate_models:
        payload = {
            "model": model_choice,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(OPENROUTER_URL, headers=headers, json=payload)
                if response.status_code != 200:
                    last_error = ValueError(f"{model_choice} error ({response.status_code}): {response.text}")
                    continue
                data_resp = response.json()

            raw = data_resp["choices"][0]["message"]["content"]
            data = _extract_json(raw)
            files = data.get("files", data)
            return validate_files(files)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue
        except ValidationError:
            raise
        except Exception as e:
            last_error = e
            continue

    raise ValueError(f"Website generate nahi ho paayi: {last_error}")


def generate_website_stream(
    prompt: str, current_files: dict | None = None
) -> Generator[str, None, None]:
    """Yields SSE-formatted events while the AI generates the website.

    Events:
      data: {"chunk": "..."}        — partial raw text from the model
      data: {"done": true, "files": {...}}  — final parsed files on success
      data: {"error": "..."}        — on failure
    """
    api_key = _get_api_key()
    if not api_key:
        yield f'data: {json.dumps({"error": "OPENROUTER_API_KEY set nahi hai. .env file check karein."})}\'\n\n'
        return

    user_message = build_user_message(prompt, current_files)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "AI Website Generator",
    }

    candidate_models = _get_candidate_models()
    last_error: Exception | None = None

    for model_choice in candidate_models:
        payload = {
            "model": model_choice,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
            "stream": True,
        }

        full_content = ""
        try:
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", OPENROUTER_URL, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        last_error = ValueError(
                            f"{model_choice} error ({resp.status_code}): {resp.text}"
                        )
                        continue

                    for line in resp.iter_lines():
                        if not line or line == "data: [DONE]":
                            continue
                        if line.startswith("data: "):
                            try:
                                chunk_data = json.loads(line[6:])
                                delta = chunk_data["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_content += content
                                    yield f"data: {json.dumps({'chunk': content})}\n\n"
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue

            # Parse accumulated content into files
            try:
                data = _extract_json(full_content)
                files = data.get("files", data)
                validated = validate_files(files)
                yield f"data: {json.dumps({'done': True, 'files': validated})}\n\n"
                return
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                continue

        except ValidationError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        except Exception as e:
            last_error = e
            continue

    yield f"data: {json.dumps({'error': f'Website generate nahi ho paayi: {last_error}'})}\n\n"
