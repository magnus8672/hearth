import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { unzipSync, strFromU8 } from 'fflate';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { MTLLoader } from 'three/addons/loaders/MTLLoader.js';
import { Mesh, SphereGeometry } from 'three';

const origin = process.env.HEARTH_BROWSER_ORIGIN || 'https://hearth.example.invalid';
test.beforeEach(async ({ page }) => {
  if (process.env.HEARTH_BROWSER_LOCAL_BUILD !== '1') return;
  await page.route(origin + '/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname !== '/' && !pathname.startsWith('/assets/')) return route.fallback();
    const file = path.resolve('apps/user-web/dist', '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(path.resolve('apps/user-web/dist') + path.sep)) return route.abort();
    await route.fulfill({ path: file });
  });
});

test('light directions stay on the selected screen side after orbit, pan and zoom', async ({ page }) => {
  // A symmetric matte sphere gives an unambiguous lighting direction without
  // depending on generated model orientation, baked texture highlights or normals.
  const sphere = new SphereGeometry(1, 48, 32).toNonIndexed();
  const positions = Buffer.from(sphere.getAttribute('position').array.buffer);
  const normals = Buffer.from(sphere.getAttribute('normal').array.buffer);
  const binary = Buffer.concat([positions, normals]);
  const document = { asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, material: 0 }] }],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [0.7, 0.7, 0.7, 1], metallicFactor: 0, roughnessFactor: 1 } }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.length }, { buffer: 0, byteOffset: positions.length, byteLength: normals.length }],
    accessors: [{ bufferView: 0, componentType: 5126, count: positions.length / 12, type: 'VEC3', min: [-1,-1,-1], max: [1,1,1] },
      { bufferView: 1, componentType: 5126, count: normals.length / 12, type: 'VEC3' }] };
  const json = Buffer.from(JSON.stringify(document)); const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32); json.copy(padded);
  const header = Buffer.alloc(20); header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + padded.length + binary.length, 8);
  header.writeUInt32LE(padded.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8); binHeader.writeUInt32LE(binary.length); binHeader.writeUInt32LE(0x004e4942, 4);
  const raw = Buffer.concat([header, padded, binHeader, binary]); sphere.dispose();
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url()).pathname;
    if (url.endsWith('/session')) return route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['capability.geometry.generate'], csrf_token: 'fixture', user_origin: origin, admin_origin: origin + ':8443' } });
    if (url.endsWith('/model')) return route.fulfill({ contentType: 'model/gltf-binary', body: raw });
    if (url.endsWith('/geometry')) return route.fulfill({ json: { items: [{ id: 'sphere', name: 'Lighting reference', status: 'completed', request: { model: 'fixture', resolution: 512, seed: 1 }, metadata: { triangles: positions.length / 36, textures: 0, bytes: raw.length } }] } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto(origin + '/#geometry');
  await page.getByRole('button', { name: 'Preview 3D' }).click();
  await expect(page.getByRole('button', { name: 'Right', exact: true })).toBeEnabled();
  await page.getByLabel('Ambient fill', { exact: true }).fill('0');
  const canvas = page.locator('canvas');
  async function sideBrightness() {
    const screenshot = await canvas.screenshot();
    return page.evaluate(async base64 => {
      const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(base64), c => c.charCodeAt(0))], { type: 'image/png' }));
      const image = document.createElement('canvas'); image.width = bitmap.width; image.height = bitmap.height;
      const ctx = image.getContext('2d')!; ctx.drawImage(bitmap, 0, 0); bitmap.close();
      const pixels = ctx.getImageData(0, 0, image.width, image.height).data;
      let left = 0, right = 0;
      for (let y = 0; y < image.height; y++) for (let x = 0; x < image.width; x++) {
        const brightness = Math.max(0, pixels[(y * image.width + x) * 4] - pixels[0]);
        if (x < image.width / 2) left += brightness; else right += brightness;
      }
      return (right - left) / Math.max(1, right + left);
    }, screenshot.toString('base64'));
  }
  for (const direction of ['Right', 'Bottom / Front / Right', 'Left', 'Bottom / Front / Left']) {
    await page.getByLabel('Light direction').selectOption(direction);
    const sign = direction.endsWith('Right') ? 1 : -1;
    await expect.poll(async () => sign * await sideBrightness()).toBeGreaterThan(0.15);
  }
  await page.getByLabel('Light direction').selectOption('Bottom / Front / Right');
  const bounds = (await canvas.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down(); await page.mouse.move(bounds.x + bounds.width * .9, bounds.y + bounds.height * .6, { steps: 15 }); await page.mouse.up();
  await expect.poll(sideBrightness).toBeGreaterThan(0.15);
  // Small pan and zoom also move the camera; the light target must move with it.
  await page.mouse.down({ button: 'right' }); await page.mouse.move(bounds.x + bounds.width * .91, bounds.y + bounds.height * .6, { steps: 5 }); await page.mouse.up({ button: 'right' });
  await page.mouse.wheel(0, -100);
  await expect.poll(sideBrightness).toBeGreaterThan(0.15);
  await canvas.screenshot({ path: '.hearth/view-relative-lighting.png' });
});

