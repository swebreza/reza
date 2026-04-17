/**
 * graph.js — D3 v7 force-directed graph for the Reza VS Code extension.
 *
 * Message protocol (extension ↔ webview):
 *   extension → webview  { type: 'init',              data: GraphPayload }
 *   extension → webview  { type: 'updateSessionState', data: SessionOnlyPayload }
 *   webview  → extension { type: 'openFile',           file_path, line_start }
 *   webview  → extension { type: 'ready' }
 *   webview  → extension { type: 'refresh' }
 */

'use strict';

/* ---------- VS Code API bridge ---------- */
const vscode = typeof acquireVsCodeApi === 'function' ? acquireVsCodeApi() : null;
function postMsg(msg) { if (vscode) vscode.postMessage(msg); }

/* ---------- State ---------- */
let nodes = [];
let edges = [];
let activeSession = null;
let simulation = null;
let svgSel = null;
let zoomBeh = null;

let activeKindFilters = new Set(['Class', 'Function', 'Test']);
let activeEdgeFilters = new Set(['CALLS', 'IMPORTS_FROM', 'INHERITS', 'TESTED_BY']);
let searchQuery = '';
let nodeStatesMap = {};   // id → state (for session-only updates)

/* ---------- Colour helpers ---------- */
const STATE_COL = {
  locked: '#ff4c4c',
  hot:    '#f97316',
  warm:   '#eab308',
  blast:  '#a78bfa',
  cold:   '#4b5563',
};

const EDGE_COL = {
  CALLS:       '#3b82f6',
  IMPORTS_FROM:'#22c55e',
  INHERITS:    '#a78bfa',
  CONTAINS:    '#6b7280',
  TESTED_BY:   '#f59e0b',
  default:     '#4b5563',
};

const KIND_COL = {
  File:     '#6b7280',
  Class:    '#7c3aed',
  Function: '#0ea5e9',
  Test:     '#f59e0b',
};

const TOOL_COL = {
  purple:     '#9b59b6',
  'deep-orange':'#e8501a',
  blue:       '#3b82f6',
  steel:      '#6b7280',
};

function nodeColor(d) {
  const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
  if (st === 'locked') return STATE_COL.locked;
  if (st === 'hot')    return STATE_COL.hot;
  if (st === 'warm')   return STATE_COL.warm;
  if (st === 'blast')  return STATE_COL.blast;
  // fall back to kind colour for cold nodes
  return KIND_COL[d.kind] ?? '#4b5563';
}

function nodeRadius(d) {
  const base = d.kind === 'File' ? 8 : d.kind === 'Class' ? 10 : 7;
  return Math.min(22, base + Math.sqrt(d.degree ?? 0) * 1.4);
}

function edgeColor(e) { return EDGE_COL[e.kind] ?? EDGE_COL.default; }

function edgeMarker(e) {
  const k = e.kind;
  if (k === 'CALLS') return 'url(#arrow-calls)';
  if (k === 'IMPORTS_FROM') return 'url(#arrow-imports)';
  if (k === 'INHERITS') return 'url(#arrow-inherits)';
  return 'url(#arrow-default)';
}

/* ---------- Overlay / loading ---------- */
const overlayEl     = document.getElementById('overlay');
const overlayMsg    = document.getElementById('overlay-msg');
const overlayErr    = document.getElementById('overlay-err');
const overlaySpin   = document.getElementById('overlay-spinner');
const ctaEl         = document.getElementById('cta');
const ctaTitle      = document.getElementById('cta-title');
const ctaDesc       = document.getElementById('cta-desc');
const ctaPath       = document.getElementById('cta-path');
const ctaButtons    = document.getElementById('cta-buttons');
const ctaHint       = document.getElementById('cta-hint');

function showLoading(msg) {
  overlayEl.classList.remove('hidden');
  overlayMsg.textContent = msg || 'Loading…';
  overlayErr.textContent = '';
  overlaySpin.style.display = '';
  ctaEl.classList.remove('visible');
}

function showError(err) {
  overlayEl.classList.remove('hidden');
  overlayMsg.textContent = '';
  overlayErr.textContent = err;
  overlaySpin.style.display = 'none';
  ctaEl.classList.remove('visible');
}

function hideOverlay() {
  overlayEl.classList.add('hidden');
  overlaySpin.style.display = '';
  ctaEl.classList.remove('visible');
}

/** Render a CTA inside the overlay (needs-init / needs-build).
 *  buttons: Array<{label, action, secondary?:boolean}> */
