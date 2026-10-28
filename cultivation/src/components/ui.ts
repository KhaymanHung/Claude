import type { CSSProperties } from 'react';
import type { GameState } from '../game/logic';

export const amber = 'oklch(0.82 0.13 78)';
export const ember = 'oklch(0.8 0.13 35)';
export const muted = '#a39e94';
export const dim = '#6f6a62';
export const text = '#ece8e1';
export const line = 'rgba(236,232,225,.14)';
export const mono = "'JetBrains Mono',monospace";

/** Apply a pure game action; returning null leaves the state unchanged. */
export type Act = (fn: (s: GameState) => GameState | null) => void;

/** Filled when affordable, outlined otherwise. */
export const btnColors = (ok: boolean, accent = amber) =>
  ({ background: ok ? accent : 'transparent', color: ok ? '#11100e' : muted, border: `1px solid ${ok ? accent : line}` });

/** Two-line buy button used by techniques, pills, formations, 道境 and gates. */
export const buyBtn = (ok: boolean, minWidth: number | string, accent = amber): CSSProperties => ({
  minWidth, minHeight: 44, borderRadius: 8, ...btnColors(ok, accent), cursor: 'pointer',
  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1, padding: '6px 12px',
});

export const rowGrid = (gap: number | string, pad = 16): CSSProperties => ({
  display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto auto', gap, alignItems: 'center',
  padding: `${pad}px 0`, borderTop: '1px solid rgba(236,232,225,.08)',
});
