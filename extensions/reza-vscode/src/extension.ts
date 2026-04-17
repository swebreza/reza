/**
 * extension.ts — entry point for the Reza VS Code extension.
 *
 * Commands:
 *   reza.showGraph       — open/focus the code graph webview (always works; shows
 *                          init/build CTA when data is missing)
 *   reza.showImpact      — blast-radius for the active editor file
 *   reza.buildGraph      — run `reza graph build` in a terminal
 *   reza.initProject     — run `reza init` in a terminal (creates .reza/context.db)
 *   reza.initAndBuild    — one-click `reza init && reza graph build`
 *   reza.refreshGraph    — force-refresh the open webview
 *   reza.startTracking   — start `reza watch` in a background terminal + print hook setup
 *
 * Lifecycle:
 *   - Singleton WebviewPanel (retained when hidden)
 *   - FileSystemWatcher on .reza/context.db → auto session/graph refresh
 *   - Workspace-level watcher for a NEW .reza/context.db appearing (first-time init)
 *   - Interval session poll as fallback (configurable refreshIntervalMs)
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

import { buildGraphPayload, buildSessionOnlyPayload, GraphPayload } from './graphProvider';
import {
  anyWorkspaceHasContextDb,
  getRezaWorkingDirectory,
  resolveRezaDataDirName,
  listAllSessions,
  getSessionScope,
} from './rezaClient';
import { AnnotatedNode } from './sessionOverlay';

// ---------------------------------------------------------------------------
// Extension state
// ---------------------------------------------------------------------------

let panel: vscode.WebviewPanel | undefined;
let dbWatcher: vscode.FileSystemWatcher | undefined;
let dbCreateWatcher: vscode.FileSystemWatcher | undefined;
let sessionPollTimer: NodeJS.Timeout | undefined;
let lastKnownNodeCount = 0;

/** Last sent graph nodes — used by session-only refresh to avoid re-query */
let lastNodes: AnnotatedNode[] = [];

// ---------------------------------------------------------------------------
// Activate
// ---------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('reza.showGraph',      () => showGraph(context)),
    vscode.commands.registerCommand('reza.showImpact',     () => showImpact()),
    vscode.commands.registerCommand('reza.buildGraph',     () => runBuildInTerminal()),
    vscode.commands.registerCommand('reza.initProject',    () => runInitInTerminal()),
    vscode.commands.registerCommand('reza.initAndBuild',   () => runInitAndBuildInTerminal()),
    vscode.commands.registerCommand('reza.startTracking',  () => runStartTracking(context)),
    vscode.commands.registerCommand('reza.refreshGraph',   () => {
      if (panel) {
        panel.webview.postMessage({ type: 'loading', message: 'Refreshing graph…' });
        void loadAndSendGraph();
      }
    }),
  );
}

// ---------------------------------------------------------------------------
// Deactivate
// ---------------------------------------------------------------------------

export function deactivate(): void {
  stopSessionPoll();
  disposeWatchers();
  if (panel) { panel.dispose(); panel = undefined; }
}

// ---------------------------------------------------------------------------
// Show graph (always opens panel — webview handles empty/needs-init states)
// ---------------------------------------------------------------------------

