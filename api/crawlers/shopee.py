from .base import BaseClient
from typing import Dict, Any, Iterable, List, Optional
import datetime as dt
import re

SHOP_URL_PAT = re.compile(r"shopee\.vn/(?:(?:shop/)?(?P<slug_or_id>[A-Za-z0-9\-_.]+))(?:#.*)?$")

class ShopeeClient(BaseClient):
    def resolve_shop_id(self, shop_link: str) -> Optional[str]:
        m = SHOP_URL_PAT.search(shop_link)
        if not m:
            return None
        slug_or_id = m.group("slug_or_id")
        return slug_or_id  # placeholder: treat slug as id if your endpoint accepts

    def list_shop_products(self, shop_id: str, offset: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        # Placeholder — replace with your partner/official endpoint
        # For now, return empty to avoid broken call; HTML crawler handles real extraction.
        return []

    def list_product_reviews(self, product_id: str, cursor: int = 0, page_size: int = 50) -> List[Dict[str, Any]]:
        # Placeholder — replace with your endpoint if available
        return []

    def crawl_shop_reviews(self, shop_link: str, max_products: int = 200, days_back: int = 365) -> Iterable[Dict[str, Any]]:
        # In this packaged project, we rely on HTML crawler service for Shopee (no API).
        # This function is kept for compatibility; it returns empty iterator.
        return []
