"""Stateless daily-plan contract for the TrojanPlate UI (POST /v1/live/plan)."""
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields as dataclass_fields
from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from trojanbites_extract.maps.directions import build_directions
from trojanbites_extract.query.filters import MealHit
from trojanbites_extract.recommend.estimates import estimate_missing, midpoint
from trojanbites_extract.recommend.live import LiveRequest, LiveDiscoveryError, _entree_score, _offcampus, _usc, venue_images
from trojanbites_extract.recommend.restrictions import canonical_allergies
from trojanbites_extract.recommend.service import NutritionContext, UserPreferences, RecommendationResult, select_meals

# ~3 mph walking pace used for UI minute estimates from straight-line meters.
_WALK_METERS_PER_MINUTE = 80
_NUTRIENTS = {'calories':'published_calories_kcal','protein_g':'published_protein_g','carbs_g':'published_carbohydrates_g','fat_g':'published_fat_g'}
_HIT_FIELDS = {f.name for f in dataclass_fields(MealHit)}
_DRINK = re.compile(r'\b(?:coffee|espresso|latte|cappuccino|americano|macchiato|mocha|tea|chai|matcha|juice|soda|cola|lemonade|water|'
    r'beer|wine|cocktail|margarita|mimosa|milkshake|shake|smoothie|boba)\b', re.I)
# Name-only breakfast evidence. Used when a menu lists the dish but does not label a meal period.
# Explicit lunch/dinner labels still win; this does not invent a dish.
_BREAKFAST_DISH = re.compile(
    r'\b(?:breakfasts?|brunch|pancakes?|waffles?|omelettes?|omelets?|scrambled eggs?|oatmeal|overnight oats|granola|'
    r'bagels?|breakfast burritos?|breakfast sandwich(?:es)?|avocado toast|french toast|hash ?browns?|eggs? benedict|'
    r'yogurt parfaits?|huevos|croissants?|muffins?|acai bowls?|breakfast tacos?|biscuits?(?: and gravy)?|'
    r'breakfast platters?|breakfast bowls?|breakfast quesadillas?|egg(?: white)?(?:s)?(?: and)?(?: cheese)? sandwich(?:es)?|'
    r'egg mcmuffins?|breakfast sandwich(?:es)?|chilaquiles)\b', re.I)
_UNVERIFIED_BREAKFAST = ('Breakfast availability is unverified: the menu does not label a breakfast period, '
    'so this dish was included only because its name matches a breakfast item.')


class Profile(BaseModel):
    model_config = ConfigDict(extra='ignore')
    goal: str = Field('balanced',max_length=200)
    preferred_cuisines: list[str] = Field(default_factory=list,max_length=20)
    dietary_preferences: list[str] = Field(default_factory=list,max_length=10)
    allergies: list[str] = Field(default_factory=list,max_length=20)
    disliked_ingredients: list[str] = Field(default_factory=list,max_length=20)
    targets: NutritionContext | None = None
    remaining: NutritionContext | None = None
    snacks: bool = False
    activity_level: str | None = Field(None, max_length=40)


class Origin(BaseModel):
    model_config = ConfigDict(extra='ignore')
    lat: float = Field(ge=-90,le=90,allow_inf_nan=False)
    lng: float = Field(ge=-180,le=180,allow_inf_nan=False)
    label: str | None = Field(None, max_length=200)


class Context(BaseModel):
    model_config = ConfigDict(extra='ignore')
    origin: Origin | None = None
    max_walk_m: int = Field(483,ge=80,le=1609)
    per_meal_budget_cents: int = Field(1500,ge=0,le=100000)
    include_unknown_prices: bool = False
    include_ai_estimates: bool = True
    daily_budget_cents: int = Field(4200,ge=0,le=1000000)
    meal_swipes_available: int = Field(3,ge=0,le=100)
    preferred_cuisines: list[str] = Field(default_factory=list,max_length=20)
    dining_hall: str = Field('All halls',max_length=100)
    dining_dollars_cents: int | None = Field(None, ge=0, le=10_000_000)
    locked_meal_ids: list[str | None] = Field(default_factory=list, max_length=20)


