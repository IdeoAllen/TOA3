(function () {
  const api = location.origin;
  const tokenKey = 'toa_cloud_token';
  const token = localStorage.getItem(tokenKey);
  if (!token) {
    location.href = 'index.html';
    return;
  }

  let sellablePacks = [];
  let allPacks = [];
  let showClearedPacks = false;
  const PROTECTED_PACK_IDS = new Set(['local_free']);

  const PAGE_META = {
    dashboard: ['运营概览', '授权台账、办公插件与桌面发版一站式管理'],
    customers: ['用户管理', '授权用户与订单对齐；停用后禁止社区插件上传下载'],
    license: ['授权管理', '签发 TOA 授权码、查询绑定状态与到期日'],
    plugins: ['办公插件', '审核、上架/下架、启用/停用；公示信息卡片'],
    traffic: ['上下载记录', '无偿流通流水查询（不计费）'],
    packs: ['产品方案', '功能选配 + 有效期 + 定价；与 TOA3 feature_packs.yml 同源'],
    menu: ['菜单信息', '与终端设置·菜单同结构；按子模块查询功能模块'],
    orders: ['订单管理', '创建订单、确认收款并自动签发授权码'],
    release: ['版本发布', '维护 TOA3 升级包与 manifest'],
  };

  const headers = () => ({
    Authorization: 'Bearer ' + token,
    'Content-Type': 'application/json',
  });

  function toast(msg, kind) {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const el = document.createElement('div');
    el.className =
      'toast' +
      (kind === 'ok' ? ' ok' : kind === 'err' ? ' err' : kind === 'warn' ? ' warn' : '');
    el.textContent = msg;
    root.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  async function apiFetch(path, opts = {}) {
    const res = await fetch(api + path, { ...opts, headers: { ...headers(), ...(opts.headers || {}) } });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      localStorage.removeItem(tokenKey);
      location.href = 'index.html';
      throw new Error('请重新登录');
    }
    if (!res.ok) throw new Error(data.detail || data.message || '请求失败');
    return data;
  }

  function setLoading(box, text) {
    box.innerHTML = `<div class="loading-state">${text || '加载中…'}</div>`;
  }

  function emptyHtml(text) {
    return `<div class="empty-state">${text}</div>`;
  }

  document.getElementById('btn-logout').onclick = () => {
    localStorage.removeItem(tokenKey);
    location.href = 'index.html';
  };

  const panels = {
    dashboard: document.getElementById('panel-dashboard'),
    license: document.getElementById('panel-license'),
    customers: document.getElementById('panel-customers'),
    plugins: document.getElementById('panel-plugins'),
    traffic: document.getElementById('panel-traffic'),
    packs: document.getElementById('panel-packs'),
    menu: document.getElementById('panel-menu'),
    packEdit: document.getElementById('panel-pack-edit'),
    orders: document.getElementById('panel-orders'),
    release: document.getElementById('panel-release'),
  };

  function showPanel(tab) {
    document.querySelectorAll('.nav-item').forEach((b) => {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    Object.keys(panels).forEach((k) => {
      if (k === 'packEdit') {
        panels[k].hidden = true;
        return;
      }
      panels[k].hidden = k !== tab;
    });
    const meta = PAGE_META[tab] || ['运营台', ''];
    document.getElementById('page-title').textContent = meta[0];
    document.getElementById('page-subtitle').textContent = meta[1];
    if (tab === 'dashboard') loadDashboard();
    if (tab === 'license') loadLicenses();
    if (tab === 'customers') loadCustomers();
    if (tab === 'plugins') loadPlugins();
    if (tab === 'traffic') loadTraffic();
    if (tab === 'packs') loadPacks();
    if (tab === 'menu') loadMenuInfo();
    if (tab === 'orders') loadOrders();
    if (tab === 'release') loadReleases();
  }

  function showPackEditPage(show) {
    panels.packs.hidden = show;
    panels.packEdit.hidden = !show;
    if (show) {
      panels.dashboard.hidden = true;
      panels.license.hidden = true;
      panels.customers.hidden = true;
      panels.plugins.hidden = true;
      panels.traffic.hidden = true;
      panels.menu.hidden = true;
      panels.orders.hidden = true;
      panels.release.hidden = true;
    }
  }

  function closePackEditor() {
    showPackEditPage(false);
    const meta = PAGE_META.packs || ['产品方案', ''];
    document.getElementById('page-title').textContent = meta[0];
    document.getElementById('page-subtitle').textContent = meta[1];
  }

  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.onclick = () => {
      closePackEditor();
      showPanel(btn.dataset.tab);
    };
  });

  function wireDialogForms() {
    document.querySelectorAll('dialog form[method="dialog"]').forEach((form) => {
      form.querySelectorAll('button[value="cancel"]').forEach((btn) => {
        btn.type = 'submit';
        btn.setAttribute('formnovalidate', '');
        if (!btn.dataset.wired) {
          btn.dataset.wired = '1';
          btn.addEventListener('click', (e) => {
            e.preventDefault();
            form.closest('dialog')?.close('cancel');
          });
        }
      });
    });
  }

  function firstFocusable(root) {
    if (!root) return null;
    return root.querySelector(
      'input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])',
    );
  }

  function openDialog(dialogEl, { focusEl } = {}) {
    if (!dialogEl) return;
    dialogEl.showModal();
    requestAnimationFrame(() => {
      const target = focusEl || firstFocusable(dialogEl);
      if (!target) return;
      target.focus();
      if (typeof target.select === 'function' && target.type !== 'number') {
        try {
          target.select();
        } catch (_) {
          /* ignore */
        }
      }
    });
  }

  function wireDialogKeyboard(dialogEl) {
    if (!dialogEl || dialogEl.dataset.kbdWired) return;
    dialogEl.dataset.kbdWired = '1';
    dialogEl.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || e.isComposing || e.defaultPrevented) return;
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'textarea' || tag === 'button') return;
      const form = dialogEl.querySelector('form');
      const primary = form?.querySelector(
        'button.primary[type="submit"], button[type="submit"].primary, button.primary[value="ok"]',
      );
      if (primary && !primary.disabled) {
        e.preventDefault();
        primary.click();
      }
    });
  }

  function enhanceAllDialogs() {
    document.querySelectorAll('dialog').forEach((dlg) => wireDialogKeyboard(dlg));
  }

  wireDialogForms();
  enhanceAllDialogs();

  document.getElementById('rel-manifest-link').href =
    api + '/api/toa/releases/manifest?product=TOA3&channel=stable';

  let lastManifest = null;

  async function loadReleaseManifestCard() {
    const verEl = document.getElementById('rel-current-version');
    const urlEl = document.getElementById('rel-current-url');
    try {
      const m = await fetch(api + '/api/toa/releases/manifest?product=TOA3&channel=stable').then((r) => r.json());
      lastManifest = m;
      const ver = (m.latest_version || m.version || '').trim();
      verEl.textContent = ver ? `v${ver.replace(/^v/i, '')}` : '尚未发布';
      const url = (m.download_url || '').trim();
      urlEl.textContent = url || '未配置安装包直链 — 请发布新版本并填写 URL';
    } catch (e) {
      verEl.textContent = '—';
      urlEl.textContent = e.message || 'manifest 加载失败';
    }
  }

  document.getElementById('rel-copy-manifest').onclick = async () => {
    try {
      if (!lastManifest) await loadReleaseManifestCard();
      const text = JSON.stringify(lastManifest || {}, null, 2);
      await navigator.clipboard.writeText(text);
      toast('manifest JSON 已复制', 'ok');
    } catch (err) {
      toast(err.message || '复制失败', 'err');
    }
  };

  function statusTag(s) {
    return { active: ['有效', 'ok'], revoked: ['已停用', 'bad'], expired: ['已过期', 'warn'] }[s] || [s, ''];
  }

  function orderStatusTag(s) {
    return {
      pending: ['待付款', 'warn'],
      fulfilled: ['已履约', 'ok'],
      cancelled: ['已取消', ''],
    }[s] || [s, ''];
  }

  function fillPackSelect(selectEl, packs, { includeAll } = { includeAll: false }) {
    selectEl.innerHTML = '';
    if (includeAll) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '全部功能 (all)';
      selectEl.appendChild(opt);
    }
    packs.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      const price = p.price_yuan ? ` · ¥${p.price_yuan}` : '';
      opt.textContent = `${p.name} (${p.id})${price}`;
      selectEl.appendChild(opt);
    });
  }

  let menuCatalogMeta = null;
  let packValidationWarnings = [];

  async function loadPackCatalog() {
    const data = await apiFetch('/api/toa/packs/catalog');
    allPacks = data.packs || [];
    sellablePacks = allPacks.filter((p) => p.is_active !== false && p.sellable);
    menuCatalogMeta = data.menu_catalog || null;
    packValidationWarnings = data.validation_warnings || [];
    const notice = document.getElementById('order-notice');
    if (notice && data.commerce && data.commerce.mock_payment_note) {
      notice.innerHTML =
        '创建订单 → 确认收款并签发授权码。' + data.commerce.mock_payment_note;
    }
    fillPackSelect(document.getElementById('lic-pack-select'), sellablePacks, { includeAll: true });
    fillPackSelect(document.getElementById('ord-pack-select'), sellablePacks);
    return data;
  }

  function isProtectedPack(id) {
    return PROTECTED_PACK_IDS.has(String(id || ''));
  }

  function visiblePacks() {
    const rows = (allPacks || []).filter((p) => showClearedPacks || p.is_active !== false);
    return rows.sort((a, b) => {
      const aActive = a.is_active !== false ? 0 : 1;
      const bActive = b.is_active !== false ? 0 : 1;
      if (aActive !== bActive) return aActive - bActive;
      const aSell = a.sellable ? 0 : 1;
      const bSell = b.sellable ? 0 : 1;
      if (aSell !== bSell) return aSell - bSell;
      return String(a.id || '').localeCompare(String(b.id || ''));
    });
  }

  function packStats() {
    const all = allPacks || [];
    const active = all.filter((p) => p.is_active !== false);
    const cleared = all.filter((p) => p.is_active === false);
    const sellable = active.filter((p) => p.sellable);
    return { all: all.length, active: active.length, cleared: cleared.length, sellable: sellable.length };
  }

  function renderPackListSummary() {
    const el = document.getElementById('pack-list-summary');
    if (!el) return;
    const st = packStats();
    const visible = visiblePacks().length;
    const activeIds = (allPacks || [])
      .filter((p) => p.is_active !== false)
      .map((p) => p.id)
      .filter(Boolean);
    const hint =
      activeIds.length && activeIds.length <= 6
        ? `有效方案：${activeIds.join('、')}`
        : `有效方案 ${st.active} 个`;
    if (showClearedPacks) {
      el.textContent = `${hint} · 已清除 ${st.cleared} 个 · 当前列表 ${visible} 条`;
    } else {
      el.textContent = `${hint} · 可售 ${st.sellable} 个${st.cleared ? ` · 另有 ${st.cleared} 个已清除（勾选右上角可查看）` : ''}`;
    }
  }

  function packSellCell(p) {
    if (p.is_active === false) {
      return '<span class="tag bad">已清除</span>';
    }
    if (!p.sellable) {
      return '<span class="tag warn">已停用</span>';
    }
    return `<span class="tag ok">可售 · ¥${p.price_yuan || 0}</span>`;
  }

  function packActionCell(p) {
    if (p.is_active === false) {
      return '<span class="muted">—</span>';
    }
    const edit = `<button type="button" class="btn-chip" data-act="edit-pack" data-id="${escHtml(p.id)}">编辑</button>`;
    if (isProtectedPack(p.id)) {
      return `<div class="cell-actions">${edit}</div>`;
    }
    const toggle = p.sellable
      ? `<button type="button" data-act="disable-pack" data-id="${escHtml(p.id)}">停用</button>`
      : `<button type="button" data-act="enable-pack" data-id="${escHtml(p.id)}">恢复售卖</button>`;
    const clear = `<button type="button" class="danger" data-act="clear-pack" data-id="${escHtml(p.id)}">清除</button>`;
    return `<div class="cell-actions">${edit}${toggle}${clear}</div>`;
  }

  function renderModuleCell(p) {
    const val = p.menu_validation || {};
    if (val.scope === 'all') {
      return '<span class="tag ok">全部模块 (all)</span>';
    }
    const mods = val.modules || [];
    const unknown = val.unknown || [];
    const chips = mods.slice(0, 8).map((m) => {
      const st = m.migration_status;
      const cls = st === 'done' ? 'ok' : st ? '' : '';
      const title = [m.name, m.group_label, st ? `就绪:${st}` : ''].filter(Boolean).join(' · ');
      return `<code class="mod-chip ${cls}" title="${title.replace(/"/g, '&quot;')}">${m.id}</code>`;
    });
    const more = mods.length > 8 ? `<span class="muted">+${mods.length - 8}</span>` : '';
    const bad = unknown.length
      ? `<div class="pack-warn">未知 ID：${unknown.map((u) => `<code>${u}</code>`).join(' ')}</div>`
      : '';
    const okTag = val.ok ? '<span class="tag ok">已对齐</span>' : '<span class="tag bad">待修正</span>';
    const inc = (p.includes || []).length ? `<div class="muted">includes: ${(p.includes || []).join(', ')}</div>` : '';
    return `${okTag} ${chips.join(' ')} ${more}${inc}${bad}`;
  }

  function renderPackCatalogMeta() {
    const box = document.getElementById('pack-catalog-meta');
    if (!box) return;
    const meta = menuCatalogMeta || {};
    const warnN = packValidationWarnings.length;
    box.innerHTML = `
      <div class="release-current-card__main">
        <span class="release-current-card__label">菜单目录（只读）</span>
        <strong>TOA3 v${meta.app_version || '—'}</strong>
        <p class="muted">${meta.module_count || 0} 个 module_id · 同步 ${meta.exported_at ? meta.exported_at.replace('T', ' ').slice(0, 19) + ' UTC' : '未同步'}</p>
      </div>
      <div class="release-current-card__actions">
        ${warnN ? `<span class="tag bad">${warnN} 个包存在未知 module</span>` : '<span class="tag ok">SKU 均已对齐菜单</span>'}
      </div>`;
  }

  let catalogModules = [];
  let catalogGroupLabels = {};
  let catalogMeta = {};
  let menuInfoSelectedId = '';

  const MENU_GROUP_ORDER = ['home', 'office', 'image', 'files', 'engines', 'business', 'system'];

  const DEFAULT_GROUP_LABELS = {
    home: '首页',
    office: '日常办公',
    image: '图片处理',
    files: '文件与目录',
    engines: '开源引擎',
    business: '培训业务',
    system: '系统',
    other: '其他',
    // 兼容旧目录
    ai: '开源引擎',
    directory: '文件与目录',
    file: '文件与目录',
  };

  const MIGRATION_STATUS_LABELS = {
    done: '已完成',
    mvp: '进行中（未做强）',
    stub: '待开发（空页面）',
    missing: '尚未建模块',
  };

  function escHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function loadCatalogModules() {
    const data = await apiFetch('/api/toa/menu-catalog/modules');
    catalogModules = data.modules || [];
    catalogMeta = data.menu_catalog || {};
    menuCatalogMeta = catalogMeta;
    catalogGroupLabels = { ...DEFAULT_GROUP_LABELS, ...(catalogMeta.group_labels || {}) };
    return catalogModules;
  }

  function migrationStatusLabel(st) {
    const key = String(st || '').toLowerCase();
    return MIGRATION_STATUS_LABELS[key] || (key ? key : '—');
  }

  function menuItemLabel(m) {
    const mid = String(m.id || '');
    const name = String(m.name || mid);
    const show = m.show === false ? '隐藏' : '显示';
    const lic = m.requires_license ? '付费' : '基础';
    const st = migrationStatusLabel(m.migration_status);
    return `${name}  [${mid}]  · ${lic} · ${show} · ${st}`;
  }

  function filterMenuModules(modules) {
    const q = String(document.getElementById('menu-q')?.value || '')
      .trim()
      .toLowerCase();
    const showHidden = !!document.getElementById('menu-show-hidden')?.checked;
    const tier = document.getElementById('menu-tier-filter')?.value || 'all';
    return (modules || []).filter((m) => {
      if (!showHidden && m.show === false) return false;
      if (tier === 'base' && m.requires_license) return false;
      if (tier === 'paid' && !m.requires_license) return false;
      if (!q) return true;
      const hay = [
        m.id,
        m.name,
        m.group,
        m.group_label,
        m.feature_id,
        m.migration_status,
        migrationStatusLabel(m.migration_status),
      ]
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function renderMenuCatalogMeta() {
    const el = document.getElementById('menu-catalog-meta');
    if (!el) return;
    const meta = catalogMeta || {};
    if (!meta.synced && !(catalogModules || []).length) {
      el.innerHTML =
        '<div class="release-current-card__main"><span class="release-current-card__label">菜单目录</span><strong>尚未同步</strong><p class="muted">请终端管理员在 TOA3 → 设置 → 菜单 中同步到运营台</p></div>';
      return;
    }
    const synced = meta.exported_at
      ? String(meta.exported_at).replace('T', ' ').slice(0, 19) + ' UTC'
      : '—';
    el.innerHTML = `
      <div class="release-current-card__main">
        <span class="release-current-card__label">终端菜单目录（与设置·菜单同结构）</span>
        <strong>TOA3 v${escHtml(meta.app_version || '—')}</strong>
        <p class="muted">${escHtml(String(meta.module_count ?? catalogModules.length))} 个功能模块 · 同步人 ${escHtml(meta.published_by || '—')} · ${escHtml(synced)}</p>
      </div>`;
  }

  function renderMenuDetail(mod) {
    const box = document.getElementById('menu-detail');
    if (!box) return;
    if (!mod) {
      box.innerHTML = '<p class="muted">选择左侧模块查看详情</p>';
      return;
    }
    const rows = [
      ['名称', mod.name],
      ['模块 ID', mod.id],
      ['子模块', `${mod.group_label || groupLabelForPicker(mod.group, [mod])} (${mod.group || '—'})`],
      ['排序', `子模块 ${mod.group_order ?? '—'} · 模块 ${mod.order ?? 0}`],
      ['侧栏显示', mod.show === false ? '隐藏' : '显示'],
      ['授权层级', mod.requires_license ? '付费' : '基础'],
      ['feature_id', mod.feature_id || mod.id],
      ['迁移状态', migrationStatusLabel(mod.migration_status)],
      ['终端版本', mod.app_version || '—'],
      ['发布人', mod.published_by || '—'],
      ['发布时间', mod.published_at || '—'],
    ];
    box.innerHTML = `
      <h3 class="menu-info-detail__title">${escHtml(mod.name || mod.id)}</h3>
      <dl class="menu-info-dl">
        ${rows
          .map(
            ([k, v]) =>
              `<div><dt>${escHtml(k)}</dt><dd><code>${escHtml(String(v ?? '—'))}</code></dd></div>`,
          )
          .join('')}
      </dl>`;
  }

  function renderMenuTree() {
    const tree = document.getElementById('menu-tree');
    const summary = document.getElementById('menu-list-summary');
    if (!tree) return;
    const filtered = filterMenuModules(catalogModules);
    if (summary) {
      summary.textContent = `共 ${filtered.length} / ${catalogModules.length} 个功能模块`;
    }
    if (!catalogModules.length) {
      tree.innerHTML =
        '<div class="module-picker-empty">暂无菜单目录 — 请终端管理员在 TOA3 设置·菜单中同步</div>';
      renderMenuDetail(null);
      return;
    }
    if (!filtered.length) {
      tree.innerHTML = '<div class="module-picker-empty">无匹配结果，请调整查询条件</div>';
      renderMenuDetail(null);
      return;
    }
    const grouped = groupModulesForPicker(filtered);
    tree.innerHTML = grouped
      .map(([gid, items]) => {
        const label = groupLabelForPicker(gid, items);
        const leaves = items
          .map((m) => {
            const active = m.id === menuInfoSelectedId ? ' is-active' : '';
            const muted = m.show === false ? ' is-hidden' : '';
            return `<button type="button" class="menu-info-leaf${active}${muted}" data-module-id="${escHtml(m.id)}" role="treeitem">
              <span class="menu-info-leaf__text">${escHtml(menuItemLabel(m))}</span>
            </button>`;
          })
          .join('');
        return `<section class="menu-info-group" data-group="${escHtml(gid)}">
          <div class="menu-info-group__head" role="treeitem" aria-expanded="true">▾ ${escHtml(label)}  (${items.length})</div>
          <div class="menu-info-group__body">${leaves}</div>
        </section>`;
      })
      .join('');

    if (menuInfoSelectedId) {
      const still = filtered.find((m) => m.id === menuInfoSelectedId);
      renderMenuDetail(still || null);
      if (!still) menuInfoSelectedId = '';
    }
  }

  async function loadMenuInfo() {
    try {
      await loadCatalogModules();
      renderMenuCatalogMeta();
      renderMenuTree();
    } catch (e) {
      toast(e.message || '加载菜单失败', 'err');
    }
  }

  function bindMenuInfoEvents() {
    const q = document.getElementById('menu-q');
    const hidden = document.getElementById('menu-show-hidden');
    const tier = document.getElementById('menu-tier-filter');
    const reload = document.getElementById('menu-reload');
    const tree = document.getElementById('menu-tree');
    if (q && !q.dataset.bound) {
      q.dataset.bound = '1';
      let t = null;
      q.addEventListener('input', () => {
        clearTimeout(t);
        t = setTimeout(renderMenuTree, 160);
      });
    }
    if (hidden && !hidden.dataset.bound) {
      hidden.dataset.bound = '1';
      hidden.addEventListener('change', renderMenuTree);
    }
    if (tier && !tier.dataset.bound) {
      tier.dataset.bound = '1';
      tier.addEventListener('change', renderMenuTree);
    }
    if (reload && !reload.dataset.bound) {
      reload.dataset.bound = '1';
      reload.onclick = loadMenuInfo;
    }
    if (tree && !tree.dataset.bound) {
      tree.dataset.bound = '1';
      tree.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-module-id]');
        if (!btn) return;
        menuInfoSelectedId = btn.dataset.moduleId || '';
        const mod = (catalogModules || []).find((m) => m.id === menuInfoSelectedId);
        tree.querySelectorAll('.menu-info-leaf.is-active').forEach((el) => el.classList.remove('is-active'));
        btn.classList.add('is-active');
        renderMenuDetail(mod || null);
      });
    }
  }

  bindMenuInfoEvents();

  function isBaseModule(mod) {
    return mod && mod.requires_license === false;
  }

  function baseModuleIds() {
    return (catalogModules || []).filter(isBaseModule).map((m) => m.id);
  }

  function paidModuleIds() {
    return (catalogModules || []).filter((m) => !isBaseModule(m)).map((m) => m.id);
  }

  function expandPickerSelection(selected) {
    const raw = Array.isArray(selected) ? selected : [];
    if (raw.includes('all')) {
      return paidModuleIds();
    }
    return raw.filter(Boolean);
  }

  function groupModulesForPicker(modules) {
    const buckets = {};
    (modules || []).forEach((m) => {
      const gid = String(m.group || 'other').trim() || 'other';
      if (!buckets[gid]) buckets[gid] = [];
      buckets[gid].push(m);
    });
    Object.keys(buckets).forEach((gid) => {
      buckets[gid].sort((a, b) => {
        const ao = Number(a.order ?? a.sort_order ?? 0);
        const bo = Number(b.order ?? b.sort_order ?? 0);
        if (ao !== bo) return ao - bo;
        return String(a.name || a.id).localeCompare(String(b.name || b.id), 'zh-CN');
      });
    });
    const ordered = [];
    const byGroupOrder = [...(modules || [])].sort(
      (a, b) => Number(a.group_order ?? 99) - Number(b.group_order ?? 99),
    );
    const seen = new Set();
    const preferOrder = [];
    MENU_GROUP_ORDER.forEach((gid) => preferOrder.push(gid));
    byGroupOrder.forEach((m) => {
      const gid = String(m.group || 'other').trim() || 'other';
      if (!preferOrder.includes(gid)) preferOrder.push(gid);
    });
    preferOrder.forEach((gid) => {
      if (buckets[gid]?.length && !seen.has(gid)) {
        seen.add(gid);
        ordered.push([gid, buckets[gid]]);
      }
    });
    Object.keys(buckets)
      .filter((gid) => !seen.has(gid))
      .sort()
      .forEach((gid) => ordered.push([gid, buckets[gid]]));
    return ordered;
  }

  function groupLabelForPicker(groupId, modules) {
    const fromMeta = catalogGroupLabels[groupId];
    if (fromMeta) return fromMeta;
    const fromMod = modules.find((m) => m.group_label)?.group_label;
    if (fromMod) return fromMod;
    return DEFAULT_GROUP_LABELS[groupId] || groupId;
  }

  function updateModulePickerSummary() {
    const box = document.getElementById('pack-module-picker');
    if (!box) return;
    const inputs = [...box.querySelectorAll('input[data-module]')];
    const baseInputs = inputs.filter((el) => el.dataset.base === '1');
    const paidInputs = inputs.filter((el) => el.dataset.base !== '1');
    const baseN = baseInputs.length;
    const paidChecked = paidInputs.filter((el) => el.checked).length;
    const paidTotal = paidInputs.length;
    const counter = box.querySelector('.module-picker-count');
    if (counter) {
      counter.textContent = `基础 ${baseN} · 方案 ${paidChecked}/${paidTotal}`;
    }
    box.querySelectorAll('.module-group').forEach((section) => {
      const gid = section.dataset.group;
      const groupBox = section.querySelector('.group-check');
      const items = [...section.querySelectorAll('input[data-module]')];
      if (!groupBox || !items.length) return;
      const paidItems = items.filter((el) => el.dataset.base !== '1');
      const baseOnly = paidItems.length === 0;
      if (baseOnly) {
        groupBox.checked = true;
        groupBox.indeterminate = false;
        groupBox.disabled = true;
      } else {
        groupBox.disabled = false;
        const n = paidItems.filter((el) => el.checked).length;
        groupBox.checked = n === paidItems.length;
        groupBox.indeterminate = n > 0 && n < paidItems.length;
      }
      const meta = section.querySelector('.group-meta');
      if (meta) {
        const baseInGroup = items.filter((el) => el.dataset.base === '1').length;
        meta.textContent = baseInGroup
          ? `${baseInGroup} 基础 · ${paidItems.filter((el) => el.checked).length}/${paidItems.length} 方案`
          : `${paidItems.filter((el) => el.checked).length}/${paidItems.length} 已选`;
      }
    });
  }

  function bindModulePickerEvents() {
    const box = document.getElementById('pack-module-picker');
    if (!box || box.dataset.bound === '1') return;
    box.dataset.bound = '1';
    box.addEventListener('change', (e) => {
      const t = e.target;
      if (!(t instanceof HTMLInputElement)) return;
      if (t.classList.contains('group-check')) {
        const gid = t.dataset.group;
        box.querySelectorAll(`input[data-module][data-group="${gid}"]:not([data-base="1"])`).forEach((el) => {
          el.checked = t.checked;
        });
      }
      updateModulePickerSummary();
    });
    box.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-picker-act]');
      if (!btn) return;
      e.preventDefault();
      const act = btn.dataset.pickerAct;
      const inputs = [...box.querySelectorAll('input[data-module]:not([data-base="1"])')];
      if (act === 'all') inputs.forEach((el) => { el.checked = true; });
      if (act === 'none') inputs.forEach((el) => { el.checked = false; });
      updateModulePickerSummary();
    });
  }

  function renderModulePicker(selected) {
    const box = document.getElementById('pack-module-picker');
    if (!box) return;
    const sel = new Set(expandPickerSelection(selected));
    if (!catalogModules.length) {
      box.innerHTML = '<div class="module-picker-empty">暂无菜单目录 — 请终端管理员在 TOA3 设置·菜单中同步目录到运营台</div>';
      return;
    }
    const grouped = groupModulesForPicker(catalogModules);
    const groupsHtml = grouped
      .map(([gid, items]) => {
        const label = groupLabelForPicker(gid, items);
        const itemsHtml = items
          .map((m) => {
            const isBase = isBaseModule(m);
            const checked = isBase || sel.has(m.id) ? 'checked' : '';
            const disabled = isBase ? 'disabled' : '';
            const baseAttr = isBase ? ' data-base="1"' : '';
            const itemCls = isBase ? 'module-item module-item--base' : 'module-item';
            const status = m.migration_status ? ` · ${m.migration_status}` : '';
            const baseTag = isBase ? '<span class="module-base-tag">基础</span>' : '';
            const title = escHtml(`${m.id} · ${m.name || ''}${status}${isBase ? ' · 基础功能' : ''}`);
            return `<label class="${itemCls}" title="${title}">
              <input type="checkbox" data-module="1" data-group="${escHtml(gid)}" value="${escHtml(m.id)}"${baseAttr} ${checked} ${disabled} />
              <span><code>${escHtml(m.id)}</code> <span class="module-name">${escHtml(m.name || m.id)}</span>${baseTag}</span>
            </label>`;
          })
          .join('');
        const paidCount = items.filter((m) => !isBaseModule(m)).length;
        const baseCount = items.length - paidCount;
        const metaText = baseCount
          ? `${baseCount} 基础 · ${paidCount} 方案`
          : `${items.length} 项`;
        return `<section class="module-group" data-group="${escHtml(gid)}">
          <label class="module-group-head">
            <input type="checkbox" class="group-check" data-group="${escHtml(gid)}" />
            <span class="group-title">${escHtml(label)}</span>
            <span class="group-meta">${metaText}</span>
          </label>
          <div class="module-group-items">${itemsHtml}</div>
        </section>`;
      })
      .join('');
    box.innerHTML = `
      <div class="module-picker-toolbar">
        <button type="button" class="btn-chip" data-picker-act="all">全选方案模块</button>
        <button type="button" class="btn-chip" data-picker-act="none">清空方案模块</button>
        <span class="module-picker-count">基础 0 · 方案 0/0</span>
      </div>
      <div class="module-picker-tree">${groupsHtml}</div>`;
    box.dataset.bound = '0';
    bindModulePickerEvents();
    updateModulePickerSummary();
  }

  function readSelectedModules() {
    const paid = [
      ...document.querySelectorAll('#pack-module-picker input[data-module]:checked:not([data-base="1"])'),
    ].map((el) => el.value);
    return [...new Set([...baseModuleIds(), ...paid])];
  }

  const packForm = document.getElementById('form-pack-edit');

  function updatePackEditActions(pack) {
    const disableBtn = document.getElementById('pack-edit-disable');
    const enableBtn = document.getElementById('pack-edit-enable');
    const clearBtn = document.getElementById('pack-edit-clear');
    const show = pack && pack.id && pack.is_active !== false;
    [disableBtn, enableBtn, clearBtn].forEach((el) => {
      if (el) el.hidden = true;
    });
    if (!show || isProtectedPack(pack.id)) return;
    if (pack.sellable) {
      if (disableBtn) disableBtn.hidden = false;
    } else if (enableBtn) {
      enableBtn.hidden = false;
    }
    if (clearBtn) clearBtn.hidden = false;
  }

  async function disablePackById(id, { fromEditor = false } = {}) {
    if (!id || isProtectedPack(id)) return;
    if (!window.confirm(`确定停用方案「${id}」？\n停用后终端与新建订单不可选，已有授权不受影响。`)) return;
    try {
      await apiFetch('/api/toa/packs/' + encodeURIComponent(id) + '/disable', { method: 'POST' });
      toast('产品方案已停用', 'ok');
      if (fromEditor) closePackEditor();
      loadPacks();
    } catch (err) {
      toast(err.message || '停用失败', 'err');
    }
  }

  async function enablePackById(id, { fromEditor = false } = {}) {
    if (!id || isProtectedPack(id)) return;
    try {
      await apiFetch('/api/toa/packs/' + encodeURIComponent(id) + '/enable', { method: 'POST' });
      toast('已恢复售卖', 'ok');
      if (fromEditor) closePackEditor();
      loadPacks();
    } catch (err) {
      toast(err.message || '恢复失败', 'err');
    }
  }

  async function clearPackById(id, { fromEditor = false } = {}) {
    if (!id || isProtectedPack(id)) return;
    if (!window.confirm(`确定清除方案「${id}」？\n清除后从目录移除且不可恢复；历史订单仍保留 plan_id。`)) return;
    try {
      await apiFetch('/api/toa/packs/' + encodeURIComponent(id), { method: 'DELETE' });
      toast('产品方案已清除', 'ok');
      if (fromEditor) closePackEditor();
      loadPacks();
    } catch (err) {
      toast(err.message || '清除失败', 'err');
    }
  }

  async function openPackEditor(pack) {
    await loadCatalogModules();
    const isNew = !pack;
    document.getElementById('pack-edit-title').textContent = isNew ? '新建产品方案' : `编辑产品方案 · ${pack.id}`;
    document.getElementById('page-title').textContent = isNew ? '新建产品方案' : `编辑产品方案 · ${pack.id}`;
    document.getElementById('page-subtitle').textContent =
      '配置功能选配、有效期与定价；保存后用于订单履约（一订单一授权码）。';
    document.getElementById('pack-edit-id').value = isNew ? '' : pack.id;
    document.getElementById('pack-edit-id').readOnly = !isNew;
    document.getElementById('pack-edit-name').value = isNew ? '' : pack.name || '';
    document.getElementById('pack-edit-desc').value = isNew ? '' : pack.desc || '';
    document.getElementById('pack-edit-price').value = isNew ? 0 : pack.price_yuan || 0;
    document.getElementById('pack-edit-validity').value = isNew ? 365 : pack.validity_days || 365;
    document.getElementById('pack-edit-sellable').checked = isNew ? true : !!pack.sellable;
    const raw = isNew ? [] : pack.raw_features || pack.features || [];
    renderModulePicker(raw);
    updatePackEditActions(isNew ? null : pack);
    showPackEditPage(true);
    requestAnimationFrame(() => {
      const target = document.getElementById(isNew ? 'pack-edit-id' : 'pack-edit-name');
      target?.focus();
      if (isNew && typeof target?.select === 'function') target.select();
    });
  }

  document.getElementById('pack-create').onclick = () => openPackEditor(null);
  document.getElementById('pack-edit-back').onclick = () => closePackEditor();
  document.getElementById('pack-edit-cancel').onclick = () => closePackEditor();
  document.getElementById('pack-edit-disable').onclick = () => {
    const id = String(document.getElementById('pack-edit-id').value || '').trim();
    disablePackById(id, { fromEditor: true });
  };
  document.getElementById('pack-edit-enable').onclick = () => {
    const id = String(document.getElementById('pack-edit-id').value || '').trim();
    enablePackById(id, { fromEditor: true });
  };
  document.getElementById('pack-edit-clear').onclick = () => {
    const id = String(document.getElementById('pack-edit-id').value || '').trim();
    clearPackById(id, { fromEditor: true });
  };
  document.getElementById('pack-show-cleared').onchange = (e) => {
    showClearedPacks = !!e.target.checked;
    loadPacks();
  };
  document.getElementById('pack-show-cleared').checked = showClearedPacks;

  packForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(packForm);
    const packId = String(fd.get('id') || '').trim();
    const body = {
      id: packId,
      name: fd.get('name'),
      desc: fd.get('desc'),
      price_yuan: fd.get('price_yuan'),
      validity_days: fd.get('validity_days'),
      sellable: fd.get('sellable') === 'on',
      features: readSelectedModules(),
      includes: [],
    };
    try {
      const exists = (allPacks || []).some((p) => p.id === packId);
      if (exists) {
        await apiFetch('/api/toa/packs/' + encodeURIComponent(packId), { method: 'PUT', body: JSON.stringify(body) });
      } else {
        await apiFetch('/api/toa/packs', { method: 'POST', body: JSON.stringify(body) });
      }
      toast('产品方案已保存', 'ok');
      closePackEditor();
      loadPacks();
    } catch (err) {
      toast(err.message || '保存失败', 'err');
    }
  });

  async function loadPacks() {
    setLoading(document.getElementById('pack-list'), '加载产品方案…');
    await loadPackCatalog();
    renderPackCatalogMeta();
    renderPackListSummary();
    const box = document.getElementById('pack-list');
    const rows = visiblePacks();
    if (!rows.length) {
      box.innerHTML = emptyHtml(showClearedPacks ? '暂无产品方案' : '暂无有效产品方案 — 可勾选「显示已清除」');
      return;
    }
    box.innerHTML = `<table class="data-table pack-table"><thead><tr>
      <th>标识</th><th>名称</th><th>售卖</th><th>有效期</th><th>终端 module_id</th><th>说明</th><th>操作</th>
    </tr></thead><tbody>${rows
      .map((p) => {
        const sell = packSellCell(p);
        const validity = `${p.validity_days || 365} 天`;
        const rowCls = p.is_active === false ? 'row-muted' : !p.sellable ? 'row-warn' : '';
        return `<tr class="${rowCls}">
          <td><code>${escHtml(p.id)}</code></td>
          <td><strong>${escHtml(p.name || '')}</strong></td>
          <td>${sell}</td>
          <td>${validity}</td>
          <td class="pack-modules">${renderModuleCell(p)}</td>
          <td>${escHtml(p.desc || '—')}</td>
          <td>${packActionCell(p)}</td>
        </tr>`;
      })
      .join('')}</tbody></table>`;
    box.querySelectorAll('[data-act=edit-pack]').forEach((b) => {
      b.onclick = () => {
        const pack = (allPacks || []).find((p) => p.id === b.dataset.id);
        if (pack) openPackEditor(pack);
      };
    });
    box.querySelectorAll('[data-act=disable-pack]').forEach((b) => {
      b.onclick = () => disablePackById(b.dataset.id);
    });
    box.querySelectorAll('[data-act=enable-pack]').forEach((b) => {
      b.onclick = () => enablePackById(b.dataset.id);
    });
    box.querySelectorAll('[data-act=clear-pack]').forEach((b) => {
      b.onclick = () => clearPackById(b.dataset.id);
    });
  }

  document.getElementById('pack-reload').onclick = loadPacks;

  async function loadDashboard() {
    const statLic = document.getElementById('stat-licenses');
    const statOrd = document.getElementById('stat-pending-orders');
    const statVer = document.getElementById('stat-current-version');
    const statPack = document.getElementById('stat-sellable-packs');
    [statLic, statOrd, statVer, statPack].forEach((el) => {
      if (el) el.textContent = '…';
    });
    try {
      await loadPackCatalog();
      const [licenses, orders, releases] = await Promise.all([
        apiFetch('/api/toa-license'),
        apiFetch('/api/toa/orders?status=pending'),
        apiFetch('/api/toa/releases?product=TOA3'),
      ]);
      const activeCount = (licenses || []).filter((r) => r.status === 'active').length;
      if (statLic) statLic.textContent = String(activeCount);
      if (statOrd) statOrd.textContent = String((orders || []).length);
      if (statPack) statPack.textContent = String(sellablePacks.length);
      const current = (releases || []).find((r) => r.is_current);
      if (statVer) statVer.textContent = current ? `v${current.version}` : '—';
    } catch (e) {
      toast(e.message || '概览加载失败', 'err');
    }
  }

  async function loadLicenses() {
    const box = document.getElementById('lic-list');
    setLoading(box, '加载授权台账…');
    const q = document.getElementById('lic-q').value.trim();
    const rows = await apiFetch('/api/toa-license' + (q ? '?q=' + encodeURIComponent(q) : ''));
    if (!rows.length) {
      box.innerHTML = emptyHtml('暂无授权记录');
      return;
    }
    box.innerHTML = `<table class="data-table"><thead><tr>
      <th>用户</th><th>手机</th><th>类型</th><th>状态</th><th>到期</th><th>订单</th><th>绑定</th><th></th>
    </tr></thead><tbody>${rows
      .map((r) => {
        const [st, cls] = statusTag(r.status);
        const prot = r.protected ? '<span class="tag">固定管理员</span>' : '';
        const bind = r.activated ? '<span class="tag ok">已绑定</span>' : '<span class="tag warn">未激活</span>';
        const entLabel = r.entitlement_label || (r.entitlement === 'paid' ? '正式版' : r.entitlement === 'admin' ? '管理员' : '体验授权');
        const planHint = r.plan_id ? `<br><span class="muted"><code>${escapeHtml(r.plan_id)}</code></span>` : '';
        const orderCell = r.order_no ? `<code>${escapeHtml(r.order_no)}</code>` : '—';
        return `<tr data-id="${r.id}">
          <td><strong>${escapeHtml(r.name || '未命名')}</strong>${prot}</td>
          <td>${escapeHtml(r.phone || '—')}</td>
          <td>${entLabel}${planHint}</td>
          <td><span class="tag ${cls}">${st}</span></td>
          <td>${escapeHtml(r.expire_date || '—')}</td>
          <td>${orderCell}</td>
          <td>${bind}${r.code_fingerprint ? `<br><span class="muted">${escapeHtml(r.code_fingerprint)}</span>` : ''}</td>
          <td class="cell-actions">
            <button type="button" data-act="view" data-id="${r.id}">查看码</button>
            ${r.protected ? '' : `<button type="button" class="danger" data-act="del" data-id="${r.id}">清除</button>`}
          </td>
        </tr>`;
      })
      .join('')}</tbody></table>`;
    if (!rows.some((r) => r.protected || r.entitlement === 'admin' || r.role === 'admin')) {
      box.insertAdjacentHTML(
        'afterbegin',
        '<p class="notice warn">固定管理员未在云台账：服务重启后会自动登记；也可终端激活管理员码后同步。</p>'
      );
    }
    box.querySelectorAll('[data-act=view]').forEach((b) => (b.onclick = () => viewKey(b.dataset.id)));
    box.querySelectorAll('[data-act=del]').forEach((b) => (b.onclick = () => delLic(b.dataset.id)));
  }

  async function viewKey(id) {
    const row = await apiFetch('/api/toa-license/' + id + '?include_key=true');
    document.getElementById('lic-key-text').textContent = row.license_key || '无';
    openDialog(document.getElementById('dlg-lic-key'), {
      focusEl: document.getElementById('lic-copy'),
    });
  }

  document.getElementById('lic-copy').onclick = async () => {
    const t = document.getElementById('lic-key-text').textContent;
    try {
      await navigator.clipboard.writeText(t);
      toast('授权码已复制', 'ok');
    } catch {
      toast('复制失败，请手动选择复制', 'err');
    }
  };

  async function delLic(id) {
    if (!confirm('确定清除此授权账号？')) return;
    await apiFetch('/api/toa-license/' + id, { method: 'DELETE' });
    toast('已清除', 'ok');
    loadLicenses();
  }

  document.getElementById('lic-reload').onclick = loadLicenses;
  document.getElementById('lic-q').onkeyup = (e) => {
    if (e.key === 'Enter') loadLicenses();
  };

  document.getElementById('lic-create').onclick = async () => {
    await loadPackCatalog();
    openDialog(document.getElementById('dlg-lic-create'));
  };

  document.getElementById('dlg-lic-create').addEventListener('close', async (e) => {
    if (e.target.returnValue !== 'ok') return;
    const fd = new FormData(e.target.querySelector('form'));
    const body = {
      name: fd.get('name'),
      phone: fd.get('phone'),
      days: fd.get('days'),
      entitlement: fd.get('entitlement') || 'trial',
    };
    const packId = String(fd.get('pack_id') || '').trim();
    if (packId) body.pack_id = packId;
    try {
      const row = await apiFetch('/api/toa-license', { method: 'POST', body: JSON.stringify(body) });
      if (row.license_key) {
        document.getElementById('lic-key-text').textContent = row.license_key;
        openDialog(document.getElementById('dlg-lic-key'), {
          focusEl: document.getElementById('lic-copy'),
        });
      }
      toast('授权码已签发', 'ok');
      loadLicenses();
    } catch (err) {
      toast(err.message || '签发失败', 'err');
    }
  });

  document.getElementById('lic-clear').onclick = async () => {
    if (!confirm('清除除固定管理员外的全部账号？')) return;
    await apiFetch('/api/toa-license/clear', { method: 'POST' });
    toast('已清除其他账号', 'ok');
    loadLicenses();
  };

  async function loadOrders() {
    const box = document.getElementById('ord-list');
    setLoading(box, '加载订单…');
    const st = document.getElementById('ord-status').value;
    const rows = await apiFetch('/api/toa/orders' + (st ? '?status=' + encodeURIComponent(st) : ''));
    if (!rows.length) {
      box.innerHTML = emptyHtml('暂无订单');
      return;
    }
    box.innerHTML = `<table class="data-table"><thead><tr>
      <th>订单号</th><th>客户</th><th>产品方案</th><th>金额</th><th>状态</th><th></th>
    </tr></thead><tbody>${rows
      .map((r) => {
        const [stLabel, cls] = orderStatusTag(r.status);
        const meta = `${r.license_days} 天 · ${r.phone}${r.machine_id ? ' · 终端 ' + r.machine_id.slice(0, 8) + '…' : ''}`;
        let acts = '';
        if (r.status === 'pending') {
          acts = `<button type="button" class="primary" data-act="pay" data-id="${r.id}">确认收款</button><button type="button" data-act="cancel" data-id="${r.id}">取消</button>`;
        } else if (r.status === 'fulfilled' && r.license_id) {
          acts = `<button type="button" data-act="key" data-id="${r.id}">查看授权码</button>`;
        }
        return `<tr>
          <td><strong>${r.order_no}</strong><br><span class="muted">${r.remark || ''}</span></td>
          <td>${r.customer_name}</td>
          <td>${r.pack_name}<br><span class="muted"><code>${r.pack_id}</code> · ${meta}</span></td>
          <td>¥${r.amount_yuan}</td>
          <td><span class="tag ${cls}">${stLabel}</span></td>
          <td class="cell-actions">${acts}</td>
        </tr>`;
      })
      .join('')}</tbody></table>`;
    box.querySelectorAll('[data-act=pay]').forEach((b) => (b.onclick = () => mockPay(b.dataset.id)));
    box.querySelectorAll('[data-act=cancel]').forEach((b) => (b.onclick = () => cancelOrd(b.dataset.id)));
    box.querySelectorAll('[data-act=key]').forEach((b) => (b.onclick = () => viewOrderKey(b.dataset.id)));
  }

  async function mockPay(id) {
    if (!confirm('确认收款并自动签发 TOA 授权码？')) return;
    try {
      const row = await apiFetch('/api/toa/orders/' + id + '/mock-pay', { method: 'POST' });
      if (row.license_key) {
        document.getElementById('lic-key-text').textContent = row.license_key;
        openDialog(document.getElementById('dlg-lic-key'), {
          focusEl: document.getElementById('lic-copy'),
        });
      }
      toast('订单已履约', 'ok');
      loadOrders();
      loadLicenses();
    } catch (err) {
      toast(err.message || '履约失败', 'err');
    }
  }

  async function cancelOrd(id) {
    if (!confirm('取消此订单？')) return;
    await apiFetch('/api/toa/orders/' + id + '/cancel', { method: 'POST' });
    toast('订单已取消', 'ok');
    loadOrders();
  }

  async function viewOrderKey(id) {
    const row = await apiFetch('/api/toa/orders/' + id + '?include_key=true');
    document.getElementById('lic-key-text').textContent = row.license_key || '无';
    openDialog(document.getElementById('dlg-lic-key'), {
      focusEl: document.getElementById('lic-copy'),
    });
  }

  document.getElementById('ord-reload').onclick = loadOrders;
  document.getElementById('ord-status').onchange = loadOrders;
  document.getElementById('ord-create').onclick = async () => {
    await loadPackCatalog();
    openDialog(document.getElementById('dlg-ord-create'));
  };

  document.getElementById('dlg-ord-create').addEventListener('close', async (e) => {
    if (e.target.returnValue !== 'ok') return;
    const fd = new FormData(e.target.querySelector('form'));
    const body = {
      pack_id: fd.get('pack_id'),
      customer_name: fd.get('customer_name'),
      phone: fd.get('phone'),
      license_days: fd.get('license_days'),
      remark: fd.get('remark'),
    };
    const amt = fd.get('amount_yuan');
    if (amt !== '' && amt != null) body.amount_yuan = amt;
    try {
      await apiFetch('/api/toa/orders', { method: 'POST', body: JSON.stringify(body) });
      toast('订单已创建', 'ok');
      loadOrders();
    } catch (err) {
      toast(err.message || '创建失败', 'err');
    }
  });

  async function loadReleases() {
    const box = document.getElementById('rel-list');
    setLoading(box, '加载发布记录…');
    await loadReleaseManifestCard();
    const rows = await apiFetch('/api/toa/releases?product=TOA3');
    window.__releaseRows = rows;
    if (!rows.length) {
      box.innerHTML = emptyHtml('暂无发布记录 — 点「发布新版本」登记首版');
      return;
    }
    box.innerHTML = `<table class="data-table"><thead><tr>
      <th>版本</th><th>渠道</th><th>下载</th><th>发布时间</th><th></th>
    </tr></thead><tbody>${rows
      .map((r) => {
        const curTag = r.is_current ? '<span class="tag ok">当前</span>' : '';
        const setBtn = r.is_current
          ? ''
          : `<button type="button" data-act="set" data-id="${r.id}">设为当前</button>`;
        const editBtn = `<button type="button" data-act="edit" data-id="${r.id}">编辑</button>`;
        const notes = (r.release_notes || '').slice(0, 120);
        const dl = (r.download_url || '').trim();
        const dlCell = dl
          ? `<a class="text-link" href="${dl}" target="_blank" rel="noopener">直链</a>
             <button type="button" class="btn-chip" data-act="copy-url" data-url="${dl.replace(/"/g, '&quot;')}">复制</button>`
          : '<span class="muted">未填</span>';
        return `<tr>
          <td><strong>v${r.version}</strong> ${curTag}<br><span class="muted">${notes || '—'}</span></td>
          <td>${r.product} / ${r.channel}</td>
          <td class="cell-actions">${dlCell}</td>
          <td>${r.published_at || '—'}</td>
          <td class="cell-actions">${editBtn} ${setBtn}</td>
        </tr>`;
      })
      .join('')}</tbody></table>`;
    box.querySelectorAll('[data-act=set]').forEach((b) => (b.onclick = async () => {
      const prev = b.textContent;
      b.disabled = true;
      b.textContent = '试链中…';
      try {
        await apiFetch('/api/toa/releases/' + b.dataset.id + '/set-current', { method: 'POST' });
        toast('已设为当前版本（直链已校验）', 'ok');
        loadReleases();
      } catch (err) {
        toast(err.message || '设为当前失败', 'err');
      } finally {
        b.disabled = false;
        b.textContent = prev;
      }
    }));
    box.querySelectorAll('[data-act=edit]').forEach((b) => (b.onclick = () => openEditRelease(b.dataset.id)));
    box.querySelectorAll('[data-act=copy-url]').forEach((b) => (b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(b.dataset.url || '');
        toast('直链已复制', 'ok');
      } catch (err) {
        toast(err.message || '复制失败', 'err');
      }
    }));
  }

  document.getElementById('rel-reload').onclick = loadReleases;

  let DOWNLOAD_PAGE_DEFAULT = `${location.origin}/download/`;
  let INSTALLER_BASE = DOWNLOAD_PAGE_DEFAULT;
  fetch('/api/toa/releases/download-config', { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : null))
    .then((cfg) => {
      if (!cfg) return;
      DOWNLOAD_PAGE_DEFAULT = cfg.download_page || DOWNLOAD_PAGE_DEFAULT;
      INSTALLER_BASE = cfg.installer_base || INSTALLER_BASE;
    })
    .catch(() => {});
  const REL_DRAFT_KEY = 'toa_cloud_release_draft_v1';
  const relDialog = document.getElementById('dlg-rel-create');
  const relForm = document.getElementById('form-rel-create');
  const relVersion = document.getElementById('rel-version');
  const relDownloadUrl = document.getElementById('rel-download-url');
  const relMinVersion = document.getElementById('rel-min-version');
  const relNotes = document.getElementById('rel-notes');
  const relChannel = document.getElementById('rel-channel');
  const relCurrentLabel = document.getElementById('rel-current-label');
  const relPreview = document.getElementById('rel-manifest-preview');
  let relUrlTouched = false;

  function readReleaseDraft() {
    try {
      const raw = localStorage.getItem(REL_DRAFT_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      return data && typeof data === 'object' ? data : null;
    } catch (_err) {
      return null;
    }
  }

  function writeReleaseDraft() {
    try {
      const payload = {
        product: 'TOA3',
        channel: relChannel.value || 'stable',
        version: normalizeVersion(relVersion.value),
        download_url: (relDownloadUrl.value || '').trim(),
        download_page: (document.getElementById('rel-download-page').value || '').trim(),
        min_version: normalizeVersion(relMinVersion.value),
        release_notes: relNotes.value || '',
        is_current: !!document.getElementById('rel-is-current').checked,
        url_touched: !!relUrlTouched,
        saved_at: Date.now(),
      };
      // 空草稿不占坑
      if (!payload.version && !payload.release_notes && !payload.download_url) {
        localStorage.removeItem(REL_DRAFT_KEY);
        return;
      }
      localStorage.setItem(REL_DRAFT_KEY, JSON.stringify(payload));
    } catch (_err) {
      /* ignore quota / private mode */
    }
  }

  function clearReleaseDraft() {
    try {
      localStorage.removeItem(REL_DRAFT_KEY);
    } catch (_err) {
      /* ignore */
    }
  }

  function applyReleaseDraft(draft) {
    if (!draft) return false;
    if (draft.channel) relChannel.value = draft.channel;
    if (draft.version) relVersion.value = normalizeVersion(draft.version);
    if (draft.download_url && draft.url_touched) {
      relDownloadUrl.value = draft.download_url;
      relUrlTouched = true;
    } else if (draft.version) {
      relDownloadUrl.value = buildDownloadUrl(draft.version);
    }
    if (draft.download_page) document.getElementById('rel-download-page').value = draft.download_page;
    if (draft.min_version) relMinVersion.value = normalizeVersion(draft.min_version);
    if (draft.release_notes != null) relNotes.value = String(draft.release_notes);
    if (typeof draft.is_current === 'boolean') {
      document.getElementById('rel-is-current').checked = draft.is_current;
    }
    refreshReleasePreview();
    return true;
  }

  function normalizeVersion(raw) {
    return String(raw || '').trim().replace(/^v/i, '');
  }

  function buildDownloadUrl(version) {
    const v = normalizeVersion(version);
    return v ? `${INSTALLER_BASE}TOA3-Setup-v${v}.exe` : '';
  }

  function bumpVersion(version, kind) {
    const parts = normalizeVersion(version).split('.').map((n) => parseInt(n, 10) || 0);
    while (parts.length < 3) parts.push(0);
    if (kind === 'major') {
      parts[0] += 1;
      parts[1] = 0;
      parts[2] = 0;
    } else if (kind === 'minor') {
      parts[1] += 1;
      parts[2] = 0;
    } else {
      parts[2] += 1;
    }
    return parts.join('.');
  }

  function currentReleaseForChannel(channel) {
    const rows = window.__releaseRows || [];
    return rows.find((r) => r.is_current && r.channel === channel) || rows.find((r) => r.channel === channel);
  }

  function refreshReleasePreview() {
    const version = normalizeVersion(relVersion.value);
    const channel = relChannel.value || 'stable';
    const url = (relDownloadUrl.value || '').trim();
    if (!version) {
      relPreview.textContent = '填写版本号后将预览 manifest 关键字段。';
      return;
    }
    relPreview.innerHTML =
      `manifest 预览 · <strong>${channel}</strong> → v<strong>${version}</strong>` +
      (url ? ` · <a class="text-link" href="${url}" target="_blank" rel="noopener">安装包</a>` : ' · <span class="muted">未填直链</span>');
  }

  function prefillReleaseForm() {
    relUrlTouched = false;
    const channel = relChannel.value || 'stable';
    const current = currentReleaseForChannel(channel);
    const curVer = current ? normalizeVersion(current.version) : '';
    relCurrentLabel.textContent = curVer ? `v${curVer}` : '尚无当前版';
    const nextVer = curVer ? bumpVersion(curVer, 'patch') : '';
    relVersion.value = nextVer;
    relDownloadUrl.value = buildDownloadUrl(nextVer);
    relMinVersion.value = current?.min_version ? normalizeVersion(current.min_version) : '3.0.0';
    relNotes.value = '';
    document.getElementById('rel-download-page').value = current?.download_page || DOWNLOAD_PAGE_DEFAULT;
    document.getElementById('rel-is-current').checked = true;
    const draft = readReleaseDraft();
    if (draft && applyReleaseDraft(draft)) {
      toast('已恢复未发布草稿（关闭弹窗不会丢）', 'ok');
    }
    refreshReleasePreview();
  }

  relDownloadUrl.addEventListener('input', () => {
    relUrlTouched = true;
    writeReleaseDraft();
    refreshReleasePreview();
  });

  relVersion.addEventListener('input', () => {
    if (!relUrlTouched) relDownloadUrl.value = buildDownloadUrl(relVersion.value);
    writeReleaseDraft();
    refreshReleasePreview();
  });

  relChannel.addEventListener('change', prefillReleaseForm);
  relNotes.addEventListener('input', () => {
    writeReleaseDraft();
    refreshReleasePreview();
  });
  relMinVersion.addEventListener('input', writeReleaseDraft);
  document.getElementById('rel-download-page').addEventListener('input', writeReleaseDraft);
  document.getElementById('rel-is-current').addEventListener('change', writeReleaseDraft);

  document.getElementById('rel-bump-row').querySelectorAll('[data-bump]').forEach((btn) => {
    btn.onclick = () => {
      const base = normalizeVersion(relVersion.value) || normalizeVersion(relCurrentLabel.textContent.replace(/^v/i, ''));
      if (!base) return;
      const next = bumpVersion(base, btn.dataset.bump);
      relVersion.value = next;
      relUrlTouched = false;
      relDownloadUrl.value = buildDownloadUrl(next);
      refreshReleasePreview();
    };
  });

  document.getElementById('rel-url-test').onclick = async () => {
    const url = (relDownloadUrl.value || '').trim();
    if (!url) {
      toast('请先填写安装包直链', 'err');
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      toast('直链须以 http:// 或 https:// 开头', 'err');
      return;
    }
    const btn = document.getElementById('rel-url-test');
    const prev = btn.textContent;
    btn.disabled = true;
    btn.textContent = '校验中…';
    try {
      const check = await apiFetch('/api/toa/releases/verify-download', {
        method: 'POST',
        body: JSON.stringify({ download_url: url }),
      });
      if (check.ok) {
        const sizeHint = check.size_mb != null ? ` · ${check.size_mb} MB` : '';
        toast(`试链通过 HTTP ${check.status}${sizeHint}`, 'ok');
      } else {
        toast(
          `试链失败 HTTP ${check.status || '—'}（${check.reason || 'unreachable'}）`,
          'err',
        );
      }
    } catch (err) {
      toast(err.message || '试链请求失败', 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  };

  document.getElementById('rel-create').onclick = async () => {
    if (!window.__releaseRows) {
      try {
        await loadReleases();
      } catch (err) {
        toast(err.message || '加载发布记录失败', 'err');
        return;
      }
    }
    prefillReleaseForm();
    openDialog(relDialog, { focusEl: relVersion });
  };

  relDialog.addEventListener('close', async (e) => {
    if (e.target.returnValue !== 'ok') return;
    const fd = new FormData(relForm);
    const version = normalizeVersion(fd.get('version'));
    if (!/^\d+\.\d+\.\d+$/.test(version)) {
      toast('版本号须为 x.y.z 格式', 'err');
      openDialog(relDialog, { focusEl: relVersion });
      return;
    }
    const downloadUrl = String(fd.get('download_url') || '').trim();
    const notes = String(fd.get('release_notes') || '').trim();
    if (!downloadUrl && fd.get('is_current') === 'on') {
      toast('设为当前版时必须填写安装包直链', 'err');
      openDialog(relDialog, { focusEl: relDownloadUrl });
      return;
    }
    if (!notes && fd.get('is_current') === 'on') {
      toast('设为当前版时必须填写更新说明', 'err');
      openDialog(relDialog, { focusEl: relNotes });
      return;
    }
    try {
      await apiFetch('/api/toa/releases', {
        method: 'POST',
        body: JSON.stringify({
          product: fd.get('product') || 'TOA3',
          channel: fd.get('channel') || 'stable',
          version,
          download_url: downloadUrl,
          download_page: fd.get('download_page') || DOWNLOAD_PAGE_DEFAULT,
          min_version: normalizeVersion(fd.get('min_version')),
          release_notes: notes,
          is_current: fd.get('is_current') === 'on',
        }),
      });
      clearReleaseDraft();
      toast('版本已发布', 'ok');
      loadReleases();
      loadDashboard();
    } catch (err) {
      toast(err.message || '发布失败', 'err');
    }
  });

  const relEditDialog = document.getElementById('dlg-rel-edit');
  const relEditForm = document.getElementById('form-rel-edit');
  const relEditId = document.getElementById('rel-edit-id');
  const relEditUrl = document.getElementById('rel-edit-download-url');
  const relEditMin = document.getElementById('rel-edit-min-version');
  const relEditNotes = document.getElementById('rel-edit-notes');
  const relEditLabel = document.getElementById('rel-edit-version-label');

  function openEditRelease(id) {
    const rows = window.__releaseRows || [];
    const row = rows.find((r) => String(r.id) === String(id));
    if (!row) {
      toast('未找到发布记录', 'err');
      return;
    }
    relEditId.value = String(row.id);
    relEditLabel.textContent = `v${row.version} · ${row.product}/${row.channel}` +
      (row.is_current ? ' · 当前版' : '');
    relEditUrl.value = row.download_url || '';
    relEditMin.value = row.min_version || '';
    relEditNotes.value = row.release_notes || '';
    openDialog(relEditDialog, { focusEl: relEditNotes });
  }

  document.getElementById('rel-edit-url-test').onclick = async () => {
    const url = (relEditUrl.value || '').trim();
    if (!url) {
      toast('请先填写安装包直链', 'err');
      return;
    }
    const btn = document.getElementById('rel-edit-url-test');
    const prev = btn.textContent;
    btn.disabled = true;
    btn.textContent = '校验中…';
    try {
      const check = await apiFetch('/api/toa/releases/verify-download', {
        method: 'POST',
        body: JSON.stringify({ download_url: url }),
      });
      if (check.ok) {
        const sizeHint = check.size_mb != null ? ` · ${check.size_mb} MB` : '';
        toast(`试链通过 HTTP ${check.status}${sizeHint}`, 'ok');
      } else {
        toast(`试链失败（${check.reason || check.status || 'unreachable'}）`, 'err');
      }
    } catch (err) {
      toast(err.message || '试链失败', 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  };

  relEditDialog.addEventListener('close', async (e) => {
    if (e.target.returnValue !== 'ok') return;
    const id = relEditId.value;
    if (!id) return;
    try {
      await apiFetch('/api/toa/releases/' + id, {
        method: 'PATCH',
        body: JSON.stringify({
          download_url: (relEditUrl.value || '').trim(),
          min_version: normalizeVersion(relEditMin.value),
          release_notes: relEditNotes.value || '',
        }),
      });
      toast('发布记录已更新', 'ok');
      loadReleases();
      loadDashboard();
    } catch (err) {
      toast(err.message || '保存失败', 'err');
      openDialog(relEditDialog, { focusEl: relEditNotes });
    }
  });

  async function loadCustomers() {
    const box = document.getElementById('cust-list');
    setLoading(box);
    const q = document.getElementById('cust-q').value.trim();
    const en = document.getElementById('cust-enabled').value;
    const qs = new URLSearchParams();
    if (q) qs.set('q', q);
    if (en === '1') qs.set('enabled', 'true');
    if (en === '0') qs.set('enabled', 'false');
    try {
      const data = await apiFetch('/api/toa/customers?' + qs.toString());
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = emptyHtml('暂无用户（授权签发或订单履约后自动出现）');
        return;
      }
      box.innerHTML = `<table class="data-table"><thead><tr>
        <th>姓名</th><th>手机</th><th>授权类型</th><th>方案/订单</th><th>到期</th><th>订单数</th><th>插件</th><th>状态</th><th>操作</th>
      </tr></thead><tbody>${items
        .map((c) => {
          const st = c.enabled ? '<span class="tag ok">启用</span>' : '<span class="tag bad">停用</span>';
          const act = c.enabled
            ? `<button type="button" class="danger cust-disable" data-id="${c.id}">停用</button>`
            : `<button type="button" class="primary cust-enable" data-id="${c.id}">启用</button>`;
          const planOrder = [
            c.plan_id ? `<code>${escapeHtml(c.plan_id)}</code>` : '',
            c.order_no ? escapeHtml(c.order_no) : '',
          ]
            .filter(Boolean)
            .join('<br>') || '—';
          return `<tr>
            <td>${escapeHtml(c.display_name || '—')}</td>
            <td>${escapeHtml(c.phone || '—')}</td>
            <td>${escapeHtml(c.entitlement_label || '—')}</td>
            <td>${planOrder}</td>
            <td>${escapeHtml(c.expire_date || '—')}</td>
            <td>${c.order_count ?? 0}</td>
            <td>${c.plugin_count ?? 0}</td>
            <td>${st}</td>
            <td class="row-actions">${act}</td>
          </tr>`;
        })
        .join('')}</tbody></table>`;
      box.querySelectorAll('.cust-enable').forEach((btn) => {
        btn.onclick = async () => {
          try {
            await apiFetch(`/api/toa/customers/${btn.dataset.id}/enable`, { method: 'POST', body: '{}' });
            toast('已启用', 'ok');
            loadCustomers();
          } catch (e) {
            toast(e.message || '失败', 'err');
          }
        };
      });
      box.querySelectorAll('.cust-disable').forEach((btn) => {
        btn.onclick = async () => {
          if (!confirm('停用后该账号无法上传/下载社区插件，确认？')) return;
          try {
            await apiFetch(`/api/toa/customers/${btn.dataset.id}/disable`, { method: 'POST', body: '{}' });
            toast('已停用', 'ok');
            loadCustomers();
          } catch (e) {
            toast(e.message || '失败', 'err');
          }
        };
      });
    } catch (e) {
      box.innerHTML = emptyHtml(e.message || '加载失败');
    }
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function pluginStatusTag(s) {
    return (
      {
        submitted: ['待审', 'warn'],
        approved: ['已通过', 'ok'],
        rejected: ['已驳回', 'bad'],
        delisted: ['已下架', ''],
      }[s] || [s || '—', '']
    );
  }

  async function plugAction(id, action, extra) {
    await apiFetch(`/api/toa-soft-assets/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, ...(extra || {}) }),
    });
  }

  async function loadPlugins() {
    const box = document.getElementById('plug-list');
    setLoading(box);
    const q = document.getElementById('plug-q').value.trim();
    const status = document.getElementById('plug-status').value;
    const qs = new URLSearchParams();
    if (q) qs.set('q', q);
    if (status) qs.set('status', status);
    try {
      const data = await apiFetch('/api/toa-soft-assets/admin/list?' + qs.toString());
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = emptyHtml('暂无办公插件投稿');
        return;
      }
      box.innerHTML = `<table class="data-table"><thead><tr>
        <th>ID</th><th>名称</th><th>plugin_id</th><th>版本</th><th>作者</th><th>审态</th><th>上架</th><th>启用</th><th>推荐</th><th>操作</th>
      </tr></thead><tbody>${items
        .map((p) => {
          const [lab, cls] = pluginStatusTag(p.review_status);
          const listed = p.listed ? '是' : '否';
          const en = p.enabled ? '<span class="tag ok">启</span>' : '<span class="tag bad">停</span>';
          const rec = p.recommended ? '<span class="tag ok">荐</span>' : '—';
          const btns = [];
          if (p.review_status === 'submitted') {
            btns.push(`<button type="button" class="primary plug-act" data-id="${p.id}" data-act="approve">通过并上架</button>`);
            btns.push(`<button type="button" class="danger plug-act" data-id="${p.id}" data-act="reject">驳回</button>`);
          }
          if (p.review_status === 'approved' && !p.listed) {
            btns.push(`<button type="button" class="primary plug-act" data-id="${p.id}" data-act="list">上架</button>`);
          }
          if (p.listed) {
            btns.push(`<button type="button" class="plug-act" data-id="${p.id}" data-act="unlist">下架</button>`);
          }
          if (p.enabled) {
            btns.push(`<button type="button" class="danger plug-act" data-id="${p.id}" data-act="disable">停用</button>`);
          } else {
            btns.push(`<button type="button" class="primary plug-act" data-id="${p.id}" data-act="enable">启用</button>`);
          }
          if (p.listed && p.enabled && p.review_status === 'approved') {
            if (p.recommended) {
              btns.push(`<button type="button" class="plug-act" data-id="${p.id}" data-act="unrecommend">取消推荐</button>`);
            } else {
              btns.push(`<button type="button" class="primary plug-act" data-id="${p.id}" data-act="recommend">设为推荐</button>`);
            }
          }
          return `<tr>
            <td>${p.id}</td>
            <td title="${escapeHtml(p.description || '')}">${escapeHtml(p.name)}</td>
            <td><code>${escapeHtml(p.plugin_id)}</code></td>
            <td>${escapeHtml(p.version)}</td>
            <td>${escapeHtml(p.author || '—')}</td>
            <td><span class="tag ${cls}">${lab}</span></td>
            <td>${listed}</td>
            <td>${en}</td>
            <td>${rec}</td>
            <td class="row-actions">${btns.join(' ')}</td>
          </tr>`;
        })
        .join('')}</tbody></table>`;
      box.querySelectorAll('.plug-act').forEach((btn) => {
        btn.onclick = async () => {
          const act = btn.dataset.act;
          let extra = {};
          if (act === 'reject') {
            const reason = prompt('驳回原因', '未通过安全/质量审核');
            if (reason === null) return;
            extra.reject_reason = reason;
          }
          if (act === 'unlist' && !confirm('下架后终端公示不再显示，确认？')) return;
          if (act === 'disable' && !confirm('停用后即使已上架也不可下载，确认？')) return;
          try {
            await plugAction(btn.dataset.id, act, extra);
            toast('已更新', 'ok');
            loadPlugins();
          } catch (e) {
            toast(e.message || '失败', 'err');
          }
        };
      });
    } catch (e) {
      box.innerHTML = emptyHtml(e.message || '加载失败');
    }
  }

  async function loadTraffic() {
    const box = document.getElementById('traf-list');
    setLoading(box);
    const qs = new URLSearchParams();
    const kind = document.getElementById('traf-kind').value;
    const plugin = document.getElementById('traf-plugin').value.trim();
    const cid = document.getElementById('traf-customer').value.trim();
    if (kind) qs.set('event_kind', kind);
    if (plugin) qs.set('plugin_id', plugin);
    if (cid) qs.set('customer_id', cid);
    try {
      const data = await apiFetch('/api/toa-soft-assets/admin/events?' + qs.toString());
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = emptyHtml('暂无流水');
        return;
      }
      box.innerHTML = `<table class="data-table"><thead><tr>
        <th>时间</th><th>事件</th><th>账号</th><th>插件</th><th>版本</th><th>结果</th><th>详情</th>
      </tr></thead><tbody>${items
        .map((e) => {
          const kindLab = e.event_kind === 'upload' ? '上传' : e.event_kind === 'download' ? '下载' : e.event_kind;
          return `<tr>
            <td>${escapeHtml((e.created_at || '').replace('T', ' ').slice(0, 19))}</td>
            <td>${kindLab}</td>
            <td>${e.customer_id ?? '—'}</td>
            <td><code>${escapeHtml(e.plugin_id)}</code></td>
            <td>${escapeHtml(e.version)}</td>
            <td>${escapeHtml(e.result)}</td>
            <td>${escapeHtml(e.detail || '')}</td>
          </tr>`;
        })
        .join('')}</tbody></table>`;
    } catch (e) {
      box.innerHTML = emptyHtml(e.message || '加载失败');
    }
  }

  document.getElementById('cust-reload').onclick = () => loadCustomers();
  document.getElementById('cust-q').onkeydown = (e) => {
    if (e.key === 'Enter') loadCustomers();
  };
  document.getElementById('cust-enabled').onchange = () => loadCustomers();
  document.getElementById('plug-reload').onclick = () => loadPlugins();
  document.getElementById('plug-q').onkeydown = (e) => {
    if (e.key === 'Enter') loadPlugins();
  };
  document.getElementById('plug-status').onchange = () => loadPlugins();
  document.getElementById('traf-reload').onclick = () => loadTraffic();

  loadPackCatalog().then(loadDashboard);
})();
