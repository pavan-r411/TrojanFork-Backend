# TrojanPlate — USC Judging Brief

**Tagline:** Your goals. Your campus. Your plate.  
**Product:** AI-powered daily diet planner for USC students  
**Scope:** University Park Campus — USC Dining + Off-Campus (0.3 mi)

---

## Problem

Trojans juggle meal swipes, dining-hall menus, nearby restaurants, budget, diet, and macros between classes. Generic diet apps recommend food that isn’t here; restaurant apps don’t plan the day.

**TrojanPlate** recommends specific available dishes for breakfast, lunch, and dinner (up to three each), explains why they fit, and replans the day when a student swaps a meal.

---

## Criteria map

### Impact & Campus Relevance — 30%

| Claim | Evidence |
|---|---|
| Real USC friction | Day-long diet planning against actual campus food |
| Trojan-specific | Village, EVK, Parkside + walkable off-campus menus |
| Campus life | Two-mode home: meal-swipe halls vs nearby cash restaurants |

**Demo:** Profile → USC Dining day plan → swap lunch → Off-Campus vegetarian under $12 within 0.3 mi.

### Technical & AI Execution — 25%

| Claim | Evidence |
|---|---|
| Grounded AI product | Ranking + explanations over verified snapshots |
| Accuracy | Unknown macros/allergens labeled; never invented offerings |
| Safety | Allergies/exclusions hard-filter; AYCE not priced per buffet item |
| Deterministic core | `POST /v1/plan/day` + `/v1/plan/swap` |

### Feasibility & Implementation — 25%

| Claim | Evidence |
|---|---|
| Deployable | FastAPI + snapshot JSON + static mobile UI |
| Partners | USC Hospitality menus, SG pilot path (`docs/ADOPTION.md`) |
| Honest scope | Dated snapshots labeled; live scrape is stretch |

### User Experience & Design — 20%

| Claim | Evidence |
|---|---|
| Mobile-first | `/` TrojanPlate UI — onboarding → modes → day plan |
| Clear choices | ≤3 recommendations per meal with `why` text |
| Uncertainty UX | Confidence labels; fewer than 3 when constraints bite |

---

## What we do not claim

- Live production Hospitality scrape every request  
- Medical nutrition advice or allergen-free guarantees  
- Walking-route distances (straight-line miles for MVP)  
- Multi-university product readiness  
