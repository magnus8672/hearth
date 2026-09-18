import * as THREE from 'three';
import { strToU8, zipSync } from 'fflate';
import { disposeGeometry, loadGeometry } from './geometry-assets';

// Convert the original scene, never the centered/scaled preview scene.
// Generated names prevent model metadata becoming OBJ directives or ZIP paths.
export async function objBundle(scene: THREE.Object3D) {
  scene.updateMatrixWorld(true);
  const files: Record<string, Uint8Array> = {};
  const lines = ['# hearth OBJ export', 'mtllib model.mtl'];
  const materials: string[] = [];
  const materialIds = new Map<THREE.Material, string>();
  let vertices = 0, uvs = 0, normals = 0, size = 0;
  const emit = (line: string) => {
    size += line.length + 1;
    if (size > 192 * 1024 * 1024) throw new Error('OBJ export exceeds 192 MB. Download the GLB or generate a simpler mesh.');
    lines.push(line);
  };
  const number = (value: number) => {
    if (!Number.isFinite(value)) throw new Error('The model contains an invalid coordinate.');
    return Number(value.toPrecision(9)).toString();
  };
  const pause = () => new Promise<void>(resolve => setTimeout(resolve, 0));
  async function materialName(source: THREE.Material) {
    const material = source as THREE.MeshStandardMaterial;
    const known = materialIds.get(material); if (known) return known;
    const name = `material_${materialIds.size}`; materialIds.set(material, name);
    const color = (material.color || new THREE.Color('white')).clone().convertLinearToSRGB();
    materials.push(`newmtl ${name}`, `Kd ${number(color.r)} ${number(color.g)} ${number(color.b)}`, `d ${number(material.opacity)}`, 'illum 2', `Pr ${number(material.roughness ?? 1)}`, `Pm ${number(material.metalness ?? 0)}`);
    for (const [kind, texture, channel, directive] of [
      ['color', material.map, -1, 'map_Kd'], ['normal', material.normalMap, -1, 'norm'],
      ['roughness', material.roughnessMap, 1, 'map_Pr'], ['metallic', material.metalnessMap, 2, 'map_Pm'],
    ] as const) {
      if (!texture) continue;
      if (texture.channel !== 0 || texture.rotation !== 0 || texture.offset.lengthSq() !== 0 || texture.repeat.x !== 1 || texture.repeat.y !== 1) throw new Error('This model uses texture coordinates OBJ cannot preserve. Download its GLB instead.');
      const canvas = document.createElement('canvas'); const image = texture.image;
      canvas.width = image.width; canvas.height = image.height;
      if (!canvas.width || !canvas.height || canvas.width > 4096 || canvas.height > 4096) throw new Error('Unsupported model texture size.');
      const context = canvas.getContext('2d'); if (!context) throw new Error('Texture export is unavailable in this browser.');
      context.drawImage(image, 0, 0);
      if (channel >= 0) {
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < pixels.data.length; i += 4) { const value = pixels.data[i + channel]; pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value; pixels.data[i + 3] = 255; }
        context.putImageData(pixels, 0, 0);
      }
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Texture export failed.')), 'image/png'));
      const file = `${name}_${kind}.png`;
      files[file] = new Uint8Array(await blob.arrayBuffer()); materials.push(`${directive} ${file}`);
      canvas.width = canvas.height = 0;
    }
    materials.push(''); return name;
  }
  const meshes: THREE.Mesh[] = [];
  scene.traverse(object => { if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh); });
  for (const [meshIndex, mesh] of meshes.entries()) {
    const geometry = mesh.geometry; const position = geometry.getAttribute('position');
    const uv = geometry.getAttribute('uv'), normal = geometry.getAttribute('normal'), color = geometry.getAttribute('color');
    if (!position) throw new Error('This model has no exportable vertices.');
    const matrix = new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld), vector = new THREE.Vector3();
    emit(`o mesh_${meshIndex}`);
    for (let i = 0; i < position.count; i++) {
      vector.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld);
      let vertex = `v ${number(vector.x)} ${number(vector.y)} ${number(vector.z)}`;
      if (color) { const c = new THREE.Color().fromBufferAttribute(color, i).convertLinearToSRGB(); vertex += ` ${number(c.r)} ${number(c.g)} ${number(c.b)}`; }
      emit(vertex);
      if (uv) emit(`vt ${number(uv.getX(i))} ${number(1 - uv.getY(i))}`);
      if (normal) { vector.fromBufferAttribute(normal, i).applyMatrix3(matrix).normalize(); emit(`vn ${number(vector.x)} ${number(vector.y)} ${number(vector.z)}`); }
      if (i % 8192 === 0) await pause();
    }
    const count = geometry.index?.count ?? position.count;
    const list = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const names: string[] = [];
    for (const material of list) names.push(await materialName(material));
    let last = ''; const reflected = mesh.matrixWorld.determinant() < 0;
    for (let i = 0; i < count; i += 3) {
      const group = geometry.groups.find(group => i >= group.start && i < group.start + group.count);
      const material = names[group?.materialIndex ?? 0];
      if (!material) throw new Error('The model contains an invalid material assignment.');
      if (material !== last) { emit(`usemtl ${material}`); last = material; }
      emit('f ' + (reflected ? [0, 2, 1] : [0, 1, 2]).map(offset => {
        const index = geometry.index?.getX(i + offset) ?? i + offset;
        return `${vertices + index + 1}${uv || normal ? '/' + (uv ? uvs + index + 1 : '') + (normal ? '/' + (normals + index + 1) : '') : ''}`;
      }).join(' '));
      if (i % 24576 === 0) await pause();
    }
    vertices += position.count; if (uv) uvs += position.count; if (normal) normals += position.count;
  }
  if (!meshes.length) throw new Error('This model has no exportable meshes.');
  files['model.obj'] = strToU8(lines.join('\n') + '\n'); files['model.mtl'] = strToU8(materials.join('\n'));
  files['README.txt'] = strToU8('Extract all files together, then import model.obj in your 3D editor.\nOriginal scene transforms and Y-up coordinates are preserved. OBJ has no unit metadata.\nThe MTL includes base color and PNG textures. Normal/roughness/metallic maps use MTL extensions; support varies by editor. GLB preserves the full original PBR material.\nPreview lighting is not baked into this export.\n');
  // Stored ZIP: avoids blocking compression or spawning blob workers under CSP.
  return zipSync(files, { level: 0 });
}

export async function downloadObj(id: string, name: string) {
  const model = await loadGeometry(id);
  try {
    const bytes = await objBundle(model.scene);
    const url = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type: 'application/zip' }));
    const link = document.createElement('a'); link.href = url;
    link.download = (name.replace(/[^a-zA-Z0-9 _-]/g, '').trim().slice(0, 80) || 'hearth-model') + '-obj.zip';
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  } finally { disposeGeometry(model.scene); }
}