for (const backend of ['hunyuan', 'trellis']) test(`real ${backend} GLB exports OBJ materials/textures and responds to preview lighting`, async ({ page }) => {
  const fixture = process.env[`HEARTH_${backend.toUpperCase()}_GLB`] || `.hearth/tuning-${backend}.glb`;
  test.skip(!fs.existsSync(fixture), 'Requires a previously generated real qualification GLB.');
  test.setTimeout(90_000);
  const raw = fs.readFileSync(fixture); const doc = JSON.parse(raw.subarray(20, 20 + raw.readUInt32LE(12)).toString());
  const triangles = doc.meshes.flatMap((mesh: any) => mesh.primitives).reduce((sum: number, primitive: any) => sum + doc.accessors[primitive.indices ?? primitive.attributes.POSITION].count / 3, 0);
  let reads = 0; let denied = false;
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url()).pathname;
    if (url.endsWith('/session')) return route.fulfill({ json: { id: 'fixture', display_name: 'Tester', roles: ['Member'], permissions: ['capability.geometry.generate'], csrf_token: 'fixture', user_origin: origin, admin_origin: origin + ':8443' } });
    if (url.endsWith('/model')) { reads++; return denied ? route.fulfill({ status: 403, json: { detail: 'Denied' } }) : route.fulfill({ contentType: 'model/gltf-binary', body: raw }); }
    if (url.endsWith('/geometry')) return route.fulfill({ json: { items: [{ id: 'qualification', name: `${backend} export`, status: 'completed', request: { model: backend, resolution: 512, seed: 42 }, metadata: { triangles, textures: doc.images.length, bytes: raw.length } }] } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto(origin + '/#geometry');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Save OBJ ZIP' }).click();
  const download = await downloadEvent; expect(download.suggestedFilename()).toBe(`${backend} export-obj.zip`);
  const output = `.hearth/${backend}-export.zip`; await download.saveAs(output);
  const files = unzipSync(fs.readFileSync(output)); const obj = strFromU8(files['model.obj']); const mtl = strFromU8(files['model.mtl']);
  expect(obj.split('\n').filter(line => line.startsWith('f '))).toHaveLength(triangles);
  expect(obj.includes('mtllib model.mtl')).toBe(true); expect(obj.includes('vt ')).toBe(true);
  expect(obj.includes('vn ')).toBe(doc.meshes.some((mesh: any) => mesh.primitives.some((primitive: any) => primitive.attributes.NORMAL !== undefined)));
  const materials = [...obj.matchAll(/^usemtl (.+)$/gm)].map(match => match[1]);
  for (const material of materials) expect(mtl).toContain(`newmtl ${material}\n`);
  const textures = [...mtl.matchAll(/^(?:map_Kd|map_Pr|map_Pm|norm) (.+)$/gm)].map(match => match[1]);
  expect(textures.length).toBeGreaterThan(0);
  for (const file of textures) expect(Buffer.from(files[file]).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  const imported = new OBJLoader().parse(obj); let importedFaces = 0;
  imported.traverse(object => { if (object instanceof Mesh) importedFaces += object.geometry.getAttribute('position').count / 3; });
  expect(importedFaces).toBe(triangles);
  const importedMaterials = new MTLLoader().parse(mtl, '');
  expect(Object.keys(importedMaterials.materialsInfo).sort()).toEqual([...new Set(materials)].sort());
  const textureIndex = doc.materials[0].pbrMetallicRoughness.baseColorTexture.index;
  const imageView = doc.bufferViews[doc.images[doc.textures[textureIndex].source].bufferView];
  const imageStart = 28 + raw.readUInt32LE(12) + (imageView.byteOffset || 0);
  const originalPng = raw.subarray(imageStart, imageStart + imageView.byteLength).toString('base64');
  const colorFile = mtl.match(/^map_Kd (.+)$/m)![1];
  const samePixels = await page.evaluate(async ([original, exported]) => {
    async function pixels(base64: string) {
      const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0)); const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
      const context = canvas.getContext('2d')!; context.drawImage(bitmap, 0, 0); bitmap.close();
      return context.getImageData(0, 0, canvas.width, canvas.height).data;
    }
    const first = await pixels(original), second = await pixels(exported);
    return first.length === second.length && first.every((value, index) => value === second[index]);
  }, [originalPng, Buffer.from(files[colorFile]).toString('base64')]);
  expect(samePixels).toBe(true);
  expect(Object.keys(files).every(name => !name.includes('/') && !name.includes('..'))).toBe(true);
  // glTF v starts at the top; OBJ v starts at the bottom. Preserve the image pixels and flip UV v.
  const uvAccessor = doc.accessors[doc.meshes[0].primitives[0].attributes.TEXCOORD_0];
  if (uvAccessor.componentType === 5126) {
    const uvView = doc.bufferViews[uvAccessor.bufferView]; const binary = 28 + raw.readUInt32LE(12);
    const sourceV = raw.readFloatLE(binary + (uvView.byteOffset || 0) + (uvAccessor.byteOffset || 0) + 4);
    const exportedV = Number(obj.match(/^vt [^ ]+ (.+)$/m)![1]); expect(exportedV).toBeCloseTo(1 - sourceV, 6);
  }
  await page.getByRole('button', { name: 'Preview 3D' }).click();
  await expect(page.getByRole('button', { name: 'Top', exact: true })).toBeEnabled();
  await page.getByLabel('Ambient fill', { exact: true }).fill('0');
  await page.getByRole('button', { name: 'Top', exact: true }).click();
  await expect(page.getByLabel('Light direction')).toHaveValue('Top');
  const top = await page.locator('canvas').screenshot();
  await page.getByRole('button', { name: 'Bottom', exact: true }).click();
  const bottom = await page.locator('canvas').screenshot(); expect(top.equals(bottom)).toBe(false);
  await page.getByLabel('Light direction').selectOption('Top / Front / Right');
  await expect(page.getByLabel('Light azimuth', { exact: true })).toHaveValue('45');
  expect(Number(await page.getByLabel('Light elevation', { exact: true }).inputValue())).toBeCloseTo(35, 0);
  await page.getByLabel('Light azimuth', { exact: true }).fill('-45');
  await page.getByLabel('Light brightness', { exact: true }).fill('5');
  expect(reads).toBe(2); // Moving lights neither refetches the model nor regenerates anything.
  await page.getByRole('button', { name: 'Reset lighting' }).click();
  await expect(page.getByLabel('Ambient fill', { exact: true })).toHaveValue('1.2');
  await expect(page.getByLabel('Light brightness', { exact: true })).toHaveValue('3');
  await page.screenshot({ path: `.hearth/${backend}-lighting.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  denied = true;
  await page.getByRole('button', { name: 'Save OBJ ZIP' }).click();
  await expect(page.getByRole('alert')).toContainText('no longer available');
  await expect(page.getByRole('button', { name: 'Save OBJ ZIP' })).toBeEnabled();
});
