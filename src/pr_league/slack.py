import httpx


class SlackError(Exception):
    pass


class SlackMessenger:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._http = client or httpx.Client(
            base_url="https://slack.com/api",
            timeout=30,
            headers={"Authorization": f"Bearer {token}"},
        )

    def send(self, user_id: str, text: str) -> None:
        response = self._http.post("/chat.postMessage", json={"channel": user_id, "text": text})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise SlackError(f"chat.postMessage to {user_id} failed: {body.get('error', 'unknown')}")
