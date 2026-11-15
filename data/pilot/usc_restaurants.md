# Trojan Fork — USC restaurant & menu dataset (pilot)

_Generated 2026-11-14. All records below come from sources read on 2026-11-14; “last checked” means the day the source was read, not the day the restaurant last updated it._

## 1. Executive summary

- **10 real restaurants profiled**, all inside the USC DPS University Park patrol area (5 are USC-operated campus dining, 5 are off-campus or USC Village tenants).
- **169 menu records**: 104 with a listed price, 63 with restaurant-published nutrition, **0 estimated**.
- **33 more venues identified** from official directories but not yet processed (section 6).
- **Biggest gap:** no single item has both a price and published nutrition. Independent restaurants publish prices but no nutrition; chains publish nutrition but not local prices online. A “under $12 with 25 g protein” search therefore has **no verified match yet** (section 8).
- **Not done in this session:** Google Places discovery (no API key), geocoding and walking times (no service reachable), the backend/API/database, and the PDF. This file is the data extraction only.

## 2. Geographic scope

**Boundary used:** USC Department of Public Safety **University Park Campus Patrol Area**.  
**Official source:** [dps.usc.edu/patrol](https://dps.usc.edu/patrol/) (page last modified 2026-04-18) and the linked [UPC Patrol Area map PDF](https://dps.usc.edu/wp-content/uploads/2025/01/UPC-Patrol-Area.pdf) (uploaded January 2025).

**Not the same as:**
- the **DPS Response Zone** — the wider area where DPS responds to calls for service; routine patrol is defined only for the Patrol Zone (USC Housing’s 2013 area map, src-03);
- **Clery geography** — the federal crime-reporting geography, which DPS states differs from its patrol area (src-01, src-04).

**Official street-by-street description (src-01):**

Start: Vermont Ave & Exposition Blvd, then:

1. West on Exposition Blvd to Normandie Ave
2. North on Normandie Ave to Adams Blvd
3. East on Adams Blvd to Vermont Ave
4. North on Vermont Ave to 22nd St
5. East on 22nd St to Hoover St
6. North on Hoover St to Washington Blvd
7. East on Washington Blvd to Grand Ave
8. South on Grand Ave to Jefferson Blvd
9. East on Jefferson Blvd to Hill St
10. South on Hill St to 37th St
11. West on 37th St to Grand Ave
12. South on Grand Ave to 39th St
13. West on 39th St to Figueroa St
14. South on Figueroa St to Martin Luther King Jr. Blvd
15. West on MLK Jr. Blvd to Vermont Ave
16. North on Vermont Ave to Exposition Blvd (closes loop)

**Polygon (approximate).** DPS publishes the boundary as text and a map image, not coordinates. Each vertex below was placed by hand at the named intersection — **not geocoded** — so treat every vertex as ±100 m. The polygon’s computed area is **2.34 sq mi**, against DPS’s stated “about 2.5 square miles”, which is a reasonable sanity check. Any restaurant within 150 m of the edge is flagged.

| # | Vertex | Lat | Lng |
|---|---|---|---|
| 1 | Vermont & Exposition | 34.0183 | -118.2916 |
| 2 | Normandie & Exposition | 34.0183 | -118.3003 |
| 3 | Normandie & Adams | 34.0327 | -118.3003 |
| 4 | Vermont & Adams | 34.0327 | -118.2916 |
| 5 | Vermont & 22nd | 34.0368 | -118.2916 |
| 6 | Hoover & 22nd | 34.0368 | -118.2841 |
| 7 | Hoover & Washington | 34.0399 | -118.2841 |
| 8 | Washington Blvd bend (approx.) | 34.0399 | -118.2800 |
| 9 | Grand & Washington | 34.0332 | -118.2690 |
| 10 | Grand & Jefferson | 34.0211 | -118.2752 |
| 11 | Hill & Jefferson | 34.0204 | -118.2729 |
| 12 | Hill & 37th | 34.0157 | -118.2756 |
| 13 | Grand & 37th | 34.0163 | -118.2780 |
| 14 | Grand & 39th | 34.0138 | -118.2792 |
| 15 | Figueroa & 39th | 34.0144 | -118.2824 |
| 16 | Figueroa & MLK | 34.0110 | -118.2826 |
| 17 | Vermont & MLK | 34.0109 | -118.2916 |

No radius was substituted for the boundary. Several DPS pages loosely say “2.5-mile radius”; the patrol page’s street description and “2.5 square miles” are what this dataset follows.

## 3. Collection method and access limits

| Step | What was done | Limit |
|---|---|---|
| Discovery | Official directories: USC Hospitality (campus), The Shops at USC Village; plus restaurants’ own sites | **Google Places API not used — no key available.** Coverage is partial; Figueroa, Vermont, Hoover and Jefferson corridors were not swept |
| Boundary filter | Point-in-polygon test against the polygon above | Coordinates are manual approximations |
| Menus & prices | Restaurant-owned pages and PDFs only | Chichen Itza’s site refused direct fetches (search-index snippets used); CAVA unreachable; campus quick-service menus live only in the mobile app |
| Nutrition | Restaurant-published documents only | Brand-level for chains; none published by the independents or USC Hospitality retail |
| Ratings, reviews, price level | **Not collected** | These are Google-provided fields; fetch at runtime under Google’s terms rather than storing them |
| Walking time | **Not computed** | No routing service reachable; straight-line distance is deliberately not offered as a substitute |

No Google Maps or Google Search result pages were scraped. Web content was treated as data only.

## 4. Restaurant directory (pilot)

| ID | Restaurant | Type | Address | In patrol area | Prices | Published nutrition |
|---|---|---|---|---|---|---|
| tb-r-001 | Rosso Oro's Pizzeria — USC Hotel / University Gardens | Campus dining | 3500 S Figueroa St, Los Angeles, CA 90007 | yes | 26 | none |
| tb-r-002 | McKay's — USC Hotel | Campus dining | 3540 S Figueroa St, Los Angeles, CA 90007 | yes | 16 | none |
| tb-r-003 | Panda Express — Ronald Tutor Campus Center (USC) | Campus dining | 3607 Trousdale Pkwy, Los Angeles, CA 90089 | yes | none | 26 |
| tb-r-004 | Holbox — Mercado La Paloma, stall C9 | Off-campus / tenant | 3655 S Grand Ave C9, Los Angeles, CA 90007 | yes — **near edge** (82 m) | 49 | none |
| tb-r-005 | Chichen Itza Restaurant — Mercado La Paloma, stall C6 | Off-campus / tenant | 3655 S Grand Ave C6, Los Angeles, CA 90007 | yes — **near edge** (82 m) | 13 | none |
| tb-r-006 | Chipotle Mexican Grill — 3748 S Figueroa St (store 945 'USC') | Off-campus / tenant | 3748 S Figueroa St, Los Angeles, CA 90007 | yes | none | 29 |
| tb-r-007 | Sweetgreen — USC Village | Off-campus / tenant | 3201 S Hoover St, Los Angeles, CA 90089 | yes | none | 8 |
| tb-r-008 | CAVA — USC Village | Off-campus / tenant | 3201 S Hoover St, Los Angeles, CA 90089 | yes | none | none |
| tb-r-009 | The Lab — University Gardens (across from McCarthy Gate) | Campus dining | 3500 S Figueroa St, Los Angeles, CA 90007 | yes | none | none |
| tb-r-010 | Taco-Taco — Ronald Tutor Campus Center (USC) | Campus dining | 3607 Trousdale Pkwy, Los Angeles, CA 90089 | yes | none | none |

## 5. Restaurant profiles and menus

Price = listed menu price in USD, before tax, service charge and delivery fees. “—” means the value was not published or not retrieved (stored as `null`). **Estimated nutrition: none anywhere in this file.**

### Rosso Oro's Pizzeria — USC Hotel / University Gardens  
`tb-r-001`

- **Address:** 3500 S Figueroa St, Los Angeles, CA 90007 (approx. 34.0203, -118.2809)
- **Patrol area:** inside, about 517 m from the boundary
- **Cuisine:** Pizza, Italian-American · **Service:** quick service · **Campus dining:** yes
- **Hours:** Mon–Sun 11:00-19:00 (valid 2026-08-24 to 2026-12-04)
- **Phone:** 213-743-2077 · **Dine-in:** yes · **Pickup:** unknown · **Delivery:** unknown
- **Links:** [website](https://hospitality.usc.edu/dining-locations/rosso-oros/) · [menu](https://hospitality.usc.edu/wp-content/uploads/2026/06/Rosso-Oros-Pizzeria-Menu-Poster-.Nuvola.pdf)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Operator page lists 3500 S Figueroa St but also says the pizzeria is inside the USC Hotel (listed at 3540). Available for Catering2Go.
- **Sources:** src-07, src-08, src-06 · last checked 2026-11-14

**Menu and prices** (nutrition: unknown — not published)

| Category | Item | Description | Price | Add-ons / labels | Src |
|---|---|---|---|---|---|
| Pizza by the slice | Fresh Mozzarella slice | — | $2.90 | 1 slice | src-08 |
| Pizza by the slice | Pepperoni slice | — | $3.75 | 1 slice | src-08 |
| Pizza by the slice | Loaded slice | — | $4.10 | 1 slice | src-08 |
| Pizza by the slice | Caprese slice | — | $3.75 | 1 slice | src-08 |
| Salads | Side Caesar or House Salad | — | $11.00 | +Grilled chicken breast $7.00 | src-08 |
| Salads | Caesar Salad | — | $16.00 | +Grilled chicken breast $7.00 | src-08 |
| Salads | Cobb Salad | — | $19.00 | +Grilled chicken breast $7.00 | src-08 |
| Salads | Antipasto Salad | — | $16.00 | +Grilled chicken breast $7.00 | src-08 |
| Specialty pies | Fresh Mozzarella pie | — | $23.00 | whole pie (size not printed) | src-08 |
| Specialty pies | Pepperoni pie | — | $30.00 | whole pie (size not printed) | src-08 |
| Specialty pies | Loaded pie | — | $33.00 | whole pie (size not printed) | src-08 |
| Specialty pies | Caprese pie | — | $30.00 | whole pie (size not printed) | src-08 |
| Pastas | Spaghetti & Meatballs | Served with garlic bread | $17.00 | — | src-08 |
| Pastas | Grilled Chicken Fettuccine Alfredo | Served with garlic bread | $17.00 | — | src-08 |
| Sandwiches | Chicken Parmesan sandwich | Served with potato chips | $12.00 | — | src-08 |
| Sandwiches | Cold Italian Sub | Served with potato chips | $12.00 | — | src-08 |
| Wings | Wings | Original Hot or BBQ; blue cheese or ranch | Half dozen $12.00 / Dozen $20.00 | — | src-08 |
| Combos | Pizza Combo | Slice of pizza, house salad, fountain drink | $11.00 | — | src-08 |
| Combos | Wings Combo | 6 wings, dressing, fries, fountain drink | $18.00 | — | src-08 |
| Sides & more | French Fries | — | $6.00 | — | src-08 |
| Sides & more | Bag of potato chips | — | $3.00 | — | src-08 |
| Sides & more | Freshly baked cookie | — | $3.00 | — | src-08 |
| Drinks | Fountain drink | — | Glass $4.00 / Pitcher $12.00 | — | src-08 |
| Drinks | Bottled water | — | $5.00 | — | src-08 |
| Drinks | Sparkling water | — | $5.00 | — | src-08 |
| Drinks | Soda can | — | $4.00 | — | src-08 |

### McKay's — USC Hotel  
`tb-r-002`

- **Address:** 3540 S Figueroa St, Los Angeles, CA 90007 (approx. 34.0195, -118.2813)
- **Patrol area:** inside, about 467 m from the boundary
- **Cuisine:** American, Breakfast · **Service:** full service · **Campus dining:** yes
- **Hours:** Mon–Sun 06:00-11:00 (valid 2026-08-24 to 2026-12-04)
- **Phone:** 213-743-4111 · **Dine-in:** yes · **Pickup:** unknown · **Delivery:** unknown
- **Links:** [website](https://hospitality.usc.edu/dining-locations/mckays/) · [menu](https://hospitality.usc.edu/wp-content/uploads/2025/08/McKays-Breakfast-Menu.pdf)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Breakfast only in the published hours. Prices exclude tax and gratuity; an 18% service charge is added to every check. Reservations via OpenTable.
- **Sources:** src-09, src-10, src-06 · last checked 2026-11-14

**Menu and prices** (nutrition: unknown — not published)

| Category | Item | Description | Price | Add-ons / labels | Src |
|---|---|---|---|---|---|
| Buffet | Breakfast Buffet | Continental, yogurt & cereal station, coffee/tea/juice, plus one a la carte item | Adult $30.00 / Child (5-11) $15.00 | — | src-10 |
| A la carte breakfast | Avocado Toast | Smashed avocado, garlic aioli, cherry tomatoes, edamame, furikake, grilled sesame bread | $16.00 | +Organic cage-free egg $5.00 | src-10 |
| A la carte breakfast | Sausage Burrito | Scrambled eggs, chicken apple sausage, cheddar, hash browns, flour tortilla, salsa | $16.00 | — | src-10 |
| A la carte breakfast | Salmon and Lox | Hard-boiled egg, capers, red onion, tomato, toasted bagel with cream cheese | $19.00 | — | src-10 |
| A la carte breakfast | American Breakfast | Two cage-free eggs, chicken apple sausage or bacon, potatoes, toast or English muffin | $23.00 | — | src-10 |
| A la carte breakfast | Omelet | Choose 3 fillings (ham, bacon, chicken apple sausage, onion, mushrooms); with potatoes | $23.00 | +Avocado $3.00 | src-10 |
| A la carte breakfast | Buttermilk Pancakes | Stack of 3, maple syrup, powdered sugar | $14.00 | +Blueberries $2.00; +Chocolate chips $2.00; +Banana $2.00; 3 pancakes | src-10 |
| Coffee & juice bar | Brewed Illy coffee | — | $4.00 | — | src-10 |
| Coffee & juice bar | Dammann herbal tea | — | $4.00 | — | src-10 |
| Coffee & juice bar | Espresso | — | $4.00 | — | src-10 |
| Coffee & juice bar | Cappuccino | — | $6.00 | — | src-10 |
| Coffee & juice bar | Latte | — | $7.00 | — | src-10 |
| Coffee & juice bar | Macchiato | — | $6.00 | — | src-10 |
| Coffee & juice bar | Hot chocolate | — | $5.00 | — | src-10 |
| Coffee & juice bar | Milk | — | $4.00 | — | src-10 |
| Coffee & juice bar | Assorted juice | — | $5.00 | — | src-10 |

### Panda Express — Ronald Tutor Campus Center (USC)  
`tb-r-003`

- **Address:** 3607 Trousdale Pkwy, Los Angeles, CA 90089 (approx. 34.0203, -118.2863)
- **Patrol area:** inside, about 537 m from the boundary
- **Cuisine:** Chinese-American · **Service:** quick service · **Campus dining:** yes
- **Hours:** Mon–Thu 10:30-18:00; Fri 10:30-17:00; Sat–Sun closed (valid 2026-08-24 to 2026-12-04)
- **Phone:** 213-821-3481 · **Dine-in:** unknown · **Pickup:** yes · **Delivery:** unknown
- **Links:** [website](https://hospitality.usc.edu/dining-locations/panda-express/) · [menu](https://www.pandaexpress.com/nutritioninformation) · [order](https://hospitality.usc.edu/mobile-ordering)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Prices for the campus unit are not published on the web (mobile app only). Nutrition is brand-wide; item availability at this unit is unconfirmed.
- **Sources:** src-11, src-12, src-06 · last checked 2026-11-14

**Nutrition — PUBLISHED BY THE RESTAURANT (not estimated). Prices not published online for this location.**

| Category | Item | Serving | kcal | Protein g | Carbs g | Fat g | Fiber g | Sugar g | Sodium mg | Notes | Src |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Sides (base) | Chow Mein | 12 oz | 520 | 14 | 89 | 12 | 5 | 11 | 1040 | USC availability not confirmed | src-12 |
| Sides (base) | Chow Fun | 12 oz | 580 | 13 | 103 | 13 | 1 | 8 | 1570 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Sides (base) | Fried Rice | 12 oz | 610 | 15 | 109 | 13 | 3 | 2 | 810 | USC availability not confirmed | src-12 |
| Sides (base) | White Steamed Rice | 12 oz | 570 | 11 | 129 | 0 | 0 | 0 | 0 | USC availability not confirmed | src-12 |
| Sides (base) | Quinoa Fried Rice | 12 oz | 600 | 15 | 91 | 19 | 4 | 1 | 740 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Sides (base) | Super Greens (side) | 10 oz | 180 | 8 | 17 | 9 | 8 | 8 | 660 | USC availability not confirmed | src-12 |
| Vegetable entrees | Eggplant Tofu | 6.1 oz | 310 | 8 | 23 | 21 | 4 | 15 | 350 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Vegetable entrees | Super Greens (entree) | 3.5 oz | 45 | 3 | 5 | 2 | 3 | 2 | 130 | USC availability not confirmed | src-12 |
| Chicken entrees | Black Pepper Chicken | 6.3 oz | 200 | 15 | 9 | 12 | 1 | 3 | 1070 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Chicken entrees | Kung Pao Chicken | 6.7 oz | 270 | 20 | 16 | 14 | 2 | 7 | 1300 | USC availability not confirmed | src-12 |
| Chicken entrees | Grilled Teriyaki Chicken | 6.1 oz | 280 | 38 | 13 | 9 | 0 | 9 | 610 | USC availability not confirmed | src-12 |
| Chicken entrees | Mushroom Chicken | 5.7 oz | 180 | 13 | 12 | 9 | 1 | 5 | 820 | USC availability not confirmed | src-12 |
| Chicken entrees | The Original Orange Chicken | 6.2 oz | 560 | 19 | 63 | 25 | 1 | 24 | 1000 | USC availability not confirmed | src-12 |
| Chicken entrees | Honey Sesame Chicken Breast | 6.2 oz | 420 | 16 | 44 | 20 | 2 | 19 | 540 | USC availability not confirmed | src-12 |
| Chicken entrees | String Bean Chicken Breast | 5.6 oz | 210 | 15 | 15 | 10 | 3 | 7 | 600 | USC availability not confirmed | src-12 |
| Chicken entrees | SweetFire Chicken Breast | 5.8 oz | 360 | 15 | 40 | 15 | 2 | 19 | 370 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Beef entrees | Beijing Beef | 5.6 oz | 480 | 14 | 46 | 27 | 2 | 21 | 600 | USC availability not confirmed | src-12 |
| Beef entrees | Broccoli Beef | 6.3 oz | 190 | 17 | 14 | 7 | 2 | 7 | 600 | USC availability not confirmed | src-12 |
| Beef entrees | Black Pepper Sirloin Steak | 5.9 oz | 200 | 17 | 15 | 8 | 1 | 8 | 560 | USC availability not confirmed | src-12 |
| Seafood entrees | Honey Walnut Shrimp | 4.4 oz | 340 | 13 | 28 | 20 | 1 | 6 | 790 | USC availability not confirmed | src-12 |
| Appetizers | Chicken Egg Roll | 1 roll (2.75 oz) | 200 | 6 | 20 | 10 | 2 | 2 | 340 | USC availability not confirmed | src-12 |
| Appetizers | Chicken Potsticker | 3 pcs (3.3 oz) | 160 | 6 | 20 | 6 | 1 | 2 | 250 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Appetizers | Cream Cheese Rangoon | 3 pcs (2.4 oz) | 190 | 5 | 24 | 8 | 2 | 1 | 180 | USC availability not confirmed | src-12 |
| Appetizers | Vegetable Spring Roll | 2 rolls (3.5 oz) | 240 | 4 | 24 | 14 | 2 | 0 | 560 | USC availability not confirmed | src-12 |
| Soup | Hot & Sour Soup (cup) | 12.2 oz | 140 | 9 | 16 | 4 | 1 | 4 | 1000 | Regional or limited-time per Panda; USC availability unknown | src-12 |
| Soup | Hot & Sour Soup (bowl) | 17.4 oz | 170 | 10 | 20 | 6 | 1 | 6 | 1260 | Regional or limited-time per Panda; USC availability unknown | src-12 |

### Holbox — Mercado La Paloma, stall C9  
`tb-r-004`

- **Address:** 3655 S Grand Ave C9, Los Angeles, CA 90007 (approx. 34.0170, -118.2783)
- **Patrol area:** inside near boundary, about 82 m from the boundary
- **Cuisine:** Mexican, Seafood · **Service:** counter service · **Campus dining:** no
- **Hours:** Mon closed; Tue–Sun 11:30-21:00
- **Phone:** not retrieved · **Dine-in:** yes · **Pickup:** yes · **Delivery:** unknown
- **Links:** [website](https://www.holboxla.com/) · [menu](https://www.holboxla.com/menu.html) · [order](https://www.toasttab.com/local/order/holbox-3655-south-grand-avenue-c9)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Menu changes daily (restaurant statement). Monday closure is implied by 'Tuesday through Sunday' hours. 8-course tasting dinners Thu/Fri by reservation.
- **Sources:** src-15, src-16, src-17, src-31 · last checked 2026-11-14

**Menu and prices** (nutrition: unknown — not published)

| Category | Item | Description | Price | Add-ons / labels | Src |
|---|---|---|---|---|---|
| Ceviches | Ceviche de Atun | Baja bluefin tuna ceviche | $28.00 ⚠ also $26.00 (src-15) | — | src-15, src-17 |
| Ceviches | Ceviche Mixto | Shrimp, octopus & white seabass ceviche | $23.00 ⚠ also $20.00 (src-15) | — | src-15, src-17 |
| Ceviches | Ceviche de Kanpachi | Farmed Baja kanpachi ceviche | $24.00 ⚠ also $23.00 (src-15) | — | src-15, src-17 |
| Ceviches | Ceviche de Jurel | Local yellowtail ceviche | $25.00 | — | src-15, src-17 |
| Ceviches | Ceviche de Mero | Baja grouper ceviche | $25.00 | — | src-15, src-17 |
| Ceviches | Ceviche de Besugo | Farmed sea bream ceviche | $26.00 ⚠ also $25.00 (src-15) | — | src-15, src-17 |
| Ceviches | Ceviche de Lenguado | Baja halibut ceviche | $25.00 | — | src-15 |
| Tostadas | Tostada de Kanpachi & Uni | Kanpachi ceviche with 20 g Santa Barbara uni | $22.00 | — | src-15 |
| Tostadas | Smoked Kanpachi Tostada | Smoked kanpachi, shrimp, scallops, arbol-guajillo sauce, avocado | $9.00 | — | src-15 |
| Tostadas | Tostada de Atun | Bluefin tuna ceviche, avocado puree, arbol-guajillo sauce | $12.00 | — | src-15 |
| Tostadas | Tuna Tartar Tostada | Bluefin tartare, salsa negra, pickled vegetables, sesame | $10.00 | — | src-15 |
| Tostadas | Tostada de Jurel | Yellowtail, almond salsa macha, avocado puree | $10.00 | — | src-15 |
| Tostadas | Tostada de Mero | Grouper ceviche, fermented habanero | $10.00 | — | src-15 |
| Tostadas | Tostada de Besugo | Sea bream, avocado, fermented habanero | $10.00 | — | src-15 |
| Tostadas | Tostada de Lenguado | Halibut ceviche, avocado, fermented habanero, aceite verde | $11.00 | — | src-15 |
| Shellfish | Erizo (sea urchin) | Live sea urchin with bay scallop ceviche | $27.00 | — | src-15 |
| Aguachiles | Scallop Aguachile | Bay scallops, lime-serrano-cilantro marinade, avocado | $16.00 | — | src-15 |
| Aguachiles | Shrimp Aguachile | Prawns, lime-serrano-cilantro marinade, crispy heads, avocado | $28.00 | — | src-15 |
| Aguachiles | Spot Prawn & Scallop Aguachile | Live spot prawns, bay scallops, lime-serrano-cilantro marinade | $36.00 | — | src-15 |
| Cocteles | Coctel Mixto | Shrimp, octopus, bay scallops in sweet & sour coctel sauce | $18.00 | — | src-15 |
| Cocteles | Coctel de Camaron | Shrimp in house coctel sauce | $18.00 | — | src-15 |
| Tacos | Smoked Kanpachi Taco | Smoked fish, cheese, salsa cruda, avocado, peanut chili oil | $8.00 ⚠ also $7.00 (src-15) | 1 taco | src-15, src-17 |
| Tacos | Baja Fish Taco | Battered rockfish, crema, mayo, salsa roja, pico de gallo | $6.00 | 1 taco | src-15, src-17 |
| Tacos | Baja Shrimp Taco | Battered shrimp, crema, mayo, salsa roja, pico de gallo | $6.00 | 1 taco | src-15 |
| Tacos | Taco de Pulpo en su Tinta | Braised and fried octopus, calamari-ink sofrito | $8.00 ⚠ also $7.00 (src-15) | 1 taco | src-15, src-17 |
| Tacos | Scallop Taco | Seared scallop, chile x'catic sauce, caramelized onion, tomato, fennel (limited quantity) | $8.00 | 1 taco | src-15 |
| Tacos | Taco de Pescado al Carbon | Mesquite-grilled kanpachi, mayo, morita sauce, cabbage, pico, avocado puree | $8.00 | 1 taco | src-15, src-17 |
| Entrees | Pescado a las Brasas | Whole grilled branzino, cilantro rice, black beans, tortillas | $29.00 | — | src-15 |
| Entrees | Spot Prawns a la Talla | 1/2 lb grilled spot prawns, garlic butter, rice, beans | $65.00 | — | src-15 |
| Entrees | Camarones al Mojo | Wood-roasted shrimp in garlic-butter-chile, rice, beans, grilled bread | $28.00 | — | src-15 |
| Entrees | Sopa de Mariscos | Seafood stew with fish, mussels, shrimp, fish sausage, grilled bread | $24.00 | — | src-15 |
| Entrees | Pulpo a las Brasas | Mesquite-grilled octopus, almond pipian, rice, beans | $26.00 | — | src-15 |
| Entrees | Filete al Carbon | Mesquite-grilled branzino filet, rice, beans, x'catic sauce | $16.00 | — | src-15 |
| Entrees | Grilled Kanpachi Collars | Two grilled kanpachi collars, rice, beans, corn tortilla | $18.00 | — | src-15 |
| Entrees | Fried Rockfish Collars (small plate) | Breaded fried rockfish collars, salsa verde | $10.00 | — | src-15 |
| Dessert | Churros & Chocolate Sauce | — | $7.00 | — | src-15 |
| Dessert | Blood Orange Cranberry Cheesecake | — | $7.00 | — | src-15 |
| Shellfish | Ostiones (oysters) | Rotating oyster varieties | 3 pc $11.00 / Half dozen $20.00 / Dozen $36.00 | — | src-15 |
| Shellfish | Pata de Mula (blood clam) | Baja blood clams on the half shell | Half order $15.00 / Full order $23.00 | — | src-15 |
| Shellfish | Almeja Preparada | Surf clam on the half shell | $18 per lb (weight-priced) | — | src-15 |
| Entrees | Langosta al Carbon | Wood-grilled spiny lobster, rice, beans, tortillas | $45 per lb (weight-priced) | — | src-15 |
| Sides | Guacamole | — | Small $9.00 / Large $14.00 | — | src-15 |
| Sides | Chips & Salsa | — | $1.00 | — | src-15 |
| Sides | Side of salsa | — | $0.25 | — | src-15 |
| Sides | Side of cilantro rice | — | $2.00 | — | src-15 |
| Sides | Side of vegetarian refried black beans | — | $2.00 | vegetarian (restaurant's wording in item name) | src-15 |
| Beverages | Sparkling lemonade | — | $5.00 | — | src-15 |
| Beverages | Mexican Coke | — | $6.00 | 500 ml | src-15 |
| Beverages | Perrier | — | $5.00 | 12 oz | src-15 |
| Beverages | San Pellegrino | — | $9.00 | 750 ml | src-15 |
| Beverages | Diet Coke | — | $2.50 | 12 oz can | src-15 |

### Chichen Itza Restaurant — Mercado La Paloma, stall C6  
`tb-r-005`

- **Address:** 3655 S Grand Ave C6, Los Angeles, CA 90007 (approx. 34.0170, -118.2783)
- **Patrol area:** inside near boundary, about 82 m from the boundary
- **Cuisine:** Mexican, Yucatecan · **Service:** counter service · **Campus dining:** no
- **Hours:** not retrieved
- **Phone:** 213-741-1075 · **Dine-in:** unknown · **Pickup:** yes · **Delivery:** unknown
- **Links:** [website](https://chichenitzarestaurant.com/) · [menu](https://chichenitzarestaurant.com/menu) · [order](https://chichenitzarestaurant.com/order)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Full hours not retrieved (site showed only 'closes at 9PM' on the day indexed). Menu is PARTIAL: the site refused direct fetches, so only items visible in search-index snippets are recorded.
- **Sources:** src-18, src-19, src-21, src-22 · last checked 2026-11-14

**Menu and prices** (nutrition: unknown — not published)

| Category | Item | Description | Price | Add-ons / labels | Src |
|---|---|---|---|---|---|
| Appetizers | Longaniza Asada (appetizer) | House chorizo smoked over mesquite, avocado, roasted tomato sauce, tortillas | $11.50 ⚠ also $10.95 (src-19) | — | src-18, src-19 |
| Main dishes | Bistec a la Yucateca | 6 oz Angus NY strip, caramelized onions, rice, black bean puree, potato, plantain, tortillas | $22.95 ⚠ also $21.95 (src-19) | — | src-18, src-19 |
| Main dishes | Cochinita Pibil | Achiote & sour-orange pork cooked in banana leaf, pickled onion, black beans, rice, tortillas | $18.95 ⚠ also $17.95 (src-19) | — | src-18, src-19 |
| Main dishes | Tikin-xic | Two 4 oz basa filets with lime & achiote over rice, citrus jicama salad | $17.95 ⚠ also $17.50 (src-19) | — | src-18, src-19 |
| Main dishes | Trio Yucateco | Panucho, salbut and taco de cochinita | $15.95 | — | src-18, src-19 |
| Tacos | Tacos de Chicharron (order of 2) | Pork cracklings, pico de gallo, avocado | $8.25 ⚠ also $7.95 (src-19) | 2 tacos | src-18, src-19 |
| Tacos | Tacos de Cochinita (order of 2) | Shredded achiote pork, pickled red onion | $8.25 ⚠ also $7.95 (src-19) | 2 tacos | src-18, src-19 |
| Tacos | Tacos de Longaniza (order of 2) | Grilled pork chorizo, roasted tomato salsa, onions | $8.25 ⚠ also $7.95 (src-19) | 2 tacos | src-18, src-19 |
| Appetizers | Panuchos (order of 2) | Fried tortilla filled with black bean puree; lettuce, shredded turkey, pickled onion, avocado | $11.95 | 2 panuchos | src-19, src-21 |
| Main dishes | Pollo Asado | Mesquite-grilled boneless chicken leg in achiote & sour orange, plantains, onions, rice, black beans | $16.50 | — | src-21 |
| Tacos | Tacos de Pescado (order of 2) | Breaded fried fish, tartar sauce, cabbage, pico de gallo | $8.95 | 2 tacos | src-22 |
| Tortas | Torta de Cochinita Pibil | Shredded achiote pork, pickled onion, house pan frances | $13.95 | — | src-22 |
| Tortas | Torta de Poc Chuc | Marinated pork, black bean puree, lettuce, charred onion, roasted tomato sauce, pan frances | $13.95 | — | src-22 |

### Chipotle Mexican Grill — 3748 S Figueroa St (store 945 'USC')  
`tb-r-006`

- **Address:** 3748 S Figueroa St, Los Angeles, CA 90007 (approx. 34.0163, -118.2819)
- **Patrol area:** inside, about 215 m from the boundary
- **Cuisine:** Mexican, Fast casual · **Service:** quick service · **Campus dining:** no
- **Hours:** Mon–Sun 10:30-23:00
- **Phone:** 213-765-9068 · **Dine-in:** unknown · **Pickup:** yes · **Delivery:** yes
- **Links:** [website](https://locations.chipotle.com/ca/los-angeles/3748-s-figueroa-st) · [menu](https://chipotle.com/content/dam/chipotle/menu/nutrition/paper-menu-standard-no-pricing120221-us.pdf) · [order](https://www.chipotle.com/)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Prices are not published online ('check local menu boards'). Nutrition is per ingredient from a July 2022 brand document; an entree's totals are the sum of the chosen ingredients.
- **Sources:** src-23, src-24 · last checked 2026-11-14

**Nutrition — PUBLISHED BY THE RESTAURANT (not estimated). Prices not published online for this location.**

| Category | Item | Serving | kcal | Protein g | Carbs g | Fat g | Fiber g | Sugar g | Sodium mg | Notes | Src |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Tortillas & shells | Flour Tortilla (burrito) | 1 ea | 320 | 8 | 50 | 9 | 3 | 0 | 600 | — | src-24 |
| Tortillas & shells | Flour Tortilla (taco) | 1 ea | 80 | 2 | 13 | 2.5 | — | 0 | 160 | Fiber printed as '<1 g'; stored as null | src-24 |
| Tortillas & shells | Crispy Corn Tortilla | 1 ea | 70 | 1 | 10 | 3 | 1 | 0 | 0 | — | src-24 |
| Rice | Cilantro-Lime Brown Rice | 4 oz | 210 | 4 | 36 | 6 | 2 | 0 | 190 | — | src-24 |
| Rice | Cilantro-Lime White Rice | 4 oz | 210 | 4 | 40 | 4 | 1 | 0 | 350 | — | src-24 |
| Beans | Black Beans | 4 oz | 130 | 8 | 22 | 1.5 | 7 | 2 | 210 | — | src-24 |
| Beans | Pinto Beans | 4 oz | 130 | 8 | 21 | 1.5 | 8 | 1 | 210 | — | src-24 |
| Vegetables | Fajita Vegetables | 2 oz | 20 | 1 | 5 | 0 | 1 | 2 | 150 | — | src-24 |
| Proteins | Barbacoa | 4 oz | 170 | 24 | 2 | 7 | 1 | 0 | 530 | — | src-24 |
| Proteins | Chicken | 4 oz | 180 | 32 | 0 | 7 | 0 | 0 | 310 | — | src-24 |
| Proteins | Carnitas | 4 oz | 210 | 23 | 0 | 12 | 0 | 0 | 450 | — | src-24 |
| Proteins | Steak | 4 oz | 150 | 21 | 1 | 6 | 1 | 0 | 330 | — | src-24 |
| Proteins | Sofritas | 4 oz | 150 | 8 | 9 | 10 | 3 | 5 | 560 | — | src-24 |
| Salsas | Fresh Tomato Salsa | 4 oz | 25 | 0 | 4 | 0 | 1 | 1 | 550 | — | src-24 |
| Salsas | Roasted Chili-Corn Salsa | 4 oz | 80 | 3 | 16 | 1.5 | 3 | 4 | 330 | — | src-24 |
| Salsas | Tomatillo-Green Chili Salsa | 2 fl oz | 15 | 0 | 4 | 0 | 0 | 2 | 260 | — | src-24 |
| Salsas | Tomatillo-Red Chili Salsa | 2 fl oz | 30 | 0 | 4 | 0 | 1 | 0 | 500 | — | src-24 |
| Toppings | Cheese | 1 oz | 110 | 6 | 1 | 8 | 0 | 0 | 190 | — | src-24 |
| Toppings | Sour Cream | 2 oz | 110 | 2 | 2 | 9 | 0 | 2 | 30 | — | src-24 |
| Toppings | Guacamole (topping/side) | 4 oz | 230 | 2 | 8 | 22 | 6 | 1 | 370 | — | src-24 |
| Toppings | Guacamole (large) | 8 oz | 460 | 4 | 16 | 44 | 12 | 2 | 740 | — | src-24 |
| Toppings | Queso Blanco (entree portion) | 2 oz | 120 | 5 | 4 | 9 | 0 | 1 | 250 | — | src-24 |
| Toppings | Queso Blanco (side) | 4 oz | 240 | 10 | 7 | 18 | 0 | 2 | 490 | — | src-24 |
| Toppings | Queso Blanco (large) | 8 oz | 480 | 20 | 14 | 37 | — | 5 | 980 | Fiber printed as '<1 g'; stored as null | src-24 |
| Toppings | Supergreens Salad Mix | 3 oz | 15 | 1 | 3 | 0 | 2 | 1 | 15 | — | src-24 |
| Toppings | Romaine Lettuce (tacos) | 1 oz | 5 | 0 | 1 | 0 | 1 | 0 | 0 | — | src-24 |
| Chips & dressing | Chips (regular) | 4 oz | 540 | 7 | 73 | 25 | 7 | 1 | 390 | — | src-24 |
| Chips & dressing | Chips (large) | 6 oz | 810 | 11 | 110 | 38 | 11 | 2 | 590 | — | src-24 |
| Chips & dressing | Chipotle-Honey Vinaigrette | 2 fl oz | 220 | 1 | 18 | 16 | 1 | 12 | 850 | — | src-24 |

### Sweetgreen — USC Village  
`tb-r-007`

- **Address:** 3201 S Hoover St, Los Angeles, CA 90089 (approx. 34.0256, -118.2852)
- **Patrol area:** inside, about 982 m from the boundary
- **Cuisine:** Salads, Bowls · **Service:** quick service · **Campus dining:** no
- **Hours:** not retrieved
- **Phone:** not retrieved · **Dine-in:** unknown · **Pickup:** unknown · **Delivery:** unknown
- **Links:** [website](https://www.uscvillage.com/store/sweetgreen) · [menu](https://www.sweetgreen.com/menu)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** USC Village menu page not retrieved, so prices are null and nutrition is brand-level. Sweetgreen's own pages disagree on nutrition for the same bowl (see Conflicts).
- **Sources:** src-25, src-27, src-28, src-29 · last checked 2026-11-14

**Nutrition — PUBLISHED BY THE RESTAURANT (not estimated). Prices not published online for this location.**

| Category | Item | Serving | kcal | Protein g | Carbs g | Fat g | Fiber g | Sugar g | Sodium mg | Notes | Src |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Bowls | Harvest Bowl | 1 bowl as listed | 740 | 32 | 60 | 41 | — | — | — | src-29 lists 760 kcal / 40 g protein / 42 g fat / 60 g carbs; contains: milk, meat, tree nuts; Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Crispy Rice Bowl | 1 bowl as listed | 640 | 28 | 61 | 30 | — | — | — | src-29 lists 680 kcal / 33 g protein / 31 g fat / 61 g carbs; contains: meat, tree nuts, sesame; Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Chicken Pesto Parm | 1 bowl as listed | 525 | 35 | 38 | 23 | — | — | — | contains: wheat, meat, milk; Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Chicken Avocado Ranch | 1 bowl as listed | 715 | 27 | 56 | 42 | — | — | — | contains: meat, milk, eggs, wheat; Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Shroomami | 1 bowl as listed | 635 | 18 | 50 | 42 | — | — | — | src-29 lists 665 kcal / 20 g protein / 45 g fat / 51 g carbs; contains: soybeans, sesame, tree nuts; 'V' marker shown on Sweetgreen's page (meaning not confirmed); Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Omega Glow | 1 bowl as listed | 750 | 32 | 52 | 45 | — | — | — | contains: soybeans, wheat, fish, tree nuts, sesame; Brand menu; USC Village availability not confirmed | src-28 |
| Bowls | Steak Honey Crunch | 1 bowl as listed | 625 | 33 | 48 | 33 | — | — | — | contains: meat, wheat; Brand menu; USC Village availability not confirmed | src-28 |
| Salads | Kale Caesar | 1 bowl as listed | 545 | 41 | 18 | 35 | — | — | — | contains: milk, eggs, fish, meat, wheat; Brand menu; USC Village availability not confirmed | src-28 |

### CAVA — USC Village  
`tb-r-008`

- **Address:** 3201 S Hoover St, Los Angeles, CA 90089 (approx. 34.0256, -118.2852)
- **Patrol area:** inside, about 982 m from the boundary
- **Cuisine:** Mediterranean, Fast casual · **Service:** quick service · **Campus dining:** no
- **Hours:** not retrieved
- **Phone:** 213-212-9838 · **Dine-in:** unknown · **Pickup:** unknown · **Delivery:** unknown
- **Links:** [website](https://cava.com/) · [order](https://catering.cava.com/order-now)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** No menu items recorded: CAVA's nutrition/allergen guide and menu pages were not reachable in this session. CAVA publishes a nutrition guide, so this is a retrieval gap, not an absence of data.
- **Sources:** src-25, src-26, src-30 · last checked 2026-11-14

_No menu items recorded — see Notes._

### The Lab — University Gardens (across from McCarthy Gate)  
`tb-r-009`

- **Address:** 3500 S Figueroa St, Los Angeles, CA 90007 (approx. 34.0203, -118.2809)
- **Patrol area:** inside, about 517 m from the boundary
- **Cuisine:** American, Gastropub · **Service:** full service · **Campus dining:** yes
- **Hours:** Mon closed; Tue–Sat 15:00-22:00; Sun closed (valid 2026-08-24 to 2026-12-04)
- **Phone:** 213-740-5956 · **Dine-in:** yes · **Pickup:** unknown · **Delivery:** unknown
- **Links:** [website](https://hospitality.usc.edu/dining-locations/the-lab/)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** No menu published on the operator page. Guest parking $2/hour at the Figueroa structure with registration.
- **Sources:** src-13, src-06 · last checked 2026-11-14

_No menu items recorded — see Notes._

### Taco-Taco — Ronald Tutor Campus Center (USC)  
`tb-r-010`

- **Address:** 3607 Trousdale Pkwy, Los Angeles, CA 90089 (approx. 34.0203, -118.2863)
- **Patrol area:** inside, about 537 m from the boundary
- **Cuisine:** Mexican, Build-your-own · **Service:** quick service · **Campus dining:** yes
- **Hours:** Mon–Thu 11:00-18:30; Fri 11:00-16:30; Sat–Sun closed (valid 2026-08-24 to 2026-12-04)
- **Phone:** 213-821-3482 · **Dine-in:** unknown · **Pickup:** yes · **Delivery:** unknown
- **Links:** [website](https://hospitality.usc.edu/dining-locations/taco-taco/) · [order](https://hospitality.usc.edu/mobile-ordering)
- **Rating / reviews / price level / accessibility:** not collected
- **Notes:** Burritos, bowls and tacos; an 'EatWell Guacamole Bowl' is named but not priced. Meal swipes accepted for select items. Itemised menu only in the Campus Dining app.
- **Sources:** src-14, src-06 · last checked 2026-11-14

_No menu items recorded — see Notes._

## 6. Identified but not yet processed

These come from official directories and are almost certainly inside the patrol area, but they were not individually verified, geocoded or menu-extracted. They are **not** in the restaurant dataset.

**USC Hospitality — University Park Campus** (src-05; regular hours 2026-08-24 to 2026-12-04, src-06)

| Venue | Location | Regular hours (closed on days not listed) |
|---|---|---|
| Amy King Dundon-Berchtold University Club | 705 W 34th St | Mon-Fri 11:00-20:00 |
| Bowls | Tutor Campus Center | Mon-Thu 11:00-19:00; Fri 11:00-17:00 |
| Burger Crush | Tutor Campus Center food court | Mon-Thu 11:00-19:00; Fri 11:00-16:00 |
| C&G Juice Co. | Tutor Campus Center | Mon-Fri 10:00-18:00 |
| Cafe Annenberg | Wallis Annenberg Hall | Mon-Thu 07:30-18:30; Fri 07:30-15:00 |
| Chad Tons Family Cafe | Fertitta Hall | Mon-Thu 11:00-18:00 |
| Coffee Bean & Tea Leaf | School of Cinematic Arts | Mon-Thu 07:00-18:00; Fri 07:00-17:00 |
| Everybody's Kitchen (dining hall) | not listed | not in extracted hours |
| Law School Cafe | not listed | Mon-Thu 08:00-15:30; Fri 08:00-14:00 |
| Literatea | DML (building code as published) | Mon-Thu 08:00-15:00; Fri 08:00-13:30 |
| MoretonFig (private events venue) | Tutor Campus Center | Closed daily to walk-ins |
| Parkside Residential Dining Hall | not listed | not in extracted hours |
| Popovich Cafe | JKP (building code as published) | Mon-Thu 07:30-17:30; Fri 07:30-14:00 |
| Seeds Marketplace | Tutor Campus Center | Mon-Thu 07:00-18:00; Fri 07:00-17:00; Sat-Sun 09:00-15:00 |
| Slice Shop | Tutor Campus Center | Mon-Thu 11:00-17:00; Fri 11:00-16:00 |
| The Upstairs | Tutor Campus Center | Mon-Wed 11:00-19:00; Thu 11:00-23:00; Fri 11:00-17:00 |
| Trojan Grounds featuring illy | BSR (building code as published) | Mon-Fri 06:30-24:00; Sat-Sun 08:00-18:00 |
| Tutor Hall Cafe | RTH (building code as published) | Mon-Thu 08:00-16:00; Fri 08:00-15:00 |
| USC Village Dining Hall | 3096 S McClintock Ave | not in extracted hours |

**The Shops at USC Village — dining tenants** (3201 S Hoover St; src-25)

| Tenant | Phone | Status |
|---|---|---|
| Bruxie | 213-461-1400 | open |
| Cafe Dulce | — | open |
| Gogobop | 213-536-5031 | open |
| Il Giardino | 213-536-5773 | open |
| Insomnia Cookies | 213-740-2311 | open |
| Jimmy John's | — | open |
| Ramen Kenjo | 213-536-5922 | open |
| Rock & Reilly's | 213-566-8660 | open |
| Softies | — | open (unit 1710, 835 W Jefferson Blvd) |
| Starbucks | 213-460-1662 | open |
| SunLife Organics | 213-536-5659 | open |
| Terra Mia Pizzeria | — | open |
| Yoboseyo! Superette | — | open |
| Big Way Hot Pot | — | coming soon |

Also not swept: the other vendors inside Mercado La Paloma, and street-front restaurants along Figueroa, Vermont, Hoover, Jefferson, Adams and Washington. **This is not a complete list of restaurants in the patrol area.**

## 7. Conflicts and missing information

**Price conflicts** — rule applied: when official sources disagree, the **higher** price is stored so a budget filter can never show a false match; the other value is kept alongside it.

| Restaurant | Item | Stored | Other value | Why they differ |
|---|---|---|---|---|
| Holbox | Ceviche de Atun | $28.00 | $26.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Holbox | Ceviche Mixto | $23.00 | $20.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Holbox | Ceviche de Kanpachi | $24.00 | $23.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Holbox | Ceviche de Besugo | $26.00 | $25.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Holbox | Smoked Kanpachi Taco | $8.00 | $7.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Holbox | Taco de Pulpo en su Tinta | $8.00 | $7.00 (src-15) | Website menu dated 3.5.26 vs. undated Toast ordering page; menu changes daily |
| Chichen Itza Restaurant | Longaniza Asada (appetizer) | $11.50 | $10.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Bistec a la Yucateca | $22.95 | $21.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Cochinita Pibil | $18.95 | $17.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Tikin-xic | $17.95 | $17.50 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Tacos de Chicharron (order of 2) | $8.25 | $7.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Tacos de Cochinita (order of 2) | $8.25 | $7.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |
| Chichen Itza Restaurant | Tacos de Longaniza (order of 2) | $8.25 | $7.95 (src-19) | Two pages on the restaurant’s own site show different prices; neither is dated |

**Other conflicts**

- **Chichen Itza, stale page:** a legacy page on the restaurant’s site (src-20) lists Cochinita Pibil at $13.95, Pollo Asado $12.95, Poc Chuc $13.95 and Tikin-Xic $13.95 — well below every other official page. Treated as outdated and not used.
- **Sweetgreen nutrition:** the brand menu page (src-28) and a Los Angeles location page (src-29) give different figures for the same bowl — e.g. Harvest Bowl 740 kcal / 32 g protein vs 760 kcal / 40 g. The brand page values are stored and flagged for review; the USC Village page should replace both.
- **Rosso Oro’s address:** the operator lists 3500 S Figueroa St yet describes it as inside the USC Hotel, which the same site lists at 3540 S Figueroa St.
- **Patrol area size:** DPS pages variously say “2.5 square miles”, “2.5-mile radius” and “approximately 2-mile radius”. The street-by-street description is authoritative here.

**Missing**

- No Google Maps Platform credentials: Places API discovery, place IDs, ratings, review counts and price levels were NOT collected. Discovery used official directories (USC Hospitality, The Shops at USC Village) and restaurants' own sites, so coverage of the patrol zone is partial.
- No geocoder or routing service was reachable: boundary vertices and restaurant coordinates are manual approximations (about +/-100 m). No walking times were computed.
- Boundary polygon is derived from the official street-by-street text; where Washington Blvd bends is an added, approximate vertex.
- No estimated nutrition was produced: no source gave ingredient weights or portions that would support a defensible estimate.
- No item in this dataset has BOTH a listed price and published nutrition, so budget+macro queries cannot return a verified match yet.
- Chichen Itza and Sweetgreen data come from search-index snippets of official pages (direct fetch failed or was not done); treat as partial.
- CAVA menu and nutrition guide were not reachable; The Lab and Taco-Taco publish no web menu.
- Chain nutrition is brand-level (Chipotle doc is July 2022); item availability and prices at the USC-area units are unconfirmed.
- Hours are regular hours only. 'Last checked' is when the source was read, not when the restaurant last updated it.
- The backend/API/database/admin workflow and the PDF were not built in this session; this is the data extraction only.

## 8. What the data can answer today

Test request: _“Find a spicy vegetarian lunch under $12 with at least 25 grams of protein.”_ Budget, protein and dietary checks are applied as hard filters on stored values; nothing is relaxed.

**Verified matches: none.** No record has a price, published protein and a published vegetarian label together.

**Uncertain alternatives (shown separately, each failing at least one check):**

| Option | What is known | What is not verified |
|---|---|---|
| Chipotle build: sofritas + black beans + brown rice + cheese | Sum of Chipotle’s published per-ingredient values: **26 g protein, 600 kcal** | Price (not published online); vegetarian status (no label in the retrieved document); spice level; values are from a 2022 document |
| Sweetgreen Shroomami | Published: 18 g protein, 635 kcal; tofu-based, carries a “V” marker | **Fails the protein requirement**; price unknown; conflicting nutrition on another Sweetgreen page |
| Rosso Oro’s Pizza Combo | **$11.00** (slice, house salad, fountain drink) | Protein unknown; vegetarian depends on slice chosen and is not labelled |
| Holbox side of vegetarian refried black beans + cilantro rice | **$4.00** total; beans are named “vegetarian” by the restaurant | Protein unknown; a side, not a full lunch |

## 9. Coverage statistics

| Measure | Count |
|---|---|
| Restaurants profiled | 10 |
| Restaurants inside boundary | 10 |
| Restaurants near boundary | 2 |
| Campus dining profiled | 5 |
| Restaurants with any menu items | 7 |
| Restaurants with item prices | 4 |
| Restaurants with published nutrition | 3 |
| Restaurants with estimated nutrition | 0 |
| Restaurants with both price and nutrition on same item | 0 |
| Restaurants with no menu items | 3 |
| Menu items total | 169 |
| Menu items with price | 104 |
| Menu items with published nutrition | 63 |
| Menu items with estimated nutrition | 0 |
| Menu items with price conflict | 13 |
| Discovered not processed | 33 |
| Sources | 32 |

## 10. Source registry

All sources read on 2026-11-14. Status: _verified fetched_ = page or PDF opened and read; _partial snippet_ = only search-index text of the official page was available; _referenced not parsed_ = located but not opened; _inaccessible_ = fetch returned nothing.

| ID | Publisher | Type | Source date | Status | Limits |
|---|---|---|---|---|---|
| src-01 | [USC Department of Public Safety](https://dps.usc.edu/patrol/) | official web page | Page metadata: last modified 2026-04-18 | verified fetched | Street-by-street text only; no coordinates published. |
| src-02 | [USC DPS Crime Analysis Unit](https://dps.usc.edu/wp-content/uploads/2025/01/UPC-Patrol-Area.pdf) | official pdf map | Upload path dated 2025-01 (no date printed in indexed text) | referenced not parsed | Visual map; not used to derive vertices. |
| src-03 | [USC Housing](https://housing.usc.edu/index.php/publication/university-park-campus-area-map) | official pdf map | Revised July 2013 | referenced not parsed | Old (2013). Used only for the Patrol Zone vs Response Zone definitions. |
| src-04 | [USC Department of Public Safety](https://dps.usc.edu/alerts/clery/clery-map/) | official web page | — | referenced not parsed | Used only to distinguish Clery geography. |
| src-05 | [USC Hospitality](https://hospitality.usc.edu/dining-locations-upc) | official web page | — | verified fetched | Names + buildings only; no menus. |
| src-06 | [USC Hospitality](https://hospitality.usc.edu/hours-of-operation) | official web page | Hours valid 2026-08-24 to 2026-12-04 | verified fetched | Regular hours only; special/holiday hours not captured. Dining halls not in the extracted list. |
| src-07 | [USC Hospitality](https://hospitality.usc.edu/dining-locations/rosso-oros/) | official web page | — | verified fetched | Page gives 3500 S Figueroa St but says 'inside the USC Hotel' (hotel is listed at 3540). |
| src-08 | [USC Hospitality](https://hospitality.usc.edu/wp-content/uploads/2026/06/Rosso-Oros-Pizzeria-Menu-Poster-.Nuvola.pdf) | official menu pdf | Upload path dated 2026-06 | verified fetched | No currency symbol, sizes, calories or dietary labels printed. |
| src-09 | [USC Hospitality](https://hospitality.usc.edu/dining-locations/mckays/) | official web page | — | verified fetched | — |
| src-10 | [USC Hospitality](https://hospitality.usc.edu/wp-content/uploads/2025/08/McKays-Breakfast-Menu.pdf) | official menu pdf | Upload path dated 2025-08 | verified fetched | Dietary legend (GF/Vegetarian/VG/Nut Free) could not be matched to items. Prices exclude tax; 18% service charge added. |
| src-11 | [USC Hospitality](https://hospitality.usc.edu/dining-locations/panda-express/) | official web page | — | verified fetched | No menu or prices for the campus unit. |
| src-12 | [Panda Restaurant Group](https://www.pandaexpress.com/nutritioninformation) | official nutrition page | Footer (c) 2026; no update date | verified fetched | Brand-wide values; availability at the USC unit not confirmed. Allergens not itemised in extraction. |
| src-13 | [USC Hospitality](https://hospitality.usc.edu/dining-locations/the-lab/) | official web page | — | verified fetched | No menu on page. |
| src-14 | [USC Hospitality](https://hospitality.usc.edu/dining-locations/taco-taco/) | official web page | — | verified fetched | Menu only in the Campus Dining mobile app. |
| src-15 | [Holbox](https://www.holboxla.com/menu.html) | official menu page | Menu dated Thursday 3.5.26 | verified fetched | Restaurant states the menu changes daily; this is a March 2026 snapshot. |
| src-16 | [Holbox](https://holboxla.com/about.html) | official web page | — | verified fetched | Hours only; no address/phone on page. |
| src-17 | [Holbox via Toast (official ordering page)](https://www.toasttab.com/local/order/holbox-3655-south-grand-avenue-c9) | official ordering page | — | partial snippet | Partial item list; undated. |
| src-18 | [Chichen Itza Restaurant](https://chichenitzarestaurant.com/menu/chichen-itza-restaurant-3655-south-grand-avenue-c6) | official menu page | — | partial snippet | Partial menu only. |
| src-19 | [Chichen Itza Restaurant](https://chichenitzarestaurant.com/menu) | official menu page | — | partial snippet | Partial menu; prices differ from src-18. |
| src-20 | [Chichen Itza Restaurant (legacy page)](https://www.chichenitzarestaurant.com/menu/todays-menu/) | official menu page | — | partial snippet | Much lower prices; treated as stale and NOT used. |
| src-21 | [Chichen Itza via Toast (official ordering page)](https://www.toasttab.com/local/order/chichen-itza-restaurant-3655-south-grand-avenue-c6) | official ordering page | — | partial snippet | Partial. |
| src-22 | [Chichen Itza Restaurant](https://chichenitzarestaurant.com/order) | official ordering page | — | partial snippet | Partial. |
| src-23 | [Chipotle Mexican Grill](https://locations.chipotle.com/ca/los-angeles/3748-s-figueroa-st) | official location page | — | verified fetched | No prices or calories on page. |
| src-24 | [Chipotle Mexican Grill](https://chipotle.com/content/dam/chipotle/menu/nutrition/paper-menu-standard-no-pricing120221-us.pdf) | official nutrition pdf | Document code STNDRD--JUL 2022 | verified fetched | 2022 document; Chipotle says to check chipotle.com for current values. Prices: 'check local menu boards'. |
| src-25 | [The Shops at USC Village](https://www.uscvillage.com/directory/dining) | official directory | — | verified fetched | No unit numbers or hours by day. |
| src-26 | [The Shops at USC Village](https://www.uscvillage.com/store/cava) | official directory | — | verified fetched | — |
| src-27 | [The Shops at USC Village](https://www.uscvillage.com/store/sweetgreen) | official directory | — | partial snippet | — |
| src-28 | [Sweetgreen](https://www.sweetgreen.com/menu) | official menu page | — | partial snippet | Brand-level menu, not the USC Village menu; no prices; index copy may be old. |
| src-29 | [Sweetgreen (other LA location page)](https://www.sweetgreen.com/locations/beverly-wilshire) | official location page | — | partial snippet | Different location; used only to show that nutrition values conflict with src-28. |
| src-30 | [CAVA](https://support.cava.com/en_us/where-can-i-find-cava-s-nutritional-and-allergen-information-BJ_6nAj3T) | official support page | — | inaccessible | Confirms a nutrition/allergen guide exists; the guide itself was not reachable. |
| src-31 | [USC Office of Undergraduate Admission](https://www.admissionblog.usc.edu/p/where-to-eat-on-and-near-campus) | official web page | — | partial snippet | Used for Holbox street address only. |
| src-32 | [The Shops at USC Village](https://www.uscvillage.com/store/softies-burger) | official directory | — | partial snippet | — |

## 11. Next steps

1. Add a Google Maps Platform key and run Places discovery over a grid of overlapping searches clipped to the polygon; dedupe by place ID and by normalised name + address.
2. Geocode the 17 boundary intersections and every address, then re-run the boundary test (expect the two Mercado La Paloma stalls to stay inside but near the edge).
3. Pull the USC Village pages for Sweetgreen and CAVA to get local prices alongside their published nutrition — the fastest way to create the first price + macro records.
4. Get campus quick-service menus (Taco-Taco, Burger Crush, Bowls, Slice Shop, Panda Express) from the Campus Dining app or from USC Hospitality directly.
5. Re-fetch Chichen Itza and Holbox ordering pages to resolve the price conflicts and complete the partial menu.
6. Process the 33 venues in section 6, then add a routing service for walking times.
