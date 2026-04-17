/**
 * graphProvider.ts — builds the unified GraphPayload that the webview renders.
 *
 * Steps:
 *   1. Check if .reza/context.db exists. If not, return an "empty/needs-init" payload.
 *   2. Call reza graph export → raw nodes + edges + base session info.
 *   3. Run blast-radius analysis on hot files  → blast file set.
 *   4. Apply sessionOverlay to annotate each node with state + toolColour.
 *   5. Return a serialisable GraphPayload for postMessage.
 */

import * as path from 'path';
import * as vscode from 'vscode';
import {
  exportGraph,
  getImpact,
  NodeDatum,
  EdgeDatum,
  GraphStats,
  SessionInfo,
  anyWorkspaceHasContextDb,
  getRezaWorkingDirectory,
  resolveRezaDataDirName,
} from './rezaClient';
import {
  applyOverlay,
  buildWebviewSession,
  stateHistogram,
  AnnotatedNode,
  WebviewSession,
} from './sessionOverlay';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GraphPayload {
  nodes: AnnotatedNode[];
  edges: EdgeDatum[];
  stats: GraphStats;
  session: WebviewSession | null;
  truncated: boolean;
  generatedAt: string;
  workspaceRoot: string;
  dbPath: string | null;
  hasDb: boolean;
  needsInit: boolean;
  needsBuild: boolean;
  errorMessage?: string;
}

export interface SessionOnlyPayload {
  session: WebviewSession | null;
  nodeStates: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Configuration helpers
// ---------------------------------------------------------------------------

function cfg<T>(key: string, fallback: T): T {
  return vscode.workspace.getConfiguration('reza').get<T>(key) ?? fallback;
}

function emptyStats(): GraphStats {
  return {
    total_nodes: 0,
    total_edges: 0,
    nodes_by_kind: {},
    edges_by_kind: {},
    languages: [],
    files_count: 0,
    last_updated: null,
  };
}

function getWorkspaceRoot(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) return '';
  try {
    return getRezaWorkingDirectory();
  } catch {
    return folders[0].uri.fsPath;
  }
}

function getDbPath(): string | null {
  const root = getWorkspaceRoot();
  if (!root) return null;
  const dirName = resolveRezaDataDirName(root);
  if (!dirName) return null;
  return path.join(root, dirName, 'context.db');
}

// ---------------------------------------------------------------------------
// Build the full payload
// ---------------------------------------------------------------------------

export async function buildGraphPayload(): Promise<GraphPayload> {
  const workspaceRoot = getWorkspaceRoot();
  const dbPath = getDbPath();
  const hasDb = anyWorkspaceHasContextDb();

  // Base payload template
  const base: GraphPayload = {
    nodes: [],
    edges: [],
    stats: emptyStats(),
    session: null,
    truncated: false,
    generatedAt: new Date().toISOString(),
    workspaceRoot,
    dbPath,
    hasDb,
    needsInit: !hasDb,
    needsBuild: false,
  };

  // 0. No DB at all → needs `reza init`
  if (!hasDb) {
    return base;
  }

  const limit = cfg<number>('nodeLimit', 800);
  const kinds = cfg<string>('defaultNodeKinds', 'Class,Function,Test');

  // 1. Export graph
  let raw;
  try {
    raw = await exportGraph(limit, kinds);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ...base, needsBuild: true, errorMessage: msg };
  }

  const stats: GraphStats = raw.stats ?? emptyStats();

  // DB present but graph never built (0 nodes) → needs build
  if ((stats.total_nodes ?? 0) === 0) {
    return { ...base, stats, needsBuild: true };
  }

  const session: SessionInfo | null = raw.session ?? null;

  // 2. Blast-radius on hot files
  let blastFiles = new Set<string>();
  if (session && session.hot_files.length > 0) {
    try {
      const impact = await getImpact(session.hot_files);
      blastFiles = new Set(impact.impacted_files);
    } catch {
      /* best-effort */
    }
  }

  // 3. Overlay
  const annotated = applyOverlay(raw.nodes as NodeDatum[], { session, blastFiles });

  // 4. Session summary
  let webviewSession: WebviewSession | null = null;
  if (session) {
    const histogram = stateHistogram(annotated);
    webviewSession = buildWebviewSession(session, blastFiles, histogram);
  }

  return {
    ...base,
    nodes: annotated,
    edges: raw.edges,
    stats,
    session: webviewSession,
    truncated: raw.nodes.length >= limit && limit > 0,
  };
}

// ---------------------------------------------------------------------------
// Lightweight session-only refresh
// ---------------------------------------------------------------------------

export async function buildSessionOnlyPayload(
  existingNodes: AnnotatedNode[],
): Promise<SessionOnlyPayload> {
  const limit = cfg<number>('nodeLimit', 800);
  const kinds = cfg<string>('defaultNodeKinds', 'Class,Function,Test');

  let raw;
  try {
    raw = await exportGraph(limit, kinds);
  } catch {
    return { session: null, nodeStates: {} };
  }
  const session: SessionInfo | null = raw.session ?? null;

  let blastFiles = new Set<string>();
  if (session && session.hot_files.length > 0) {
    try {
      const impact = await getImpact(session.hot_files);
      blastFiles = new Set(impact.impacted_files);
    } catch {
      /* silent */
    }
  }

  const annotated = applyOverlay(existingNodes, { session, blastFiles });
  const histogram = session
    ? stateHistogram(annotated)
    : { locked: 0, hot: 0, warm: 0, blast: 0, cold: 0 };
  const webviewSession = session ? buildWebviewSession(session, blastFiles, histogram) : null;

  const nodeStates: Record<string, string> = {};
  for (const n of annotated) {
    nodeStates[n.id] = n.state;
  }

  return { session: webviewSession, nodeStates };
}
