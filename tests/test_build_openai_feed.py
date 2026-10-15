"""Regression tests for Ads eligibility and product variants."""
import unittest
from collections import Counter
from scripts.build_openai_feed import normalize_row


def product(**changes):
    values = {
        "item_id": "100", "title": "Pług śnieżny", "description": "Pług do traktora",
        "url": "https://agrolsklep.pl/p/100", "brand": "Demarol",
        "seller_name": "Maszyny rolnicze na sprzedaż - Agrol Sklep",
        "image_url": "https://agrolsklep.pl/img/100.jpg", "availability": "in_stock",
        "price": "1999.00 PLN", "sale_price": "", "group_id": "100",
        "listing_has_variations": "", "variant_dict": "",
    }
    values.update(changes)
    return values


class NormalizationTests(unittest.TestCase):
    def convert(self, row):
        return normalize_row(row, 2, set(), set(), Counter())

    def test_standalone_ads_flag_and_seller(self):
        r = self.convert(product())
        self.assertEqual(r["is_ads_eligible"], "true")
        self.assertEqual(r["listing_has_variations"], "false")
        self.assertEqual(r["group_id"], "")
        self.assertEqual(r["seller_name"], "AGROL")
        self.assertEqual(r["brand"], "Demarol")

    def test_variant_preserves_grouping(self):
        r = self.convert(product(item_id="101", group_id="55", listing_has_variations="true", variant_dict='{"Wariant Produktu":"2,5m"}'))
        self.assertEqual(r["listing_has_variations"], "true")
        self.assertEqual(r["group_id"], "55")
        self.assertTrue(r["variant_dict"])

    def test_explicit_ads_ineligible_is_preserved(self):
        self.assertEqual(self.convert(product(is_ads_eligible="false"))["is_ads_eligible"], "false")

    def test_invalid_ads_flag_rejected(self):
        with self.assertRaises(ValueError):
            self.convert(product(is_ads_eligible="maybe"))

    def test_invalid_price_rejected(self):
        with self.assertRaises(ValueError):
            self.convert(product(price="19 USD bad"))

    def test_malformed_variant_rejected(self):
        with self.assertRaises(ValueError):
            self.convert(product(item_id="101", group_id="55", listing_has_variations="true", variant_dict='not json'))

    def test_duplicate_id_rejected(self):
        seen = set()
        normalize_row(product(), 2, seen, set(), Counter())
        with self.assertRaises(ValueError):
            normalize_row(product(), 3, seen, set(), Counter())


if __name__ == "__main__":
    unittest.main()
