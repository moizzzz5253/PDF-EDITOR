/* PDF//SCOPE theme: presets plus a custom accent/background picker.
   Loaded in <head> so colours are applied before the first paint.
   The choice is saved in this browser only (localStorage). */
(() => {
  const KEY = 'pdfscope.theme';
  const PRESETS = {
    phosphor: { label: 'Phosphor', swatch: ['#050a09', '#3dffb0', '#35d7ff'], vars: {
      bg: '#050a09', top: '#07100e', panel: '#0a1412', panel2: '#0d1a17', line: '#17342d', line2: '#1f4a3f',
      phos: '#3dffb0', cyan: '#35d7ff', amber: '#ffb340', red: '#ff4d5e', violet: '#b48cff', text: '#d2f3e8', dim: '#6b968a' } },
    light: { label: 'Paper', swatch: ['#f3f6f4', '#0b7a55', '#0b6e99'], vars: {
      bg: '#f3f6f4', top: '#e6ece9', panel: '#ffffff', panel2: '#f0f5f2', line: '#cfdcd6', line2: '#a9c2b8',
      phos: '#0b7a55', cyan: '#0b6e99', amber: '#b35c00', red: '#c92a2a', violet: '#6b3fc0', text: '#122a22', dim: '#55706a' } },
    blush: { label: 'Blush', swatch: ['#170b13', '#ff8fc7', '#ffb3d9'], vars: {
      bg: '#170b13', top: '#1c0e17', panel: '#22121c', panel2: '#2b1726', line: '#4d2a40', line2: '#70405c',
      phos: '#ff8fc7', cyan: '#ffb3d9', amber: '#ffc96b', red: '#ff4d7d', violet: '#d69cff', text: '#ffe4f0', dim: '#b07c98' } },
    sakura: { label: 'Sakura', swatch: ['#fff5f9', '#d6336c', '#c2255c'], vars: {
      bg: '#fff5f9', top: '#ffe4ef', panel: '#ffffff', panel2: '#fff0f6', line: '#f2c4d8', line2: '#e494b5',
      phos: '#d6336c', cyan: '#c2255c', amber: '#e8590c', red: '#c92a2a', violet: '#9c36b5', text: '#3b1a2b', dim: '#9a6b82' } },
    hotpink: { label: 'Hot Pink', swatch: ['#12020c', '#ff2e97', '#ff7ac2'], vars: {
      bg: '#12020c', top: '#170311', panel: '#1d0415', panel2: '#260519', line: '#5c0f3d', line2: '#8a1a5c',
      phos: '#ff2e97', cyan: '#ff7ac2', amber: '#ffd166', red: '#ff4d6d', violet: '#e0aaff', text: '#ffd6ec', dim: '#c2578f' } },
    rosegold: { label: 'Rose Gold', swatch: ['#1a1210', '#e8b4a0', '#f2cdb8'], vars: {
      bg: '#1a1210', top: '#150e0c', panel: '#241a17', panel2: '#2e211d', line: '#4d3530', line2: '#6e4a42',
      phos: '#e8b4a0', cyan: '#f2cdb8', amber: '#ffb36b', red: '#ff6b6b', violet: '#d4a5a5', text: '#f6e3da', dim: '#a88478' } },
  };

  // Relative luminance of a #rrggbb colour (0 = black, 1 = white)
  function luminance(hex) {
    const n = parseInt(hex.slice(1), 16);
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  // Custom: the picked background and accent drive the rest of the palette.
  function customVars(st) {
    const base = (PRESETS[st.base] || PRESETS.phosphor).vars;
    const bg = st.bg || base.bg;
    const acc = st.accent || base.phos;
    const light = luminance(bg) > 0.3;
    const mix = (pct, c) => `color-mix(in srgb, ${bg} ${pct}%, ${c})`;
    return {
      ...base, bg, top: mix(92, '#000'), panel: mix(90, acc), panel2: mix(84, acc),
      line: mix(72, acc), line2: mix(55, acc), phos: acc,
      text: light ? '#111816' : '#e6f5ef', dim: light ? '#4f6660' : '#8aa89e',
    };
  }

  function resolve(st) {
    return st.preset === 'custom' ? customVars(st) : (PRESETS[st.preset] || PRESETS.phosphor).vars;
  }

  function apply(st) {
    const root = document.documentElement;
    for (const [k, v] of Object.entries(resolve(st))) root.style.setProperty('--' + k, v);
    root.dataset.theme = st.preset;
  }

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || { preset: 'phosphor' }; }
    catch (e) { return { preset: 'phosphor' }; }
  }

  function save(st) {
    try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) { /* private window: keep it for this page only */ }
  }

  let state = load();
  apply(state);

  document.addEventListener('DOMContentLoaded', build);

  function build() {
    const btn = document.getElementById('themeBtn');
    if (!btn) return;
    const panel = document.createElement('div');
    panel.id = 'themePanel';
    panel.hidden = true;
    panel.innerHTML = `
      <h4>THEME</h4>
      <div class="tp-presets"></div>
      <label>Accent <input type="color" id="tpAccent"></label>
      <label>Background <input type="color" id="tpBg"></label>
      <div class="tp-row"><button id="tpReset" class="tp-reset">Reset to Phosphor</button></div>`;
    document.body.appendChild(panel);

    const grid = panel.querySelector('.tp-presets');
    for (const [id, p] of Object.entries(PRESETS)) {
      const b = document.createElement('button');
      b.className = 'tp-preset';
      b.dataset.id = id;
      b.innerHTML = `<span class="sw">${p.swatch.map(c => `<i style="background:${c}"></i>`).join('')}</span>${p.label}`;
      b.addEventListener('click', () => { state = { preset: id }; applyAndSave(); });
      grid.appendChild(b);
    }

    const accIn = panel.querySelector('#tpAccent');
    const bgIn = panel.querySelector('#tpBg');
    const onPick = () => {
      const base = state.preset === 'custom' ? state.base : state.preset;
      state = { preset: 'custom', base: PRESETS[base] ? base : 'phosphor', accent: accIn.value, bg: bgIn.value };
      applyAndSave();
    };
    accIn.addEventListener('input', onPick);
    bgIn.addEventListener('input', onPick);
    panel.querySelector('#tpReset').addEventListener('click', () => { state = { preset: 'phosphor' }; applyAndSave(); });

    btn.addEventListener('click', e => { e.stopPropagation(); panel.hidden = !panel.hidden; });
    document.addEventListener('click', e => {
      if (!panel.hidden && !panel.contains(e.target)) panel.hidden = true;
    });

    function sync() {
      const cur = resolve(state);
      accIn.value = cur.phos;
      bgIn.value = cur.bg;
      panel.querySelectorAll('.tp-preset').forEach(b => b.classList.toggle('on', b.dataset.id === state.preset));
    }
    function applyAndSave() { apply(state); save(state); sync(); }
    sync();
  }
})();
