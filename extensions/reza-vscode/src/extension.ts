/**
 * extension.ts — entry point for the Reza VS Code extension.
 *
 * Registers:
 *   reza.showGraph   — open / focus the code graph webview
 *   reza.showImpact  — run blast-radius for active file and show result
 *   reza.buildGraph  — run `reza graph build` in terminal
 *   reza.refreshGraph— force-refresh the open webview
 *
 * Lifecycle:
 *   - Creates a single retained WebviewPanel (singleton pattern)
 *   - FileSystemWatcher on .reza/context.db triggers lightweight session refresh
 *   - Interval-based session poll as fallback (configurable refreshIntervalMs)
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

import { buildGraphPayload, buildSessionOnlyPayload, GraphPayload } from './graphProvider';
import { buildGraph as cliRunBuildGraph } from './rezaClient';
import { AnnotatedNode } from './sessionOverlay';

// ---------------------------------------------------------------------------
// Extension state
// ---------------------------------------------------------------------------

let panel: vscode.WebviewPanel | undefined;
let dbWatcher: vscode.FileSystemWatcher | undefined;
let sessionPollTimer: NodeJS.Timeout | undefined;

/** Last sent graph nodes — used by session-only refresh to avoid re-query */
let lastNodes: AnnotatedNode[] = [];

// ---------------------------------------------------------------------------
// Activate
// ---------------------------------------------------------------------------

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('reza.showGraph',   () => showGraph(context)),
    vscode.commands.registerCommand('reza.showImpact',  () => showImpact()),
    vscode.commands.registerCommand('reza.buildGraph',  () => runBuildInTerminal()),
    vscode.commands.registerCommand('reza.refreshGraph',() => {
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
  if (dbWatcher) { dbWatcher.dispose(); dbWatcher = undefined; }
  if (panel)     { panel.dispose();     panel = undefined; }
}

// ---------------------------------------------------------------------------
// Show graph
// ---------------------------------------------------------------------------

async function showGraph(context: vscode.ExtensionContext): Promise<void> {
  if (panel) {
    panel.reveal(vscode.ViewColumn.Two);
    return;
  }

  const workspaceRoot = getWorkspaceRoot();
  if (!workspaceRoot) {
    void vscode.window.showErrorMessage('Reza: No workspace folder open.');
    return;
  }

  const dbPath = path.join(workspaceRoot, '.reza', 'context.db');
  if (!fs.existsSync(dbPath)) {
    const choice = await vscode.window.showWarningMessage(
      'Reza: context.db not found. Build the graph first?',
      'Build Graph', 'Cancel',
    );
    if (choice === 'Build Graph') runBuildInTerminal();
    return;
  }

  // Create panel
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

  // Message handler (webview → extension)
  panel.webview.onDidReceiveMessage(
    (msg: { type: string; file_path?: string; line_start?: number }) => {
      switch (msg.type) {
        case 'ready':
          void loadAndSendGraph();
          break;
        case 'refresh':
          void loadAndSendGraph();
          break;
        case 'openFile':
          if (msg.file_path) void openFile(msg.file_path, msg.line_start ?? 1);
          break;
      }
    },
    undefined,
    [],
  );

  panel.onDidDispose(() => {
    panel = undefined;
    stopSessionPoll();
    if (dbWatcher) { dbWatcher.dispose(); dbWatcher = undefined; }
  });

  // FileSystemWatcher — refresh session on DB write
  dbWatcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(workspaceRoot, '.reza/context.db'),
  );
  dbWatcher.onDidChange(() => void refreshSession());

  // Interval poll as fallback
  startSessionPoll();
}

// ---------------------------------------------------------------------------
// Load full graph payload → send to webview
// ---------------------------------------------------------------------------

async function loadAndSendGraph(): Promise<void> {
  if (!panel) return;
  try {
    const payload: GraphPayload = await buildGraphPayload();
    lastNodes = payload.nodes;
    panel.webview.postMessage({ type: 'init', data: payload });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.webview.postMessage({ type: 'error', message: msg });
    void vscode.window.showErrorMessage(`Reza graph error: ${msg}`);
  }
}

// ---------------------------------------------------------------------------
// Session-only refresh (lightweight — no graph re-query)
// ---------------------------------------------------------------------------

async function refreshSession(): Promise<void> {
  if (!panel || lastNodes.length === 0) return;
  try {
    const payload = await buildSessionOnlyPayload(lastNodes);
    panel.webview.postMessage({ type: 'updateSessionState', data: payload });
  } catch {
    // silent — session refresh is best-effort
  }
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
// Blast-radius for active editor file
// ---------------------------------------------------------------------------

async function showImpact(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    void vscode.window.showInformationMessage('Reza: Open a file first to see its blast radius.');
    return;
  }

  const workspaceRoot = getWorkspaceRoot();
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
// Build graph in integrated terminal
// ---------------------------------------------------------------------------

function runBuildInTerminal(): void {
  const workspaceRoot = getWorkspaceRoot();
  if (!workspaceRoot) return;

  let terminal = vscode.window.terminals.find(t => t.name === 'Reza Build');
  if (!terminal) {
    terminal = vscode.window.createTerminal({ name: 'Reza Build', cwd: workspaceRoot });
  }
  terminal.show();
  terminal.sendText('reza graph build');
}

// ---------------------------------------------------------------------------
// Open file at line
// ---------------------------------------------------------------------------

async function openFile(filePath: string, lineStart: number): Promise<void> {
  const workspaceRoot = getWorkspaceRoot();
  let uri: vscode.Uri;

  if (path.isAbsolute(filePath)) {
    uri = vscode.Uri.file(filePath);
  } else if (workspaceRoot) {
    uri = vscode.Uri.file(path.join(workspaceRoot, filePath));
  } else {
    return;
  }

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

  // Generate a cryptographically random nonce for CSP
  const nonce = generateNonce();

  // Replace nonce placeholders
  html = html.replace(/\{\{NONCE\}\}/g, nonce);

  // Rewrite graph.js src to webview URI
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

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function getWorkspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}