function showCTA({ title, desc, path: workspacePath, buttons, hint }) {
  overlayEl.classList.remove('hidden');
  overlayMsg.textContent = '';
  overlayErr.textContent = '';
  overlaySpin.style.display = 'none';

  ctaTitle.textContent = title;
  ctaDesc.textContent  = desc;
  ctaPath.textContent  = workspacePath || '';
  ctaPath.style.display = workspacePath ? 'block' : 'none';
  ctaHint.textContent   = hint || '';
  ctaHint.style.display = hint ? 'block' : 'none';

  ctaButtons.innerHTML = '';
  for (const b of buttons) {
    const btn = document.createElement('button');
    btn.textContent = b.label;
    if (b.secondary) btn.classList.add('secondary');
    btn.addEventListener('click', () => postMsg({ type: b.action }));
    ctaButtons.appendChild(btn);
  }

  ctaEl.classList.add('visible');
}

/* ---------- Build / render graph ---------- */
function buildGraph(payload) {
  nodes = payload.nodes ?? [];
  edges = payload.edges ?? [];
  activeSession = payload.session ?? null;

  // seed nodeStatesMap
  nodeStatesMap = {};
  for (const n of nodes) nodeStatesMap[n.id] = n.state ?? 'cold';

  // Render sidebar + workspace info first so empty-state still shows context
  renderSidebar(activeSession, payload.stats, payload);

  // Empty-state CTAs based on payload flags
  if (payload.needsInit) {
    showCTA({
      title: 'Reza is not initialized in this project',
      desc: 'Set up Reza here to build a code knowledge graph and auto-track your LLM sessions. One click does everything.',
      path: payload.workspaceRoot || '',
      buttons: [
        { label: 'Initialize & Build Graph', action: 'initAndBuild' },
        { label: 'Start Auto-Tracking', action: 'startTracking', secondary: true },
      ],
      hint: 'This runs `reza init` + `reza graph build` in a terminal. Auto-refreshes the moment the graph is ready.',
    });
    return;
  }

  if (payload.needsBuild) {
    showCTA({
      title: 'Graph is empty for this project',
      desc: 'The database is initialized, but the code graph has not been built yet. Build it now to see all files, classes and functions as a live graph.',
      path: payload.dbPath || payload.workspaceRoot || '',
      buttons: [
        { label: 'Build Graph Now', action: 'buildGraph' },
        { label: 'Start Auto-Tracking', action: 'startTracking', secondary: true },
      ],
      hint: payload.errorMessage
        ? 'Last attempt: ' + payload.errorMessage
        : 'This runs `reza graph build` in a terminal. The panel refreshes automatically when done.',
    });
    return;
  }

  hideOverlay();
  renderD3();
}

