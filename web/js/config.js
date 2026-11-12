export const CONFIG = {
  bgOpacity: 0.5,
  // Opacity of featured photos once fully in the foreground.
  // 1.0 = "prominent" (opacity rises as they come forward).
  // 0.0 = literal spec wording (they fade out as they come forward).
  foregroundOpacity: 1.0,
  holdSeconds: 30,         // time spent in the foreground
  transitionSeconds: 2.5,  // forward and backward travel time
  gapSeconds: 1.0,         // pause between returning and picking the next pair
  startDelaySeconds: 2.0,
  maxPhotos: 60,           // photos placed in the cloud (keeps memory sane)
  coverage: 0.5,           // approx. fraction of viewport covered by the cloud
  speedRange: [14, 38],    // px per second
  foregroundWidthFrac: 0.42,
  foregroundHeightFrac: 0.72,
};
