import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { unzipSync, strFromU8 } from 'fflate';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { MTLLoader } from 'three/addons/loaders/MTLLoader.js';
import { Mesh } from 'three';

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