/* ---------- D3 render ---------- */
function renderD3() {
  const wrap = document.getElementById('graph-wrap');
  const W = wrap.clientWidth;
  const H = wrap.clientHeight;

  // filter nodes + edges
  const visibleNodeIds = new Set(
    nodes.filter(n => activeKindFilters.has(n.kind)).map(n => n.id)
  );

  const visibleNodes = nodes.filter(n => visibleNodeIds.has(n.id));
  const visibleEdges = edges.filter(e =>
    activeEdgeFilters.has(e.kind)
    && visibleNodeIds.has(e.source?.id ?? e.source)
    && visibleNodeIds.has(e.target?.id ?? e.target)
  );

  // build lookup for simulation (D3 mutates source/target to objects)
  const nodeById = new Map(visibleNodes.map(n => [n.id, n]));

  const linkData = visibleEdges.map(e => ({
    ...e,
    source: nodeById.get(e.source?.id ?? e.source) ?? e.source,
    target: nodeById.get(e.target?.id ?? e.target) ?? e.target,
  }));

  // stop previous sim
  if (simulation) simulation.stop();

  svgSel = d3.select('svg#graph');
  const canvas = svgSel.select('#canvas');
  const edgesLayer = canvas.select('#edges-layer');
  const nodesLayer = canvas.select('#nodes-layer');

  edgesLayer.selectAll('*').remove();
  nodesLayer.selectAll('*').remove();

  // zoom behaviour
  if (!zoomBeh) {
    zoomBeh = d3.zoom()
      .scaleExtent([0.05, 4])
      .on('zoom', ev => canvas.attr('transform', ev.transform));
    svgSel.call(zoomBeh);
    svgSel.on('dblclick.zoom', null);
  }

  /* ---- Edges ---- */
  const edgeSel = edgesLayer
    .selectAll('line.edge')
    .data(linkData, d => `${d.source?.id ?? d.source}→${d.target?.id ?? d.target}→${d.kind}`)
    .join('line')
    .attr('class', 'edge')
    .attr('stroke', edgeColor)
    .attr('stroke-width', d => Math.max(0.5, (d.confidence ?? 1) * 1.5))
    .attr('marker-end', edgeMarker);

  /* ---- Nodes ---- */
  const nodeSel = nodesLayer
    .selectAll('g.node')
    .data(visibleNodes, d => d.id)
    .join('g')
    .attr('class', 'node')
    .call(
      d3.drag()
        .on('start', dragStart)
        .on('drag',  dragged)
        .on('end',   dragEnd)
    )
    .on('click', nodeClicked)
    .on('mouseover', nodeMouseover)
    .on('mouseout',  nodeMouseout);

  // pulse ring for locked nodes
  nodeSel.each(function(d) {
    const g = d3.select(this);
    const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
    if (st === 'locked') {
      g.append('circle')
        .attr('class', 'locked-ring')
        .attr('r', nodeRadius(d) + 5)
        .style('--r', `${nodeRadius(d) + 5}px`);
    }
  });

  nodeSel.append('circle')
    .attr('r', nodeRadius)
    .attr('fill', nodeColor)
    .attr('stroke', d => {
      const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
      if (st === 'locked') return STATE_COL.locked;
      if (st === 'hot')    return '#fb923c';
      if (st === 'blast')  return STATE_COL.blast;
      return '#374151';
    });

  nodeSel.append('text')
    .attr('dy', d => nodeRadius(d) + 11)
    .attr('text-anchor', 'middle')
    .text(d => d.name.length > 18 ? d.name.slice(0, 16) + '…' : d.name);

  /* ---- Simulation ---- */
  simulation = d3.forceSimulation(visibleNodes)
    .force('link', d3.forceLink(linkData)
      .id(d => d.id)
      .distance(70)
      .strength(0.3)
    )
    .force('charge', d3.forceManyBody().strength(-180).distanceMax(350))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide(d => nodeRadius(d) + 4))
    .on('end', () => {
      if (typeof window.__rezaFitToView === 'function') window.__rezaFitToView(600);
    })
    .on('tick', () => {
      edgeSel
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => {
          // shorten line so it doesn't overlap node circle
          const r = nodeRadius(d.target);
          const dx = d.target.x - d.source.x;
          const dy = d.target.y - d.source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          return d.target.x - (dx / dist) * (r + 6);
        })
        .attr('y2', d => {
          const r = nodeRadius(d.target);
          const dx = d.target.x - d.source.x;
          const dy = d.target.y - d.source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          return d.target.y - (dy / dist) * (r + 6);
        });

      nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    });

  applySearch();
}

