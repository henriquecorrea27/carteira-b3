"""Discord webhook (free). Messages go as plain content (≤ 2000 chars each), with mentions disabled."""

import logging
import time

import httpx

from app.notifications.base import NotifierError

log = logging.getLogger(__name__)
_RETRIES = 3


class DiscordNotifier:
    name = "discord"
    max_length = 2000

    def __init__(self, webhook_url: str, client: httpx.Client | None = None, username: str = "Carteira B3"):
        self._url = webhook_url
        self._client = client or httpx.Client(timeout=20)
        self._username = username

    def send(self, messages: list[str]) -> None:
        for content in messages:
            if len(content) > self.max_length:
                raise NotifierError(f"mensagem com {len(content)} caracteres (limite {self.max_length})")
            self._post({"content": content, "username": self._username, "allowed_mentions": {"parse": []}})

    def _post(self, payload: dict) -> None:
        for attempt in range(1, _RETRIES + 1):
            try:
                response = self._client.post(self._url, params={"wait": "true"}, json=payload)
            except httpx.HTTPError as err:
                if attempt == _RETRIES:
                    raise NotifierError(f"sem conexão com o Discord ({type(err).__name__})") from err
                time.sleep(2 * attempt)
                continue
            if response.status_code == 429 and attempt < _RETRIES:
                retry_after = _retry_after(response)
                log.info("discord rate limit, retrying in %.1fs", retry_after)
                time.sleep(retry_after)
                continue
            if response.is_success:
                return
            raise NotifierError(_describe(response))


def _retry_after(response: httpx.Response) -> float:
    try:
        return min(float(response.json().get("retry_after", 1)), 30.0)
    except ValueError:
        return 1.0


def _describe(response: httpx.Response) -> str:
    if response.status_code in (401, 404):
        return f"o Discord recusou o webhook (HTTP {response.status_code}) — confira a DISCORD_WEBHOOK_URL"
    try:
        detail = response.json().get("message")
    except ValueError:
        detail = None
    return f"o Discord respondeu HTTP {response.status_code}" + (f": {detail}" if detail else "")
