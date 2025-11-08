import time, random, requests, datetime as dt
from typing import Iterable, Dict, Any, List, Optional

DEFAULT_HEADERS = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
]

class BaseClient:
    def __init__(self, rate_per_min: int = 60, proxies: Optional[List[str]] = None, auth_header: Optional[str] = None):
        self.delay = max(60.0 / max(rate_per_min, 1), 0.2)
        self.proxies = proxies or []
        self.auth_header = auth_header
        self._last = 0.0

    def _throttle(self):
        now = time.time()
        dt_ = now - self._last
        if dt_ < self.delay:
            time.sleep(self.delay - dt_)
        self._last = time.time()

    def _pick_headers(self) -> Dict[str, str]:
        h = random.choice(DEFAULT_HEADERS).copy()
        if self.auth_header:
            h.update({"Authorization": self.auth_header})
        return h

    def _pick_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        p = random.choice(self.proxies)
        return {"http": p, "https": p}

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        self._throttle()
        return requests.get(url, params=params or {}, headers=self._pick_headers(), proxies=self._pick_proxy(), timeout=25)

    @staticmethod
    def days_ago_iso(days: int) -> str:
        return (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
