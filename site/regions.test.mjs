import test from "node:test";
import assert from "node:assert/strict";
import { inRegion, regionById } from "./regions.mjs";

test("regional windows include representative thermal monitoring locations", () => {
  for (const [id, latitude, longitude] of [
    ["india", 22.5, 82.5], ["middle-east", 29.3, 47.5],
    ["north-america", 56, -110], ["south-america", -3, -60],
    ["europe", 38, 23], ["southeast-asia", -2, 113],
    ["africa", -10, 25], ["australia", -33, 151],
  ]) {
    assert.equal(inRegion({ latitude, longitude }, id), true, id);
    assert.equal(inRegion({ latitude, longitude }, "global"), true);
  }
  assert.equal(inRegion({ latitude: 22.5, longitude: 82.5 }, "south-america"), false);
});

test("invalid coordinates cannot appear as global or regional detections", () => {
  for (const [latitude, longitude] of [[NaN, 0], [0, Infinity], [91, 0], [0, -181], [null, 0], [0, "82"]]) {
    assert.equal(inRegion({ latitude, longitude }, "global"), false);
  }
  assert.equal(inRegion({ latitude: 0, longitude: 0 }, "global"), true);
  assert.equal(inRegion({ latitude: -90, longitude: -180 }, "global"), true);
  assert.equal(inRegion({ latitude: 90, longitude: 180 }, "global"), true);
  assert.equal(regionById("unrecognized").id, "india");
});
