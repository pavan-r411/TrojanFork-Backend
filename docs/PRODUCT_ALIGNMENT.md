# TrojanPlate vs current backend — honest alignment

**Verdict:** The TrojanPlate product idea is strong for judging. The **current backend architecture does not match it yet**. You are not building the wrong product — you have been building the **data/catalog layer** while the product plan describes a **daily diet planner**. Keep the catalog; reframe and extend the product layer.

**Working name going forward:** TrojanPlate  
**Tagline:** Your goals. Your campus. Your plate.  
**Primary product:** Daily diet planning (not restaurant discovery)

---

## Are you doing something wrong?

| Area | Status | Notes |
|---|---|---|
| Problem + audience (USC students, real menus) | **Right** | Strong Impact / campus relevance |
| Two modes (USC Dining + Off-Campus) | **Right** | Clear UX; matches judging story |
| Honest nutrition / no invented allergen safety | **Right** | Matches AI safety scoring |
| Treating this repo as “nearby restaurant search API” | **Misaligned** | That is a supporting feature, not the product |
| Multi-campus / UCLA expansion now | **Wrong priority** | Out of scope until USC day-planner demo works |
| Live Places + Claude on every request | **Wrong for MVP** | Background or pre-snapshotted data only |
| Per-dish prices on AYCE dining halls | **Wrong** | Model a **visit / meal swipe**, not buffet item prices |
| Claiming live daily Hospitality scrape without a dated snapshot | **Risky** | For hackathon: verified snapshot + clear label; refresh is stretch |

**Bottom line:** Keep extraction/storage. Stop optimizing for “suggest nearby dishes.” Build **profile → mode → day plan (3 options/meal) → swap/replan** on top of two food sources.

---

## What matches today (reuse)

| TrojanPlate need | Already in this repo |
|---|---|
| USC-only scope | `usc_upc` campus pack, DPS boundary |
| 0.3-mile off-campus walk preference | `default_walk_miles: 0.3`, nearby filters |
| Verified off-campus menus | Pilot catalog in `data/pilot/` |
| Don’t invent macros | Estimation off; nulls preserved |
| Background AI extraction | Ingestion jobs + Claude adapter |
| Hospitality entry point | Seeds for Village / EVK / Parkside |
| Fast stored responses | FastAPI + SQLite catalog |

## What the product plan needs that we do **not** have yet

| TrojanPlate need | Gap |
|---|---|
| Student profile / goals / allergies | No profile or day-plan model |
| Two explicit planner modes | One blended suggest API |
| Full-day plan (B/L/D + snacks) | Dish search only |
| Up to 3 ranked options **per meal** + explanations | Flat meal list |
| Meal select / swap → replan rest of day | Missing |
| USC dining hall **dated menu periods** | Seeds exist; no date/meal-period dining snapshot pipeline |
| AYCE visit vs swipe / Dining Dollars | Missing |
| Off-campus daily + per-meal budget tracking across the day | Partial (budget filter only) |
| Mobile frontend + public URL | Backend-only so far |
| Product name TrojanPlate | Still branded Trojan Fork in many places |

---

## Correct product architecture (conceptual)

```text
┌─────────────────────────────────────────────────────────┐
│  TrojanPlate mobile-first web (frontend — separate app) │
│  Home: [USC Dining]  [Off-Campus]                       │
│  Profile · Day plan · Swap · Explanations               │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Planner API (new product layer)                        │
│  profile · plan day · swap · explain                    │
│  Mode A: residential dining  |  Mode B: off-campus      │
└─────────────┬───────────────────────────┬───────────────┘
              │                           │
   ┌──────────▼──────────┐     ┌──────────▼──────────┐
   │ Food Source A       │     │ Food Source B         │
   │ USC dining snapshot │     │ Nearby verified menus │
   │ Village/EVK/Parkside│     │ 0.3 mi · cuisine/budget│
   │ meal_period + date  │     │ cash prices           │
   └──────────┬──────────┘     └──────────┬────────────┘
              │                           │
              └────────────┬──────────────┘
                           │
              ┌────────────▼────────────┐
              │ Catalog + ingest (keep) │
              │ fetch → parse → Claude  │
              │ validate → store        │
              │ NEVER invent dishes     │
              └─────────────────────────┘
```

