import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { disposeGeometry, loadGeometry } from './geometry-assets';
import { defaultLighting, lightDirection, lightPresets } from './geometry-lighting';

export default function GeometryPreview({ id }: { id: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  const [lighting, setLighting] = useState(defaultLighting);
  const lights = useRef<{ key: THREE.DirectionalLight; fill: THREE.AmbientLight } | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!lights.current) return;
    lights.current.key.position.set(...lightDirection(lighting.azimuth, lighting.elevation)).multiplyScalar(5);
    lights.current.key.intensity = lighting.intensity; lights.current.fill.intensity = lighting.fill;
  }, [lighting]);
  useEffect(() => {
    const element = host.current!; setError(''); setLoaded(false);
    const abort = new AbortController();
    let disposed = false;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
    catch { setError('3D preview needs WebGL. You can still download the GLB.'); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, .01, 100);
    camera.position.set(2, 1.4, 2.5);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.minDistance = .6;
    controls.maxDistance = 8;
    const fill = new THREE.AmbientLight(0xffffff, defaultLighting.fill); scene.add(fill);
    const light = new THREE.DirectionalLight(0xffffff, 3);
    // Both source and target share the camera frame so direction labels match
    // the viewport through orbit, pan and zoom (including corner presets).
    light.position.set(...lightDirection(defaultLighting.azimuth, defaultLighting.elevation)).multiplyScalar(5);
    camera.add(light, light.target); scene.add(camera);
    lights.current = { key: light, fill };
    const resize = new ResizeObserver(() => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      renderer.setSize(width, height, false); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix();
    }); resize.observe(element);
    loadGeometry(id, abort.signal)
      .then(model => {
        if (disposed) { disposeGeometry(model.scene); return; }
        const box = new THREE.Box3().setFromObject(model.scene);
        const size = box.getSize(new THREE.Vector3()); const center = box.getCenter(new THREE.Vector3());
        const scale = 2 / Math.max(size.x, size.y, size.z, .001);
        model.scene.position.copy(center.multiplyScalar(-scale)); model.scene.scale.setScalar(scale);
        scene.add(model.scene); setLoaded(true);
      }).catch(reason => { if (!disposed) setError(reason.message || 'Preview unavailable. Download the GLB to inspect it.'); });
    renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
    return () => { disposed = true; abort.abort(); lights.current = null; resize.disconnect(); renderer.setAnimationLoop(null); controls.dispose(); disposeGeometry(scene); renderer.dispose(); renderer.domElement.remove(); };
  }, [id]);
  const preset = lightPresets.find(item => Math.abs(item.azimuth - lighting.azimuth) < .01 && Math.abs(item.elevation - lighting.elevation) < .01);
  const select = (name: string) => { const selected = lightPresets.find(item => item.name === name); if (selected) setLighting(current => ({ ...current, azimuth: selected.azimuth, elevation: selected.elevation })); };
  return <><div ref={host} className="geometry-preview" role="img" aria-label="Interactive preview of your generated 3D model" />{error && <p role="alert">{error}</p>}{!error && !loaded && <p role="status">Loading 3D preview…</p>}
    <fieldset className="geometry-lighting" disabled={!loaded}><legend>Preview lighting</legend>
      <div className="target-actions">{['Top', 'Bottom', 'Front', 'Back', 'Left', 'Right'].map(name => <button type="button" className="quiet-button" key={name} aria-pressed={preset?.name === name} onClick={() => select(name)}>{name}</button>)}</div>
      <div className="geometry-lighting-controls">
        <label>Light direction<select value={preset?.name || ''} onChange={event => select(event.target.value)}><option value="" disabled>Custom direction</option>{lightPresets.map(item => <option key={item.name}>{item.name}</option>)}</select></label>
        <label>Direction around view · {Math.round(lighting.azimuth)}°<input aria-label="Light azimuth" type="range" min="-180" max="180" step="1" value={lighting.azimuth} onChange={event => setLighting(current => ({ ...current, azimuth: Number(event.target.value) }))} /></label>
        <label>Height · {Math.round(lighting.elevation)}°<input aria-label="Light elevation" type="range" min="-90" max="90" step="1" value={lighting.elevation} onChange={event => setLighting(current => ({ ...current, elevation: Number(event.target.value) }))} /></label>
        <label>Light brightness · {lighting.intensity.toFixed(1)}<input aria-label="Light brightness" type="range" min="0" max="8" step="0.1" value={lighting.intensity} onChange={event => setLighting(current => ({ ...current, intensity: Number(event.target.value) }))} /></label>
        <label>Ambient fill · {lighting.fill.toFixed(1)}<input aria-label="Ambient fill" type="range" min="0" max="4" step="0.1" value={lighting.fill} onChange={event => setLighting(current => ({ ...current, fill: Number(event.target.value) }))} /></label>
      </div><button type="button" className="quiet-button" onClick={() => setLighting(defaultLighting)}>Reset lighting</button>
      <p className="small-copy">Directions follow your view: Right lights from screen-right, Top from above, and Front from your side of the model. The light follows as you orbit. Preview lighting does not change your downloads.</p>
    </fieldset><p className="small-copy">Drag to orbit · scroll to zoom · right-drag to pan · drag the lower edge to resize.</p></>;
}
