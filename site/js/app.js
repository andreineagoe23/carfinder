import { card } from "./cards.js";
import { $, FLAGS, copyText, el, euro, median, store, timeAgo } from "./dom.js";
import { GitHub, GitHubError, repoFromLocation } from "./github.js";
import { COUNTRIES, SITES, buildLinks } from "./links.js";
import { checklist, keyOf, readShared, shareLink, shortlist, whatsappText } from "./shortlist.js";

const DEFAULT_QUERY = {
  make: "Mazda",
  model: "CX-3",
  year: { min: 2015, max: 2017 },
  mileage_km: { min: null, max: 160000 },
  price_eur: { min: 8000, max: 10000 },
  fuel: ["petrol"],
  gearbox: [],
  location: { zip: "93339", country: "DE", radius_km: 200 },
  ro_location: { city: null, radius_km: 100 },
  sites: Object.keys(SITES),
};
// Kleinanzeigen location IDs we already know; more are learned from search results.
const KNOWN_KA_LOCATIONS = { 93339: "6234" };
const POLL_MS = 5000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
const FORM_KEY = "lastQuery.v3";

const form = $("#search-form");

const state = {
  catalog: { makes: [] },
  settings: { repo: "", token: "", ...store.get("settings", {}) },
  kaLocations: { ...KNOWN_KA_LOCATIONS, ...store.get("kaLocations", {}) },
  result: null,
  shared: null, // shortlist opened from someone's #list= link
  view: "intro", // intro | results | shortlist
};

// ---------- catalog & form

function findMake(name) {
  return state.catalog.makes.find((m) => m.name === name);
}

function fillMakes() {
  form.make.replaceChildren(...state.catalog.makes.map((m) => el("option", { value: m.name }, m.name)));
}

function fillModels(selected) {
  const make = findMake(form.make.value);
  const models = make ? make.models : [];
  form.model.replaceChildren(
    el("option", { value: "" }, "All models"),
    ...models.map((m) => el("option", { value: m.name }, m.name)),
  );
  form.model.value = selected && models.some((m) => m.name === selected) ? selected : "";
}

function fillCities(cities) {
  form.ro_city.append(...cities.map((c) => el("option", { value: c.slug }, c.name)));
}

function fillSites() {
  for (const country of Object.keys(COUNTRIES)) {
    form.querySelector(`[data-sites="${country}"]`).replaceChildren(
      ...Object.entries(SITES)
        .filter(([, site]) => site.country === country)
        .map(([key, site]) =>
          el(
            "label",
            { class: "chip", title: site.fetches ? site.note : `${site.note}. Link only: no automated reading.` },
            el("input", { type: "checkbox", name: "site", value: key }),
            site.name,
            site.fetches ? null : el("small", {}, " link"),
          ),
        ),
    );
  }
}

function checked(name) {
  return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
}

function numberOrNull(input) {
  return input.value === "" ? null : Number(input.value);
}

function readForm() {
  const f = form.elements;
  const countries = checked("country");
  const q = {
    name: `${f.make.value} ${f.model.value || "(all models)"}`,
    make: f.make.value,
    model: f.model.value || null,
    year: { min: numberOrNull(f.year_min), max: numberOrNull(f.year_max) },
    mileage_km: { min: null, max: numberOrNull(f.km_max) },
    price_eur: { min: numberOrNull(f.price_min), max: numberOrNull(f.price_max) },
    fuel: checked("fuel"),
    gearbox: checked("gearbox"),
    location: { zip: f.zip.value.trim(), country: "DE", radius_km: Number(f.radius.value) },
    ro_location: { city: f.ro_city.value || null, radius_km: Number(f.ro_radius.value) },
    sites: checked("site").filter((site) => countries.includes(SITES[site].country)),
    overrides: {},
  };
  const ids = mobileIds(q);
  if (ids) q.overrides.mobile_de = ids;
  const location = state.kaLocations[q.location.zip];
  if (location) q.overrides.kleinanzeigen = { location_id: location };
  return q;
}

