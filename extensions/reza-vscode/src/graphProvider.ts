/**
 * graphProvider.ts — builds the unified GraphPayload that the webview renders.
 *
 * Steps:
 *   1. Call reza graph export → raw nodes + edges + base session info
 *   2. Run blast-radius analysis on hot files  → blast file set
 *   3. Apply sessionOverlay to annotate each node with state + toolColour
 *   4. Return a serialisable GraphPayload for postMessage
 */

import * as vscode from 'vscode';
import {
  exportGraph,
  getImpact,
  NodeDatum,
  EdgeDatum,
  GraphStats,
  SessionInfo,
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
}

export interface SessionOnlyPayload {
  session: WebviewSession | null;
  nodeStates: Record<string, string>; // qualified_name → state
}

// ---------------------------------------------------------------------------
// Configuration helpers
// ---------------------------------------------------------------------------

function cfg<T>(key: string, fallback: T): T {
  return vscode.workspace.getConfiguration('reza').get<T>(key) ?? fallback;
}

// ---------------------------------------------------------------------------
// Build the full payload
// ---------------------------------------------------------------------------

export async function buildGraphPayload(): Promise<GraphPayload> {
  const limit = cfg<number>('nodeLimit', 800);
  const kinds = cfg<string>('defaultNodeKinds', 'Class,Function,Test');

  // 1. Export graph (includes basic session info from reza CLI)
  const raw = await exportGraph(limit, kinds);

  const stats: GraphStats = raw.stats ?? {
    total_nodes: raw.nodes.length,
    total_edges: raw.edges.length,
    nodes_by_kind: {},
    edges_by_kind: {},
    languages: [],
    files_count: 0,
    last_updated: null,
  };

  const session: SessionInfo | null = raw.session ?? null;

  // 2. Blast-radius analysis (only if there are hot files)
  let blastFiles = new Set<string>();
  if (session && session.hot_files.length > 0) {
    try {
      const impact = await getImpact(session.hot_files);
      blastFiles = new Set(impact.impacted_files);
    } catch {
      // blast analysis is best-effort; silent failure
    }
  }

  // 3. Apply session overlay
  const annotated = applyOverlay(raw.nodes as NodeDatum[], { session, blastFiles });

  // 4. Build webview session summary
  let webviewSession: WebviewSession | null = null;
  if (session) {
    const histogram = stateHistogram(annotated);
    webviewSession = buildWebviewSession(session, blastFiles, histogram);
  }

  return {
    nodes: annotated,
    edges: raw.edges,
    stats,
    session: webviewSession,
    truncated: raw.nodes.length >= limit && limit > 0,
    generatedAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Lightweight session-only refresh (no graph re-query, just re-overlay)
// ---------------------------------------------------------------------------

export async function buildSessionOnlyPayload(
  existingNodes: AnnotatedNode[],
): Promise<SessionOnlyPayload> {
  const limit = cfg<number>('nodeLimit', 800);
  const kinds = cfg<string>('defaultNodeKinds', 'Class,Function,Test');

  const raw = await exportGraph(limit, kinds);
  const session: SessionInfo | null = raw.session ?? null;

  let blastFiles = new Set<string>();
  if (session && session.hot_files.length > 0) {
    try {
      const impact = await getImpact(session.hot_files);
      blastFiles = new Set(impact.impacted_files);
    } catch {
      // silent
    }
  }

  const annotated = applyOverlay(existingNodes, { session, blastFiles });
  const histogram = session ? stateHistogram(annotated) : { locked: 0, hot: 0, warm: 0, blast: 0, cold: 0 };
  const webviewSession = session ? buildWebviewSession(session, blastFiles, histogram) : null;

  const nodeStates: Record<string, string> = {};
  for (const n of annotated) {
    nodeStates[n.id] = n.state;
  }

  return { session: webviewSession, nodeStates };
}
