import { GitHub, GitHubError, repoFromLocation } from "./github.js";
import { COUNTRIES, SITES, buildLinks } from "./links.js";

const DEFAULT_QUERY = {
  make: "Mazda",
  model: "CX-3",
  year: { min: 2015, max: 2017 },
  mileage_km: { min: null, max: 160000 },
  price_eur: { min: 8000, max: 10000 },
  fuel: ["petrol"],
  gearbox: [],
  location: { zip: "93339", country: "DE", radius_km: 200 },
  sites: Object.keys(SITES),
};
// Kleinanzeigen location IDs we already know; more are learned from search results.
const KNOWN_KA_LOCATIONS = { 93339: "6234" };
const POLL_MS = 5000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
const FLAGS = { DE: "🇩🇪", RO: "🇷🇴" };
const PRICE_LABELS = {
  "top-price": ["Top price", "good"],
  "good-price": ["Good price", "good"],
  "fair-price": ["Fair price", "ok"],
  "somewhat-expensive": ["A bit pricey", "warn"],
  expensive: ["Expensive", "bad"],
};

const $ = (sel) => document.querySelector(sel);
const form = $("#search-form");
const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-IE");

const store = {
  get(key, fallback) {
    try {
      return JSON.parse(localStorage.getItem(`carfinder.${key}`)) ?? fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    localStorage.setItem(`carfinder.${key}`, JSON.stringify(value));
  },
};

const state = {
  catalog: { makes: [] },
  settings: { repo: "", token: "", ...store.get("settings", {}) },
  kaLocations: { ...KNOWN_KA_LOCATIONS, ...store.get("kaLocations", {}) },
  result: null,
  polling: null,
};

// ---------- small DOM helpers (all listing text goes through textContent, never innerHTML)

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "href" || key === "src") node.setAttribute(key, safeUrl(value));
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function safeUrl(url) {
  return /^https:\/\//i.test(url) || url.startsWith("#") || url.startsWith("./") ? url : "#";
}

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso)) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

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

function sitesByCountry() {
  return Object.keys(COUNTRIES).map((country) => [
    country,
    Object.entries(SITES).filter(([, site]) => site.country === country),
  ]);
}

function fillSites() {
  $("#site-chips").replaceChildren(
    ...sitesByCountry().map(([country, sites]) =>
      el(
        "div",
        { class: "site-group" },
        el("span", { class: "site-group-name" }, `${FLAGS[country]} ${COUNTRIES[country]}`),
        el(
          "div",
          { class: "chips" },
          sites.map(([key, site]) =>
            el(
              "label",
              { class: "chip", title: site.fetches ? site.note : `${site.note}. Link only: no automated reading.` },
              el("input", { type: "checkbox", name: "site", value: key }),
              site.name,
              site.fetches ? null : el("small", {}, " link"),
            ),
          ),
        ),
      ),
    ),
  );
}

function checked(name) {
  return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
}

function numberOrNull(input) {
  return input.value === "" ? null : Number(input.value);
}

function readForm() {
  const f = form.elements;
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
    sites: checked("site"),
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
  const sites = q.sites?.length ? q.sites : Object.keys(SITES);
  for (const input of form.querySelectorAll('input[type="checkbox"]')) {
    const list = { fuel: q.fuel, gearbox: q.gearbox, site: sites }[input.name] || [];
    input.checked = list.includes(input.value);
  }
  renderLinks();
}

