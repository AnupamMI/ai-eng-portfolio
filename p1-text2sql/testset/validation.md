# Test-set validation

**0 errors, 1 warnings.**

## Warnings

- da1: readings rev and orders give the same result on seed 1

## Composition

| split | clear | ambiguous | metric | time_window | entity | scope | granularity | (question, reading) pairs |
|---|---|---|---|---|---|---|---|---|
| dev | 5 | 5 | 1 | 1 | 1 | 1 | 1 | 15 |
| test | 25 | 25 | 6 | 5 | 5 | 5 | 4 | 77 |

## Gold SQL difficulty, clear vs ambiguous (test set, mean per question)

Ambiguous questions use their first reading. The groups should differ in ambiguity,
not in SQL difficulty.

| measure | clear | ambiguous |
|---|---|---|
| joins | 0.96 | 1.00 |
| aggregates | 1.00 | 1.04 |
| subqueries/CTEs | 0.16 | 0.04 |
| uses dates | 0.56 | 0.72 |
| GROUP BY | 0.48 | 0.48 |
| HAVING | 0.12 | 0.04 |
| chars | 171.36 | 173.60 |

## Results per reading (seed 0 rows / seed 1 rows)

| id | reading | rows s0 | rows s1 | first rows (seed 0) |
|---|---|---|---|---|
| dc1 | r1 | 1 | 1 | (10) |
| dc2 | r1 | 1 | 1 | (109216.19) |
| dc3 | r1 | 3 | 3 | (Deluxe Router) / (Compact Headphones) / (Compact Monitor) |
| dc4 | r1 | 4 | 4 | (cancelled, 253) / (delivered, 2656) / (placed, 33) |
| dc5 | r1 | 1 | 1 | (70) |
| da1 | rev | 1 | 1 | (Emma Das) |
| da1 | orders | 1 | 1 | (Noah Khan) |
| da2 | 30d | 1 | 1 | (7) |
| da2 | 90d | 1 | 1 | (29) |
| da3 | 3orders | 1 | 1 | (263) |
| da3 | both_years | 1 | 1 | (200) |
| da4 | gross | 1 | 1 | (165067.31) |
| da4 | net | 1 | 1 | (149832.91) |
| da5 | monthly | 30 | 30 | (2024-01, 12) / (2024-02, 8) / (2024-03, 8) |
| da5 | yearly | 3 | 3 | (2024, 124) / (2025, 125) / (2026, 51) |
| c01 | r1 | 1 | 1 | (82203.21) |
| c02 | r1 | 1 | 1 | (101) |
| c03 | r1 | 1 | 1 | (117043.23) |
| c04 | r1 | 5 | 1 | (Classic Anthology) / (Classic Cookbook) / (Eco Journal) |
| c05 | r1 | 1 | 1 | (31) |
| c06 | r1 | 5 | 5 | (Zara Garcia) / (Ravi Patel) / (Omar Chen) |
| c07 | r1 | 6 | 6 | (Books, 1437) / (Clothing, 1332) / (Electronics, 1482) |
| c08 | r1 | 6 | 6 | (Books, 26826.67) / (Clothing, 45908.61) / (Electronics, 444285.62) |
| c09 | r1 | 1 | 1 | (340) |
| c10 | r1 | 1 | 1 | (42847.20) |
| c11 | r1 | 1 | 1 | (India) |
| c12 | r1 | 1 | 1 | (134) |
| c13 | r1 | 1 | 1 | (1345.56) |
| c14 | r1 | 15 | 9 | (2971) / (2974) / (2975) |
| c15 | r1 | 12 | 12 | (2025-01, 68) / (2025-02, 53) / (2025-03, 77) |
| c16 | r1 | 1 | 1 | (Classic Vase) |
| c17 | r1 | 4 | 4 | (bank_transfer, 110883.30) / (card, 819711.18) / (paypal, 198288.35) |
| c18 | r1 | 41 | 50 | (Emma Müller) / (Mateo Novak) / (Nora Patel) |
| c19 | r1 | 1 | 1 | (525.39) |
| c20 | r1 | 3 | 1 | (Deluxe Scarf) / (Pro Biography) / (Pro Charger) |
| c21 | r1 | 19 | 20 | (Lucas Fischer) / (Omar Chen) / (Emma Müller) |
| c22 | r1 | 1 | 1 | (8.29) |
| c23 | r1 | 1 | 1 | (10025.41) |
| c24 | r1 | 8 | 12 | (Omar Müller, 15) / (Arjun Khan, 11) / (Mateo Khan, 0) |
| c25 | r1 | 1 | 1 | (180533.43) |
| a01 | rev | 1 | 1 | (Zara Garcia) |
| a01 | orders | 1 | 1 | (Arjun Nguyen) |
| a02 | units | 1 | 1 | (Classic Textbook) |
| a02 | rev | 1 | 1 | (Classic Drive) |
| a03 | rev | 6 | 6 | (Electronics) / (Sports) / (Home) |
| a03 | units | 6 | 6 | (Electronics) / (Books) / (Toys) |
| a04 | units | 1 | 1 | (Classic Vase) |
| a04 | customers | 1 | 1 | (Deluxe Speaker) |
| a05 | rev | 1 | 1 | (204347.02) |
| a05 | cash | 1 | 1 | (194710.21) |
| a06 | rev | 3 | 3 | (Chloe Sharma) / (Kenji Haddad) / (Omar Smith) |
| a06 | orders | 3 | 3 | (Kenji Haddad) / (Ravi Nguyen) / (Arjun Patel) |
| a07 | calendar | 1 | 1 | (319) |
| a07 | 30d | 1 | 1 | (435) |
| a08 | ytd | 1 | 1 | (772986.30) |
| a08 | 12m | 1 | 1 | (1131947.00) |
| a09 | 30d | 3 | 3 | (Emma Silva) / (Ethan Kim) / (Arjun Lopez) |
| a09 | 90d | 3 | 3 | (Kenji Smith) / (Ravi Ito) / (Emma Silva) |
| a10 | q1 | 1 | 1 | (21) |
| a10 | 3m | 1 | 1 | (30) |
| a11 | 7d | 1 | 1 | (65810.06) |
| a11 | week | 1 | 1 | (69442.36) |
| a12 | registered | 1 | 1 | (300) |
| a12 | ever | 1 | 1 | (269) |
| a12 | 90d | 1 | 1 | (214) |
| a13 | delivered | 1 | 1 | (307) |
| a13 | paid | 1 | 1 | (369) |
| a14 | units | 1 | 1 | (613) |
| a14 | distinct | 1 | 1 | (60) |
| a15 | 2orders | 267 | 274 | (Emma Wilson) / (Nora Kim) / (Lucas Fischer) |
| a15 | 2months | 260 | 267 | (Emma Wilson) / (Nora Kim) / (Lucas Fischer) |
| a16 | signup | 1 | 1 | (51) |
| a16 | first_order | 1 | 1 | (48) |
| a17 | all | 1 | 1 | (1219) |
| a17 | not_cancelled | 1 | 1 | (1118) |
| a18 | all | 1 | 1 | (536.58) |
| a18 | not_cancelled | 1 | 1 | (546.11) |
| a19 | europe | 1 | 1 | (91) |
| a19 | eu | 1 | 1 | (58) |
| a20 | any | 1 | 1 | (108) |
| a20 | full | 1 | 1 | (68) |
| a21 | not_cancelled | 1 | 1 | (171) |
| a21 | all | 1 | 1 | (173) |
| a22 | calendar | 24 | 24 | (2024-07, 14719.94) / (2024-08, 15280.18) / (2024-09, 8968.24) |
| a22 | month_of_year | 12 | 12 | (01, 133947.26) / (02, 109656.36) / (03, 150890.19) |
| a23 | list | 269 | 275 | (Emma Wilson, 20) / (Nora Kim, 9) / (Lucas Fischer, 16) |
| a23 | avg_buyers | 1 | 1 | (11.15) |
| a23 | avg_all | 1 | 1 | (10.00) |
| a24 | monthly | 12 | 12 | (2025-01, 16187.86) / (2025-02, 10781.99) / (2025-03, 18504.38) |
| a24 | quarterly | 4 | 4 | (1, 45474.23) / (2, 66670.30) / (3, 65907.60) |
| a25 | list | 30 | 30 | (2026-06-01, 11) / (2026-06-02, 15) / (2026-06-03, 13) |
| a25 | avg | 1 | 1 | (14.50) |
