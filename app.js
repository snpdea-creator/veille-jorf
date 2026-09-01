/* Veille JORF — logique d'affichage */
(function () {
  const DATA = typeof JO_DATA !== 'undefined' ? JO_DATA : { weeks: {}, categories: {}, total_texts: 0, generated_at: '' };

  const CAT_ORDER = ['enseignement_agricole', 'concours', 'statuts', 'nominations', 'avis_vacance', 'organisation_admin'];
  const CAT_META = {
    enseignement_agricole: { label: 'Enseignement agricole & EPLEFPA', color: '#2f5d22' },
    concours: { label: 'Concours & recrutements', color: '#9a6a00' },
    statuts: { label: 'Statuts des personnels (tous corps)', color: '#1f5a6b' },
    nominations: { label: 'Nominations (directions, services déconcentrés, offices)', color: '#8a3b52' },
    avis_vacance: { label: 'Avis de vacance — emplois de direction (MASA & DDI avec agents MASA)', color: '#6b4d1f' },
  organisation_admin: { label: 'Organisation administrative du MASA', color: '#5b4b8a' },
  };

  // Merge DATA.categories labels if present
  if (DATA.categories) {
    Object.keys(DATA.categories).forEach(k => { if (CAT_META[k]) CAT_META[k].label = DATA.categories[k]; });
  }

  const state = {
    week: null,
    search: '',
    activeCats: new Set(CAT_ORDER),
  };

  const $ = (sel) => document.querySelector(sel);
  const weeks = Object.keys(DATA.weeks || {}).sort().reverse();

  function fmtDate(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
      return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });
    } catch { return iso; }
  }

  function weekLabel(wk) {
    // wk = "2026-W34"
    const [y, w] = wk.split('-W');
    // Lundi de la semaine
    const jan4 = new Date(Date.UTC(+y, 0, 4));
    const dayOfWeek = jan4.getUTCDay() || 7;
    const monday = new Date(jan4);
    monday.setUTCDate(jan4.getUTCDate() + 1 - dayOfWeek + (+w - 1) * 7);
    const end = new Date(monday);
    end.setUTCDate(monday.getUTCDate() + 6);
    const f = (d) => d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', timeZone: 'UTC' });
    return `Sem. ${w} · ${f(monday)} – ${f(end)} ${y}`;
  }

  function initWeekSelect() {
    const sel = $('#week-select');
    if (!weeks.length) {
      sel.innerHTML = '<option>Aucune donnée</option>';
      return;
    }
    sel.innerHTML = weeks.map(w => `<option value="${w}">${weekLabel(w)}</option>`).join('');
    state.week = weeks[0];
    sel.value = state.week;
    sel.addEventListener('change', () => { state.week = sel.value; render(); });
  }

  function currentItems() {
    if (!state.week) return [];
    return (DATA.weeks[state.week] || []).slice();
  }

  function filterItems(items) {
    const q = state.search.trim().toLowerCase();
    return items.filter(it => {
      if (!state.activeCats.has(it.categories[0]) && !it.categories.some(c => state.activeCats.has(c))) return false;
      if (!q) return true;
      const hay = (it.title + ' ' + (it.author || '') + ' ' + (it.summary || '') + ' ' + it.id).toLowerCase();
      return hay.includes(q);
    });
  }

  function renderKPIs() {
    const items = currentItems();
    const row = $('#kpi-row');
    const counts = {};
    CAT_ORDER.forEach(c => counts[c] = 0);
    items.forEach(it => it.categories.forEach(c => { if (counts[c] !== undefined) counts[c]++; }));
    const total = items.length;

    const cards = [
      { value: total, label: 'Textes cette semaine', accent: true, color: null },
      ...CAT_ORDER.map(c => ({ value: counts[c], label: CAT_META[c].label, accent: false, color: CAT_META[c].color })),
    ];
    row.innerHTML = cards.map(c => `
      <div class="kpi ${c.accent ? 'accent' : ''}">
        <div class="kpi-value">${c.color ? `<span class="swatch" style="background:${c.color}"></span>` : ''}${c.value}</div>
        <div class="kpi-label">${c.label}</div>
      </div>`).join('');
  }

  function renderChips() {
    const items = currentItems();
    const counts = {};
    CAT_ORDER.forEach(c => counts[c] = 0);
    items.forEach(it => it.categories.forEach(c => { if (counts[c] !== undefined) counts[c]++; }));
    const wrap = $('#cat-chips');
    wrap.innerHTML = CAT_ORDER.map(c => `
      <button class="chip ${state.activeCats.has(c) ? 'active' : ''}" data-cat="${c}">
        <span class="swatch" style="background:${CAT_META[c].color}"></span>
        ${CAT_META[c].label}
        <span class="count">${counts[c]}</span>
      </button>`).join('');
    wrap.querySelectorAll('.chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const c = btn.dataset.cat;
        if (state.activeCats.has(c)) state.activeCats.delete(c); else state.activeCats.add(c);
        if (state.activeCats.size === 0) state.activeCats = new Set(CAT_ORDER);
        renderChips(); renderResults();
      });
    });
  }

  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }

  function renderResults() {
    const items = filterItems(currentItems());
    const root = $('#results');
    const empty = $('#empty-note');
    if (!items.length) {
      root.innerHTML = '';
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    // Group by category in CAT_ORDER
    let html = '';
    CAT_ORDER.forEach(c => {
      const catItems = items.filter(it => it.categories.includes(c));
      if (!catItems.length) return;
      html += `
        <section class="results-section">
          <div class="section-head">
            <span class="swatch" style="background:${CAT_META[c].color}"></span>
            <h2>${CAT_META[c].label}</h2>
            <span class="section-count">${catItems.length}</span>
          </div>
          <div class="text-list">
            ${catItems.map(it => renderCard(it, c)).join('')}
          </div>
        </section>`;
    });
    root.innerHTML = html;
  }

  function renderCard(it, cat) {
    const otherCats = it.categories.filter(c => c !== cat);
    const catBadges = otherCats.map(c => `<span class="badge badge-cat cat-${c}">${CAT_META[c] ? CAT_META[c].label : c}</span>`).join('');
    const nature = it.nature ? it.nature.charAt(0) + it.nature.slice(1).toLowerCase() : '';
    return `
      <article class="text-card cat-${cat}">
        <h3 class="card-title"><a href="${it.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(it.title)}</a></h3>
        ${it.summary ? `<p class="card-summary">${escapeHtml(it.summary)}</p>` : ''}
        <div class="card-meta">
          <span class="meta-item"><svg class="mi" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>${fmtDate(it.date)}</span>
          ${it.author ? `<span class="meta-item"><svg class="mi" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>${escapeHtml(it.author)}</span>` : ''}
          ${nature ? `<span class="badge badge-nature">${escapeHtml(nature)}</span>` : ''}
          ${catBadges}
        </div>
      </article>`;
  }

  function render() {
    renderKPIs();
    renderChips();
    renderResults();
  }

  function initMeta() {
    const el = $('#last-update');
    if (DATA.generated_at) {
      const d = new Date(DATA.generated_at);
      el.textContent = `Dernière mise à jour : ${d.toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' })}`;
    } else {
      el.textContent = 'Mise à jour quotidienne';
    }
  }

  function initSearch() {
    const input = $('#search');
    let t;
    input.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => { state.search = input.value; renderResults(); }, 180);
    });
  }

  // Theme toggle
  (function () {
    const t = document.querySelector('[data-theme-toggle]');
    const r = document.documentElement;
    let d = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
    r.setAttribute('data-theme', d);
    function icon() {
      return d === 'dark'
        ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
    t.innerHTML = icon();
    t.addEventListener('click', () => {
      d = d === 'dark' ? 'light' : 'dark';
      r.setAttribute('data-theme', d);
      t.setAttribute('aria-label', 'Basculer en mode ' + (d === 'dark' ? 'clair' : 'sombre'));
      t.innerHTML = icon();
    });
  })();

  initMeta();
  initWeekSelect();
  initSearch();
  render();
})();