class PlanRequest(BaseModel):
    mode: Literal['usc_dining','off_campus']
    date: date
    profile: Profile = Field(default_factory=Profile)
    context: Context = Field(default_factory=Context)


def rank_across_kitchens(candidates, preferences, period, offset=0, avoid_restaurants=None):
    """One pick per kitchen (up to three kitchens) so a slot never collapses to a single venue.

    When only one kitchen has eligible inventory, return up to three distinct dishes from it
    and explain the restaurant repeat rather than inventing venues.
    """
    avoid={str(r) for r in (avoid_restaurants or set()) if r}
    groups={}
    for item in candidates:
        groups.setdefault(item.restaurant_id,[]).append(item)
    if not groups:
        return select_meals(candidates,preferences,period)
    if len(groups)==1:
        result=select_meals(candidates,preferences,period)
        seen=set(); unique=[]
        for meal in result.meals:
            did=meal.get('item_id')
            if did in seen: continue
            seen.add(did)
            unique.append(meal)
        result.meals=unique[:3]
        name=next(iter(groups.values()))[0].restaurant_name
        if len(result.meals)>1:
            result.warnings=list(dict.fromkeys(list(result.warnings)+[
                f'Only one eligible restaurant ({name}) had enough distinct dishes for this meal; '
                'showing alternatives from the same kitchen rather than inventing venues.']))
        elif avoid and next(iter(groups)) in avoid:
            result.warnings=list(dict.fromkeys(list(result.warnings)+[
                f'Restaurant repeat: {name} — not enough unused kitchens remained under your filters.']))
        return result
    wanted={c.casefold() for c in getattr(preferences,'preferred_cuisines',None) or []}
    kitchens=list(groups.values())
    # Prefer kitchens not already used earlier in the day, then rotate by meal slot,
    # then preferred cuisines — deterministic, not random.
    kitchens=kitchens[offset%len(kitchens):]+kitchens[:offset%len(kitchens)]
    kitchens.sort(key=lambda items:(items[0].restaurant_id in avoid,
                                    not any(c.casefold() in wanted for c in (items[0].cuisines or []))))
    def best(items):
        result=select_meals(items,preferences,period)
        result.meals=result.meals[:1]
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(best,kitchens[:3]))
    meals=[meal for r in results for meal in r.meals][:3]
    warnings=list(dict.fromkeys(warning for r in results for warning in r.warnings))
    reused=[m.get('restaurant_name') or m.get('restaurant_id') for m in meals if m.get('restaurant_id') in avoid]
    if reused:
        warnings.append('Restaurant repeat: '+', '.join(dict.fromkeys(str(x) for x in reused))+
                        ' — not enough unused kitchens remained under your filters.')
    return RecommendationResult(
        provider='openai' if all(r.provider=='openai' for r in results) else 'deterministic',
        status='completed' if all(r.status=='completed' for r in results) else 'partial_personalization',
        meals=meals, warnings=warnings)


def _fill_estimates(meals, sources):
    """Estimate nutrition only for the dishes actually recommended (one call per plan), so every card
    and the daily totals have numbers. Published values are never replaced."""
    todo={}
    for meal in meals:
        known=(meal.get('ai_estimates') or {}).get('ranges',{})
        if any(meal.get(field) is None and key not in known for key,field in _NUTRIENTS.items()):
            todo.setdefault(meal['item_id'],MealHit(**{k:v for k,v in meal.items() if k in _HIT_FIELDS}))
    if not todo: return []
    _,notes=estimate_missing(list(todo.values()),sources,include_price=False,limit=len(todo))
    for meal in meals:
        hit=todo.get(meal['item_id'])
        if hit is not None: meal['ai_estimates']=hit.ai_estimates
    return notes


