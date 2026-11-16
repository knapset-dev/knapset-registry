"""
Sample Info Provider Module.
Domain: general
"""

from typing import Any, Dict, List
from info_providers.base import BaseInfoProvider, NormalizedListing


class SampleMarketProvider(BaseInfoProvider):
    name = "sample_provider"
    title = "Sample Market Provider"
    source_domain = "example-market.org"
    default_currency = "USD"
    version = "1.0.0"
    author = "knapset-dev"
    description = "Reference BaseInfoProvider skeleton returning deterministic sample listings"
    min_app_version = "1.0.0"
    category = "general"
    domain = "general"
    tags = ["sample", "provider", "reference"]

    def adapt_item(self, raw_data: Dict[str, Any]) -> NormalizedListing:
        return NormalizedListing(
            id=str(raw_data.get("id", "sample-101")),
            title=str(raw_data.get("title", "Sample Item")),
            price=float(raw_data.get("price", 0.0)),
            currency=str(raw_data.get("currency", "USD")),
            url=str(raw_data.get("url", "https://example-market.org")),
            source=self.name,
            description=str(raw_data.get("description", "")),
            is_new=bool(raw_data.get("is_new", True)),
            condition="new" if raw_data.get("is_new", True) else "used",
            condition_label="new" if raw_data.get("is_new", True) else "used",
            is_secure_deal=True,
            deal_type="buyer protection",
            seller_name="ExampleStore",
            seller_verified=True,
            seller_score=5.0,
            raw=raw_data,
        )

    def fetch_listings(
        self,
        category: str,
        query: str = "",
        pages: int = 1,
        **kwargs: Any,
    ) -> List[NormalizedListing]:
        sample = {
            "id": f"sample-{category}-101",
            "title": f"Sample {category.upper()} {query}".strip(),
            "price": 200.0,
            "currency": "USD",
            "url": "https://example-market.org/item/101",
            "description": "Brand new item with standard seller warranty.",
            "is_new": True,
        }
        return [self.adapt_item(sample)]
