export const defaultLighting = { azimuth: 37, elevation: 45, intensity: 3, fill: 1.2 };
export function lightDirection(azimuth: number, elevation: number): [number, number, number] {
  const a = azimuth * Math.PI / 180, e = elevation * Math.PI / 180;
  return [Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)];
}
export const lightPresets = [-1, 0, 1].flatMap(y => [-1, 0, 1].flatMap(z => [-1, 0, 1].flatMap(x => {
  if (!x && !y && !z) return [];
  const name = [y === 1 ? 'Top' : y === -1 ? 'Bottom' : '', z === 1 ? 'Front' : z === -1 ? 'Back' : '', x === 1 ? 'Right' : x === -1 ? 'Left' : ''].filter(Boolean).join(' / ');
  return [{ name, azimuth: Math.atan2(x, z) * 180 / Math.PI, elevation: Math.atan2(y, Math.hypot(x, z)) * 180 / Math.PI }];
})));
