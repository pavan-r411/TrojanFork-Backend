# TrojanPlate — hackathon demo script (≤3 min)

**Local URL:** http://127.0.0.1:8000/ui/  
**Requires:** backend `.env` with `OPENAI_API_KEY` and `GOOGLE_MAPS_API_KEY` (Places API New).

## Script

1. **Saved profile (15s)**  
   Open `/ui/`. Click **Sign in** (or continue locally). Load/create a profile with diet + budget. Reload the page — profile and today’s plan selections remain.

2. **Real eligible options (45s)**  
   Choose **USC Dining** → Refresh. Show dated hall dishes from the official USC feed. Switch to **Off-Campus** near Tommy Trojan / USC Village. Show live Places → website menu cards (or labeled **Saved menu** supplements). Point out **Nutrition unavailable** / AI-estimated labels when macros are missing.

3. **Restaurant variety (20s)**  
   Open Breakfast / Lunch / Dinner carousels. Up to three choices from distinct restaurants when inventory allows. If breakfast is short, read the reason code note (not invented dishes).

4. **Persistent daily plan (20s)**  
   Select one meal per slot. Open **My Plan**. Show cash vs swipes, tax/fees excluded, planned (not eaten) totals.

5. **Swap + totals (30s)**  
   Swap a meal → confirm preview (calories / protein / cash / swipes / restaurant) → Confirm. Totals update. Tap **Undo last swap**.

6. **Directions (20s)**  
   Tap **Get directions** on a selected card (or the venue name). Google Maps opens walking directions to the branch Place ID / coordinates. If destination missing, show unavailable — never guess.

## Talking points

- Hard constraints beat diversity preferences.  
- Unknown nutrition stays `null`, never zero.  
- Allergies are never suggested for removal.  
- Off-campus breakfast empty was caused by unlabeled menus; name-inferred breakfast is labeled unverified (see `docs/BREAKFAST_FAILURE.md`).
