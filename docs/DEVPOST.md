# TrojanPlate — Devpost checklist

**Deadline:** Sunday, November 15, 2026, 11:00 AM PT

## Links to fill

- [ ] Public demo URL — frontend app + this API (backend: deploy via `render.yaml` / ngrok)  
- [x] Backend GitHub: https://github.com/pavan-r411/TrojanFork-Backend/tree/murali-krishna  
- [ ] Demo video ≤ 3 minutes (record from the frontend)  
- [x] Pitch deck source: [`PITCH_SLIDES.md`](PITCH_SLIDES.md) — export to PDF / Google Slides  
- [ ] Screenshot of working frontend UI  

## Suggested description (short)

TrojanPlate is an AI-powered daily diet planner for USC students. It learns goals and dietary preferences, then recommends breakfast, lunch, and dinner from real USC dining hall menus (Village, EVK, Parkside) or walkable off-campus restaurants within 0.3 miles. Each meal offers up to three grounded choices with explanations; swapping a meal updates the rest of the day. Unknown nutrition stays labeled — we never invent dishes, prices, or allergen safety.

**Tagline:** Your goals. Your campus. Your plate.

## Demo script (under 3 min)

1. Open `/` — onboarding (vegetarian + high protein).  
2. USC Dining → build day → show 3 halls / explanations.  
3. Choose/swap lunch → remaining plan updates.  
4. Off-Campus → cuisine + $12 budget → walkable dishes.  
5. Close on impact for Trojans.

## Tech stack

Python, FastAPI, dated menu snapshots, deterministic plan engine (frontend is a separate app).