/* ---------- Drag ---------- */
function dragStart(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
function dragEnd(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

/* ---------- Click → open file ---------- */
function nodeClicked(event, d) {
  event.stopPropagation();
  if (d.file_path) {
    postMsg({ type: 'openFile', file_path: d.file_path, line_start: d.line_start ?? 1 });
  }
}

/* ---------- Tooltip ---------- */
const tooltip = document.getElementById('tooltip');

const STATE_BADGE_STYLE = {
  locked: 'background:#ff4c4c22;color:#ff4c4c;',
  hot:    'background:#f9731622;color:#f97316;',
  warm:   'background:#eab30822;color:#eab308;',
  blast:  'background:#a78bfa22;color:#a78bfa;',
  cold:   'background:#4b556322;color:#8b949e;',
};

function nodeMouseover(event, d) {
  const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
  const badgeStyle = STATE_BADGE_STYLE[st] ?? STATE_BADGE_STYLE.cold;
  tooltip.innerHTML = `
    <div class="tt-kind">${d.kind}${d.language ? ' · ' + d.language : ''}</div>
    <div class="tt-name">${escHtml(d.name)}</div>
    ${d.params ? `<div style="color:#8b949e;font-size:10px;margin-top:2px;">${escHtml(d.params)}</div>` : ''}
    <div class="tt-file">${escHtml(d.file_path)}${d.line_start ? ':' + d.line_start : ''}</div>
    <div class="tt-state"><span class="tt-badge" style="${badgeStyle}">${st.toUpperCase()}</span>
      ${d.degree ? `<span style="color:#8b949e;font-size:10px;margin-left:6px;">${d.degree} connections</span>` : ''}
    </div>
  `;
  tooltip.style.opacity = '1';
  moveTooltip(event);
}

function nodeMouseout() { tooltip.style.opacity = '0'; }

document.addEventListener('mousemove', ev => {
  if (tooltip.style.opacity === '1') moveTooltip(ev);
});

function moveTooltip(event) {
  const wrap = document.getElementById('graph-wrap');
  const rect  = wrap.getBoundingClientRect();
  let x = event.clientX - rect.left + 14;
  let y = event.clientY - rect.top  + 14;
  if (x + 270 > rect.width)  x = event.clientX - rect.left - 280;
  if (y + 120 > rect.height) y = event.clientY - rect.top  - 130;
  tooltip.style.left = x + 'px';
  tooltip.style.top  = y + 'px';
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ---------- Search ---------- */
document.getElementById('search-box').addEventListener('input', function() {
  searchQuery = this.value.trim().toLowerCase();
  applySearch();
});

function applySearch() {
  if (!simulation) return;
  const nodesLayer = d3.select('#nodes-layer');
  const edgesLayer = d3.select('#edges-layer');

  if (!searchQuery) {
    nodesLayer.selectAll('.node circle').classed('dimmed', false);
    nodesLayer.selectAll('.node text').classed('dimmed', false);
    edgesLayer.selectAll('.edge').classed('hidden', false);
    return;
  }

  const matchIds = new Set(
    nodes
      .filter(n => n.name.toLowerCase().includes(searchQuery)
                || (n.file_path ?? '').toLowerCase().includes(searchQuery))
      .map(n => n.id)
  );

  nodesLayer.selectAll('g.node').each(function(d) {
    const matched = matchIds.has(d.id);
    d3.select(this).select('circle').classed('dimmed', !matched);
    d3.select(this).select('text').classed('dimmed', !matched);
  });

  edgesLayer.selectAll('line.edge').classed('hidden', d => {
    const srcId = d.source?.id ?? d.source;
    const tgtId = d.target?.id ?? d.target;
    return !matchIds.has(srcId) && !matchIds.has(tgtId);
  });
}

/* ---------- Filters ---------- */
document.querySelectorAll('.chip[data-filter]').forEach(chip => {
  chip.addEventListener('click', function() {
    this.classList.toggle('active');
    const filter = this.dataset.filter;
    const val = this.dataset.val;

    if (filter === 'kind') {
      if (this.classList.contains('active')) activeKindFilters.add(val);
      else activeKindFilters.delete(val);
      renderD3();
    } else if (filter === 'edge') {
      if (this.classList.contains('active')) activeEdgeFilters.add(val);
      else activeEdgeFilters.delete(val);
      // just hide/show edges without restarting simulation
      d3.selectAll('line.edge').each(function(d) {
        const show = activeEdgeFilters.has(d.kind);
        d3.select(this).classed('hidden', !show);
      });
    }
  });
});

/* ---------- Refresh button ---------- */
document.getElementById('btn-refresh').addEventListener('click', () => {
  showLoading('Refreshing…');
  postMsg({ type: 'refresh' });
});

/* ---------- Sidebar collapse toggle (persisted in sessionStorage) ---------- */
const sidebarEl = document.getElementById('sidebar');
const sidebarToggleBtn = document.getElementById('sidebar-toggle');

function applySidebarState(collapsed) {
  if (collapsed) {
    sidebarEl.classList.add('collapsed');
    sidebarToggleBtn.setAttribute('aria-expanded', 'false');
  } else {
    sidebarEl.classList.remove('collapsed');
    sidebarToggleBtn.setAttribute('aria-expanded', 'true');
  }
  // Let CSS transition complete before re-centering simulation.
  setTimeout(handleResize, 220);
}

try {
  const saved = sessionStorage.getItem('reza.sidebarCollapsed');
  if (saved === '1') applySidebarState(true);
  else applySidebarState(false);
} catch (_) {
  applySidebarState(false);
}

sidebarToggleBtn.addEventListener('click', () => {
  const next = !sidebarEl.classList.contains('collapsed');
  applySidebarState(next);
  try { sessionStorage.setItem('reza.sidebarCollapsed', next ? '1' : '0'); } catch (_) {}
});

/* ---------- Window resize: recenter force + refit zoom ---------- */
let resizeRaf = 0;
function handleResize() {
  if (resizeRaf) cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = 0;
    const wrap = document.getElementById('graph-wrap');
    if (!wrap) return;
    const W = wrap.clientWidth;
    const H = wrap.clientHeight;
    if (!simulation || W === 0 || H === 0) return;
    simulation.force('center', d3.forceCenter(W / 2, H / 2));
    simulation.alpha(0.25).restart();
  });
}

window.addEventListener('resize', handleResize);

/* Also react when the panel itself is resized inside VS Code even if the
   window size doesn't change (e.g. sidebar toggle). */
if (typeof ResizeObserver === 'function') {
  const ro = new ResizeObserver(handleResize);
  ro.observe(document.getElementById('graph-wrap'));
}

/* ---------- Fit-to-view helper ---------- */
function fitToView(durationMs = 400) {
  if (!svgSel || !zoomBeh) return;
  const wrap = document.getElementById('graph-wrap');
  if (!wrap) return;
  const W = wrap.clientWidth;
  const H = wrap.clientHeight;
  if (W === 0 || H === 0) return;

  const visible = nodes.filter(n => activeKindFilters.has(n.kind) && typeof n.x === 'number');
  if (!visible.length) return;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of visible) {
    const r = nodeRadius(n) + 8;
    if (n.x - r < minX) minX = n.x - r;
    if (n.y - r < minY) minY = n.y - r;
    if (n.x + r > maxX) maxX = n.x + r;
    if (n.y + r > maxY) maxY = n.y + r;
  }
  const gw = Math.max(1, maxX - minX);
  const gh = Math.max(1, maxY - minY);
  const scale = Math.min(W / gw, H / gh) * 0.9;
  const k = Math.max(0.05, Math.min(4, scale));
  const tx = (W - k * (minX + maxX)) / 2;
  const ty = (H - k * (minY + maxY)) / 2;
  svgSel.transition().duration(durationMs).call(
    zoomBeh.transform,
    d3.zoomIdentity.translate(tx, ty).scale(k)
  );
}

