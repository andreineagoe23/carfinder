// Shortlist: star cars, add notes, and share the list (link or WhatsApp) with whoever goes
// to see them. Stored in this browser; a shared link carries the cars inside the URL itself.

import { placeLine, specsLine } from "./cards.js";
import { FLAGS, el, euro, store } from "./dom.js";

const KEY = "shortlist";

export const shortlist = {
  items() {
    return store.get(KEY, []);
  },
  has(key) {
    return this.items().some((item) => item.key === key);
  },
  toggle(listing) {
    const items = this.items();
    const key = keyOf(listing);
    const next = items.some((i) => i.key === key)
      ? items.filter((i) => i.key !== key)
      : [...items, { key, listing: slim(listing), note: "", added_at: new Date().toISOString() }];
    store.set(KEY, next);
    return next;
  },
  setNote(key, note) {
    store.set(KEY, this.items().map((i) => (i.key === key ? { ...i, note } : i)));
  },
  remove(key) {
    store.set(KEY, this.items().filter((i) => i.key !== key));
  },
};

export function keyOf(listing) {
  return `${listing.source}:${listing.source_id}`;
}

// What a shortlisted car keeps: enough to show a card without the original search.
function slim(l) {
  const keep = [
    "source", "source_id", "country", "url", "title", "model", "price_eur", "listed_price", "listed_currency",
    "old_price_eur", "negotiable", "price_label", "mileage_km", "year", "first_registration", "fuel", "gearbox",
    "power_hp", "zip", "city", "distance_km", "seller_type", "seller_name", "images", "flags", "score", "score_parts",
  ];
  return Object.fromEntries(keep.filter((k) => l[k] != null).map((k) => [k, l[k]]));
}

// ---------- sharing

const SHORT = {
  source: "s", source_id: "id", country: "co", url: "u", title: "t", model: "m", price_eur: "p",
  mileage_km: "k", year: "y", first_registration: "r", fuel: "f", gearbox: "g", power_hp: "h",
  zip: "z", city: "c", seller_type: "st", images: "i", note: "n",
};
const LONG = Object.fromEntries(Object.entries(SHORT).map(([k, v]) => [v, k]));

async function pipe(bytes, stream) {
  const body = new Blob([bytes]).stream().pipeThrough(stream);
  return new Uint8Array(await new Response(body).arrayBuffer());
}

function toBase64Url(bytes) {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function fromBase64Url(text) {
  const binary = atob(text.replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

export async function shareLink(items) {
  const compact = items.map(({ listing, note }) => {
    const out = {};
    for (const [long, short] of Object.entries(SHORT)) {
      const value = long === "note" ? note : long === "images" ? listing.images?.slice(0, 1) : listing[long];
      if (value != null && value !== "" && !(Array.isArray(value) && !value.length)) out[short] = value;
    }
    return out;
  });
  const packed = await pipe(new TextEncoder().encode(JSON.stringify(compact)), new CompressionStream("deflate-raw"));
  return `${location.origin}${location.pathname}#list=${toBase64Url(packed)}`;
}

export async function readShared(encoded) {
  const bytes = await pipe(fromBase64Url(encoded), new DecompressionStream("deflate-raw"));
  const compact = JSON.parse(new TextDecoder().decode(bytes));
  return compact.map((entry) => {
    const listing = {};
    let note = "";
    for (const [short, value] of Object.entries(entry)) {
      if (LONG[short] === "note") note = String(value);
      else if (LONG[short]) listing[LONG[short]] = value;
    }
    return { key: keyOf(listing), listing, note };
  });
}

export function whatsappText(items, link) {
  const lines = [`🚗 Cars to look at (${items.length})`, ""];
  items.forEach(({ listing: l, note }, i) => {
    lines.push(`${i + 1}. ${l.title} — ${euro.format(l.price_eur)}`);
    lines.push(`   ${specsLine(l)}`);
    const place = placeLine(l);
    if (place) lines.push(`   📍 ${FLAGS[l.country || "DE"]} ${place}`);
    if (note) lines.push(`   📝 ${note}`);
    lines.push(`   ${l.url}`, "");
  });
  if (link) lines.push(`All of them with photos and a viewing checklist: ${link}`);
  return lines.join("\n");
}

// ---------- viewing checklist (for whoever goes to see the car in Germany)

const CHECKLIST = [
  [
    "Before you go",
    [
      "Call and ask: is it still available (noch verfügbar?), accident-free (unfallfrei?), how many owners (Vorbesitzer), when is the next TÜV (HU)?",
      "Ask for the VIN (FIN) and run a vehicle history check on it.",
      "Never pay a deposit for a car you haven't seen.",
    ],
  ],
  [
    "Papers",
    [
      "Both registration papers: Zulassungsbescheinigung Teil I and Teil II (the “Fahrzeugbrief”). No Teil II, no deal.",
      "The seller's name on Teil II matches their ID card.",
      "The VIN on the papers matches the car (windscreen corner and door pillar).",
      "Service book (Serviceheft / Scheckheft) and invoices; latest TÜV report. Does the mileage add up across them?",
      "Ask for the COC (certificate of conformity) — it makes registration in Romania (RAR) easier.",
    ],
  ],
  [
    "The car",
    [
      "Rust: wheel arches, sills (Schweller), door bottoms, boot floor.",
      "Accident signs: paint colour differences, uneven panel gaps, overspray on rubber seals.",
      "Tyres: even wear and enough tread; note the brake discs.",
      "Start it cold: no smoke, no rattles, all warning lights go out.",
      "Test drive: smooth gear changes, brakes pull straight, no steering pull, air conditioning cold.",
    ],
  ],
  [
    "Buying",
    [
      "Written contract (Kaufvertrag) — the ADAC template is standard. Write in the km, “unfallfrei” if the seller confirms it, and the handover date and time.",
      "Pay by bank transfer at handover or at the seller's bank; avoid carrying large cash.",
      "To drive it to Romania: export plates (Ausfuhrkennzeichen, with insurance) from the local registration office — bring both registration papers, the contract and your ID.",
    ],
  ],
];

export function checklist() {
  return el(
    "section",
    { class: "card checklist" },
    el("h2", {}, "Viewing checklist"),
    el("p", { class: "muted small" }, "General tips for buying a used car in Germany — not legal advice."),
    CHECKLIST.map(([title, items]) =>
      el(
        "div",
        { class: "check-group" },
        el("h3", {}, title),
        el("ul", {}, items.map((text) => el("li", {}, el("label", {}, el("input", { type: "checkbox" }), " ", text)))),
      ),
    ),
  );
}
