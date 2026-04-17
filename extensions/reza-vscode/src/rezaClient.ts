/**
 * rezaClient.ts — CLI bridge for the reza VS Code extension.
 *
 * Spawns the reza CLI and parses JSON output. No native SQLite dependency.
 * All data comes from `reza <command> --json` stdout.
 */

import { exec as _exec } from 'child_process';
import { promisify } from 'util';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

const exec = promisify(_exec);

// ---------------------------------------------------------------------------
// Types (mirrors reza CLI JSON output shapes)
// ---------------------------------------------------------------------------

export interface NodeDatum {
  id: string;           // qualified_name
  name: string;
  kind: string;         // File | Class | Function | Test
  file_path: string;
  line_start: number;
  line_end: number;
  language: string;
  params: string | null;
  return_type: string | null;
  is_test: boolean;
  parent_name: string | null;
  degree: number;
  state: NodeState;     // set by session overlay
}

export interface EdgeDatum {
  kind: string;         // CALLS | IMPORTS_FROM | INHERITS | CONTAINS | TESTED_BY
  source: string;       // qualified_name
  target: string;       // qualified_name
  file_path: string;
  line: number;
  confidence: number;
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  nodes_by_kind: Record<string, number>;
  edges_by_kind: Record<string, number>;
  languages: string[];
  files_count: number;
  last_updated: string | null;
}

export interface SessionInfo {
  id: string;
  llm_name: string;
  status: string;
  working_on: string | null;
  hot_files: string[];
  locked_files: string[];
}

export interface GraphExportData {
  nodes: NodeDatum[];
  edges: EdgeDatum[];
  stats: GraphStats;
  session: SessionInfo | null;
}

export interface ImpactData {
  changed_files: string[];
  impacted_files: string[];
  changed_nodes: number;
  impacted_nodes: number;
  edges: number;
  test_gaps: string[];
  truncated: boolean;
}

export type NodeState = 'locked' | 'hot' | 'warm' | 'blast' | 'cold';

// ---------------------------------------------------------------------------
// Core executor
// ---------------------------------------------------------------------------

function getRezaPath(): string {
  const cfg = vscode.workspace.getConfiguration('reza');
  return cfg.get<string>('rezaPath') ?? 'reza';
}

/** Folder name on disk: .reza, .REZA, etc. */
export function resolveRezaDataDirName(root: string): string | null {
  for (const name of ['.reza', '.REZA', '.Reza']) {
    if (fs.existsSync(path.join(root, name, 'context.db'))) {
      return name;
    }
  }
  try {
    const entries = fs.readdirSync(root, { withFileTypes: true });
    for (const e of entries) {
      if (e.isDirectory() && e.name.toLowerCase() === '.reza') {
        if (fs.existsSync(path.join(root, e.name, 'context.db'))) {
          return e.name;
        }
      }
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** First workspace folder that contains context.db; else first folder (for cwd when no db yet). */
export function getRezaWorkingDirectory(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    throw new Error('No workspace folder open.');
  }
  for (const f of folders) {
    const root = f.uri.fsPath;
    if (resolveRezaDataDirName(root)) {
      return root;
    }
  }
  return folders[0].uri.fsPath;
}

export function anyWorkspaceHasContextDb(): boolean {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) return false;
  return folders.some((f) => resolveRezaDataDirName(f.uri.fsPath) !== null);
}

async function runReza(args: string[]): Promise<unknown> {
  const cmd = `"${getRezaPath()}" ${args.join(' ')}`;
  const cwd = getRezaWorkingDirectory();
  try {
    const { stdout } = await exec(cmd, { cwd, timeout: 30_000 });
    return JSON.parse(stdout);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`reza command failed: ${cmd}\n${msg}`);
  }
}

// ---------------------------------------------------------------------------
// Graph data
// ---------------------------------------------------------------------------

export async function exportGraph(
  limit: number,
  kinds: string,
  sessionId?: string,
): Promise<GraphExportData> {
  const args = [
    'graph', 'export',
    '--limit', String(limit),
    '--kinds', kinds,
  ];
  if (sessionId) {
    args.push('--session-id', sessionId);
  }
  return runReza(args) as Promise<GraphExportData>;
}

export async function getGraphStats(): Promise<GraphStats> {
  return runReza(['graph', 'status', '--json']) as Promise<GraphStats>;
}

export async function getImpact(files: string[]): Promise<ImpactData> {
  const args = ['graph', 'impact', '--json', ...files];
  return runReza(args) as Promise<ImpactData>;
}

// ---------------------------------------------------------------------------
// Session data
// ---------------------------------------------------------------------------

export async function getActiveSessions(): Promise<SessionInfo[]> {
  return runReza(['session', 'list', '--status', 'active', '--json']) as Promise<SessionInfo[]>;
}

// ---------------------------------------------------------------------------
// Cross-tool session browser (list / scope / pack)
// ---------------------------------------------------------------------------

export interface SessionSummary {
  id: string;
  llm_name: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  last_turn_at: string | null;
  working_on: string;
  summary: string;
  source_tool: string | null;
  source_id: string | null;
  source_path: string | null;
  turn_count: number;
  token_total: number;
  files_touched: string[];
  first_user_message: string;
}

export interface SessionScope {
  session: SessionSummary;
  scope: {
    files: string[];
    nodes: Array<{
      qualified_name: string;
      kind: string;
      name: string;
      file_path: string;
      line_start: number;
      line_end: number;
      language: string;
      parent_name: string | null;
    }>;
    node_ids: string[];
    edges: Array<{
      kind: string;
      source: string;
      target: string;
      file_path: string;
      line: number;
    }>;
  };
}

export async function listAllSessions(
  limit: number = 50,
  source: 'all' | 'cursor' | 'codex' | 'claude' | 'manual' = 'all',
): Promise<SessionSummary[]> {
  const args = [
    'session', 'list',
    '--limit', String(limit),
    '--source', source,
    '--json',
  ];
  return runReza(args) as Promise<SessionSummary[]>;
}

export async function getSessionScope(sessionId: string): Promise<SessionScope> {
  return runReza(['session', 'graph', sessionId, '--json']) as Promise<SessionScope>;
}

export async function getActiveLocks(): Promise<Array<{
  file_path: string;
  session_id: string;
  llm_name: string;
  claimed_at: string;
}>> {
  return runReza(['locks', '--json']) as Promise<Array<{
    file_path: string;
    session_id: string;
    llm_name: string;
    claimed_at: string;
  }>>;
}

// ---------------------------------------------------------------------------
// Graph build
// ---------------------------------------------------------------------------

export async function buildGraph(projectDir: string): Promise<Record<string, unknown>> {
  return runReza(['graph', 'build', '--dir', `"${projectDir}"`]) as Promise<Record<string, unknown>>;
}

export async function updateGraph(projectDir: string): Promise<Record<string, unknown>> {
  return runReza(['graph', 'update', '--dir', `"${projectDir}"`]) as Promise<Record<string, unknown>>;
}