/* Expose for debugging / keyboard shortcut */
window.__rezaFitToView = fitToView;

/* ---------- Sidebar renderer ---------- */
function renderSidebar(session, stats, payload) {
  const content = document.getElementById('session-content');
  const timeEl  = document.getElementById('session-time');

  if (stats) {
    timeEl.textContent = stats.last_updated
      ? 'Updated ' + relativeTime(stats.last_updated)
      : '';
  }

  const projectBlock = payload
    ? `<div class="sidebar-section" style="padding:10px 14px;">
         <div class="stat-label" style="margin-bottom:4px;">Project</div>
         <div style="font-size:11px;color:var(--text);word-break:break-all;">${escHtml(shortenPath(payload.workspaceRoot ?? ''))}</div>
         ${payload.dbPath ? `<div style="font-size:10px;color:var(--text-dim);margin-top:3px;word-break:break-all;">${escHtml(shortenPath(payload.dbPath))}</div>` : '<div style="font-size:10px;color:var(--col-hot);margin-top:3px;">no context.db</div>'}
       </div>`
    : '';

  if (!session) {
    content.innerHTML = projectBlock + '<div id="no-session">No active session detected.</div>';
    if (stats) {
      content.innerHTML += `
        <div class="sidebar-section">
          <div class="stat-row"><span class="stat-label">Total nodes</span><span class="stat-val">${stats.total_nodes ?? 0}</span></div>
          <div class="stat-row"><span class="stat-label">Total edges</span><span class="stat-val">${stats.total_edges ?? 0}</span></div>
          <div class="stat-row"><span class="stat-label">Files indexed</span><span class="stat-val">${stats.files_count ?? 0}</span></div>
        </div>`;
    }
    return;
  }

  const tc = session.toolColour ?? 'steel';
  const toolHex = TOOL_COL[tc] ?? '#6b7280';
  const hist = session.histogram ?? {};

  const total = Object.values(hist).reduce((a, b) => a + b, 0) || 1;
  function hbar(state, col) {
    const pct = ((hist[state] ?? 0) / total * 100).toFixed(1);
    return `<div class="hbar" style="background:${col};width:${pct}%;"></div>`;
  }

  content.innerHTML = projectBlock + `
    <div class="sidebar-section">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span class="session-badge" style="background:${toolHex}22;color:${toolHex};">
          <span class="pulse"></span>
          ${escHtml(session.llm_name || 'LLM')}
        </span>
        <span style="color:var(--text-dim);font-size:10px;">${escHtml(session.id?.slice(0,12) ?? '')}</span>
      </div>
      ${session.working_on ? `<div style="color:var(--text-dim);font-size:11px;margin-bottom:6px;">Working on: <span style="color:var(--text);">${escHtml(session.working_on)}</span></div>` : ''}

      <div class="stat-row"><span class="stat-label">Locked files</span><span class="stat-val" style="color:var(--col-locked);">${session.locked_files?.length ?? 0}</span></div>
      <div class="stat-row"><span class="stat-label">Hot files</span><span class="stat-val" style="color:var(--col-hot);">${session.hot_files?.length ?? 0}</span></div>
      <div class="stat-row"><span class="stat-label">Blast radius</span><span class="stat-val" style="color:var(--col-blast);">${session.blast_files?.length ?? 0} files</span></div>

      <div class="histogram" style="margin-top:10px;">
        ${hbar('locked', STATE_COL.locked)}
        ${hbar('hot',    STATE_COL.hot)}
        ${hbar('warm',   STATE_COL.warm)}
        ${hbar('blast',  STATE_COL.blast)}
        ${hbar('cold',   STATE_COL.cold)}
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:3px;">
        <span style="font-size:9px;color:var(--col-locked);">lock ${hist.locked ?? 0}</span>
        <span style="font-size:9px;color:var(--col-hot);">hot ${hist.hot ?? 0}</span>
        <span style="font-size:9px;color:var(--col-blast);">blast ${hist.blast ?? 0}</span>
        <span style="font-size:9px;color:var(--text-dim);">cold ${hist.cold ?? 0}</span>
      </div>
    </div>

    ${session.locked_files?.length ? `
    <div class="sidebar-section">
      <div style="color:var(--col-locked);font-size:11px;font-weight:600;margin-bottom:5px;">🔒 Locked</div>
      <div id="locked-files-list">
        ${session.locked_files.map(f => fileItem(f, STATE_COL.locked)).join('')}
      </div>
    </div>` : ''}

    ${session.hot_files?.length ? `
    <div class="sidebar-section">
      <div style="color:var(--col-hot);font-size:11px;font-weight:600;margin-bottom:5px;">🔥 Hot files</div>
      <div id="hot-files-list">
        ${session.hot_files.map(f => fileItem(f, STATE_COL.hot)).join('')}
      </div>
    </div>` : ''}
  `;

  // click file items → open file
  content.querySelectorAll('.file-item').forEach(el => {
    el.addEventListener('click', () => {
      postMsg({ type: 'openFile', file_path: el.dataset.path, line_start: 1 });
    });
  });
}