async function showGraph(context: vscode.ExtensionContext): Promise<void> {
  if (panel) {
    panel.reveal(vscode.ViewColumn.Two);
    return;
  }

  if (!vscode.workspace.workspaceFolders?.length) {
    void vscode.window.showErrorMessage('Reza: No workspace folder open.');
    return;
  }

  panel = vscode.window.createWebviewPanel(
    'rezaGraph',
    'Reza Code Graph',
    vscode.ViewColumn.Two,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [
        vscode.Uri.file(path.join(context.extensionPath, 'dist', 'webview')),
      ],
    },
  );

  panel.webview.html = buildHtml(context, panel.webview);

  panel.webview.onDidReceiveMessage(
    (msg: {
      type: string;
      file_path?: string;
      line_start?: number;
      session_id?: string;
      limit?: number;
      source?: 'all' | 'cursor' | 'codex' | 'claude' | 'manual';
    }) => {
      switch (msg.type) {
        case 'ready':
          void loadAndSendGraph();
          void pushSessionsList();
          break;
        case 'refresh':
          void loadAndSendGraph();
          void pushSessionsList();
          break;
        case 'openFile':
          if (msg.file_path) void openFile(msg.file_path, msg.line_start ?? 1);
          break;
        case 'buildGraph':
          runBuildInTerminal();
          break;
        case 'initProject':
          runInitInTerminal();
          break;
        case 'initAndBuild':
          runInitAndBuildInTerminal();
          break;
        case 'startTracking':
          runStartTracking(context);
          break;
        case 'listSessions':
          void pushSessionsList(msg.limit ?? 50, msg.source ?? 'all');
          break;
        case 'selectSession':
          if (msg.session_id) void pushSessionScope(msg.session_id);
          break;
        case 'copySessionPack':
          if (msg.session_id) runSessionLoadInTerminal(msg.session_id);
          break;
        case 'syncCursor':
          runSyncInTerminal('sync-cursor');
          break;
        case 'syncCodex':
          runSyncInTerminal('sync-codex');
          break;
      }
    },
    undefined,
    [],
  );

  panel.onDidDispose(() => {
    panel = undefined;
    stopSessionPoll();
    disposeWatchers();
  });

  setupWatchers();
  startSessionPoll();
}

// ---------------------------------------------------------------------------
// Sessions browser (cross-tool session list + subgraph scope)
// ---------------------------------------------------------------------------