def _allergen_label(mode, source, user_allergens, unmapped):
    """Short text for `allergen_information_status`; the UI shows it as "allergens <label>"."""
    listed=source.get('allergens') or []
    status=source.get('allergen_status')
    if mode=='usc_dining' and status=='published':
        label='listed by USC: '+', '.join(listed) if listed else 'none listed by USC'
        if unmapped: label+=f" ({', '.join(unmapped)} not covered by USC tags)"
        return label
    if mode=='usc_dining' and status=='not_analyzed':
        return 'not analyzed by USC'
    if listed:
        return 'published: '+', '.join(listed)
    return 'unverified'


def _meal_basis(hit, source, period):
    """How a dish qualifies for a period.

    Prefer published meal-period labels. Breakfast requires a label or a breakfast-like name
    on an otherwise unlabeled menu. Lunch and dinner may use unlabeled all-day menus
    (marked unlabeled — never invented). A menu that already names other periods is not
    reclassified into a missing slot.
    """
    periods=[str(p).lower() for p in (source.get('meal_periods') or [])]
    if period in periods or (period=='breakfast' and 'brunch' in periods):
        return 'labeled'
    if period=='lunch' and 'brunch' in periods and 'lunch' not in periods:
        return 'labeled'
    if period in {'lunch','dinner'} and not periods:
        return 'unlabeled'
    text=f"{getattr(hit,'item_name','')} {source.get('evidence') or ''}"
    if period=='breakfast' and not periods and _BREAKFAST_DISH.search(text):
        return 'inferred'
    return None


def _basis_rank(basis):
    """Prefer labeled service windows, then inferred breakfast names, then unlabeled all-day."""
    return {'labeled':0,'inferred':1,'unlabeled':2}.get(basis, 9)


def _empty_state(period, recommendations, diagnostics, *, off_campus, errored, availability_note=''):
    """Why a slot is empty, plus next steps that never tell the student to drop an allergy."""
    actions=[]
    reason=None
    message=''
    if not recommendations:
        if errored:
            reason='MENU_RETRIEVAL_FAILED'
            message='Menu retrieval failed for this meal. Retry without changing allergy filters.'
            actions=[{'id':'retry','label':'Retry'}]
        elif off_campus and period=='breakfast':
            reason='NO_BREAKFAST_MENU_PUBLISHED'
            message=(availability_note or
                     'No nearby restaurant published a breakfast menu we could read for this location and budget. '
                     'Try a wider radius or another landmark — do not remove allergy restrictions.')
            actions=[
                {'id':'widen_radius','label':'Widen radius'},
                {'id':'change_origin','label':'Change starting point'},
                {'id':'retry','label':'Retry'},
            ]
        elif off_campus:
            reason='NO_MEALS_MATCH_CONSTRAINTS'
            message=(availability_note or
                     'No published dishes matched this meal period under your required filters. '
                     'Review budget or radius; allergy restrictions stay in place.')
            actions=[
                {'id':'review_filters','label':'Review filters'},
                {'id':'widen_radius','label':'Widen radius'},
                {'id':'retry','label':'Retry'},
            ]
        else:
            reason='NO_MEALS_MATCH_CONSTRAINTS'
            message=(availability_note or
                     f'USC lists no {period} dishes for this date that match your filters. '
                     'Weekend menus may list Brunch instead of Breakfast or Lunch.')
            actions=[
                {'id':'change_hall','label':'Try another dining hall'},
                {'id':'retry','label':'Retry'},
            ]
    return {'reason_code':reason,'message':message,'diagnostics':diagnostics,'actions':actions}


