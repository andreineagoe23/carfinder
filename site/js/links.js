// Search-link builders for each site. Mirror of src/carfinder/sites/*.py (build_url);
// tests/js/links.test.mjs checks both produce the same URLs.

export const COUNTRIES = { DE: "Germany", RO: "Romania" };

// fetches: carfinder reads the listings itself; otherwise it can only link to the site.
export const SITES = {
  mobile_de: { name: "mobile.de", country: "DE", fetches: false, note: "Biggest German market, mostly dealers" },
  autoscout24: { name: "AutoScout24", country: "DE", fetches: true, note: "Mostly dealers, with a price rating" },
  kleinanzeigen: { name: "Kleinanzeigen", country: "DE", fetches: true, note: "Mostly private sellers — check carefully" },
  autovit: { name: "Autovit", country: "RO", fetches: true, note: "Biggest Romanian market, mostly dealers" },
  olx_ro: { name: "OLX.ro", country: "RO", fetches: false, note: "Mostly private sellers — check carefully" },
  publi24: { name: "Publi24", country: "RO", fetches: false, note: "Classifieds, private sellers" },
  autouncle_ro: { name: "AutoUncle.ro", country: "RO", fetches: false, note: "Collects Romanian ads and rates the price" },
};

export function slugify(text, sep) {
  return text
    .normalize("NFKD")
    .replace(/[^\x00-\x7f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, sep)
    .split(sep)
    .filter(Boolean)
    .join(sep);
}

export function snapRadius(km, allowed) {
  for (const radius of allowed) {
    if (radius >= km) {
      return [radius, radius === km ? null : `radius ${km} km not offered, using ${radius} km`];
    }
  }
  const top = allowed[allowed.length - 1];
  return [top, `radius ${km} km exceeds site maximum, using ${top} km`];
}

export function span(range, sep) {
  const { min = null, max = null } = range || {};
  if (min == null && max == null) return null;
  return `${min ?? ""}${sep}${max ?? ""}`;
}

function withQuery(url, params) {
  const query = params.toString();
  return query ? `${url}?${query}` : url;
}

function addRanges(params, ranges) {
  for (const [name, range] of ranges) {
    if (range?.min != null) params.append(`search[filter_float_${name}:from]`, String(range.min));
    if (range?.max != null) params.append(`search[filter_float_${name}:to]`, String(range.max));
  }
}

// ---------- Germany

const MOBILE = {
  url: "https://suchen.mobile.de/fahrzeuge/search.html",
  radii: [10, 20, 50, 100, 150, 200],
  fuels: { petrol: "PETROL", diesel: "DIESEL", hybrid: "HYBRID", electric: "ELECTRICITY", lpg: "LPG" },
  gearboxes: { manual: "MANUAL_GEAR", automatic: "AUTOMATIC_GEAR" },
};

export function mobileDe(q, ids) {
  if (!ids?.make_id || (q.model && !ids.model_id)) {
    return { error: `${q.make} ${q.model || ""} isn't in the mobile.de catalog` };
  }
  const [radius, note] = snapRadius(q.location.radius_km, MOBILE.radii);
  const params = new URLSearchParams([
    ["isSearchRequest", "true"],
    ["s", "Car"],
    ["vc", "Car"],
    ["dam", "false"],
    ["ms", `${ids.make_id};${q.model ? ids.model_id : ""};;`],
  ]);
  for (const [key, value] of [
    ["fr", span(q.year, ":")],
    ["ml", span(q.mileage_km, ":")],
    ["p", span(q.price_eur, ":")],
  ]) {
    if (value) params.append(key, value);
  }
  for (const f of q.fuel || []) params.append("ft", MOBILE.fuels[f]);
  for (const g of q.gearbox || []) params.append("tr", MOBILE.gearboxes[g]);
  params.append("zip", q.location.zip);
  params.append("zipr", String(radius));
  params.append("cn", q.location.country);
  return { url: `${MOBILE.url}?${params}`, notes: note ? [note] : [] };
}

const AS24 = {
  url: "https://www.autoscout24.de/lst",
  radii: [10, 20, 50, 100, 150, 200],
  fuels: { petrol: "B", diesel: "D", hybrid: "2", electric: "E", lpg: "L" },
  gearboxes: { manual: "M", automatic: "A" },
  countries: { DE: "D", AT: "A", NL: "NL", BE: "B", LU: "L", FR: "F", IT: "I", ES: "E" },
};

export function autoScout24(q) {
  const country = AS24.countries[q.location.country];
  if (!country) return { error: `AutoScout24 country '${q.location.country}' not supported` };
  const [radius, note] = snapRadius(q.location.radius_km, AS24.radii);
  const params = new URLSearchParams([
    ["atype", "C"],
    ["cy", country],
    ["damaged_listing", "exclude"],
    ["ustate", "N,U"],
    ["sort", "standard"],
    ["desc", "0"],
  ]);
  for (const [key, value] of [
    ["fregfrom", q.year?.min],
    ["fregto", q.year?.max],
    ["kmfrom", q.mileage_km?.min],
    ["kmto", q.mileage_km?.max],
    ["pricefrom", q.price_eur?.min],
    ["priceto", q.price_eur?.max],
  ]) {
    if (value != null) params.append(key, String(value));
  }
  if (q.fuel?.length) params.append("fuel", q.fuel.map((f) => AS24.fuels[f]).join(","));
  if (q.gearbox?.length) params.append("gear", q.gearbox.map((g) => AS24.gearboxes[g]).join(","));
  params.append("zip", q.location.zip);
  params.append("zipr", String(radius));
  const path = [AS24.url, slugify(q.make, "-"), q.model ? slugify(q.model, "-") : null].filter(Boolean).join("/");
  return { url: `${path}?${params}`, notes: note ? [note] : [] };
}

const KA = {
  url: "https://www.kleinanzeigen.de",
  radii: [5, 10, 20, 30, 50, 100, 150, 200],
  fuels: { petrol: "benzin", diesel: "diesel", hybrid: "hybrid", electric: "elektro", lpg: "lpg" },
  gearboxes: { manual: "manuell", automatic: "automatik" },
};

// locationId comes from a previous search run (the browser can't look it up itself).
export function kleinanzeigen(q, locationId) {
  if (q.location.country !== "DE") return { error: "Kleinanzeigen only covers Germany" };
  const notes = [];
  const [radius, note] = snapRadius(q.location.radius_km, KA.radii);
  if (note) notes.push(note);

  const filters = { "autos.marke_s": slugify(q.make, "_") };
  if (q.model) filters["autos.model_s"] = slugify(q.model, "_");
  const years = span(q.year, ",");
  if (years) filters["autos.ez_i"] = years;
  const km = span(q.mileage_km, ",");
  if (km) filters["autos.km_i"] = km;
  if (q.fuel?.length === 1) filters["autos.fuel_s"] = KA.fuels[q.fuel[0]];
  else if (q.fuel?.length) notes.push("only one fuel type can be filtered; showing all fuels");
  if (q.gearbox?.length === 1) filters["autos.shift_s"] = KA.gearboxes[q.gearbox[0]];
  else if (q.gearbox?.length) notes.push("only one gearbox can be filtered; showing all gearboxes");

  const segments = [q.location.zip];
  const price = span(q.price_eur, ":");
  if (price) segments.push(`preis:${price}`);
  const filterPart = Object.keys(filters)
    .sort()
    .map((k) => `+${k}:${encodeURIComponent(filters[k])}`)
    .join("");
  const location = locationId ? `l${locationId}` : "";
  if (!locationId) notes.push("run one search to pin the location; until then the radius is ignored");
  segments.push(`c216${location}r${radius}${filterPart}`);
  return { url: `${KA.url}/s-autos/${segments.join("/")}`, notes };
}

// ---------- Romania (whole country)

const AUTOVIT_FUELS = {
  petrol: ["petrol"],
  diesel: ["diesel"],
  hybrid: ["hybrid", "plugin-hybrid"],
  electric: ["electric"],
  lpg: ["petrol-lpg"],
};

export function autovit(q) {
  const path = ["https://www.autovit.ro/autoturisme", slugify(q.make, "-"), q.model ? slugify(q.model, "-") : null]
    .filter(Boolean)
    .join("/");
  const params = new URLSearchParams();
  addRanges(params, [["year", q.year], ["mileage", q.mileage_km], ["price", q.price_eur]]);
  (q.fuel || []).flatMap((f) => AUTOVIT_FUELS[f]).forEach((v, i) => params.append(`search[filter_enum_fuel_type][${i}]`, v));
  if (q.gearbox?.length === 1) params.append("search[filter_enum_gearbox]", q.gearbox[0]);
  return { url: withQuery(path, params), notes: [] };
}

export function olx(q) {
  const path = `https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/${slugify(q.make, "-")}/`;
  const params = new URLSearchParams();
  if (q.model) params.append("search[filter_enum_model][0]", slugify(q.model, "-"));
  addRanges(params, [["year", q.year], ["price", q.price_eur]]);
  const notes = q.fuel?.length || q.gearbox?.length || q.mileage_km?.max != null ? ["set fuel, gearbox and km on the site"] : [];
  return { url: withQuery(path, params), notes };
}

const PUBLI24_FUELS = { petrol: "benzina", diesel: "diesel" };

export function publi24(q) {
  const parts = ["https://www.publi24.ro/anunturi/auto-moto/masini-second-hand", slugify(q.make, "-")];
  if (q.model) parts.push(slugify(q.model, "-"));
  const params = new URLSearchParams();
  if (q.fuel?.length === 1 && PUBLI24_FUELS[q.fuel[0]]) params.append("carfueltype", PUBLI24_FUELS[q.fuel[0]]);
  if (q.gearbox?.length === 1 && q.gearbox[0] === "automatic") params.append("gearname", "automata");
  return { url: withQuery(`${parts.join("/")}/`, params), notes: ["set years, price and km on the site"] };
}

export function autoUncleRo(q) {
  const parts = ["https://www.autouncle.ro/ro/masini-second-hand", encodeURIComponent(q.make.replaceAll(" ", "-"))];
  if (q.model) parts.push(encodeURIComponent(q.model.replaceAll(" ", "-")));
  return { url: parts.join("/"), notes: ["set years, price and km on the site"] };
}

export function buildLinks(q, { mobileIds, kaLocationId } = {}) {
  const builders = {
    mobile_de: () => mobileDe(q, mobileIds),
    autoscout24: () => autoScout24(q),
    kleinanzeigen: () => kleinanzeigen(q, kaLocationId),
    autovit: () => autovit(q),
    olx_ro: () => olx(q),
    publi24: () => publi24(q),
    autouncle_ro: () => autoUncleRo(q),
  };
  const keys = q.sites?.length ? q.sites : Object.keys(SITES);
  return keys.filter((site) => builders[site]).map((site) => ({ site, ...SITES[site], ...builders[site]() }));
}
