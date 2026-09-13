import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { describe, expect, it } from 'vitest';

const schema = JSON.parse(readFileSync('packages/contracts/schema/hearth.json', 'utf8'));
const cases = JSON.parse(readFileSync('tests/fixtures/contracts.json', 'utf8')) as Array<{name: string; contract: string; valid: boolean; payload: unknown}>;
const ajv = new Ajv2020({ strict: true, allErrors: true });
addFormats(ajv);
ajv.addSchema(schema);
describe('shared versioned wire contracts', () => {
  for (const fixture of cases) {
    it(fixture.name, () => {
      const validate = ajv.getSchema(`https://hearth.invalid/contracts/v1#/$defs/${fixture.contract}`)!;
      expect(validate(fixture.payload)).toBe(fixture.valid);
    });
  }
});
