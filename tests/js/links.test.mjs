// Run with: node --test tests/js/
// Expected URLs match the Python link builders (tests/test_sites.py, `carfinder links`).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  autoScout24,
  autoUncleRo,
  autovit,
  buildLinks,
  kleinanzeigen,
  mobileDe,
  olx,
  publi24,
  slugify,
  snapRadius,
} from "../../site/js/links.js";

const query = {
  make: "Mazda",
  model: "CX-3",
  year: { min: 2015, max: 2017 },
  mileage_km: { min: null, max: 160000 },
  price_eur: { min: 8000, max: 10000 },
  fuel: ["petrol"],
  gearbox: [],
  location: { zip: "93339", country: "DE", radius_km: 200 },
};

test("slugify matches Python", () => {
  assert.equal(slugify("CX-3", "-"), "cx-3");
  assert.equal(slugify("Mercedes-Benz", "_"), "mercedes_benz");
  assert.equal(slugify("Škoda", "-"), "skoda");
});

test("snapRadius rounds up", () => {
  assert.deepEqual(snapRadius(200, [50, 100, 200]), [200, null]);
  assert.equal(snapRadius(120, [50, 100, 200])[0], 200);
});

test("mobile.de", () => {
  const place = { latLng: "48.9667,11.6833", name: "Riedenburg, Bayern" };
  // Same URL as the Python builder; location format copied from a real mobile.de search.
  assert.equal(
    mobileDe(query, { make_id: "16800", model_id: "34" }, place).url,
    "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&s=Car&vc=Car&dam=false" +
      "&ms=16800%3B34%3B%3B&fr=2015%3A2017&ml=%3A160000&p=8000%3A10000&ft=PETROL&cn=DE" +
      "&ll=48.9667%2C11.6833&rd=200&gn=Riedenburg%2C+Bayern",
  );
  assert.ok(mobileDe(query, { make_id: "16800", model_id: "34" }, null).notes.some((n) => n.includes("location")));
  assert.ok(mobileDe(query, null).error);
});

test("AutoScout24", () => {
  assert.equal(
    autoScout24(query).url,
    "https://www.autoscout24.de/lst/mazda/cx-3?atype=C&cy=D&damaged_listing=exclude&ustate=N%2CU" +
      "&sort=standard&desc=0&fregfrom=2015&fregto=2017&kmto=160000&pricefrom=8000&priceto=10000" +
      "&fuel=B&zip=93339&zipr=200",
  );
});

test("Kleinanzeigen with location", () => {
  assert.equal(
    kleinanzeigen(query, "6234").url,
    "https://www.kleinanzeigen.de/s-autos/93339/preis:8000:10000/c216l6234r200" +
      "+autos.ez_i:2015%2C2017+autos.fuel_s:benzin+autos.km_i:%2C160000" +
      "+autos.marke_s:mazda+autos.model_s:cx_3",
  );
});

test("Kleinanzeigen without location warns", () => {
  const link = kleinanzeigen(query, null);
  assert.match(link.url, /\/c216r200\+/);
  assert.ok(link.notes.some((n) => n.includes("location")));
});

test("buildLinks respects site selection", () => {
  const links = buildLinks({ ...query, sites: ["autoscout24"] });
  assert.deepEqual(links.map((l) => l.site), ["autoscout24"]);
});

// Same query as the Python URLs these were generated from (`Site(...).link(profile).url`).
const ro = { ...query, fuel: ["petrol", "hybrid"], gearbox: ["automatic"] };
const anyModel = { ...ro, model: null };

test("Autovit", () => {
  const params =
    "?search%5Bfilter_float_year%3Afrom%5D=2015&search%5Bfilter_float_year%3Ato%5D=2017" +
    "&search%5Bfilter_float_mileage%3Ato%5D=160000&search%5Bfilter_float_price%3Afrom%5D=8000" +
    "&search%5Bfilter_float_price%3Ato%5D=10000&search%5Bfilter_enum_fuel_type%5D%5B0%5D=petrol" +
    "&search%5Bfilter_enum_fuel_type%5D%5B1%5D=hybrid&search%5Bfilter_enum_fuel_type%5D%5B2%5D=plugin-hybrid" +
    "&search%5Bfilter_enum_gearbox%5D=automatic";
  assert.equal(autovit(ro).url, `https://www.autovit.ro/autoturisme/mazda/cx-3${params}`);
  assert.equal(autovit(anyModel).url, `https://www.autovit.ro/autoturisme/mazda${params}`);
});

test("OLX.ro", () => {
  assert.equal(
    olx(ro).url,
    "https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/mazda/?search%5Bfilter_enum_model%5D%5B0%5D=cx-3" +
      "&search%5Bfilter_float_year%3Afrom%5D=2015&search%5Bfilter_float_year%3Ato%5D=2017" +
      "&search%5Bfilter_float_price%3Afrom%5D=8000&search%5Bfilter_float_price%3Ato%5D=10000",
  );
});

test("Publi24 and AutoUncle.ro", () => {
  assert.equal(publi24(ro).url, "https://www.publi24.ro/anunturi/auto-moto/masini-second-hand/mazda/cx-3/?gearname=automata");
  assert.equal(publi24(anyModel).url, "https://www.publi24.ro/anunturi/auto-moto/masini-second-hand/mazda/?gearname=automata");
  assert.equal(autoUncleRo(ro).url, "https://www.autouncle.ro/ro/masini-second-hand/Mazda/CX-3");
  assert.equal(autoUncleRo(anyModel).url, "https://www.autouncle.ro/ro/masini-second-hand/Mazda");
});

test("all models on German sites", () => {
  assert.match(autoScout24(anyModel).url, /^https:\/\/www\.autoscout24\.de\/lst\/mazda\?/);
  assert.match(mobileDe(anyModel, { make_id: "16800" }).url, /ms=16800%3B%3B%3B/);
  assert.doesNotMatch(kleinanzeigen(anyModel, "6234").url, /model_s/);
});

test("Autovit around a Romanian city", () => {
  const q = { ...query, year: { min: 2015 }, mileage_km: {}, price_eur: {}, fuel: [], ro_location: { city: "cluj-napoca", radius_km: 60 } };
  const link = autovit(q);
  // Same URL as the Python builder for this query.
  assert.equal(link.url, "https://www.autovit.ro/autoturisme/mazda/cx-3/cluj-napoca?search%5Bdist%5D=75&search%5Bfilter_float_year%3Afrom%5D=2015");
  assert.deepEqual(link.notes, ["radius 60 km not offered, using 75 km"]);
  assert.ok(olx(q).notes.includes("pick the city on the site"));
});
