/**
 * rezaClient.ts — CLI bridge for the reza VS Code extension.
 *
 * Spawns the reza CLI and parses JSON output. No native SQLite dependency.
 * All data comes from `reza <command> --json` stdout.
 */

import { exec as _exec } from 'child_process';
import { promisify } from 'util';
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

function getWorkspaceRoot(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    throw new Error('No workspace folder open.');
  }
  return folders[0].uri.fsPath;
}

async function runReza(args: string[]): Promise<unknown> {
  const cmd = `"${getRezaPath()}" ${args.join(' ')}`;
  const cwd = getWorkspaceRoot();
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
