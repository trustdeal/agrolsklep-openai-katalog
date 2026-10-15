"""Build a validated OpenAI Ads product CSV from the AGROLSKLEP CTX TSV feed.

Only the publisher output is normalized. WooCommerce/CTX source data is unchanged.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import urllib.request
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCE_URL = "https://agrolsklep.pl/wp-content/uploads/woo-feed/chatgpt/tsv/openai.tsv"
DEFAULT_OUTPUT = Path("public/openai.csv")
REQUIRED_FIELDS = (
    "item_id", "title", "description", "url", "brand", "seller_name",
    "image_url", "availability", "price",
)
STOCK_VALUES = {"in_stock", "out_of_stock", "pre_order", "backorder", "unknown"}
PRICE_RE = re.compile(r"^(\d+(?:\.\d{1,2})?) ([A-Z]{3})$")
LEGACY_SELLER = "Maszyny rolnicze na sprzedaż - Agrol Sklep"
CANONICAL_SELLER = "AGROL"


def validated_price(value: str, *, item_id: str, label: str) -> tuple[Decimal, str]:
    match = PRICE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Item {item_id}: invalid {label} {value!r}; expected '123.45 PLN'")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as error:
        raise ValueError(f"Item {item_id}: invalid {label}") from error
    if amount <= 0:
        raise ValueError(f"Item {item_id}: non-positive {label}")
    return amount, match.group(2)


def normalize_row(
    row: dict[str, str], line: int, seen_ids: set[str],
    seen_variants: set[tuple[str, str]], warnings: Counter[str]
) -> dict[str, str] | None:
    if None in row or any(value is None for value in row.values()):
        raise ValueError(f"Line {line}: malformed tab-separated data")
    row = {key: (val or "").strip() for key, val in row.items()}
    item_id = row["item_id"]
    if not item_id or item_id in seen_ids:
        raise ValueError(f"Line {line}: missing or duplicate item_id {item_id!r}")
    seen_ids.add(item_id)

    for key in REQUIRED_FIELDS:
        if key != "price" and not row[key]:
            raise ValueError(f"Line {line} (item {item_id}): empty required {key}")
    if not row["url"].startswith("https://") or not row["image_url"].startswith("https://"):
        raise ValueError(f"Line {line} (item {item_id}): product/image URL must be HTTPS")
    if row["availability"] not in STOCK_VALUES:
        raise ValueError(f"Line {line} (item {item_id}): invalid availability")
    if len(row["title"]) > 150 or len(row["description"]) > 5000:
        raise ValueError(f"Line {line} (item {item_id}): title/description too long")

    if not row["price"]:
        warnings["skipped_no_price"] += 1
        return None
    price, currency = validated_price(row["price"], item_id=item_id, label="price")
    if row.get("sale_price"):
        sale_price, sale_currency = validated_price(
            row["sale_price"], item_id=item_id, label="sale_price"
        )
        if sale_currency != currency or sale_price >= price:
            raise ValueError(f"Line {line} (item {item_id}): invalid sale_price")

    # Ads eligibility is not interchangeable with search/checkout eligibility.
    ads_eligible = row.get("is_ads_eligible", "").lower() or "true"
    if ads_eligible not in {"true", "false"}:
        raise ValueError(f"Line {line} (item {item_id}): invalid is_ads_eligible")
    row["is_ads_eligible"] = ads_eligible

    # Unset flag used to leave hundreds of standalone products ambiguous.
    variants_flag = row.get("listing_has_variations", "").lower() or "false"
    if variants_flag not in {"true", "false"}:
        raise ValueError(f"Line {line} (item {item_id}): invalid listing_has_variations")
    row["listing_has_variations"] = variants_flag
    variant_dict = row.get("variant_dict", "")
    if variants_flag == "false":
        if variant_dict:
            raise ValueError(f"Line {line} (item {item_id}): standalone item has variant_dict")
        row["group_id"] = ""  # Standalone items must not point at themselves.
    else:
        group_id = row.get("group_id", "")
        if not group_id or group_id == item_id:
            raise ValueError(f"Line {line} (item {item_id}): invalid variant group_id")
        if not variant_dict:
            warnings["variants_without_variant_dict"] += 1
        else:
            try:
                variant_values = json.loads(variant_dict)
            except json.JSONDecodeError as error:
                raise ValueError(f"Line {line} (item {item_id}): invalid variant_dict JSON") from error
            if not isinstance(variant_values, dict) or not variant_values:
                raise ValueError(f"Line {line} (item {item_id}): empty/invalid variant_dict")
            signature = (group_id, json.dumps(variant_values, sort_keys=True, ensure_ascii=False))
            if signature in seen_variants:
                warnings["duplicate_variant_signatures"] += 1
            seen_variants.add(signature)

    # Fix seller name but DO NOT invent manufacturers. Source brand needs mapping in WooCommerce.
    if row["seller_name"] == LEGACY_SELLER:
        row["seller_name"] = CANONICAL_SELLER
        warnings["seller_name_normalized"] += 1
    if row["brand"] == LEGACY_SELLER:
        warnings["generic_brand_needs_source_fix"] += 1
    return row


def build_feed(raw: bytes, output: Path, minimum_products: int = 1900) -> dict[str, int]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t")
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or not set(REQUIRED_FIELDS).issubset(headers):
        raise ValueError(f"Missing or duplicate columns: {headers}")
    if "listing_has_variations" not in headers or "group_id" not in headers or "variant_dict" not in headers:
        raise ValueError("Missing variant structure columns")
    fields = list(headers)
    if "is_ads_eligible" not in fields:
        fields.insert(fields.index("price") + 1, "is_ads_eligible")

    rows: list[dict[str, str]] = []
    warnings: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_variants: set[tuple[str, str]] = set()
    count = 0
    for line, raw_row in enumerate(reader, start=2):
        count += 1
        row = normalize_row(raw_row, line, seen_ids, seen_variants, warnings)
        if row is not None:
            rows.append(row)
    if count < minimum_products or len(rows) < minimum_products:
        raise ValueError(f"Catalog unexpectedly small: source={count}, output={len(rows)}")
    if warnings["skipped_no_price"] > max(10, int(count * 0.01)):
        raise ValueError(f"Too many items without price: {warnings['skipped_no_price']}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Source: {count}, published: {len(rows)}, ads_eligible_true: "
          f"{sum(row['is_ads_eligible'] == 'true' for row in rows)}")
    print(f"Warnings: {dict(warnings)}")
    return {"source": count, "published": len(rows), **warnings}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, default=None, help="Use saved input TSV for local testing")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.source_file:
        raw = args.source_file.read_bytes()
    else:
        url = os.environ.get("SOURCE_URL", SOURCE_URL)
        request = urllib.request.Request(url, headers={"User-Agent": "AgrolsklepCatalogPublisher/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise ValueError(f"Feed HTTP {response.status}")
            raw = response.read(50_000_001)
        if not raw or len(raw) > 50_000_000:
            raise ValueError("Empty feed or larger than 50 MB")
    summary = build_feed(raw, args.output)
    if args.output == DEFAULT_OUTPUT:
        (args.output.parent / "index.html").write_text(
            '<!doctype html><html lang="pl"><meta charset="utf-8">'
            '<title>AGROLSKLEP — product feed</title>'
            '<p>AGROLSKLEP — product catalog for advertising.</p>'
            '<p><a href="openai.csv">Current OpenAI product feed (CSV)</a></p>'
            '</html>\n', encoding="utf-8"
        )
        (args.output.parent / ".nojekyll").touch()
    print("Feed ready:", args.output, summary)


if __name__ == "__main__":
    main()
