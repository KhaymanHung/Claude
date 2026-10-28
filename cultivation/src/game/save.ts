// localStorage persistence. Format is compatible with the prototype's
// `cultivation-save-v1` (and migrates the older `lumen-save-v1`).
import { G } from './data';
import { Q } from './format';
import { LEGACY_SAVE_KEY, SAVE_KEY, START_LOG, fresh, type GameState } from './logic';

export interface Loaded { state: GameState; savedAt: number }

export function loadGame(): Loaded | null {
  let raw: string | null = null;
  try { raw = localStorage.getItem(SAVE_KEY) || localStorage.getItem(LEGACY_SAVE_KEY); } catch { return null; }
  if (!raw) return null;
  try {
    const d: any = JSON.parse(raw);
    d.log = (d.log || []).filter((e: { text: string }) => !/[A-Za-z]{2,}/.test(e.text));
    if (d.embersEarned == null) d.embersEarned = d.embers || 0;
    if (!d.log.length) d.log = [{ id: Math.random(), text: START_LOG, time: '--:--' }];
    // Pre-unit saves stored amounts in realm units.
    if (!d.qv) { const q = Q(d.realm || 0); d.light = (d.light || 0) * q; d.rq = (d.rq || 0) * q; d.qv = 1; }
    if (d.upgrades) {
      const U0 = d.upgrades;
      const lv = (k: string) => U0[k] === true ? 1 : (U0[k] || 0);
      const mv = (from: string, to: string) => { const n = lv(from); if (n) { U0[to] = lv(to) + n; delete U0[from]; } };
      mv('c2', 'c1'); mv('c4', 'c3'); mv('x1', 'r0'); mv('x2', 'r0');
      for (let i = 0; i < 7; i++) {
        let n = 0;
        for (let t = 0; t < 4; t++) { const k = `g${i}t${t}`, v = U0[k]; if (v) { n += v === true ? 1 : v; delete U0[k]; } }
        if (n) U0[`g${i}`] = (U0[`g${i}`] || 0) + n;
      }
    }
    const savedAt: number = d.savedAt || Date.now();
    delete d.savedAt;
    const state: GameState = { ...fresh(), ...d, realm: d.realm || 0, owned: G.map((_, i) => (d.owned || [])[i] || 0), toasts: [] };
    return { state, savedAt };
  } catch {
    return null;
  }
}

export function saveGame(s: GameState) {
  const { toasts, ...rest } = s;
  try { localStorage.setItem(SAVE_KEY, JSON.stringify({ ...rest, savedAt: Date.now() })); } catch { /* storage unavailable */ }
}

export function wipeSave() {
  try { localStorage.removeItem(SAVE_KEY); localStorage.removeItem(LEGACY_SAVE_KEY); } catch { /* storage unavailable */ }
}