function writeForm(q) {
  const f = form.elements;
  f.make.value = q.make;
  fillModels(q.model);
  f.year_min.value = q.year?.min ?? "";
  f.year_max.value = q.year?.max ?? "";
  f.price_min.value = q.price_eur?.min ?? "";
  f.price_max.value = q.price_eur?.max ?? "";
  f.km_max.value = q.mileage_km?.max ?? "";
  f.zip.value = q.location.zip;
  f.radius.value = String(q.location.radius_km);
  f.ro_city.value = q.ro_location?.city || "";
  f.ro_radius.value = String(q.ro_location?.radius_km ?? 100);
  const sites = q.sites?.length ? q.sites : Object.keys(SITES);
  const countries = Object.keys(COUNTRIES).filter((c) => sites.some((s) => SITES[s]?.country === c));
  for (const input of form.querySelectorAll('input[type="checkbox"]')) {
    const list = { fuel: q.fuel, gearbox: q.gearbox, site: sites, country: countries }[input.name] || [];
    input.checked = list.includes(input.value);
  }
  syncRegions();
  renderLinks();
}

/** Show each country's fields only when it's ticked; ticking a country ticks its sites if none are. */
function syncRegions(changed) {
  for (const region of form.querySelectorAll(".region")) {
    const country = region.dataset.country;
    const on = region.querySelector('input[name="country"]').checked;
    region.querySelector(".region-body").hidden = !on;
    const sites = [...region.querySelectorAll('input[name="site"]')];
    if (on && changed === country && !sites.some((s) => s.checked)) sites.forEach((s) => (s.checked = true));
  }
  form.ro_radius.disabled = !form.ro_city.value;
}

function validate(q) {
  if (!q.make) return "Pick a make.";
  const countries = checked("country");
  if (!countries.length) return "Pick Germany, Romania or both.";
  if (countries.includes("DE") && !/^\d{5}$/.test(q.location.zip)) return "Zip must be a 5-digit German postcode.";
  for (const [label, range] of [["Year", q.year], ["Price", q.price_eur]]) {
    if (range.min != null && range.max != null && range.min > range.max) return `${label}: “from” is above “to”.`;
  }
  if (!q.sites.length) return "Pick at least one site.";
  return null;
}

function mobileIds(q) {
  const make = findMake(q.make);
  if (!make) return null;
  if (!q.model) return { make_id: String(make.mobile_de) };
  const model = make.models.find((m) => m.name === q.model);
  return model ? { make_id: String(make.mobile_de), model_id: String(model.mobile_de) } : null;
}

/** Stable ID per search (ignores the display name and lookup overrides). */
async function queryId(q) {
  const { name, overrides, ...rest } = q;
  const canonical = JSON.stringify(rest, Object.keys(flatKeys(rest)).sort());
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
}

function flatKeys(obj, out = {}) {
  for (const [key, value] of Object.entries(obj)) {
    out[key] = true;
    if (value && typeof value === "object" && !Array.isArray(value)) flatKeys(value, out);
  }
  return out;
}

// ---------- site links

function renderLinks() {
  const q = readForm();
  const links = q.sites.length
    ? buildLinks(q, { mobileIds: mobileIds(q), kaLocationId: state.kaLocations[q.location.zip] })
    : [];
  const groups = Object.keys(COUNTRIES)
    .map((country) => [country, links.filter((l) => l.country === country)])
    .filter(([, group]) => group.length);
  $("#links").replaceChildren(
    ...(groups.length ? groups : [[null, []]]).map(([country, group]) =>
      country
        ? el(
            "div",
            { class: "link-group" },
            el("h3", {}, `${FLAGS[country]} ${COUNTRIES[country]}`),
            el(
              "div",
              { class: "links" },
              group.map((link) =>
                el(
                  "div",
                  { class: "link-item" },
                  link.error
                    ? el("span", { class: "link disabled" }, link.name)
                    : el("a", { class: "link", href: link.url, target: "_blank", rel: "noopener" }, `${link.name} ↗`),
                  el("small", { class: "trust" }, link.fetches ? `${link.note} · shown below` : link.note),
                  ...(link.error ? [link.error] : link.notes).map((n) => el("small", { class: "muted" }, n)),
                ),
              ),
            ),
          )
        : el("p", { class: "muted small" }, "Pick at least one site."),
    ),
  );
}

