// Pure background-cloud logic: sizing and 2D bouncing. No DOM, no depth, no rotation.
const rand = (a, b) => a + Math.random() * (b - a);
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function computeLongSide(count, vw, vh, coverage) {
  const avgAspect = 1.4;
  const area = (vw * vh * coverage) / Math.max(count, 1);
  return clamp(Math.sqrt(area * avgAspect), 70, Math.min(vw, vh) * 0.4);
}

export function sizeFor(aspect, longSide) {
  return aspect >= 1
    ? { w: longSide, h: longSide / aspect }
    : { w: longSide * aspect, h: longSide };
}

export function randomVelocity([minSpeed, maxSpeed]) {
  const speed = rand(minSpeed, maxSpeed);
  const angle = rand(0.25, 1.32);               // avoid purely axis-aligned drift
  return {
    vx: Math.cos(angle) * speed * (Math.random() < 0.5 ? -1 : 1),
    vy: Math.sin(angle) * speed * (Math.random() < 0.5 ? -1 : 1),
  };
}

export function placeRandomly(p, vw, vh) {
  p.x = rand(0, Math.max(0, vw - p.w));
  p.y = rand(0, Math.max(0, vh - p.h));
}

/** Advance one photo by dt seconds, bouncing off the viewport edges. */
export function stepPhoto(p, dt, vw, vh) {
  const maxX = Math.max(0, vw - p.w), maxY = Math.max(0, vh - p.h);
  p.x += p.vx * dt;
  p.y += p.vy * dt;
  if (p.x < 0) { p.x = 0; p.vx = Math.abs(p.vx); }
  else if (p.x > maxX) { p.x = maxX; p.vx = -Math.abs(p.vx); }
  if (p.y < 0) { p.y = 0; p.vy = Math.abs(p.vy); }
  else if (p.y > maxY) { p.y = maxY; p.vy = -Math.abs(p.vy); }
}