function fileItem(path, dotColor) {
  const short = path.split(/[\\/]/).slice(-2).join('/');
  return `<div class="file-item" data-path="${escHtml(path)}" title="${escHtml(path)}">
    <span class="fi-dot" style="background:${dotColor};"></span>
    <span class="fi-name">${escHtml(short)}</span>
  </div>`;
}

function shortenPath(p) {
  if (!p) return '';
  // Keep last 3 segments for readability
  const sep = p.includes('\\') ? '\\' : '/';
  const parts = p.split(sep).filter(Boolean);
  if (parts.length <= 3) return p;
  return '…' + sep + parts.slice(-3).join(sep);
}

function relativeTime(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)   return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400)return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

/* ---------- Session-only update (no graph re-render) ---------- */
function applySessionUpdate(payload) {
  activeSession = payload.session ?? null;

  if (payload.nodeStates) {
    for (const [id, state] of Object.entries(payload.nodeStates)) {
      nodeStatesMap[id] = state;
    }
  }

  // smooth colour transition
  d3.select('#nodes-layer')
    .selectAll('g.node')
    .transition()
    .duration(500)
    .select('circle')
    .attr('fill', d => nodeColor(d))
    .attr('stroke', d => {
      const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
      if (st === 'locked') return STATE_COL.locked;
      if (st === 'hot')    return '#fb923c';
      if (st === 'blast')  return STATE_COL.blast;
      return '#374151';
    });

  // update locked rings
  d3.select('#nodes-layer').selectAll('g.node').each(function(d) {
    const g = d3.select(this);
    const st = nodeStatesMap[d.id] ?? d.state ?? 'cold';
    g.select('.locked-ring').remove();
    if (st === 'locked') {
      g.insert('circle', ':first-child')
        .attr('class', 'locked-ring')
        .attr('r', nodeRadius(d) + 5)
        .style('--r', `${nodeRadius(d) + 5}px`);
    }
  });

  renderSidebar(activeSession, null, null);
}

