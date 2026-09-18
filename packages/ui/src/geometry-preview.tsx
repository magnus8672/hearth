import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export default function GeometryPreview({ id }: { id: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const element = host.current!;
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
    scene.add(new THREE.HemisphereLight(0xffffff, 0x665544, 2.4));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(3, 5, 4); scene.add(light);
    const resize = new ResizeObserver(() => {
      const width = element.clientWidth;
      renderer.setSize(width, 360, false); camera.aspect = width / 360; camera.updateProjectionMatrix();
    }); resize.observe(element);
    const manager = new THREE.LoadingManager();
    manager.onError = () => { if (!disposed) setError('A model texture could not be loaded. Download the GLB to inspect it in your editor.'); };
    // The server validates self-contained GLBs. Defense in depth: even a bad
    // asset cannot make the preview fetch remote textures or arbitrary URLs.
    manager.setURLModifier(url => { if (!url.startsWith('blob:')) throw new Error('External model resource blocked.'); return url; });
    const clean = (object: THREE.Object3D) => object.traverse(child => {
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
          for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose();
          material.dispose();
        }
      }
    });
    fetch(`/api/v1/geometry/${id}/model`, { credentials: 'same-origin', cache: 'no-store', signal: abort.signal })
      .then(response => { if (!response.ok) throw new Error('Model unavailable.'); return response.arrayBuffer(); })
      .then(bytes => new GLTFLoader(manager).parseAsync(bytes, ''))
      .then(model => {
        if (disposed) { clean(model.scene); return; }
        const box = new THREE.Box3().setFromObject(model.scene);
        const size = box.getSize(new THREE.Vector3()); const center = box.getCenter(new THREE.Vector3());
        const scale = 2 / Math.max(size.x, size.y, size.z, .001);
        model.scene.position.copy(center.multiplyScalar(-scale)); model.scene.scale.setScalar(scale);
        scene.add(model.scene);
      }).catch(reason => { if (!disposed) setError(reason.message || 'Preview unavailable. Download the GLB to inspect it.'); });
    renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
    return () => { disposed = true; abort.abort(); resize.disconnect(); renderer.setAnimationLoop(null); controls.dispose(); clean(scene); renderer.dispose(); renderer.domElement.remove(); };
  }, [id]);
  return <><div ref={host} className="geometry-preview" role="img" aria-label="Interactive preview of your generated 3D model" />{error && <p role="alert">{error}</p>}<p className="small-copy">Drag to orbit · scroll to zoom · right-drag to pan. Download the GLB for use in your 3D editor.</p></>;
}
