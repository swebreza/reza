/**
 * sessionOverlay.ts — computes per-node session state.
 *
 * Priority order (highest wins):
 *   locked  — file currently locked by active session
 *   hot     — file modified in this session
 *   warm    — file modified in last 24 h (cross-session)
 *   blast   — file in blast radius of hot files
 *   cold    — no session activity
 *
 * "tool" colour is derived from the session's llm_name:
 *   cursor → purple  |  claude → deep-orange  |  codex → blue  |  other → steel
 */

import { NodeDatum, NodeState, SessionInfo } from './rezaClient';

export interface OverlayOptions {
  session: SessionInfo | null;
  blastFiles: Set<string>;
  /** Absolute → relative path normalizer. Pass identity if paths already match. */
  normalizePath?: (p: string) => string;
}

// ---------------------------------------------------------------------------
// Tool colour map
// ---------------------------------------------------------------------------

export type ToolColour = 'purple' | 'deep-orange' | 'blue' | 'steel';

export function toolColour(llmName: string | undefined): ToolColour {
  if (!llmName) return 'steel';
  const n = llmName.toLowerCase();
  if (n.includes('cursor')) return 'purple';
  if (n.includes('claude')) return 'deep-orange';
  if (n.includes('codex') || n.includes('openai')) return 'blue';
  return 'steel';
}

// ---------------------------------------------------------------------------
// State computation
// ---------------------------------------------------------------------------

function computeState(
  filePath: string,
  opts: OverlayOptions,
  norm: (p: string) => string,
): NodeState {
  if (!opts.session) return 'cold';

  const fp = norm(filePath);
  const hotSet = new Set(opts.session.hot_files.map(norm));
  const lockedSet = new Set(opts.session.locked_files.map(norm));
  const blastSet = new Set([...opts.blastFiles].map(norm));

  if (lockedSet.has(fp)) return 'locked';
  if (hotSet.has(fp))    return 'hot';
  if (blastSet.has(fp))  return 'blast';

  return 'cold';
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface AnnotatedNode extends NodeDatum {
  state: NodeState;
  toolColour: ToolColour;
}

/**
 * Apply session overlay to every node in-place (mutates state + toolColour).
 * Returns the same array for convenience.
 */
export function applyOverlay(
  nodes: NodeDatum[],
  opts: OverlayOptions,
): AnnotatedNode[] {
  const norm = opts.normalizePath ?? ((p: string) => p);
  const colour = toolColour(opts.session?.llm_name);

  for (const node of nodes) {
    const n = node as AnnotatedNode;
    n.state = computeState(node.file_path, opts, norm);
    n.toolColour = colour;
  }

  return nodes as AnnotatedNode[];
}

/**
 * Count how many nodes are in each state.
 */
export function stateHistogram(nodes: AnnotatedNode[]): Record<NodeState, number> {
  const counts: Record<NodeState, number> = {
    locked: 0, hot: 0, warm: 0, blast: 0, cold: 0,
  };
  for (const n of nodes) {
    counts[n.state] = (counts[n.state] ?? 0) + 1;
  }
  return counts;
}

/**
 * Produce a minimal `GraphPayload.session` shape suitable for the webview.
 */
export interface WebviewSession {
  id: string;
  llm_name: string;
  status: string;
  working_on: string | null;
  hot_files: string[];
  locked_files: string[];
  blast_files: string[];
  toolColour: ToolColour;
  histogram: Record<NodeState, number>;
}

export function buildWebviewSession(
  session: SessionInfo,
  blastFiles: Set<string>,
  histogram: Record<NodeState, number>,
): WebviewSession {
  return {
    id: session.id,
    llm_name: session.llm_name,
    status: session.status,
    working_on: session.working_on,
    hot_files: session.hot_files,
    locked_files: session.locked_files,
    blast_files: [...blastFiles],
    toolColour: toolColour(session.llm_name),
    histogram,
  };
}