**Intelligence split (keep this):**

1. **Hard filters (deterministic):** allergies, exclusions, hard budget, availability, distance.  
2. **Ranking (deterministic + light scoring):** nutrition fit, cuisine, cost, convenience, variety.  
3. **AI (optional, never invents catalog):** explain why a pick fits; parse natural-language prefs; help extract menus offline.  
4. **Unknowns stay labeled** (confirmed / estimated / unavailable).

---

## How fetching should work (framework design)

### Mode A — USC Dining

**Goal:** Actual published dishes for a **menu date + meal period** across Village, EVK, Parkside.

| Step | Behavior |
|---|---|
| 1. Source | USC Hospitality dining menus (`hospitality.usc.edu/dining-hall-menus/`) |
| 2. Hackathon path | **Dated verified snapshot** in repo (JSON/MD) labeled with `menu_date` — judges know it’s a snapshot |
| 3. Stretch path | Background job: fetch HTML → parse stations/dishes → validate → store keyed by `(hall, date, meal_period)` |
| 4. Product model | `DiningHallVisit` = one swipe / AYCE session; dishes are **components**, not priced à la carte |
| 5. Output | Ranked **meal combinations** or primary dishes per period, with hall name + why it fits |

Do **not** block MVP on perfect live scrape. Snapshot first; auto-refresh later.

### Mode B — Off-Campus

**Goal:** Specific menu items from a **small verified set** within ~0.3 mi.

| Step | Behavior |
|---|---|
| 1. Source | Existing pilot restaurant menus + optional Places discovery for venue list only |
| 2. Distance | Straight-line now; walking routes = P1 |
| 3. Filters | Hard: allergies, diet exclusions, budget; Soft: cuisine, convenience |
| 4. Day budget | Track remaining daily cash after each locked meal |
| 5. Output | Up to 3 dish recommendations per meal period with price + distance + explanation |

### Shared planner engine

Input: profile + mode + today’s situation (meal needed, budget/swipes, location, already eaten).  
Process: eligible foods → hard filter → rank → assemble day → explain.  
On swap: lock chosen meals → re-rank remaining periods only.

---

## Revised implementation order (deadline-aware)

Deadline: **Sun Nov 15, 2026 · 11:00 AM PT**. Finish end-to-end demo before polish.

| Phase | Work | Done when |
|---|---|---|
| **P0a** | Rename narrative → TrojanPlate; lock 2 demo student profiles | Pitch + JUDGING match product |
| **P0b** | Dining-hall snapshot dataset (3 halls, ≥1 date, B/L/D) | Mode A has real dishes |
| **P0c** | Curate off-campus subset from pilot (few venues, 0.3 mi story) | Mode B has real dishes |
| **P0d** | Profile + day-plan API (plan + 3 options/meal + explanations) | Backend matches product |
| **P0e** | Mobile-first frontend (2 home modes + day view) | Judge can click through |
| **P0f** | Public HTTPS deploy + Devpost assets | Submission complete |
| **P1** | Swap / replan remaining day | Interactive intelligence |
| **P2** | Live Hospitality refresh, Routes API, more venues | Only if P0 solid |

**Cut without guilt:** UCLA, Places-heavy discovery, medical nutrition claims, PWA, hybrid campus+off-campus same day, account login.

---

## Suggested demo story (maps to your §11)

1. Onboard demo student (e.g. vegetarian + training protein).  
2. **USC Dining** → B/L/D from Village/EVK/Parkside snapshot; show “why”.  
3. **Off-Campus** → same profile, cuisine + $ budget, 0.3 mi.  
4. Swap lunch → dinner options / remaining budget update.  
5. Disclose snapshot / unknown macros honestly.

---

## What to stop doing

1. Framing the product as multi-university extraction.  
2. Shipping more catalog infrastructure before a day-plan UI.  
3. Pricing buffet items like restaurant SKUs.  
4. Waiting on live Claude/Places keys to have a demo — use snapshots.  
5. Building features that aren’t in the 3-minute video.
