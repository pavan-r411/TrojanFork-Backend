# Why off-campus breakfast came back empty

Off-campus breakfast failed because of an asymmetric meal-period rule in the daily planner, not because the dishes were missing.

## What the planner did

`daily_plan` decided whether a saved or live dish could fill a slot with one check:

- the dish's `meal_periods` contained that period, or
- the period was **lunch or dinner** and `meal_periods` was empty

Breakfast had no unlabeled fallback. A dish with an empty `meal_periods` list could be lunch and dinner, and was rejected for breakfast.

## Why `meal_periods` was usually empty

Live extraction only keeps a meal period when the restaurant page explicitly labels that dish or menu for it, and the label quote is still on the page. The extractor is told not to call a dish breakfast just because someone could eat it in the morning. Most restaurant menus list a name and a price and never say "breakfast", so `meal_periods` stays `[]`.

Those same unlabeled dishes then filled lunch and dinner. Breakfast stayed empty, and the slot note said no nearby restaurant published a breakfast menu.

Saved menus that already stored `meal_periods: ["breakfast"]` were unaffected. That is why a curated breakfast item could appear while a live menu of pancakes could not.

## What changed

Breakfast may now include a dish whose **name or menu evidence** matches a breakfast-item pattern when the menu did not label any meal period. The card is marked `meal_period_evidence: "inferred"` and the slot note says breakfast availability is unverified.

That match does not invent a dish. The dish still has to come from the menu text. A menu that already labels the dish as lunch or dinner is not reclassified as breakfast. Lunch and dinner still accept unlabeled dishes. Allergies are not relaxed, and an empty breakfast slot does not suggest removing them.

Unknown nutrition stays null. A missing macro is not turned into a number by this change.
