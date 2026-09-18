import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export async function loadGeometry(id: string, signal?: AbortSignal) {
  const manager = new THREE.LoadingManager();
  let textureFailed = false;
  manager.onError = () => { textureFailed = true; };
  manager.setURLModifier(url => {
    if (!url.startsWith('blob:')) throw new Error('External model resource blocked.');
    return url;
  });
  const response = await fetch(`/api/v1/geometry/${encodeURIComponent(id)}/model`, { credentials: 'same-origin', cache: 'no-store', signal });
  if (!response.ok) throw new Error('This model is no longer available to your account.');
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > 64 * 1024 * 1024) throw new Error('The model exceeds the supported size.');
  const model = await new GLTFLoader(manager).parseAsync(bytes, '');
  if (textureFailed) { disposeGeometry(model.scene); throw new Error('A model texture could not be loaded. Download the GLB to inspect it in your editor.'); }
  return model;
}

export function disposeGeometry(object: THREE.Object3D) {
  const textures = new Set<THREE.Texture>();
  object.traverse(child => {
    if (!(child instanceof THREE.Mesh)) return;
    child.geometry.dispose();
    for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
      material.dispose();
    }
  });
  for (const texture of textures) {
    texture.dispose();
    if (typeof ImageBitmap !== 'undefined' && texture.image instanceof ImageBitmap) texture.image.close();
  }
}
