(() => {
  'use strict';
  document.documentElement.classList.add('enhanced');
  const appearance = document.querySelector('#appearance');
  const themeKey = 'hearth-website-appearance';
  const themes = new Set(['system', 'light', 'dark']);
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(theme) {
    if (theme === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    appearance.value = theme;
    const dark = theme === 'dark' || (theme === 'system' && systemTheme.matches);
    document.querySelector('meta[name="theme-color"]').content = dark ? '#171412' : '#F5F0E8';
  }
  let saved = 'system';
  try { const value = localStorage.getItem(themeKey); if (themes.has(value)) saved = value; } catch { /* Reading stays available when storage is blocked. */ }
  applyTheme(saved);
  appearance.addEventListener('change', () => {
    applyTheme(appearance.value);
    try { localStorage.setItem(themeKey, appearance.value); } catch { /* Theme selection still works for this visit. */ }
  });
  systemTheme.addEventListener('change', () => { if (appearance.value === 'system') applyTheme('system'); });
  const routes = {
    write: { prompt: '“Help me find the right words.”', role: 'Writing specialist', location: 'everyday laptop' },
    code: { prompt: '“Help me untangle this code.”', role: 'Code specialist', location: 'spare desktop' },
    image: { prompt: '“Imagine a garden in the stars.”', role: 'Image specialist', location: 'creative workstation' }
  };
  const farm = document.querySelector('.farm');
  document.querySelectorAll('[data-request]').forEach(button => {
    button.addEventListener('click', () => {
      const route = routes[button.dataset.request];
      farm.dataset.route = button.dataset.request;
      document.querySelectorAll('[data-request]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
      document.querySelector('#route-prompt').textContent = route.prompt;
      const location = document.createElement('span');
      location.className = 'route-location';
      location.textContent = `/ ${route.location}`;
      document.querySelector('#route-result').replaceChildren(`${route.role} `, location);
    });
  });
})();
