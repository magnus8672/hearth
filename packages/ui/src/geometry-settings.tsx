import schema from '../../contracts/schema/geometry-tuning.json';

export type TuningProfile = 'trellis-v1' | 'hunyuan-v1';
export type TuningValues = Record<string, number | string | boolean>;
type Setting = { title: string; description: string; default: number | string | boolean; type: string; enum?: (number | string)[]; minimum?: number; maximum?: number };
const schemas = schema as Record<TuningProfile, Record<string, Setting>>;
export function tuningDefaults(profile: TuningProfile): TuningValues {
  return Object.fromEntries(Object.entries(schemas[profile]).map(([key, field]) => [key, field.default]));
}
const mesh = new Set(['remesh_band', 'decimation', 'octree_resolution', 'chunks', 'surface_level', 'bounds', 'remove_floaters', 'remove_degenerate', 'max_faces']);
const texture = new Set(['texture', 'unwrap', 'atlas_size', 'texture_resolution', 'paint_steps', 'paint_guidance', 'paint_seed', 'texture_size', 'render_size', 'bake_exp', 'delight', 'delight_image_guidance', 'delight_text_guidance']);

export function GeometrySettings({ profile, values, onChange, disabled }: { profile: TuningProfile; values: TuningValues; onChange: (values: TuningValues) => void; disabled: boolean }) {
  return <div className="geometry-settings">
    <p className="small-copy">Settings are saved with each request. Higher quality settings take longer and use more memory. Generation has a 20-minute limit.</p>
    {['Generation', 'Mesh', 'Texture'].map(group => <details key={group} open={group === 'Generation'}>
      <summary>{group} settings</summary>
      <fieldset disabled={disabled}>
        {Object.entries(schemas[profile]).filter(([key]) => (texture.has(key) ? 'Texture' : mesh.has(key) ? 'Mesh' : 'Generation') === group).map(([key, field]) => {
          const value = values[key] ?? field.default;
          const inactive = (texture.has(key) && key !== 'texture' && values.texture === false) || (key.startsWith('delight_') && values.delight === false);
          return <label key={key}>
            {field.type === 'boolean' ? <span><input type="checkbox" checked={Boolean(value)} disabled={inactive} onChange={event => onChange({ ...values, [key]: event.target.checked })} /> {field.title}</span> : <>{field.title}
              {field.enum ? <select value={String(value)} disabled={inactive} onChange={event => onChange({ ...values, [key]: field.type === 'integer' ? Number(event.target.value) : event.target.value })}>
                {field.enum.map(option => <option key={option} value={String(option)}>{option === 0 ? 'Automatic' : option}</option>)}
              </select> : <input required type="number" min={field.minimum} max={field.maximum} step={field.type === 'integer' ? 1 : 'any'} value={String(value)} disabled={inactive} onChange={event => onChange({ ...values, [key]: event.target.value === '' ? '' : Number(event.target.value) })} />}
            </>}
            <span className="small-copy">{field.description}</span>
          </label>;
        })}
      </fieldset>
    </details>)}
    <button className="quiet-button" type="button" disabled={disabled} onClick={() => onChange(tuningDefaults(profile))}>Reset tuning defaults</button>
  </div>;
}

export function SavedGeometrySettings({ trellis, hunyuan }: { trellis?: TuningValues | null; hunyuan?: TuningValues | null }) {
  const values = trellis || hunyuan;
  if (!values) return null;
  const fields = schemas[trellis ? 'trellis-v1' : 'hunyuan-v1'];
  return <details className="geometry-settings"><summary>Generation settings</summary><dl>{Object.entries(values).map(([key, value]) => <div key={key}><dt>{fields[key]?.title || key}</dt><dd>{typeof value === 'boolean' ? (value ? 'On' : 'Off') : String(value)}</dd></div>)}</dl></details>;
}