function learnKaLocation(result) {
  const link = result.links?.find((l) => l.site === "kleinanzeigen" && l.url);
  const match = link?.url.match(/\/c216l(\d+)r\d+/);
  if (!match) return;
  state.kaLocations[result.query.location.zip] = match[1];
  store.set("kaLocations", state.kaLocations);
}

// ---------- views

function showView(view) {
  state.view = view;
  document.body.classList.toggle("shared-view", view === "shortlist" && Boolean(state.shared));
  $("#intro").hidden = view !== "intro";
  $("#results-section").hidden = view !== "results";
  $("#shortlist-section").hidden = view !== "shortlist";
  $(".content").scrollTo?.(0, 0);
}

function toggleStar(listing) {
  shortlist.toggle(listing);
  updateShortlistCount();
  if (state.view === "shortlist") renderShortlist();
  else renderResults();
}

function updateShortlistCount() {
  $("#shortlist-count").textContent = shortlist.items().length;
}

// ---------- results

function sortListings(listings, how) {
  const by = {
    score: (a, b) => (b.score ?? 0) - (a.score ?? 0),
    price: (a, b) => a.price_eur - b.price_eur,
    km: (a, b) => (a.mileage_km ?? 1e9) - (b.mileage_km ?? 1e9),
    year: (a, b) => (b.year ?? 0) - (a.year ?? 0),
    distance: (a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9),
    new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""),
  }[how];
  return [...listings].sort(by);
}

/** "🇩🇪 12 cars, median €9,800 · 🇷🇴 5 cars, median €11,200" when both countries have results. */
function countryComparison(listings) {
  const parts = Object.keys(COUNTRIES)
    .map((country) => {
      const prices = listings.filter((l) => (l.country || "DE") === country).map((l) => l.price_eur);
      return prices.length ? `${FLAGS[country]} ${prices.length} cars, median ${euro.format(median(prices))}` : null;
    })
    .filter(Boolean);
  return parts.length > 1 ? parts.join(" · ") : null;
}

function renderResults() {
  const result = state.result;
  if (!result) return;
  const all = result.listings;
  const prices = all.map((l) => l.price_eur);
  $("#results-title").textContent = result.query.name || `${result.query.make} ${result.query.model || ""}`;
  $("#results-meta").replaceChildren(
    [
      `${all.length} car${all.length === 1 ? "" : "s"}`,
      prices.length ? `from ${euro.format(Math.min(...prices))}` : null,
      `updated ${timeAgo(result.updated_at)}`,
    ]
      .filter(Boolean)
      .join(" · "),
    countryComparison(all) ? el("span", { class: "compare" }, countryComparison(all)) : null,
  );

  $("#results-warnings").replaceChildren(
    ...Object.entries(result.errors || {}).map(([site, error]) =>
      el("p", { class: "warning" }, `${SITES[site]?.name || site}: ${error}`),
    ),
  );

  const onlyNew = $("#only-new").checked;
  const country = $("#filter-country").value;
  const seller = $("#filter-seller").value;
  const text = $("#filter-text").value.trim().toLowerCase();
  const visible = sortListings(all, $("#sort").value).filter(
    (l) =>
      (!onlyNew || l.first_seen === result.updated_at) &&
      (!country || (l.country || "DE") === country) &&
      (!seller || l.seller_type === seller) &&
      (!text || `${l.title} ${l.city || ""} ${l.seller_name || ""}`.toLowerCase().includes(text)),
  );
  $("#results").replaceChildren(
    ...(visible.length
      ? visible.map((l) =>
          card(l, {
            isNew: l.first_seen === result.updated_at && result.created_at !== result.updated_at,
            starred: shortlist.has(keyOf(l)),
            onStar: toggleStar,
          }),
        )
      : [el("p", { class: "muted empty" }, all.length ? "Nothing matches these filters." : "No cars found. Try widening price, years or radius.")]),
  );
}

// ---------- shortlist

