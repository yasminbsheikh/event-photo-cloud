// Simulates the featured-photo lifecycle headlessly (no browser needed).
// Run: node tests/cycle.test.mjs
import assert from 'node:assert/strict';
import { FeaturedController } from '../web/js/featured.js';
import { CONFIG } from '../web/js/config.js';
import { stepPhoto } from '../web/js/cloud.js';

const mk = () => ({ w: 100, h: 80, x: 50, y: 50, vx: 20, vy: 15, state: 'background', depth: 0, slot: 0 });
const photos = Array.from({ length: 6 }, mk);
const ctl = new FeaturedController(photos, CONFIG);

const dt = 1 / 30, seen = [];
let prevPhase = ctl.phase, prevDepth = new Map(photos.map((p) => [p, 0])), maxJump = 0;
const transitions = [];
let tNow = 0, phaseStart = 0;

for (let i = 0; i < 30 * 200; i++) {
  photos.forEach((p) => stepPhoto(p, dt, 800, 600));
  ctl.update(dt); tNow += dt;
  const featured = photos.filter((p) => p.state !== 'background');
  assert.ok(featured.length === 0 || featured.length === 2, 'exactly 0 or 2 featured');
  assert.ok(photos.every((p) => p.x >= 0 && p.x <= 700 && p.y >= 0 && p.y <= 520), 'stays in bounds');
  for (const p of photos) { maxJump = Math.max(maxJump, Math.abs(p.depth - prevDepth.get(p))); prevDepth.set(p, p.depth); }
  if (ctl.phase !== prevPhase) {
    transitions.push([prevPhase, ctl.phase, +(tNow - phaseStart).toFixed(1)]);
    phaseStart = tNow; prevPhase = ctl.phase;
    if (ctl.phase === 'forward') seen.push(ctl.pair.slice());
  }
}
console.log(transitions.slice(0, 5).map((t) => t.join(' > ')).join('\n'));
const fg = transitions.find((t) => t[0] === 'foreground');
assert.ok(Math.abs(fg[2] - CONFIG.holdSeconds) < 0.2, 'holds ~30s');
assert.ok(maxJump < 0.05, `depth smooth (max step ${maxJump.toFixed(3)})`);
assert.ok(seen.length >= 5, 'cycle repeats');
// 6 photos => 3 pairs per full pass; no photo repeats within a pass
const firstPass = seen.slice(0, 3).flat();
assert.equal(new Set(firstPass).size, 6, 'all photos shown before any repeat');
for (let i = 1; i < seen.length; i++) assert.ok(!seen[i].some((p) => seen[i - 1].includes(p)), 'no consecutive repeats');
console.log(`OK: ${seen.length} pairs over 200 simulated seconds`);