def _recommendation(meal, rank, source, body, timestamp, images, unmapped, user_allergens, period_evidence='labeled'):
    estimates=meal.get('ai_estimates') or {};ranges=estimates.get('ranges',{})
    statuses={key:('published' if meal.get(field) is not None else 'estimated' if ranges.get(key) else 'unknown') for key,field in _NUTRIENTS.items()}
    status='estimated' if 'estimated' in statuses.values() else 'published' if 'published' in statuses.values() else 'unknown'
    estimated_price=ranges.get('price') if meal['price_amount'] is None else None
    price=meal['price_amount'] if meal['price_amount'] is not None else midpoint(estimated_price)
    # An assumed serving only applies when some nutrition value is itself an estimate.
    assumed=estimates.get('assumed_serving') if status=='estimated' else None
    meters=round(meal['distance_miles']*1609.344) if meal.get('distance_miles') is not None else None
    kind=source.get('source_kind') or ('usc_official_feed' if body.mode=='usc_dining' else 'live_menu')
    published_cuisine=next(iter(meal.get('cuisines') or source.get('cuisines') or []),None)
    cuisine=published_cuisine or estimates.get('cuisine')
    image=images.get(meal['restaurant_name']) or {}
    reason=meal.get('recommendation_reason') or 'Matches your requested filters.'
    if status=='estimated': reason+=' Nutrition figures are AI estimates.'
    elif status=='unknown' and 'nutrition' not in reason.lower(): reason+=' Nutrition is not published for this dish.'
    if period_evidence=='inferred': reason+=' '+_UNVERIFIED_BREAKFAST
    directions=build_directions(
        name=meal['restaurant_name'],
        place_id=source.get('place_id'),
        lat=source.get('lat'),
        lng=source.get('lng'),
        address=source.get('address'),
        location_confirmed_at=source.get('location_confirmed_at') or (timestamp if source.get('lat') is not None else None),
        truck=bool(source.get('is_food_truck')),
    )
    venue_type=source.get('venue_type')
    if venue_type=='usc_retail' or source.get('payment_model')=='dining_dollars_or_cash':
        kind_venue='restaurant'
        payment_label='USC retail — Dining Dollars or cash; confirm price on site'
    elif body.mode=='usc_dining' or venue_type=='usc_dining_hall':
        kind_venue='dining_hall'
        payment_label='Dining hall entry (meal swipe / AYCE)'
    else:
        kind_venue='restaurant'
        payment_label='Published menu price; tax/fees excluded'
    venue={'id':meal['restaurant_id'],'name':meal['restaurant_name'],'type':kind_venue,
           'place_id':source.get('place_id'),'lat':source.get('lat'),'lng':source.get('lng'),'address':source.get('address')}
    label=f"{source['station']} station" if source.get('station') else source.get('branch')
    if label: venue['location_label']=label
    return {'id':meal['item_id'],'rank':rank,'meal_title':meal['item_name'],'item_ids':[meal['item_id']],'venue':venue,
        'cuisine':cuisine,'cuisine_status':'published' if published_cuisine else 'inferred' if cuisine else 'unknown',
        'image_url':image.get('url'),'image_credit':image.get('credit'),
        'dietary_tags':source.get('diet_claims') or meal.get('diet_claims') or [],
        'price_cents':round(price*100) if price is not None else None,
        'published_price_cents':round(meal['price_amount']*100) if meal['price_amount'] is not None else None,
        'price_status':'estimated' if estimated_price else 'published' if price is not None else 'unknown',
        'price_range_cents':{k:round(v*100) for k,v in estimated_price.items()} if estimated_price else None,
        'payment_label':payment_label,
        'walking_meters':meters,'walking_minutes':max(1,round(meters/_WALK_METERS_PER_MINUTE)) if meters is not None else None,
        'distance_metric':'haversine_miles_straight_line',
        'directions_url':directions.get('url'),
        'directions':directions,
        'meal_period_evidence':period_evidence,
        'nutrition':{**{key:meal.get(field) if meal.get(field) is not None else midpoint(ranges.get(key)) for key,field in _NUTRIENTS.items()},
            'serving_size':meal.get('serving_label') or assumed,
            'serving_status':'published' if meal.get('serving_label') else 'estimated' if assumed else 'unknown',
            'status':status,
            'display_status':'Nutrition unavailable' if status=='unknown' else ('AI-estimated nutrition' if status=='estimated' else 'Published nutrition'),
            'field_status':statuses,'estimated_ranges':{key:value for key,value in ranges.items() if key!='price'},
            'published':{key:meal.get(field) for key,field in _NUTRIENTS.items()}},
        'allergens':source.get('allergens') or [],
        'allergen_information_status':_allergen_label(body.mode,source,user_allergens,unmapped),
        'source':{'url':source.get('menu_url',''),'menu_date':str(body.date) if body.mode=='usc_dining' else None,
            'verified_at':timestamp if kind!='curated_snapshot' else None,'kind':kind,
            'status':'verified' if kind=='usc_official_feed' else 'stale' if kind=='curated_snapshot' else 'needs_verification'},
        'reason':reason}


