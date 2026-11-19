"""AI Power Grid video backend for Hermes (community plugin, not an official AIPG project).

The grid takes a video as a job: ``POST /videos/jobs`` answers at once with a job id and the
clip is fetched from ``GET /videos/jobs/{id}`` when it is done. A job cannot be cancelled and
is billed when it completes, so the request carries the most it may cost, taken from the
grid's public price list.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from agent.secret_scope import get_secret_str
from agent.video_gen_provider import VideoGenProvider, error_response, save_url_video, success_response

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.aipowergrid.io/v1"
KEY_PAGE = "https://console.aipowergrid.io/dashboard/api-key"
CLIENT = {"X-AIPG-Client": "hermes-aipg-video/1.0.0", "Accept": "application/json"}

FPS = 24
SECONDS = (2, 3, 5, 8, 10)  # the grid takes 8n+1 frames; these are whole seconds at 24 fps
DEFAULT_SECONDS = 3
# aspect ratio → resolution → size the video models on the grid accept
SIZES = {
    "16:9": {"540p": "960x544", "480p": "768x448"},
    "9:16": {"540p": "544x960"},
    "1:1": {"540p": "704x704"},
}
MEDIA_HOSTS = (".aipg.art", ".aipowergrid.io")
POLL_SECONDS = 5.0
WAIT_SECONDS = 600.0
MAX_INLINE_IMAGE_CHARS = 8_000_000


def _api_key() -> str:
    return get_secret_str("AIPG_API_KEY").strip()


def _base_url() -> str:
    return (get_secret_str("AIPG_BASE_URL").strip() or DEFAULT_BASE_URL).rstrip("/")


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail", body.get("error")) if isinstance(body, dict) else body
        if isinstance(detail, dict):
            detail = detail.get("message") or detail
        return str(detail)[:400] if detail else f"HTTP {response.status_code}"
    except Exception:
        return f"HTTP {response.status_code}"


def _own_media(url: str) -> bool:
    """Only https links to the grid's own storage are downloaded."""
    try:
        parts = urlparse(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password
            and any(host.endswith(s) and len(host) > len(s) for s in MEDIA_HOSTS))


def _online_models(client: httpx.Client, base: str) -> list[str]:
    response = client.get(f"{base}/status/models", headers=CLIENT, timeout=15)
    response.raise_for_status()
    rows = response.json()
    return [str(m["name"]) for m in (rows if isinstance(rows, list) else [])
            if isinstance(m, dict) and m.get("type") == "video" and (m.get("count") or 0) > 0 and m.get("name")]


def _rates(client: httpx.Client, base: str) -> dict[str, float]:
    """Price per second of video by lower-cased model name, from the public price list."""
    response = client.get(f"{base}/pricing", headers=CLIENT, timeout=15)
    response.raise_for_status()
    out: dict[str, float] = {}
    for m in ((response.json().get("price_book") or {}).get("models") or []):
        rate = (m.get("rates") or {}).get("per_video_second_usd")
        if isinstance(rate, (int, float)) and rate > 0:
            out[str(m.get("model")).lower()] = float(rate)
    return out


def _seconds(duration: Optional[int]) -> int:
    """The longest offered length that is not above the wish, so a clip never costs more than asked for."""
    if not duration:
        return DEFAULT_SECONDS
    return max([s for s in SECONDS if s <= int(duration)] or [SECONDS[0]])


def _size(aspect_ratio: str, resolution: str) -> tuple[str, str]:
    ratio = aspect_ratio if aspect_ratio in SIZES else "16:9"
    by_resolution = SIZES[ratio]
    return ratio, by_resolution.get((resolution or "").lower(), by_resolution["540p"])


