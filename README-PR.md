# PR: AGROL OpenAI Ads — jawna kwalifikacja produktów, poprawa wariantów

Zmiana proponowana do `trustdeal/agrolsklep-openai-katalog`, **nie wdrożona** na `main`.

- Dodaje do publikowanego CSV `is_ads_eligible=true` dla produktów bez jawnej flagi; respektuje `false` ze źródła.
- Normalizuje samodzielne produkty: `listing_has_variations=false`, puste `group_id`. Nie zmienia grupowania prawidłowych wariantów.
- Zamienia błędną nazwę SEO w polu sprzedawcy na `AGROL`. Nie zgaduje marki producenta — `brand` pozostaje ze źródła; generator raportuje tę usterkę.
- Waliduje obowiązkowe pola, HTTPS, ceny i waluty, `sale_price`, flagi oraz JSON wariantów; ostrzega o powtórzonych wariantach i brakujących słownikach wariantów.
- Zachowuje dzienny harmonogram oraz publikację przez GitHub Pages na tym samym adresie `/openai.csv`; nie modyfikuje reklam ani feedów w Ads Manager.
- Uruchamia testy jednostkowe przed publikacją.

**Obowiązkowa weryfikacja przed merge:** na źródłowym pliku TSV sprawdzić liczbę rekordów, poprawny układ kolumn oraz wyświetlanie produktów i wyświetlenia kampanii po publikacji. To nie jest gwarantowana naprawa zera w statystykach `Ready`. Źródłowy `brand` wymaga osobnej naprawy w WooCommerce/CTX.

**GitHub permissions:** próba utworzenia gałęzi przez aktualny konektor zwróciła 403 (`Resource not accessible by integration`), więc załączony zestaw nie został przesłany do repozytorium. Po odblokowaniu zapisu należy opublikować go jako osobny Pull Request, bez automatycznego merge.
