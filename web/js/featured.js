// Foreground lifecycle. Explicit states, per photo and for the pair:
//   background -> forward -> foreground -> backward -> background
// photo.depth is 0 (cloud plane) .. 1 (fully in front).
const shuffle = (arr) => {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

export class FeaturedController {
  constructor(photos, cfg) {
    this.photos = photos;
    this.cfg = cfg;
    this.phase = 'background';
    this.timer = 0;
    this.waitFor = cfg.startDelaySeconds;
    this.queue = [];
    this.pair = [];
    this.last = [];
  }

  _refill() {
    const fresh = shuffle(this.photos.filter((p) => !this.queue.includes(p)));
    // Photos from the previous pair go to the back, so pairs rarely repeat.
    fresh.sort((a, b) => this.last.includes(a) - this.last.includes(b));
    this.queue = this.queue.concat(fresh);
  }

  _pick() {
    if (this.queue.length < 2) this._refill();
    this.pair = this.queue.splice(0, 2);
    this.last = this.pair;
    this.pair.forEach((p, i) => { p.slot = i; });
  }

  _set(phase, depth) {
    this.phase = phase;
    this.timer = 0;
    this.pair.forEach((p) => { p.state = phase; if (depth !== undefined) p.depth = depth; });
  }

  update(dt) {
    if (this.photos.length < 2) return;
    const { transitionSeconds: T, holdSeconds, gapSeconds } = this.cfg;
    this.timer += dt;

    switch (this.phase) {
      case 'background':
        if (this.timer >= this.waitFor) { this._pick(); this._set('forward'); }
        break;
      case 'forward': {
        const t = Math.min(this.timer / T, 1);
        this.pair.forEach((p) => { p.depth = t; });
        if (t >= 1) this._set('foreground', 1);
        break;
      }
      case 'foreground':
        if (this.timer >= holdSeconds) this._set('backward');
        break;
      case 'backward': {
        const t = 1 - Math.min(this.timer / T, 1);
        this.pair.forEach((p) => { p.depth = t; });
        if (t <= 0) {
          this._set('background', 0);
          this.pair = [];
          this.waitFor = gapSeconds;
          this.timer = 0;
        }
        break;
      }
    }
  }
}