class AIPGVideoGenProvider(VideoGenProvider):
    """Text-to-video and image-to-video on AI Power Grid."""

    name = "aipg"
    display_name = "AI Power Grid"

    def is_available(self) -> bool:
        return bool(_api_key())

    def list_models(self) -> list[dict[str, Any]]:
        """Video models that have a worker right now; empty when the grid cannot be reached."""
        try:
            base = _base_url()
            with httpx.Client() as client:
                names = _online_models(client, base)
                try:
                    rates = _rates(client, base)
                except Exception:
                    rates = {}
        except Exception as exc:
            logger.debug("AIPG video model list failed: %s", exc)
            return []
        return [{"id": n, "display": n, "modalities": ["text", "image"],
                 **({"price": f"${rates[n.lower()]:g} per second"} if n.lower() in rates else {})} for n in names]

    def capabilities(self) -> dict[str, Any]:
        return {"modalities": ["text", "image"], "aspect_ratios": list(SIZES), "resolutions": ["480p", "540p"],
                "min_duration": SECONDS[0], "max_duration": SECONDS[-1], "supports_audio": False,
                "supports_negative_prompt": False, "supports_seed": False, "supports_upscale": False,
                "max_reference_images": 0, "max_inline_image_chars": MAX_INLINE_IMAGE_CHARS}

    def get_setup_schema(self) -> dict[str, Any]:
        return {"name": "AI Power Grid", "badge": "paid",
                "tag": "open video models served by independent GPU operators; clips of 2 to 10 seconds with sound, "
                       "from text or a start picture; billed per second of video (community plugin)",
                "env_vars": [{"key": "AIPG_API_KEY", "prompt": "AI Power Grid API key", "url": KEY_PAGE}]}

    def generate(
        self, prompt: str, *, model: Optional[str] = None, image_url: Optional[str] = None,
        reference_image_urls: Optional[list[str]] = None, duration: Optional[int] = None,
        aspect_ratio: str = "16:9", resolution: str = "540p", negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None, seed: Optional[int] = None, **kwargs: Any,
    ) -> dict[str, Any]:
        prompt = (prompt or "").strip()
        ratio, size = _size(aspect_ratio, resolution)
        seconds = _seconds(duration)
        state = {"model": (model or "").strip()}

        def fail(error: str, error_type: str) -> dict[str, Any]:
            return error_response(error=error, error_type=error_type, provider=self.name, model=state["model"],
                                  prompt=prompt, aspect_ratio=ratio)

        if not prompt:
            return fail("prompt is required", "invalid_request")
        key = _api_key()
        if not key:
            return fail(f"AIPG_API_KEY is not set. Create a key at {KEY_PAGE}.", "missing_credentials")
        image = (image_url or "").strip()
        if image and not image.lower().startswith("data:image/"):
            return fail("AI Power Grid takes the start picture as a file: pass the path of a local image "
                        "instead of a web link.", "invalid_image_url")
        base = _base_url()
        auth = {**CLIENT, "Authorization": f"Bearer {key}"}
        try:
            with httpx.Client() as client:
                if not state["model"]:
                    online = _online_models(client, base)
                    if not online:
                        return fail("No video model is online on AI Power Grid right now.", "no_model")
                    state["model"] = online[0]
                rate = _rates(client, base).get(state["model"].lower())
                if not rate:
                    return fail(f"AI Power Grid publishes no price for the video model {state['model']!r}; "
                                "nothing was sent.", "no_price")
                # the most this clip may cost: the published price plus a little room for rounding
                ceiling = math.ceil(rate * seconds * 1e6) + 1000
                body: dict[str, Any] = {"model": state["model"], "prompt": prompt, "frames": seconds * FPS + 1,
                                        "size": size, "max_cost_micro_usd": ceiling}
                if image:
                    body["image"] = image
                response = client.post(f"{base}/videos/jobs", json=body, timeout=120,
                                       headers={**auth, "Idempotency-Key": str(uuid.uuid4())})
                if response.status_code not in (200, 202):
                    why = {402: "Not enough credit on the AI Power Grid account for this clip.",
                           429: "AI Power Grid is busy with other clips of this account, or too many requests were sent; "
                                "try again in a minute."}.get(response.status_code, _detail(response))
                    return fail(f"{why} Nothing was billed.", "api_error")
                job = response.json()
                job_id = str(job.get("job_id") or "")
                if not job_id:
                    return fail("AI Power Grid accepted the request but returned no job id.", "empty_response")
                deadline = time.monotonic() + WAIT_SECONDS
                while job.get("state") not in ("completed", "closed_without_result"):
                    if time.monotonic() >= deadline:
                        return fail(f"The clip was not ready after {int(WAIT_SECONDS)} seconds (job {job_id}). The job "
                                    "cannot be cancelled: it may still complete and be billed.", "timeout")
                    time.sleep(POLL_SECONDS)
                    try:
                        polled = client.get(f"{base}/videos/jobs/{job_id}", headers=auth, timeout=30)
                    except httpx.HTTPError:
                        continue
                    if polled.status_code == 200:
                        job = polled.json()
        except httpx.HTTPError as exc:
            return fail(f"AI Power Grid could not be reached: {exc}", "api_error")

        billed = job.get("actual_micro")
        cost = billed / 1e6 if isinstance(billed, (int, float)) else None
        if job.get("state") != "completed":
            paid = f"and billed ${cost:.4f}" if cost else "nothing was billed"
            return fail(f"AI Power Grid ended the clip without a result; {paid} (job {job_id}).", "job_failed")
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        media = (result.get("media") or [{}])[0] if isinstance(result.get("media"), list) else {}
        url = str(media.get("url") or "") if isinstance(media, dict) else ""
        if not url:
            return fail(f"AI Power Grid reports the clip as done but sent no file (job {job_id}).", "empty_response")
        if not _own_media(url):
            return fail("AI Power Grid returned a video link that does not point to its own storage; it was not "
                        f"opened (job {job_id}).", "untrusted_url")
        try:
            video = str(save_url_video(url, prefix="aipg"))
        except Exception as exc:
            logger.debug("AIPG: saving the clip locally failed (%s); returning the link", exc)
            video = url
        extra: dict[str, Any] = {"job_id": job_id, "size": size, "has_audio": True}
        if cost is not None:
            extra["cost_usd"] = round(cost, 6)
        if result.get("worker"):
            extra["worker"] = str(result["worker"])
        return success_response(video=video, model=str(job.get("model") or state["model"]), prompt=prompt,
                                modality="image" if image else "text", aspect_ratio=ratio, duration=seconds,
                                provider=self.name, extra=extra)


def register(ctx) -> None:
    """Plugin entry point."""
    ctx.register_video_gen_provider(AIPGVideoGenProvider())
