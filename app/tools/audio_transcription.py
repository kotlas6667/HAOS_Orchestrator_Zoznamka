from __future__ import annotations

import base64
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx

from app.config import settings

_OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"

_MIME_TO_SUFFIX = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
}


def _normalize_audio_bytes(audio_base64: str) -> bytes:
    raw = (audio_base64 or "").strip()
    if not raw:
        raise ValueError("audio_base64 is empty")
    return base64.b64decode(raw, validate=False)


def _suffix_for_content_type(content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    return _MIME_TO_SUFFIX.get(normalized, ".bin")


async def transcribe_audio(
    *,
    audio_base64: str,
    audio_content_type: str = "",
    preferred_provider: str = "",
) -> dict[str, str]:
    """Transcribe an audio payload to plain text for Discord + reply generation."""
    audio_bytes = _normalize_audio_bytes(audio_base64)
    provider = (preferred_provider or settings.dating_reply_provider or "openai").strip().lower()

    if provider == "gemini" and settings.gemini_api_key:
        text = await _transcribe_with_gemini(audio_bytes, audio_content_type)
        return {
            "provider": "gemini",
            "model": settings.dating_reply_gemini_model,
            "text": text,
        }

    if settings.openai_api_key:
        text = await _transcribe_with_openai(audio_bytes, audio_content_type)
        return {
            "provider": "openai",
            "model": "gpt-4o-mini-transcribe",
            "text": text,
        }

    if settings.gemini_api_key:
        text = await _transcribe_with_gemini(audio_bytes, audio_content_type)
        return {
            "provider": "gemini",
            "model": settings.dating_reply_gemini_model,
            "text": text,
        }

    raise RuntimeError("Chýba OPENAI_API_KEY aj GEMINI_API_KEY, audio neviem prepísať.")


async def _transcribe_with_openai(audio_bytes: bytes, audio_content_type: str) -> str:
    suffix = _suffix_for_content_type(audio_content_type)
    with NamedTemporaryFile(suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        temp_path.write_bytes(audio_bytes)
        with temp_path.open("rb") as handle:
            files = {"file": (temp_path.name, handle, audio_content_type or "application/octet-stream")}
            data = {"model": "gpt-4o-mini-transcribe"}
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
            async with httpx.AsyncClient(verify=False, timeout=120.0) as client:
                response = await client.post(
                    _OPENAI_TRANSCRIPTION_URL,
                    headers=headers,
                    data=data,
                    files=files,
                )
                response.raise_for_status()
        payload = response.json()

    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("OpenAI vrátil prázdny prepis audia.")
    return text


async def _transcribe_with_gemini(audio_bytes: bytes, audio_content_type: str) -> str:
    model = (settings.dating_reply_gemini_model or "gemini-2.5-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": settings.gemini_api_key}
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "Prepíš hlasovú správu do čistého textu. "
                        "Nepridávaj komentár, nepopisuj zvuky navyše, vráť len prepísaný text. "
                        "Ak je audio nezrozumiteľné, uveď čo najpresnejší čiastočný prepis."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "Prepíš túto audio správu do slovenčiny alebo pôvodného jazyka správy."},
                    {
                        "inline_data": {
                            "mime_type": audio_content_type or "audio/mp4",
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
    }
    async with httpx.AsyncClient(verify=False, timeout=120.0) as client:
        response = await client.post(url, params=params, json=payload)
        response.raise_for_status()
        data = response.json()

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini nevrátil kandidátov pre prepis audia.")

    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text = "\n".join(str(part.get("text") or "").strip() for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise RuntimeError("Gemini vrátil prázdny prepis audia.")
    return text