async function pushSessionsList(
  limit: number = 50,
  source: 'all' | 'cursor' | 'codex' | 'claude' | 'manual' = 'all',
): Promise<void> {
  if (!panel) return;
  try {
    const sessions = await listAllSessions(limit, source);
    panel.webview.postMessage({
      type: 'sessionsList',
      data: { sessions, source, limit },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.webview.postMessage({
      type: 'sessionsList',
      data: { sessions: [], source, limit, error: msg },
    });
  }
}

async function pushSessionScope(sessionId: string): Promise<void> {
  if (!panel) return;
  try {
    const scope = await getSessionScope(sessionId);
    panel.webview.postMessage({ type: 'sessionScope', data: scope });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    void vscode.window.showErrorMessage(`Reza: failed to load session scope — ${msg}`);
  }
}

function runSessionLoadInTerminal(sessionId: string): void {
  const terminal = getOrCreateTerminal('Reza Handoff');
  terminal.show();
  // --copy puts it on the clipboard; `|| Write-Host` keeps the command visible.
  terminal.sendText(`reza session load ${sessionId} --copy`);
  void vscode.window.showInformationMessage(
    `Reza: building handoff pack for ${sessionId} — check clipboard when done.`,
  );
}

function runSyncInTerminal(cmd: 'sync-cursor' | 'sync-codex'): void {
  const terminal = getOrCreateTerminal('Reza Sync');
  terminal.show();
  terminal.sendText(`reza ${cmd}`);
  // Refresh list after a moment so the new sessions show up.
  setTimeout(() => void pushSessionsList(), 4000);
}

// ---------------------------------------------------------------------------
// Load full graph payload → send to webview
// ---------------------------------------------------------------------------

async function loadAndSendGraph(): Promise<void> {
  if (!panel) return;
  try {
    const payload: GraphPayload = await buildGraphPayload();
    lastNodes = payload.nodes;
    lastKnownNodeCount = payload.stats?.total_nodes ?? 0;
    panel.webview.postMessage({ type: 'init', data: payload });

    // If we just gained a DB, set up watchers fresh
    if (payload.hasDb && !dbWatcher) {
      setupWatchers();
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.webview.postMessage({ type: 'error', message: msg });
  }
}

// ---------------------------------------------------------------------------
// Session-only refresh
// ---------------------------------------------------------------------------

async function refreshSession(): Promise<void> {
  if (!panel) return;

  // If last fetch had 0 nodes, do a FULL re-fetch instead (watching for build to finish).
  if (lastKnownNodeCount === 0 || lastNodes.length === 0) {
    await loadAndSendGraph();
    return;
  }

  try {
    const payload = await buildSessionOnlyPayload(lastNodes);
    panel.webview.postMessage({ type: 'updateSessionState', data: payload });
  } catch {
    /* silent */
  }
}

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------

function setupWatchers(): void {
  disposeWatchers();

  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) return;

  // 1. If DB already exists somewhere, watch that file for changes.
  if (anyWorkspaceHasContextDb()) {
    try {
      const workspaceRoot = getRezaWorkingDirectory();
      const rezaDirName = resolveRezaDataDirName(workspaceRoot) ?? '.reza';
      dbWatcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(workspaceRoot, `${rezaDirName}/context.db`),
      );
      dbWatcher.onDidChange(() => void refreshSession());
      dbWatcher.onDidCreate(() => void loadAndSendGraph());
      dbWatcher.onDidDelete(() => void loadAndSendGraph());
    } catch {
      /* no workspace */
    }
  }

  // 2. Always watch for new .reza/context.db or .REZA/context.db appearing
  //    (first-time init triggers re-fetch automatically).
  dbCreateWatcher = vscode.workspace.createFileSystemWatcher(
    '**/.{reza,REZA,Reza}/context.db',
  );
  dbCreateWatcher.onDidCreate(() => void loadAndSendGraph());
  dbCreateWatcher.onDidChange(() => void refreshSession());
}

function disposeWatchers(): void {
  if (dbWatcher)       { dbWatcher.dispose();       dbWatcher       = undefined; }
  if (dbCreateWatcher) { dbCreateWatcher.dispose(); dbCreateWatcher = undefined; }
}

// ---------------------------------------------------------------------------
// Polling helpers
// ---------------------------------------------------------------------------

function startSessionPoll(): void {
  stopSessionPoll();
  const ms = vscode.workspace.getConfiguration('reza').get<number>('refreshIntervalMs') ?? 3000;
  if (ms > 0) {
    sessionPollTimer = setInterval(() => void refreshSession(), ms);
  }
}

function stopSessionPoll(): void {
  if (sessionPollTimer) {
    clearInterval(sessionPollTimer);
    sessionPollTimer = undefined;
  }
}

// ---------------------------------------------------------------------------
// Blast-radius
// ---------------------------------------------------------------------------

async function showImpact(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    void vscode.window.showInformationMessage('Reza: Open a file first to see its blast radius.');
    return;
  }

  const folder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  let workspaceRoot: string;
  try {
    workspaceRoot = folder?.uri.fsPath ?? getRezaWorkingDirectory();
  } catch {
    workspaceRoot = folder?.uri.fsPath ?? '';
  }
  const filePath = workspaceRoot
    ? path.relative(workspaceRoot, editor.document.fileName)
    : editor.document.fileName;

  void vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Reza: Computing blast radius…' },
    async () => {
      try {
        const { getImpact } = await import('./rezaClient');
        const result = await getImpact([filePath]);
        const files = result.impacted_files.join(', ') || 'none';
        void vscode.window.showInformationMessage(
          `Blast radius: ${result.impacted_nodes} nodes across ${result.impacted_files.length} files. ${files.slice(0, 120)}`,
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        void vscode.window.showErrorMessage(`Reza impact error: ${msg}`);
      }
    },
  );
}

// ---------------------------------------------------------------------------
// Terminal commands
// ---------------------------------------------------------------------------

function getOrCreateTerminal(name: string): vscode.Terminal {
  const cwd = getWorkspaceRootSafe();
  let terminal = vscode.window.terminals.find(t => t.name === name);
  if (!terminal) {
    terminal = vscode.window.createTerminal({ name, cwd });
  }
  return terminal;
}

function getWorkspaceRootSafe(): string | undefined {
  try {
    return getRezaWorkingDirectory();
  } catch {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }
}

function runBuildInTerminal(): void {
  const terminal = getOrCreateTerminal('Reza Build');
  terminal.show();
  terminal.sendText('reza graph build');
  armBuildCompletionPoll();
}

