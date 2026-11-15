(() => {
  const state = {
    mode: null,
    profile: null,
    situation: null,
    locked: [],
    plan: null,
  };

  const $ = (id) => document.getElementById(id);
  const views = ["onboard", "home", "situation", "plan"];

  function show(name) {
    views.forEach((v) => {
      const el = $(`view-${v}`);
      if (el) el.classList.toggle("hidden", v !== name);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function csv(id) {
    return $(id)
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function readProfile() {
    return {
      nutrition_goal: $("goal").value,
      dietary_preference: $("diet").value || null,
      allergies: csv("allergies"),
      exclusions: csv("exclusions"),
      prefer_high_protein: $("highProtein").checked,
      preferred_foods: [],
    };
  }

  function readSituation() {
    const base = {
      mode: state.mode,
      meal_periods: ["breakfast", "lunch", "dinner"],
      lat: 34.0224,
      lng: -118.2851,
      include_snacks: $("snacks").checked,
      ranking_priority: "balanced",
    };
    if (state.mode === "usc_dining") {
      return {
        ...base,
        meal_swipes_remaining: Number($("swipes").value || 0),
      };
    }
    return {
      ...base,
      budget_per_meal: Number($("budgetMeal").value || 0),
      budget_daily: Number($("budgetDay").value || 0),
      preferred_cuisines: csv("cuisines"),
      max_miles: Number($("maxMiles").value || 0.3),
    };
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return res.json();
  }

  function renderPlan(plan) {
    state.plan = plan;
    $("menuMeta").textContent = [
      plan.mode === "usc_dining" ? "USC Dining" : "Off-Campus",
      plan.menu?.menu_date ? `menu ${plan.menu.menu_date}` : null,
      plan.menu?.source_note ? "dated snapshot" : null,
    ]
      .filter(Boolean)
      .join(" · ");

    $("limits").textContent = (plan.limitations || []).join(" ");

    const root = $("planRoot");
    root.innerHTML = "";
    (plan.periods || []).forEach((period) => {
      const box = document.createElement("article");
      box.className = "period";
      const title = document.createElement("h2");
      title.textContent = period.meal_period;
      if (period.locked) {
        const badge = document.createElement("span");
        badge.className = "locked-badge";
        badge.textContent = " · locked";
        title.appendChild(badge);
      }
      box.appendChild(title);

      (period.recommendations || []).forEach((rec) => {
        const card = document.createElement("div");
        card.className = "rec";
        const price =
          rec.price?.model === "meal_swipe_ayce"
            ? "Meal swipe / AYCE"
            : rec.price?.amount != null
              ? `$${rec.price.amount}`
              : "Price unknown";
        const nut =
          rec.nutrition?.confidence === "unavailable"
            ? "Nutrition unavailable"
            : `Nutrition ${rec.nutrition?.confidence || "unknown"}`;
        card.innerHTML = `
          <span class="rank">#${rec.rank || 1}</span>
          <h3>${rec.name || ""}</h3>
          <p class="meta">${rec.venue_name || ""}${
            rec.distance_miles != null ? ` · ${rec.distance_miles} mi` : ""
          } · ${price} · ${nut}</p>
          <ul>${(rec.why || []).map((w) => `<li>${w}</li>`).join("")}</ul>
        `;
        if (!period.locked) {
          const actions = document.createElement("div");
          actions.className = "actions";
          const choose = document.createElement("button");
          choose.className = "choose";
          choose.textContent = "Choose this";
          choose.onclick = () => swap(period.meal_period, rec.dish_id, "selected");
          const swapBtn = document.createElement("button");
          swapBtn.textContent = "Swap to this";
          swapBtn.onclick = () => swap(period.meal_period, rec.dish_id, "selected");
          actions.appendChild(choose);
          actions.appendChild(swapBtn);
          card.appendChild(actions);
        }
        box.appendChild(card);
      });

      (period.notes || []).forEach((n) => {
        const note = document.createElement("p");
        note.className = "note";
        note.textContent = n;
        box.appendChild(note);
      });
      root.appendChild(box);
    });
    show("plan");
  }

  async function buildPlan() {
    state.profile = readProfile();
    state.situation = readSituation();
    state.locked = [];
    const btn = $("buildPlan");
    btn.disabled = true;
    btn.textContent = "Planning…";
    try {
      const plan = await post("/v1/plan/day", {
        profile: state.profile,
        situation: state.situation,
        locked: state.locked,
      });
      renderPlan(plan);
    } catch (err) {
      alert(`Could not build plan: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "Build my day";
    }
  }

  async function swap(mealPeriod, dishId, status) {
    state.locked = [
      ...state.locked.filter((l) => l.meal_period !== mealPeriod),
      { meal_period: mealPeriod, dish_id: dishId, status },
    ];
    try {
      const plan = await post("/v1/plan/swap", {
        profile: state.profile,
        situation: state.situation,
        locked: state.locked,
        meal_period: mealPeriod,
        dish_id: dishId,
        status,
      });
      renderPlan(plan);
    } catch (err) {
      alert(`Swap failed: ${err.message}`);
    }
  }

  $("toHome").onclick = () => {
    state.profile = readProfile();
    show("home");
  };
  $("editProfile").onclick = () => show("onboard");
  $("backHome").onclick = () => show("home");
  $("newPlan").onclick = () => {
    state.locked = [];
    state.plan = null;
    show("home");
  };
  $("buildPlan").onclick = buildPlan;

  document.querySelectorAll(".mode-card").forEach((btn) => {
    btn.onclick = () => {
      state.mode = btn.dataset.mode;
      $("sitTitle").textContent =
        state.mode === "usc_dining" ? "USC Dining — today’s situation" : "Off-Campus — today’s situation";
      $("uscFields").classList.toggle("hidden", state.mode !== "usc_dining");
      $("offFields").classList.toggle("hidden", state.mode !== "off_campus");
      show("situation");
    };
  });

  show("onboard");
})();
