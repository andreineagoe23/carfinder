// Run with: node --test tests/js/
// Expected URLs match the Python link builders (tests/test_sites.py, `carfinder links`).
import assert from "node:assert/strict";
import { test } from "node:test";

import { autoScout24, buildLinks, kleinanzeigen, mobileDe, slugify, snapRadius } from "../../site/js/links.js";

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
  assert.equal(
    mobileDe(query, { make_id: "16800", model_id: "34" }).url,
    "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&s=Car&vc=Car&dam=false" +
      "&ms=16800%3B34%3B%3B&fr=2015%3A2017&ml=%3A160000&p=8000%3A10000&ft=PETROL&zip=93339&zipr=200&cn=DE",
  );
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
