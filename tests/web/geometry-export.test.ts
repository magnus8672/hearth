import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { unzipSync, strFromU8 } from 'fflate';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { objBundle } from '../../packages/ui/src/geometry-obj';
import { lightDirection, lightPresets } from '../../packages/ui/src/geometry-lighting';

describe('geometry exports', () => {
  it('preserves world positions, normals, UV orientation and separate material assignments', async () => {
    const scene = new THREE.Scene(); const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute([0, .25, 1, .25, 0, .75], 2)); geometry.computeVertexNormals();
    for (const [index, color] of ['red', 'blue'].entries()) {
      const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color })); mesh.name = '../bad\nmtllib external';
      mesh.position.set(10 + index, 2, 3); scene.add(mesh);
    }
    const files = unzipSync(await objBundle(scene)); const obj = strFromU8(files['model.obj']), mtl = strFromU8(files['model.mtl']);
    expect(Object.keys(files).sort()).toEqual(['README.txt', 'model.mtl', 'model.obj']);
    expect(obj).toContain('v 10 2 3\n'); expect(obj).toContain('vt 0 0.75\n');
    expect(obj).toContain('f 1/1/1 2/2/2 3/3/3'); expect(obj).toContain('f 4/4/4 5/5/5 6/6/6');
    expect(obj).toContain('usemtl material_0'); expect(obj).toContain('usemtl material_1'); expect(obj).not.toContain('external');
    expect(mtl).toContain('newmtl material_0\nKd 1 0 0'); expect(mtl).toContain('newmtl material_1\nKd 0 0 1');
    const restored = new OBJLoader().parse(obj); const bounds = new THREE.Box3().setFromObject(restored);
    expect(bounds.min.toArray()).toEqual([10, 2, 3]); expect(bounds.max.toArray()).toEqual([12, 3, 3]);
    expect(scene.children[0].position.toArray()).toEqual([10, 2, 3]);
  });
  it('exports reflected indexed meshes with corrected winding and material groups', async () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0, 1,0,0, 0,1,0, 1,1,0], 3));
    geometry.setIndex([0,1,2, 1,3,2]); geometry.addGroup(0, 3, 0); geometry.addGroup(3, 3, 1);
    const mesh = new THREE.Mesh(geometry, [new THREE.MeshStandardMaterial(), new THREE.MeshStandardMaterial()]); mesh.scale.x = -1;
    const obj = strFromU8(unzipSync(await objBundle(mesh))['model.obj']);
    expect(obj).toContain('f 1 3 2'); expect(obj).toContain('usemtl material_1\nf 2 3 4');
  });
});

it('offers every noncentral face, edge and corner with normalized light vectors', () => {
  expect(lightPresets).toHaveLength(26); expect(new Set(lightPresets.map(p => p.name)).size).toBe(26);
  for (const preset of lightPresets) {
    const direction = lightDirection(preset.azimuth, preset.elevation);
    expect(Math.hypot(...direction)).toBeCloseTo(1);
    expect(Math.sign(direction[1]) === 1).toBe(preset.name.includes('Top'));
  }
  expect(lightDirection(0, 0)).toEqual([0,0,1]);
  expect(lightDirection(0, 90)[1]).toBe(1); expect(lightDirection(0, -90)[1]).toBe(-1);
});