/* ========================================================================
   Cross-tool sessions browser
   ------------------------------------------------------------------------
   Renders the list of imported Cursor/Codex/Claude sessions in the sidebar
   and wires click-to-scope onto the graph.  When a session is selected the
   webview either *highlights* the files/nodes it touched (default) or
   *filters* the graph down to just its subgraph.
   ======================================================================== */

const sessState = {
  sessions: [],
  selectedId: null,
  selectedScope: null,   // { files, node_ids }
  mode: (sessionStorage.getItem('reza:sessionMode') || 'highlight'),  // 'highlight' | 'subgraph'
  source: (sessionStorage.getItem('reza:sessionSource') || 'all'),
};

function sessionsSendListRequest() {
  postMsg({ type: 'listSessions', source: sessState.source, limit: 80 });
}

function relativeAge(iso) {
  if (!iso) return '—';
  const d = Date.parse(iso);
  if (isNaN(d)) return iso;
  const diff = (Date.now() - d) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function renderSessionsList() {
  const listEl = document.getElementById('sessions-list');
  const emptyEl = document.getElementById('sessions-empty');
  const countEl = document.getElementById('sp-count');
  if (!listEl || !emptyEl) return;

  countEl.textContent = sessState.sessions.length
    ? `(${sessState.sessions.length})`
    : '';

  if (sessState.sessions.length === 0) {
    listEl.innerHTML = '';
    emptyEl.style.display = 'block';
    return;
  }
  emptyEl.style.display = 'none';

  const rows = sessState.sessions.map(s => {
    const tool = (s.source_tool || 'manual').toLowerCase();
    const taskText = (s.working_on || s.first_user_message || '(no summary)')
      .replace(/\s+/g, ' ');
    const shortId = s.id.length > 26 ? s.id.slice(0, 24) + '…' : s.id;
    const age = relativeAge(s.last_turn_at || s.started_at);
    const active = s.id === sessState.selectedId ? ' active' : '';
    return `
      <div class="sess-row tool-${escHtml(tool)}${active}" data-id="${escHtml(s.id)}">
        <div class="sr-body">
          <div class="sr-head">
            <span class="tool">${escHtml(tool)}</span>
            <span>·</span>
            <span title="${escHtml(s.id)}">${escHtml(shortId)}</span>
            <span>·</span>
            <span>${escHtml(age)}</span>
          </div>
          <div class="sr-task" title="${escHtml(s.working_on || s.first_user_message || '')}">
            ${escHtml(taskText)}
          </div>
          <div class="sr-stats">
            <span class="stat"><b>${s.turn_count}</b> turns</span>
            <span class="stat"><b>${s.token_total.toLocaleString()}</b> tok</span>
            <span class="stat"><b>${(s.files_touched || []).length}</b> files</span>
          </div>
        </div>
        <div class="sr-actions">
          <button data-act="pack" title="Copy session pack to clipboard">⧉ Pack</button>
        </div>
      </div>`;
  }).join('');

  listEl.innerHTML = rows;

  listEl.querySelectorAll('.sess-row').forEach(el => {
    const sid = el.getAttribute('data-id');
    el.addEventListener('click', ev => {
      // Action buttons handled below
      if (ev.target.closest('button[data-act]')) return;
      selectSession(sid);
    });
    const packBtn = el.querySelector('button[data-act="pack"]');
    if (packBtn) {
      packBtn.addEventListener('click', ev => {
        ev.stopPropagation();
        postMsg({ type: 'copySessionPack', session_id: sid });
      });
    }
  });
}

function selectSession(sessionId) {
  if (!sessionId) return;
  sessState.selectedId = sessionId;
  postMsg({ type: 'selectSession', session_id: sessionId });
  renderSessionsList();
  const clearBtn = document.getElementById('sp-clear');
  if (clearBtn) clearBtn.style.display = 'inline-block';
}

function clearSessionSelection() {
  sessState.selectedId = null;
  sessState.selectedScope = null;
  renderSessionsList();
  const clearBtn = document.getElementById('sp-clear');
  if (clearBtn) clearBtn.style.display = 'none';
  // Re-render full graph.
  renderD3();
}

function applySessionScope(scope) {
  /* Apply the loaded session scope to the graph.  Two modes:
     - highlight: keep all nodes visible, boost scope-nodes with the 'hot'
       state and dim the rest.
     - subgraph : hide non-scope nodes entirely. */
  sessState.selectedScope = scope;

  const fileSet = new Set((scope.files || []).map(f => f.replace(/\\/g, '/')));
  const nodeIds = new Set(scope.node_ids || []);

  // Dim classes on existing d3 selection
  const nodesLayer = d3.select('#nodes-layer');
  const edgesLayer = d3.select('#edges-layer');

  if (sessState.mode === 'highlight') {
    // All visible, scope ones highlighted.
    nodesLayer.selectAll('g.node').each(function(d) {
      const inScope = nodeIds.has(d.id) || fileSet.has((d.file_path || '').replace(/\\/g, '/'));
      d3.select(this).select('circle').classed('dimmed', !inScope);
      d3.select(this).select('text').classed('dimmed', !inScope);
      if (inScope) {
        d3.select(this).select('circle')
          .attr('fill', STATE_COL.hot)
          .attr('stroke', '#fb923c');
      } else {
        d3.select(this).select('circle')
          .attr('fill', nodeColor(d))
          .attr('stroke', d.state === 'locked' ? STATE_COL.locked : '#374151');
      }
    });
    edgesLayer.selectAll('line.edge').classed('hidden', d => {
      const a = d.source?.id ?? d.source;
      const b = d.target?.id ?? d.target;
      return !(nodeIds.has(a) || nodeIds.has(b));
    });
  } else {
    // subgraph mode: hide everything not in scope.
    nodesLayer.selectAll('g.node').each(function(d) {
      const inScope = nodeIds.has(d.id) || fileSet.has((d.file_path || '').replace(/\\/g, '/'));
      d3.select(this).style('display', inScope ? null : 'none');
    });
    edgesLayer.selectAll('line.edge').each(function(d) {
      const a = d.source?.id ?? d.source;
      const b = d.target?.id ?? d.target;
      const inScope = nodeIds.has(a) && nodeIds.has(b);
      d3.select(this).style('display', inScope ? null : 'none');
    });
  }
}

/* Wire up source filter + mode toggle + sync buttons + clear */
document.addEventListener('DOMContentLoaded', () => {
  const src = document.getElementById('sp-source-filter');
  if (src) {
    src.value = sessState.source;
    src.addEventListener('change', () => {
      sessState.source = src.value;
      sessionStorage.setItem('reza:sessionSource', sessState.source);
      sessionsSendListRequest();
    });
  }

  const modeButtons = document.querySelectorAll('#sp-mode-toggle button[data-mode]');
  modeButtons.forEach(btn => {
    if (btn.dataset.mode === sessState.mode) btn.classList.add('active');
    else btn.classList.remove('active');
    btn.addEventListener('click', () => {
      sessState.mode = btn.dataset.mode;
      sessionStorage.setItem('reza:sessionMode', sessState.mode);
      modeButtons.forEach(b => b.classList.toggle('active', b === btn));
      if (sessState.selectedScope) {
        if (sessState.mode === 'highlight') {
          // un-hide everything, then re-apply
          d3.select('#nodes-layer').selectAll('g.node').style('display', null);
          d3.select('#edges-layer').selectAll('line.edge').style('display', null);
        }
        applySessionScope(sessState.selectedScope);
      }
    });
  });

  const sc = document.getElementById('sp-sync-cursor');
  if (sc) sc.addEventListener('click', () => postMsg({ type: 'syncCursor' }));
  const sx = document.getElementById('sp-sync-codex');
  if (sx) sx.addEventListener('click', () => postMsg({ type: 'syncCodex' }));

  const clearBtn = document.getElementById('sp-clear');
  if (clearBtn) clearBtn.addEventListener('click', clearSessionSelection);
});

/* ---------- Message handler ---------- */
window.addEventListener('message', ev => {
  const msg = ev.data;
  if (!msg || !msg.type) return;

  if (msg.type === 'init') {
    hideOverlay();
    buildGraph(msg.data);
    if (sessState.selectedScope) {
      // Reapply scope when graph is rebuilt (e.g. after refresh)
      setTimeout(() => applySessionScope(sessState.selectedScope), 250);
    }
  } else if (msg.type === 'updateSessionState') {
    applySessionUpdate(msg.data);
  } else if (msg.type === 'error') {
    showError(msg.message ?? 'Unknown error');
  } else if (msg.type === 'loading') {
    showLoading(msg.message ?? 'Loading…');
  } else if (msg.type === 'sessionsList') {
    sessState.sessions = msg.data?.sessions || [];
    renderSessionsList();
  } else if (msg.type === 'sessionScope') {
    applySessionScope(msg.data?.scope || { files: [], node_ids: [] });
  }
});

/* ---------- Boot ---------- */
postMsg({ type: 'ready' });