async function renderShortlist() {
  const shared = state.shared;
  const items = shared || shortlist.items();
  $("#shortlist-title").textContent = shared ? "Cars shared with you" : "Your shortlist";
  $("#shortlist-meta").textContent = items.length
    ? `${items.length} car${items.length === 1 ? "" : "s"}${shared ? "" : " · saved in this browser"}`
    : "";

  await renderShortlistActions();

  $("#shortlist-cars").replaceChildren(
    ...(items.length
      ? items.map(({ key, listing, note }) =>
          card(listing, {
            starred: true,
            onStar: shared ? null : toggleStar,
            extra: shared
              ? note
                ? el("p", { class: "note" }, `📝 ${note}`)
                : null
              : el("textarea", {
                  class: "note-input",
                  rows: "2",
                  placeholder: "Note for the viewing, e.g. “ask about the timing chain”",
                  oninput: (e) => {
                    shortlist.setNote(key, e.target.value);
                    clearTimeout(noteTimer);
                    noteTimer = setTimeout(renderShortlistActions, 400); // share link carries the notes
                  },
                }, note),
          }),
        )
      : [el("p", { class: "muted empty" }, "Nothing here yet. Tap ☆ on a car in your results to add it.")]),
  );
  $("#shortlist-checklist").replaceChildren(items.length ? checklist() : "");
}

let noteTimer;

/** Share buttons are rebuilt whenever the list or a note changes, so links are never stale. */
async function renderShortlistActions() {
  const shared = state.shared;
  const items = shared || shortlist.items();
  const actions = [];
  if (state.result || shared) {
    actions.push(el("button", { type: "button", class: "ghost", onclick: () => leaveShortlist() }, state.result ? "← Back to results" : "← New search"));
  }
  if (items.length && !shared) {
    const link = await shareLink(items);
    const message = whatsappText(items, link);
    actions.push(
      el("a", { class: "button primary", href: `https://wa.me/?text=${encodeURIComponent(message)}`, target: "_blank", rel: "noopener" }, "Send on WhatsApp"),
      el("button", { type: "button", onclick: async () => flash(await copyText(message), "Message copied") }, "Copy message"),
      el("button", { type: "button", onclick: async () => flash(await copyText(link), "Link copied") }, "Copy link"),
    );
  }
  if (items.length) actions.push(el("button", { type: "button", class: "ghost", onclick: () => window.print() }, "Print"));
  $("#shortlist-actions").replaceChildren(...actions);
}

function openShortlist() {
  state.shared = null;
  history.replaceState(null, "", "#shortlist");
  showView("shortlist");
  renderShortlist();
}

function leaveShortlist() {
  state.shared = null;
  document.body.classList.remove("shared-view");
  if (state.result) {
    history.replaceState(null, "", `#s=${state.result.id}`);
    showView("results");
    renderResults();
  } else {
    history.replaceState(null, "", location.pathname);
    showView("intro");
  }
}

function flash(ok, message) {
  setStatus(ok ? message : "", "ok");
  if (ok) setTimeout(() => setStatus(""), 2500);
}

// ---------- status line

function setStatus(message, kind = "info", link = null) {
  const box = $("#status");
  box.hidden = !message;
  box.className = `status ${kind}`;
  box.replaceChildren(
    kind === "busy" ? el("span", { class: "spinner", "aria-hidden": "true" }) : "",
    message || "",
    link ? el("a", { href: link.href, target: "_blank", rel: "noopener" }, ` ${link.text}`) : "",
  );
}

// ---------- GitHub-backed actions

function github() {
  return new GitHub(state.settings.repo || repoFromLocation() || "", state.settings.token);
}

/** Results of an earlier search, e.g. from a #s=<id> link. */
async function openResult(id) {
  setStatus("Loading…", "busy");
  try {
    const result = await github().readResults(`searches/${id}.json`);
    if (!result) {
      setStatus("That search no longer exists.", "error");
      return;
    }
    showResult(result);
    setStatus("");
  } catch (err) {
    setStatus(err.message, "error");
  }
}

function showResult(result) {
  state.result = result;
  state.shared = null;
  learnKaLocation(result);
  writeForm(result.query);
  history.replaceState(null, "", `#s=${result.id}`);
  showView("results");
  renderResults();
}

