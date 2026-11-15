"""Stateless daily-plan contract for the existing TrojanPlate UI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from trojanbites_extract.recommend.live import LiveRequest, LiveDiscoveryError, _offcampus, _usc
from trojanbites_extract.recommend.service import NutritionContext, UserPreferences, RecommendationResult, select_meals


class Profile(BaseModel):
    goal: str = Field('balanced',max_length=200)
    preferred_cuisines: list[str] = Field(default_factory=list,max_length=20)
    dietary_preferences: list[str] = Field(default_factory=list,max_length=10)
    allergies: list[str] = Field(default_factory=list,max_length=20)
    disliked_ingredients: list[str] = Field(default_factory=list,max_length=20)
    targets: NutritionContext | None = None
    remaining: NutritionContext | None = None
    snacks: bool = False


class Origin(BaseModel):
    lat: float = Field(ge=-90,le=90,allow_inf_nan=False)
    lng: float = Field(ge=-180,le=180,allow_inf_nan=False)


class Context(BaseModel):
    origin: Origin | None = None
    max_walk_m: int = Field(483,ge=80,le=1609)
    per_meal_budget_cents: int = Field(1500,ge=0,le=100000)
    include_unknown_prices: bool = False
    include_ai_estimates: bool = True
    daily_budget_cents: int = Field(4200,ge=0,le=1000000)
    meal_swipes_available: int = Field(3,ge=0,le=100)
    preferred_cuisines: list[str] = Field(default_factory=list,max_length=20)
    dining_hall: str = Field('All halls',max_length=100)


class PlanRequest(BaseModel):
    mode: Literal['usc_dining','off_campus']
    date: date
    profile: Profile = Field(default_factory=Profile)
    context: Context = Field(default_factory=Context)


def rank_across_kitchens(candidates, preferences, period):
    groups={}
    for item in candidates:
        groups.setdefault(item.restaurant_id,[]).append(item)
    if len(groups)<2:
        return select_meals(candidates,preferences,period)
    def best(items):
        result=select_meals(items,preferences,period)
        result.meals=result.meals[:1]
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(best,list(groups.values())[:3]))
    return RecommendationResult(
        provider='openai' if all(r.provider=='openai' for r in results) else 'deterministic',
        status='completed' if all(r.status=='completed' for r in results) else 'partial_personalization',
        meals=[meal for r in results for meal in r.meals][:3],
        warnings=list(dict.fromkeys(warning for r in results for warning in r.warnings)))


def daily_plan(body: PlanRequest) -> dict:
    ctx=body.context;p=body.profile
    if body.mode=='off_campus' and ctx.origin is None:
        raise LiveDiscoveryError('Choose a location before building an off-campus plan.')
    preferences=UserPreferences(goal=p.goal,preferred_cuisines=list(dict.fromkeys(value.strip() for value in (ctx.preferred_cuisines or p.preferred_cuisines) if value.strip())),allergies=p.allergies,excluded_ingredients=p.disliked_ingredients,
        targets=p.targets,remaining=p.remaining)
    base=LiveRequest(mode=body.mode,date=body.date,meal_period='lunch',
        lat=ctx.origin.lat if ctx.origin else None,lng=ctx.origin.lng if ctx.origin else None,
        radius_miles=ctx.max_walk_m/1609.344,dining_hall=ctx.dining_hall,
        diet=p.dietary_preferences,preferences=preferences,
        budget_max=ctx.per_meal_budget_cents/100 if body.mode=='off_campus' else None,include_unknown_prices=ctx.include_unknown_prices,include_ai_estimates=ctx.include_ai_estimates)
    warnings=[]
    periods=['breakfast','lunch','dinner']+(['snack'] if p.snacks else [])
    # Discover/extract once per daily off-campus request; no cross-request cache.
    restricted=bool(p.allergies or p.disliked_ingredients)
    shared=([],[],[]) if restricted or body.mode=='usc_dining' else _offcampus(base)
    eligible_restaurants=len({item.restaurant_id for item in shared[0]}) if body.mode=='off_campus' else None
    timestamp=datetime.now(timezone.utc).isoformat()
    used_ids=set()
    used_names=set()
    dish_key=lambda name: ' '.join(name.casefold().strip(' .!').split())
    def slot(period):
        request=base.model_copy(update={'meal_period':period})
        try:
            hits,sources,notes=(shared if body.mode=='off_campus' or restricted else _usc(request))
            if body.mode=='usc_dining' and ctx.include_ai_estimates:
                from trojanbites_extract.recommend.estimates import estimate_missing
                hits,estimate_notes=estimate_missing(hits,sources,include_price=False);notes=notes+estimate_notes
            by_source={source['item_id']:source for source in sources}
            candidates=list({h.item_id:h for h in hits if h.item_id not in used_ids and dish_key(h.item_name) not in used_names}.values())
            if body.mode=='off_campus':
                candidates=[h for h in candidates if (period in by_source.get(h.item_id,{}).get('meal_periods',[]) or
                    (period in {'lunch','dinner'} and not by_source.get(h.item_id,{}).get('meal_periods')))]
            # Reserve candidates for later slots instead of filling the first slot with everything.
            later=periods[periods.index(period)+1:]
            reserves=sum(any((later_period in by_source.get(h.item_id,{}).get('meal_periods',[]) or
                (later_period in {'lunch','dinner'} and not by_source.get(h.item_id,{}).get('meal_periods'))) for h in candidates) for later_period in later) if body.mode=='off_campus' else 0
            limit=min(3,max(1,len(candidates)//(1+reserves)))
            result=rank_across_kitchens(candidates,preferences,period)
            result.meals=[m for m in result.meals if m['item_id'] not in used_ids][:limit]
            used_ids.update(m['item_id'] for m in result.meals)
            used_names.update(dish_key(m['item_name']) for m in result.meals)
            if not result.meals and body.mode=='off_campus':
                notes=notes+(['No published breakfast menu matched your location and filters.'] if period=='breakfast' else ['Not enough distinct published dishes matched this meal period. Try adjusting your budget or radius.'])
            by_id={source['item_id']:source for source in sources}
            recommendations=[]
            for rank,meal in enumerate(result.meals,1):
                source=by_id.get(meal['item_id'],{})
                from trojanbites_extract.recommend.estimates import midpoint
                estimates=meal.get('ai_estimates') or {};ranges=estimates.get('ranges',{})
                fields={'calories':'published_calories_kcal','protein_g':'published_protein_g','carbs_g':'published_carbohydrates_g','fat_g':'published_fat_g'}
                statuses={key:('published' if meal.get(field) is not None else 'estimated' if ranges.get(key) else 'unknown') for key,field in fields.items()}
                status='estimated' if 'estimated' in statuses.values() else 'published' if 'published' in statuses.values() else 'unknown'
                estimated_price=ranges.get('price') if meal['price_amount'] is None else None
                price=meal['price_amount'] if meal['price_amount'] is not None else midpoint(estimated_price)
                recommendations.append({'id':meal['item_id'],'rank':rank,'meal_title':meal['item_name'],
                    'item_ids':[meal['item_id']],'venue':{'id':meal['restaurant_id'],'name':meal['restaurant_name'],
                    'type':'dining_hall' if body.mode=='usc_dining' else 'restaurant'},
                    'cuisine':None,'image_url':None,'dietary_tags':source.get('diet_claims',[]),
                    'price_cents':round(price*100) if price is not None else None,
                    'published_price_cents':round(meal['price_amount']*100) if meal['price_amount'] is not None else None,
                    'price_status':'estimated' if estimated_price else 'published' if price is not None else 'unknown',
                    'price_range_cents':{k:round(v*100) for k,v in estimated_price.items()} if estimated_price else None,
                    'payment_label':'Dining hall entry' if body.mode=='usc_dining' else 'Published menu price; tax/fees excluded',
                    'walking_meters':round(meal['distance_miles']*1609.344) if meal.get('distance_miles') is not None else None,
                    'walking_minutes':None,'distance_metric':'haversine_miles_straight_line',
                    'nutrition':{**{key:meal.get(field) if meal.get(field) is not None else midpoint(ranges.get(key)) for key,field in fields.items()},
                    'serving_size':meal.get('serving_label') or estimates.get('assumed_serving'),
                    'serving_status':'published' if meal.get('serving_label') else 'estimated' if estimates.get('assumed_serving') else 'unknown',
                    'status':status,'field_status':statuses,'estimated_ranges':{key:value for key,value in ranges.items() if key!='price'},
                    'published':{key:meal.get(field) for key,field in fields.items()}},'allergen_information_status':'unverified',
                    'source':{'url':source.get('menu_url',''),'menu_date':str(body.date) if body.mode=='usc_dining' else None,
                        'verified_at':timestamp,'status':'needs_verification'},
                    'reason':meal.get('recommendation_reason','Matches your requested filters.')})
            return {'slot':period,'optional':period=='snack','selected_recommendation_id':None,'locked':False,
                'recommendations':recommendations,'availability_note':' '.join(dict.fromkeys(result.warnings+notes)) or 'No published eligible dishes for this meal period.',
                'personalization':{'provider':result.provider,'status':result.status}},notes+result.warnings
        except LiveDiscoveryError as exc:
            return {'slot':period,'optional':period=='snack','selected_recommendation_id':None,'locked':False,
                'recommendations':[],'availability_note':str(exc)},[str(exc)]
    # Coordinate slots: independent parallel ranking cannot enforce daily variety.
    results=[slot(period) for period in periods]
    for _,notes in results: warnings.extend(notes)
    if body.mode=='off_campus' and ctx.include_unknown_prices:
        warnings.append('Meals with unpublished prices are included by your choice; their budget fit cannot be verified.')
    if body.mode=='off_campus':
        warnings.extend(['Distance is straight-line, not a walking route. Off-campus meal-period availability is unverified.']+shared[2])
    warnings.append('Live published menus may have incomplete nutrition. Confirm availability and allergens with the provider.')
    return {'plan_id':str(uuid4()),'mode':body.mode,'date':str(body.date),'generated_at':timestamp,'data_mode':'live',
        'diversity':{'eligible_restaurants':eligible_restaurants,'include_unknown_prices':ctx.include_unknown_prices},
        'slots':[row for row,_ in results],'warnings':list(dict.fromkeys(warnings)),
        'summary':{'total_cost_cents':0,'remaining_budget_cents':ctx.daily_budget_cents,'swipes_used':0,
            'remaining_swipes':ctx.meal_swipes_available,'nutrition':{'calories':0,'protein_g':0,'coverage':'No meals selected'}}}