def daily_plan(body: PlanRequest) -> dict:
    ctx=body.context;p=body.profile
    off_campus=body.mode=='off_campus'
    if off_campus and ctx.origin is None:
        raise LiveDiscoveryError('Choose a location before building an off-campus plan.')
    # Off-campus live GPS is limited to the USC DPS patrol zone; landmarks stay allowed as fallback.
    if off_campus and ctx.origin is not None:
        try:
            from trojanbites_extract.campus.registry import load_campus
            from trojanbites_extract.campus.zones import classify_location
            zone = classify_location(ctx.origin.lat, ctx.origin.lng, load_campus('usc_upc'))
            if zone.location_zone == 'outside_dps':
                raise LiveDiscoveryError(
                    'Live location is outside the USC DPS patrol area. '
                    'Choose a campus landmark (USC Village, Tommy Trojan, or Leavey Library) for Off-Campus suggestions.'
                )
        except LiveDiscoveryError:
            raise
        except Exception:
            pass
    cuisines=list(dict.fromkeys(value.strip() for value in (ctx.preferred_cuisines or p.preferred_cuisines) if value.strip()))
    allergies=[value.strip() for value in p.allergies if value.strip()]
    dislikes=[value.strip() for value in p.disliked_ingredients if value.strip()]
    # Discovery applies allergies/dislikes using published evidence; ranking then only sees eligible, labeled dishes.
    preferences=UserPreferences(goal=p.goal,preferred_cuisines=cuisines,allergies=allergies,excluded_ingredients=dislikes,
        targets=p.targets,remaining=p.remaining)
    ranking=preferences.model_copy(update={'allergies':[],'excluded_ingredients':[]})
    user_allergens,unmapped=canonical_allergies(allergies)
    base=LiveRequest(mode=body.mode,date=body.date,meal_period='lunch',
        lat=ctx.origin.lat if ctx.origin else None,lng=ctx.origin.lng if ctx.origin else None,
        radius_miles=min(1,max(.05,ctx.max_walk_m/1609.344)),dining_hall=ctx.dining_hall,
        diet=p.dietary_preferences,preferences=preferences,
        budget_max=ctx.per_meal_budget_cents/100 if off_campus else None,include_unknown_prices=ctx.include_unknown_prices,include_ai_estimates=ctx.include_ai_estimates)
    periods=['breakfast','lunch','dinner']+(['snack'] if p.snacks else [])
    # Discover/extract once per daily off-campus request. all_periods=True so the
    # curated supplement keeps breakfast-only dishes (shared request uses lunch).
    # Accept monkeypatched _offcampus(body) callables that ignore kwargs.
    if off_campus:
        try:
            shared=_offcampus(base, all_periods=True)
        except TypeError:
            shared=_offcampus(base)
    else:
        shared=([],[],[])
    eligible_restaurants=len({item.restaurant_id for item in shared[0]}) if off_campus else None
    timestamp=datetime.now(timezone.utc).isoformat()
    used_ids=set();used_names=set();used_restaurants=set();all_sources={}
    dish_key=lambda name: ' '.join(name.casefold().strip(' .!').split())
    # Gather each period's pool first (USC feeds are cached per hall+date only — never by meal
    # period — so a daily plan reuses one feed per hall while filtering each meal separately).
    pools={}
    retrieval_source='live_retrieval'
    for period in periods:
        if off_campus:
            pools[period]=(shared[0],shared[1],[])
            continue
        try:
            hits,sources,notes=_usc(base.model_copy(update={'meal_period':period}))
            pools[period]=(hits,sources,list(notes))
        except LiveDiscoveryError as exc:
            pools[period]=exc
    def offered(hit,period):
        pool=pools[period]
        if isinstance(pool,LiveDiscoveryError): return False
        if off_campus: return _meal_basis(hit,all_sources.get(hit.item_id,{}),period) is not None
        return any(hit.item_id==other.item_id for other in pool[0])
    for pool in pools.values():
        if not isinstance(pool,LiveDiscoveryError): all_sources.update({source['item_id']:source for source in pool[1]})
    if off_campus and shared[1] and all((s.get('source_kind')=='curated_snapshot') for s in shared[1]):
        retrieval_source='curated_snapshot'
    elif off_campus and shared[1] and any((s.get('source_kind')=='curated_snapshot') for s in shared[1]):
        retrieval_source='live_and_curated'
    slots=[]
    # Slots are ranked in order: independent parallel ranking cannot enforce daily variety.
    for index,period in enumerate(periods):
        pool=pools[period]
        if isinstance(pool,LiveDiscoveryError):
            diagnostics={'meal_period':period,'mode':body.mode,'requested_service_time':{'breakfast':'08:30','lunch':'12:30','dinner':'18:30','snack':'15:30'}.get(period),
                'pool_dishes':0,'eligible_dishes':0,'removed_already_selected':0,'removed_wrong_meal_period':0,
                'labeled_matches':0,'inferred_breakfast_matches':0,'unlabeled_matches':0,'drinks_excluded':0,
                'distinct_dishes_remaining':0,'distinct_restaurants_remaining':0,'missing_nutrition_count':0,
                'final_selected_ids':[],'retrieval_source':retrieval_source,'allergies_applied':allergies,
                'allergies_kept':True,'used_restaurants_prior':sorted(used_restaurants),'pool_error':str(pool)}
            slots.append((period,RecommendationResult(provider='deterministic',status='unavailable',meals=[]),[str(pool)],{},diagnostics,True))
            continue
        hits,sources,notes=pool
        removed_selected=sum(1 for h in hits if h.item_id in used_ids or dish_key(h.item_name) in used_names)
        fresh=list({h.item_id:h for h in hits if h.item_id not in used_ids and dish_key(h.item_name) not in used_names}.values())
        evidence={}
        labeled=inferred=unlabeled=removed_period=0
        if off_campus:
            candidates=[]
            for hit in fresh:
                basis=_meal_basis(hit,all_sources.get(hit.item_id,{}),period)
                if basis=='labeled': labeled+=1
                elif basis=='inferred': inferred+=1
                elif basis=='unlabeled': unlabeled+=1
                else: removed_period+=1
                if basis:
                    evidence[hit.item_id]=basis
                    candidates.append(hit)
        else:
            candidates=fresh
            labeled=len(candidates)
        drinks_excluded=0
        if period!='snack':
            # Drinks are not meals; mains lead so ranking limits and the no-AI fallback stay sensible.
            kept=[]
            for hit in candidates:
                if _DRINK.search(hit.item_name):
                    drinks_excluded+=1
                    continue
                kept.append(hit)
            candidates=kept
            # Prefer published meal labels, then substantial entrees — never invent periods.
            candidates.sort(key=lambda h:(_basis_rank(evidence.get(h.item_id,'labeled')), -_entree_score(h.item_name)))
        # Aim for up to 3 choices. Unlabeled all-day dishes can also serve later slots, so
        # reserve some of that shared pool — but never throttle a slot that already has
        # period-specific inventory (labeled breakfast / name-inferred breakfast). Those
        # used to count as "offered" for lunch/dinner via the unlabeled path and capped
        # breakfast at 1 even when several breakfast dishes were available.
        specific=sum(1 for h in candidates if evidence.get(h.item_id) in {'labeled','inferred'})
        if specific:
            limit=min(3,len(candidates))
        else:
            reserves=sum(any(offered(h,later) for h in candidates) for later in periods[index+1:])
            limit=min(3,max(1,len(candidates)//(1+reserves)) if candidates else 0)
        # Prefer kitchens not already used for an earlier meal in this daily plan.
        preferred=[h for h in candidates if h.restaurant_id not in used_restaurants]
        ranking_pool=preferred if len({h.restaurant_id for h in preferred})>=1 and preferred else candidates
        result=rank_across_kitchens(ranking_pool or candidates,ranking,period,index,avoid_restaurants=used_restaurants)
        # If preferring unused kitchens left the slot thin, fill remaining seats from the full pool
        # without duplicating dishes — still one kitchen per card when possible.
        picked_ids={m['item_id'] for m in result.meals}
        if len(result.meals)<limit and ranking_pool is not candidates:
            extra=rank_across_kitchens(
                [h for h in candidates if h.item_id not in picked_ids],
                ranking,period,index,avoid_restaurants=used_restaurants|{m.get('restaurant_id') for m in result.meals})
            for meal in extra.meals:
                if meal['item_id'] in picked_ids: continue
                if any(meal.get('restaurant_id')==m.get('restaurant_id') for m in result.meals): continue
                result.meals.append(meal)
                result.warnings=list(dict.fromkeys(list(result.warnings)+list(extra.warnings)))
                if len(result.meals)>=limit: break
        # Distinct restaurants within the slot when enough kitchens exist; otherwise keep
        # distinct dishes from the same kitchen and explain the repeat upstream.
        kitchen_count=len({h.restaurant_id for h in candidates})
        unique_meals=[]; seen_venues=set(); seen_dishes=set(); seen_slot_names=set()
        def _accept(meal):
            did=meal['item_id']; name=dish_key(meal.get('item_name') or ''); rid=meal.get('restaurant_id')
            if did in used_ids or did in seen_dishes or (name and name in seen_slot_names): return False
            if kitchen_count>=2 and rid in seen_venues: return False
            seen_dishes.add(did)
            if name: seen_slot_names.add(name)
            if rid: seen_venues.add(rid)
            unique_meals.append(meal)
            return True
        for meal in result.meals:
            _accept(meal)
            if len(unique_meals)>=limit: break
        if len(unique_meals)<limit:
            refill=rank_across_kitchens(
                [h for h in candidates if h.item_id not in seen_dishes and dish_key(h.item_name) not in seen_slot_names
                 and (kitchen_count<2 or h.restaurant_id not in seen_venues)],
                ranking,period,index+1,avoid_restaurants=used_restaurants|seen_venues)
            for meal in refill.meals:
                _accept(meal)
                if len(unique_meals)>=limit: break
            result.warnings=list(dict.fromkeys(list(result.warnings)+list(refill.warnings)))
        result.meals=unique_meals[:limit]
        prior_restaurants=sorted(used_restaurants)
        used_ids.update(m['item_id'] for m in result.meals)
        used_names.update(dish_key(m['item_name']) for m in result.meals)
        used_restaurants.update(m.get('restaurant_id') for m in result.meals if m.get('restaurant_id'))
        if any(evidence.get(m['item_id'])=='inferred' for m in result.meals):
            notes.append('Breakfast availability is unverified: these dishes match breakfast by name only and the menu does not label a breakfast period.')
        if not result.meals:
            if off_campus and period=='breakfast':
                notes.append('No nearby restaurant publishes a breakfast menu we could read for this location and budget. Try a wider radius or another starting point.')
            elif off_campus:
                notes.append('Not enough distinct published dishes matched this meal period. Try adjusting your budget or radius.')
            elif not notes:
                notes.append(f'USC lists no {period} dishes for this date that match your filters.')
        missing_nutrition=sum(1 for h in candidates if h.published_calories_kcal is None)
        diagnostics={'meal_period':period,'mode':body.mode,
            'requested_service_time':{'breakfast':'08:30','lunch':'12:30','dinner':'18:30','snack':'15:30'}.get(period),
            'pool_dishes':len(hits),'eligible_dishes':len(candidates),
            'removed_already_selected':removed_selected,'removed_wrong_meal_period':removed_period,
            'labeled_matches':labeled,'inferred_breakfast_matches':inferred,'unlabeled_matches':unlabeled,
            'drinks_excluded':drinks_excluded,
            'distinct_dishes_remaining':len({h.item_id for h in candidates}),
            'distinct_restaurants_remaining':len({h.restaurant_id for h in candidates}),
            'missing_nutrition_count':missing_nutrition,
            'final_selected_ids':[m['item_id'] for m in result.meals],
            'final_restaurant_ids':[m.get('restaurant_id') for m in result.meals],
            'retrieval_source':retrieval_source,'allergies_applied':allergies,'allergies_kept':True,
            'used_restaurants_prior':prior_restaurants,'pool_error':None}
        slots.append((period,result,notes,evidence,diagnostics,False))
    chosen=[meal for _,result,_,_,_,_ in slots for meal in result.meals]
    warnings=[]
    if ctx.include_ai_estimates and chosen:
        warnings.extend(_fill_estimates(chosen,list(all_sources.values())))
    images=venue_images(shared[1],{meal['restaurant_name'] for meal in chosen}) if off_campus and chosen else {}
    rows=[]
    for period,result,notes,evidence,diagnostics,errored in slots:
        recommendations=[_recommendation(meal,rank,all_sources.get(meal['item_id'],{}),body,timestamp,images,unmapped,user_allergens,
            period_evidence=evidence.get(meal['item_id'],'labeled')) for rank,meal in enumerate(result.meals,1)]
        availability_note=' '.join(dict.fromkeys(notes+result.warnings)) or ('' if recommendations else 'No published eligible dishes for this meal period.')
        rows.append({'slot':period,'optional':period=='snack','selected_recommendation_id':None,'locked':False,
            'recommendations':recommendations,
            'availability_note':availability_note,
            'empty_state':_empty_state(period,recommendations,diagnostics,off_campus=off_campus,errored=errored,availability_note=availability_note),
            'personalization':{'provider':result.provider,'status':result.status}})
        warnings.extend(notes+result.warnings)
    if off_campus and ctx.include_unknown_prices:
        warnings.append('Meals with unpublished prices are included by your choice; their budget fit cannot be verified.')
    if off_campus:
        warnings.extend(list(shared[2])+['Distance is straight-line, not a walking route. Off-campus meal-period availability is unverified.'])
    if any(item['nutrition']['status']=='estimated' or item['price_status']=='estimated' for row in rows for item in row['recommendations']):
        warnings.append('AI estimates are approximate, not published facts. Tracking uses range midpoints; portions and budget fit are uncertain.')
    if not off_campus and chosen:
        warnings.append("USC's official feed publishes dishes, diet tags and allergens but no calories or macros, so dining-hall nutrition is AI-estimated.")
    warnings.append('Confirm availability and allergens with the provider.')
    return {'plan_id':str(uuid4()),'mode':body.mode,'date':str(body.date),'generated_at':timestamp,'data_mode':'live',
        'diversity':{'eligible_restaurants':eligible_restaurants,'include_unknown_prices':ctx.include_unknown_prices},
        'restrictions':{'allergens_filtered':sorted(user_allergens),'allergies_label_only':unmapped,'disliked':dislikes,
            'basis':'usc_published_allergen_tags' if not off_campus else 'dish_text_only'},
        'sources_checked':list(getattr(shared[2],'venues',[])),
        'slots':rows,'warnings':list(dict.fromkeys(warnings)),
        'summary':{'total_cost_cents':0,'remaining_budget_cents':ctx.daily_budget_cents,'swipes_used':0,
            'remaining_swipes':ctx.meal_swipes_available,'nutrition':{'calories':0,'protein_g':0,'coverage':'No meals selected'}}}