async function runSearch(event) {
  event.preventDefault();
  const q = readForm();
  const problem = validate(q);
  $("#form-error").hidden = !problem;
  $("#form-error").textContent = problem || "";
  if (problem) return;
  if (!state.settings.token) {
    openSettings("Add a GitHub token to run searches. The site links work without one.");
    return;
  }

  const id = await queryId(q);
  const started = new Date();
  const button = $("#search-button");
  button.disabled = true;
  setStatus("Starting search on GitHub Actions…", "busy");
  try {
    await github().dispatch({ query: JSON.stringify(q), id });
    await pollForResult(id, started);
  } catch (err) {
    const hints = {
      401: " The token is invalid or expired — paste a new one in Settings.",
      403: " The token can't start workflows. Edit it on GitHub: Repository access → Only select repositories → this repo, and Permissions → Actions: Read and write.",
      404: " Repository not found — check owner/name in Settings, and that the token can access it.",
    };
    const hint = (err instanceof GitHubError && hints[err.status]) || "";
    setStatus(`${err.message}.${hint}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function pollForResult(id, started) {
  const gh = github();
  const since = new Date(started.getTime() - 30_000); // tolerate clock skew vs. the runner
  while (Date.now() - started < POLL_TIMEOUT_MS) {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    const result = await gh.readResults(`searches/${id}.json`);
    if (result && new Date(result.updated_at) >= since) {
      showResult(result);
      setStatus(`Found ${result.listings.length} cars.`, "ok");
      return;
    }
    const run = await gh.runSince(new Date(started.getTime() - 10_000));
    const seconds = Math.round((Date.now() - started) / 1000);
    if (run?.status === "completed" && run.conclusion !== "success") {
      setStatus(`The search failed (${run.conclusion}).`, "error", { href: run.html_url, text: "See the log ↗" });
      return;
    }
    const phase = run ? (run.status === "in_progress" ? "Searching the sites" : "Waiting for a runner") : "Starting";
    setStatus(`${phase}… ${seconds}s`, "busy", run ? { href: run.html_url, text: "Watch on GitHub ↗" } : null);
  }
  setStatus("Still not done after 10 minutes — check the Actions tab on GitHub.", "error");
}

// ---------- settings

function openSettings(reason) {
  const f = $("#settings-form").elements;
  const s = state.settings;
  f.repo.value = s.repo || repoFromLocation() || "";
  f.token.value = s.token || "";
  $("#settings-reason").hidden = !reason;
  $("#settings-reason").textContent = reason || "";
  $("#settings").showModal();
}

function saveSettings() {
  if ($("#settings").returnValue !== "save") return;
  const f = $("#settings-form").elements;
  state.settings = { repo: f.repo.value.trim(), token: f.token.value.trim() };
  store.set("settings", state.settings);
}

// ---------- boot

async function loadJson(path, fallback) {
  try {
    return await (await fetch(path)).json();
  } catch {
    setStatus(`Couldn't load ${path}.`, "error");
    return fallback;
  }
}

async function route() {
  const hash = location.hash;
  const resultId = hash.match(/^#s=([a-f0-9]{12})$/)?.[1];
  const sharedList = hash.match(/^#list=([A-Za-z0-9_-]+)$/)?.[1];
  if (resultId) return openResult(resultId);
  if (hash === "#shortlist") return openShortlist();
  if (sharedList) {
    try {
      state.shared = await readShared(sharedList);
      showView("shortlist");
      renderShortlist();
    } catch {
      setStatus("This shared list link is broken or incomplete.", "error");
    }
  }
}

async function main() {
  fillSites();
  const [catalog, cities] = await Promise.all([
    loadJson("data/catalog.json", { makes: [] }),
    loadJson("data/ro_cities.json", []),
  ]);
  state.catalog = catalog;
  fillMakes();
  fillCities(cities);
  writeForm(store.get(FORM_KEY, DEFAULT_QUERY));
  updateShortlistCount();

  form.make.addEventListener("change", () => {
    fillModels();
    renderLinks();
  });
  form.addEventListener("input", (event) => {
    if (event.target.name === "country" || event.target.name === "ro_city") syncRegions(event.target.value);
    renderLinks();
    store.set(FORM_KEY, readForm());
  });
  form.addEventListener("submit", runSearch);
  for (const id of ["#sort", "#only-new", "#filter-text", "#filter-country", "#filter-seller"]) {
    $(id).addEventListener("input", renderResults);
  }
  $("#open-shortlist").addEventListener("click", openShortlist);
  $("#open-settings").addEventListener("click", () => openSettings());
  $("#settings").addEventListener("close", saveSettings);
  window.addEventListener("hashchange", route);
  route();
}

main();