function validate(q) {
  if (!q.make) return "Pick a make.";
  if (!/^\d{5}$/.test(q.location.zip)) return "Zip must be a 5-digit German postcode.";
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
  const links = buildLinks(q, { mobileIds: mobileIds(q), kaLocationId: state.kaLocations[q.location.zip] });
  const groups = Object.keys(COUNTRIES)
    .map((country) => [country, links.filter((l) => l.country === country)])
    .filter(([, group]) => group.length);
  $("#links").replaceChildren(
    ...groups.map(([country, group]) =>
      el(
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
      ),
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

function renderResults() {
  const result = state.result;
  if (!result) return;
  $("#results-section").hidden = false;
  $("#intro").hidden = true;

  const all = result.listings;
  const prices = all.map((l) => l.price_eur).sort((a, b) => a - b);
  const median = prices.length ? prices[Math.floor(prices.length / 2)] : null;
  $("#results-title").textContent = result.query.name || `${result.query.make} ${result.query.model}`;
  $("#results-meta").textContent = [
    `${all.length} car${all.length === 1 ? "" : "s"}`,
    prices.length ? `from ${euro.format(prices[0])}` : null,
    median ? `median ${euro.format(median)}` : null,
    `updated ${timeAgo(result.updated_at)}`,
  ]
    .filter(Boolean)
    .join(" · ");

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
      ? visible.map((l) => card(l, result))
      : [el("p", { class: "muted empty" }, all.length ? "Nothing matches these filters." : "No cars found yet. Try widening price, years or radius.")]),
  );
}

function card(l, result) {
  const isNew = l.first_seen === result.updated_at && result.created_at !== result.updated_at;
  const label = PRICE_LABELS[l.price_label];
  const history = l.price_history || [];
  const firstPrice = history.length > 1 ? history[0].price_eur : null;
  const scoreClass = l.score >= 70 ? "good" : l.score >= 50 ? "ok" : "low";
  const specs = [
    l.first_registration || l.year,
    l.mileage_km != null ? `${num.format(l.mileage_km)} km` : null,
    l.power_hp ? `${l.power_hp} hp` : null,
    l.gearbox,
    l.fuel,
  ].filter(Boolean);

  return el(
    "article",
    { class: "car" },
    el(
      "a",
      { class: "photo", href: l.url, target: "_blank", rel: "noopener" },
      l.images?.length
        ? el("img", { src: l.images[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
        : el("span", { class: "no-photo" }, "No photo"),
      el("span", { class: `score ${scoreClass}`, title: "Match score (price vs similar cars, km/year, seller, site rating)" }, l.score ?? "–"),
    ),
    el(
      "div",
      { class: "body" },
      el(
        "div",
        { class: "badges" },
        el("span", { class: "badge site" }, `${FLAGS[l.country || "DE"]} ${SITES[l.source]?.name || l.source}`),
        isNew ? el("span", { class: "badge new" }, "NEW") : null,
        label ? el("span", { class: `badge ${label[1]}` }, label[0]) : null,
        l.seller_type ? el("span", { class: "badge" }, l.seller_type === "dealer" ? "Dealer" : "Private") : null,
        l.negotiable ? el("span", { class: "badge" }, "VB") : null,
      ),
      el("h3", {}, el("a", { href: l.url, target: "_blank", rel: "noopener" }, l.title)),
      el(
        "p",
        { class: "price" },
        euro.format(l.price_eur),
        l.old_price_eur ? el("s", {}, euro.format(l.old_price_eur)) : null,
        firstPrice && firstPrice !== l.price_eur ? el("s", {}, euro.format(firstPrice)) : null,
      ),
      l.listed_currency
        ? el("p", { class: "muted small" }, `Listed at ${num.format(l.listed_price)} ${l.listed_currency === "RON" ? "lei" : l.listed_currency}`)
        : null,
      el("p", { class: "specs" }, [l.model, ...specs].filter(Boolean).join(" · ")),
      el(
        "p",
        { class: "muted small" },
        [l.zip, l.city].filter(Boolean).join(" "),
        l.distance_km != null ? ` · ${l.distance_km} km away` : "",
        l.seller_name ? ` · ${l.seller_name}` : "",
      ),
      l.flags?.length ? el("ul", { class: "flags" }, l.flags.map((f) => el("li", {}, f))) : null,
      l.also_on?.length
        ? el(
            "p",
            { class: "small" },
            "Also on ",
            l.also_on.map((o, i) => [i ? ", " : "", el("a", { href: o.url, target: "_blank", rel: "noopener" }, o.name)]),
          )
        : null,
      el("p", { class: "muted small" }, `First seen ${timeAgo(l.first_seen)}`),
    ),
  );
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

async function loadSaved() {
  const repo = state.settings.repo || repoFromLocation();
  if (!repo) return;
  let index = [];
  try {
    index = (await github().readResults("index.json")) || [];
  } catch (err) {
    setStatus(`Couldn't load saved searches (${err.message}).`, "error");
    return;
  }
  $("#saved-empty").hidden = index.length > 0;
  $("#saved-list").replaceChildren(
    ...index.map((s) =>
      el(
        "li",
        {},
        el(
          "button",
          { type: "button", class: "saved-item", onclick: () => openSaved(s.id) },
          el("span", { class: "saved-name" }, s.name, s.new_count ? el("span", { class: "badge new" }, `${s.new_count} new`) : null),
          el("span", { class: "muted small" }, `${s.count} cars · ${timeAgo(s.updated_at)}`),
        ),
        el("button", { type: "button", class: "icon", title: "Delete", "aria-label": `Delete ${s.name}`, onclick: () => deleteSaved(s) }, "×"),
      ),
    ),
  );
}

async function openSaved(id) {
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
  learnKaLocation(result);
  writeForm(result.query);
  history.replaceState(null, "", `#s=${result.id}`);
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
    openSettings("Add a GitHub token to run searches. The site links above work without one.");
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
      loadSaved();
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

async function deleteSaved(saved) {
  if (!state.settings.token) {
    openSettings("Add a GitHub token to delete searches.");
    return;
  }
  if (!confirm(`Delete the saved search “${saved.name}” and its results?`)) return;
  try {
    await github().dispatch({ delete: saved.id });
    setStatus("Deleting… it disappears from the list in about a minute.", "info");
  } catch (err) {
    setStatus(err.message, "error");
  }
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
  renderResults();
  loadSaved();
}

// ---------- boot

async function main() {
  fillSites();
  try {
    state.catalog = await (await fetch("data/catalog.json")).json();
  } catch {
    setStatus("Couldn't load the car catalog.", "error");
  }
  fillMakes();
  writeForm(store.get("lastQuery.v2", DEFAULT_QUERY));

  form.make.addEventListener("change", () => {
    fillModels();
    renderLinks();
  });
  form.addEventListener("input", () => {
    renderLinks();
    store.set("lastQuery.v2", readForm());
  });
  form.addEventListener("submit", runSearch);
  for (const id of ["#sort", "#only-new", "#filter-text", "#filter-country", "#filter-seller"]) {
    $(id).addEventListener("input", renderResults);
  }
  $("#open-settings").addEventListener("click", () => openSettings());
  $("#settings").addEventListener("close", saveSettings);

  const hashId = location.hash.match(/^#s=([a-f0-9]{12})$/)?.[1];
  if (hashId) openSaved(hashId);
  loadSaved();
}

main();