function runInitInTerminal(): void {
  const terminal = getOrCreateTerminal('Reza Init');
  terminal.show();
  terminal.sendText('reza init');
  armBuildCompletionPoll();
}

function runInitAndBuildInTerminal(): void {
  const terminal = getOrCreateTerminal('Reza Setup');
  terminal.show();
  // PowerShell / cmd / bash all understand "cmd1; cmd2" reasonably
  terminal.sendText('reza init ; reza graph build');
  armBuildCompletionPoll();
}

/** After kicking off a terminal command, poll every ~2s for a few minutes
 *  to auto-refresh the panel as soon as the DB grows. */
function armBuildCompletionPoll(): void {
  const start = Date.now();
  const maxMs = 10 * 60 * 1000; // 10 minutes
  let lastSize = -1;
  const iv = setInterval(async () => {
    if (Date.now() - start > maxMs) { clearInterval(iv); return; }
    if (!panel) { clearInterval(iv); return; }
    try {
      const root = getWorkspaceRootSafe();
      if (!root) return;
      const dirName = resolveRezaDataDirName(root);
      if (!dirName) return;
      const dbPath = path.join(root, dirName, 'context.db');
      const st = await fs.promises.stat(dbPath).catch(() => null);
      if (!st) return;
      if (st.size !== lastSize) {
        lastSize = st.size;
        await loadAndSendGraph();
      }
    } catch {
      /* silent */
    }
  }, 2000);
}

// ---------------------------------------------------------------------------
// Start auto-tracking (reza watch + hook installer)
// ---------------------------------------------------------------------------

function runStartTracking(_context: vscode.ExtensionContext): void {
  const root = getWorkspaceRootSafe();
  if (!root) {
    void vscode.window.showErrorMessage('Reza: No workspace folder open.');
    return;
  }

  // 1. Ensure init (safe to re-run)
  const setupTerminal = getOrCreateTerminal('Reza Setup');
  setupTerminal.show();
  setupTerminal.sendText('reza init');

  // 2. Install Claude hook if available (no-op if unsupported)
  setupTerminal.sendText('reza install-claude-hook');

  // 3. Start background file watcher in its own terminal
  const watchTerminal = getOrCreateTerminal('Reza Watch');
  watchTerminal.show();
  watchTerminal.sendText('reza watch');

  armBuildCompletionPoll();

  void vscode.window.showInformationMessage(
    'Reza: Auto-tracking started — file changes and Claude sessions will be recorded to .reza/context.db.',
  );
}

// ---------------------------------------------------------------------------
// Open file at line
// ---------------------------------------------------------------------------

async function openFile(filePath: string, lineStart: number): Promise<void> {
  const workspaceRoot = getWorkspaceRootSafe();
  if (!workspaceRoot) return;

  const uri = path.isAbsolute(filePath)
    ? vscode.Uri.file(filePath)
    : vscode.Uri.file(path.join(workspaceRoot, filePath));

  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    const line = Math.max(0, lineStart - 1);
    await vscode.window.showTextDocument(doc, {
      viewColumn: vscode.ViewColumn.One,
      selection: new vscode.Range(line, 0, line, 0),
    });
  } catch {
    void vscode.window.showErrorMessage(`Reza: Could not open file: ${filePath}`);
  }
}

// ---------------------------------------------------------------------------
// HTML builder
// ---------------------------------------------------------------------------

function buildHtml(context: vscode.ExtensionContext, webview: vscode.Webview): string {
  const distWebview = path.join(context.extensionPath, 'dist', 'webview');
  const htmlPath    = path.join(distWebview, 'graph.html');

  let html = fs.readFileSync(htmlPath, 'utf8');

  const nonce = generateNonce();
  html = html.replace(/\{\{NONCE\}\}/g, nonce);

  const graphJsUri = webview.asWebviewUri(
    vscode.Uri.file(path.join(distWebview, 'graph.js')),
  );
  html = html.replace('src="graph.js"', `src="${graphJsUri}"`);

  return html;
}

function generateNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 32; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}
