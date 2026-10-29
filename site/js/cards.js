// One car card: photo gallery, price, specs, warnings and the reasons behind the score.

import { FLAGS, el, euro, num, timeAgo } from "./dom.js";
import { SITES } from "./links.js";

const PRICE_LABELS = {
  "top-price": ["Top price", "good"],
  "good-price": ["Good price", "good"],
  "fair-price": ["Fair price", "ok"],
  "somewhat-expensive": ["A bit pricey", "warn"],
  expensive: ["Expensive", "bad"],
};

export function specsLine(l) {
  return [
    l.model,
    l.first_registration || l.year,
    l.mileage_km != null ? `${num.format(l.mileage_km)} km` : null,
    l.power_hp ? `${l.power_hp} hp` : null,
    l.gearbox,
    l.fuel,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function placeLine(l) {
  return [[l.zip, l.city].filter(Boolean).join(" "), l.distance_km != null ? `${l.distance_km} km away` : null]
    .filter(Boolean)
    .join(" · ");
}

function gallery(l, starButton) {
  const images = l.images || [];
  let index = 0;
  const img = images.length
    ? el("img", { src: images[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" })
    : null;
  const counter = el("span", { class: "photo-count" }, images.length > 1 ? `1/${images.length}` : "");
  const step = (delta) => (event) => {
    event.preventDefault();
    index = (index + delta + images.length) % images.length;
    img.src = images[index];
    counter.textContent = `${index + 1}/${images.length}`;
  };
  const scoreClass = l.score >= 70 ? "good" : l.score >= 50 ? "ok" : "low";
  return el(
    "div",
    { class: "photo" },
    el(
      "a",
      { href: l.url, target: "_blank", rel: "noopener", "aria-label": `Open ${l.title}` },
      img || el("span", { class: "no-photo" }, "No photo"),
    ),
    images.length > 1
      ? [
          el("button", { type: "button", class: "nav prev", "aria-label": "Previous photo", onclick: step(-1) }, "‹"),
          el("button", { type: "button", class: "nav next", "aria-label": "Next photo", onclick: step(1) }, "›"),
          counter,
        ]
      : null,
    starButton,
    l.score != null ? el("span", { class: `score ${scoreClass}` }, l.score) : null,
  );
}

/**
 * opts: { isNew, starred, onStar(listing) } — onStar omitted for read-only views.
 */
export function card(l, opts = {}) {
  const label = PRICE_LABELS[l.price_label];
  const history = l.price_history || [];
  const firstPrice = history.length > 1 ? history[0].price_eur : null;
  const star = opts.onStar
    ? el(
        "button",
        {
          type: "button",
          class: `star${opts.starred ? " on" : ""}`,
          title: opts.starred ? "Remove from shortlist" : "Add to shortlist",
          "aria-pressed": opts.starred ? "true" : "false",
          onclick: () => opts.onStar(l),
        },
        opts.starred ? "★" : "☆",
      )
    : null;

  return el(
    "article",
    { class: "car" },
    gallery(l, star),
    el(
      "div",
      { class: "body" },
      el(
        "div",
        { class: "badges" },
        el("span", { class: "badge site" }, `${FLAGS[l.country || "DE"]} ${SITES[l.source]?.name || l.source}`),
        opts.isNew ? el("span", { class: "badge new" }, "NEW") : null,
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
      el("p", { class: "specs" }, specsLine(l)),
      el("p", { class: "muted small" }, placeLine(l), l.seller_name ? ` · ${l.seller_name}` : ""),
      l.flags?.length ? el("ul", { class: "flags" }, l.flags.map((f) => el("li", {}, f))) : null,
      l.also_on?.length
        ? el(
            "p",
            { class: "small" },
            "Also on ",
            l.also_on.map((o, i) => [i ? ", " : "", el("a", { href: o.url, target: "_blank", rel: "noopener" }, o.name)]),
          )
        : null,
      l.score_parts?.length
        ? el(
            "details",
            { class: "why" },
            el("summary", {}, `Why ${l.score}?`),
            el("ul", {}, el("li", { class: "muted" }, "Starts at 40"), l.score_parts.map((p) => el("li", {}, p))),
          )
        : null,
      opts.extra || null,
      l.first_seen ? el("p", { class: "muted small" }, `First seen ${timeAgo(l.first_seen)}`) : null,
    ),
  );
}
