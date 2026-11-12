import { CONFIG } from './config.js';
import { computeLongSide, sizeFor, randomVelocity, placeRandomly, stepPhoto, clamp } from './cloud.js';
import { FeaturedController } from './featured.js';

const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => t * t * (3 - 2 * t);   // smoothstep

export class Scene {
  constructor(cloudLayer, featuredLayer) {
    this.cloudLayer = cloudLayer;
    this.featuredLayer = featuredLayer;
    this.photos = [];
    this.controller = new FeaturedController(this.photos, CONFIG);
    this.vw = innerWidth; this.vh = innerHeight;
    this.last = performance.now();
    requestAnimationFrame((t) => this._frame(t));
    let timer;
    addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(() => this._resize(), 100); });
  }

  /** items: [{el, aspect}] with already-loaded <img> elements. */
  setPhotos(items) {
    this.cloudLayer.replaceChildren();
    this.featuredLayer.replaceChildren();
    this.photos.length = 0;
    for (const { el, aspect } of items) {
      el.className = 'photo';
      el.style.opacity = CONFIG.bgOpacity;
      this.photos.push({
        el, aspect, w: 0, h: 0, x: 0, y: 0, ...randomVelocity(CONFIG.speedRange),
        state: 'background', depth: 0, slot: 0,
      });
      this.cloudLayer.appendChild(el);
    }
    this._layout(true);
    Object.assign(this.controller, { phase: 'background', timer: 0, queue: [], pair: [], last: [],
      waitFor: CONFIG.startDelaySeconds });
  }

  _layout(initial) {
    this.vw = innerWidth; this.vh = innerHeight;
    const L = computeLongSide(this.photos.length, this.vw, this.vh, CONFIG.coverage);
    for (const p of this.photos) {
      Object.assign(p, sizeFor(p.aspect, L));
      p.el.style.width = p.w + 'px';
      p.el.style.height = p.h + 'px';
      if (initial) placeRandomly(p, this.vw, this.vh);
      p.x = clamp(p.x, 0, Math.max(0, this.vw - p.w));
      p.y = clamp(p.y, 0, Math.max(0, this.vh - p.h));
    }
  }

  _resize() { this._layout(false); }

  _frame(now) {
    const dt = Math.min((now - this.last) / 1000, 0.05);   // frame-rate independent
    this.last = now;
    // Background physics runs for every photo, always. Featured photos keep a
    // simulated "home" position so the return trip lands exactly on it.
    for (const p of this.photos) stepPhoto(p, dt, this.vw, this.vh);
    this.controller.update(dt);
    for (const p of this.photos) this._render(p);
    requestAnimationFrame((t) => this._frame(t));
  }

  _render(p) {
    const inFront = p.state !== 'background';
    const layer = inFront ? this.featuredLayer : this.cloudLayer;
    if (p.el.parentNode !== layer) layer.appendChild(p.el);

    if (!inFront) {
      p.el.style.transform = `translate(${p.x}px, ${p.y}px)`;
      p.el.style.opacity = CONFIG.bgOpacity;
      return;
    }
    const e = ease(p.depth);
    const targetScale = Math.min(
      (CONFIG.foregroundWidthFrac * this.vw) / p.w,
      (CONFIG.foregroundHeightFrac * this.vh) / p.h);
    const cx = this.vw * (p.slot === 0 ? 0.27 : 0.73), cy = this.vh * 0.5;
    const x = lerp(p.x, cx - p.w / 2, e);
    const y = lerp(p.y, cy - p.h / 2, e);
    p.el.style.transform = `translate(${x}px, ${y}px) scale(${lerp(1, targetScale, e)})`;
    p.el.style.opacity = lerp(CONFIG.bgOpacity, CONFIG.foregroundOpacity, e);
  }
}
