// Pure game rules. Every action takes the current state and returns the next
// state, or null when the action is not allowed (can't afford, maxed, …).
import { BN, G, GT, LAST, M, MS, PB, PL, QN, R, XB, ZMAX, ZN, type DaoItem } from './data';
import { Q, fAny, fmt } from './format';

export type BuyMode = '1' | '10' | 'max';

export interface LogEntry { id: number; text: string; time: string; kind?: 'ach' | 'ember' }
export interface Toast { id: number; title: string; name: string; desc: string; at: number }

export interface GameState {
  light: number;          // current 元氣, in base units
  lifetime: number;       // earned this life
  allTime: number;        // earned across all lives
  owned: number[];        // technique levels
  upgrades: Record<string, number | boolean>; // 秘訣 levels (true = legacy level 1)
  embers: number;         // 道果 on hand
  embersEarned: number;   // 道果 earned in total
  dao: Record<string, number>;
  qv: number;             // save version marker for the per-realm unit change
  xue: number;            // acupoints opened (0–60)
  realm: number;
  rq: number;             // earned since entering this realm
  ltY?: number;           // lifetime when 元嬰 was reached
  gates: number[];        // gates cleared per realm
  pills: Record<string, number>;
  zhen: number;           // formation level
  ach: Record<string, boolean>;
  clicks: number;
  collapses: number;      // reincarnations
  log: LogEntry[];
  mode: BuyMode;
  toasts?: Toast[];       // transient, not saved
}

export const SAVE_KEY = 'cultivation-save-v1';
export const LEGACY_SAVE_KEY = 'lumen-save-v1';
export const START_LOG = '你坐了下來。試著運轉一下元氣。';

export function fresh(): GameState {
  return { light: 0, lifetime: 0, allTime: 0, owned: G.map(() => 0), upgrades: {}, embers: 0, embersEarned: 0, dao: {}, qv: 1, xue: 0, realm: 0, rq: 0, gates: [], pills: {}, zhen: 0, ach: {}, clicks: 0, collapses: 0, log: [], mode: '1', toasts: [] };
}

// ---------- small accessors ----------

export const realmName = (r: number) => R[r].name + (r <= 8 ? '期' : '');
export const L = (s: GameState, id: string) => (s.dao || {})[id] || 0;
export const gl = (s: GameState, r: number) => (s.gates || [])[r] || 0;
export const gSum = (s: GameState) => (s.gates || []).reduce((a, b) => a + (b || 0), 0);
export const pLv = (s: GameState, k: number) => (s.pills || {})['p' + k] || 0;
export const msB = (k: number) => Math.pow(MS, Math.floor(k / 10));
export const emB = (s: GameState) => Math.pow(1 + (s.embersEarned || 0), 0.08);

// ---------- 秘訣 ----------

export interface Upgrade {
  id: string; kind: 'gen' | 'click' | 'clickPct' | 'global'; name: string; desc: string; cost: number;
  gen?: number; mult?: number; pct?: number; req: (s: GameState) => boolean;
}

function buildUpgrades(r: number): Upgrade[] {
  const RN = R[r];
  const list: Upgrade[] = G.map((g, i) => ({
    id: `g${i}`, kind: 'gen' as const, gen: i, name: `${RN.gens[i][0]}秘要`, desc: `${RN.gens[i][0]}產出翻倍`,
    cost: g.cost * 2, req: (s: GameState) => (s.owned[i] || 0) >= 1,
  }));
  list.push(
    { id: 'c1', kind: 'click', mult: 2, name: '心無旁騖', desc: '運氣所得翻倍', cost: 100, req: s => s.clicks >= 25 },
    { id: 'c3', kind: 'clickPct', pct: 0.02, name: '借力打力', desc: '運氣額外獲得每秒產出的 2%', cost: 50000, req: s => (s.rq || 0) >= 2e4 * Q(s.realm) },
  );
  RN.ups.forEach((n, k) => list.push({ id: 'r' + k, kind: 'global', mult: 2, name: n, desc: '所有元氣翻倍', cost: 5e5, req: s => (s.rq || 0) >= 2e5 * Q(s.realm) }));
  return list;
}
const UC: Upgrade[][] = [];
export const upgradesOf = (r: number) => UC[r] || (UC[r] = buildUpgrades(r));

export function uLv(s: GameState, u: Upgrade) { const v = s.upgrades[u.id]; return v === true ? 1 : (v || 0); }
const U_GROW = { gen: 10, global: 20, click: 10, clickPct: 8 };
export const uCost = (s: GameState, u: Upgrade) => u.cost * Q(s.realm) * Math.pow(U_GROW[u.kind], uLv(s, u)) * (1 - 0.01 * L(s, 'd9'));

// ---------- production ----------

export interface Derived { each: number[]; rate: number; click: number }

export function derive(s: GameState): Derived {
  let global = 1, clickMult = 1, clickPct = 0;
  const gm = G.map(() => 1);
  for (const u of upgradesOf(s.realm)) {
    const n = uLv(s, u); if (!n) continue;
    if (u.kind === 'gen') gm[u.gen!] *= Math.pow(2, n);
    else if (u.kind === 'global') global *= Math.pow(u.mult!, n);
    else if (u.kind === 'click') clickMult *= Math.pow(u.mult!, n);
    else clickPct += u.pct! * n;
  }
  clickPct += 0.01 * L(s, 'd11');
  global *= (1 + 0.25 * pLv(s, 0)) * Math.pow(1.1, s.zhen || 0);
  global *= Math.pow(1.02, L(s, 'd13'));
  global *= 1 + 0.02 * L(s, 'd1');
  global *= 1 + 0.005 * achN(s);
  global *= Math.pow(5, s.realm) * Math.pow(1.15, gSum(s));
  const xu = s.xue || 0;
  global *= (1 + 0.03 * xu) * Math.pow(1.15, Math.floor(xu / 5));
  clickMult *= Math.pow(1.5, L(s, 'd2'));
  const em = emB(s), QQ = Q(s.realm);
  const each = G.map((g, i) => g.rate * gm[i] * msB(s.owned[i] || 0) * global * em * QQ);
  const rate = each.reduce((a, e, i) => a + e * (s.owned[i] || 0), 0);
  return { each, rate, click: clickMult * em * QQ + rate * clickPct };
}

// ---------- costs ----------

const cf = (s: GameState) => 1 - 0.01 * L(s, 'd4');
/** Cost of n levels of technique i starting from level k. */
export function costN(i: number, k: number, n: number, s: GameState) {
  const b = G[i].cost * Q(s.realm) * cf(s) * Math.pow(1.15, k);
  return b * (Math.pow(1.15, n) - 1) / 0.15;
}
export function buyN(s: GameState, i: number) {
  if (s.mode !== 'max') return Number(s.mode);
  const b = G[i].cost * Q(s.realm) * cf(s) * Math.pow(1.15, s.owned[i] || 0);
  return Math.max(1, Math.floor(Math.log(s.light * 0.15 / b + 1) / Math.log(1.15)));
}
export const gateCost = (r: number, j: number, s: GameState) => {
  const n = GT[r]!.items.length;
  return (1 - 0.06 * pLv(s, 1)) * BN[r] * Q(r) * 0.55 * Math.pow(2.2, j - (n - 1)) * (1 - 0.01 * L(s, 'd8'));
};
export const xueCost = (k: number, s: GameState) => (1 - 0.06 * pLv(s, 1)) * XB[Math.floor(k / 5)] * Math.pow(1.6, k % 5) * (1 - 0.01 * L(s, 'd7'));
export const pCost = (s: GameState, k: number) => PB[k].base * Q(s.realm) * Math.pow(PB[k].grow, pLv(s, k));
export const zCost = (s: GameState) => 500 * Q(s.realm) * Math.pow(6, s.zhen || 0);
export const daoCost = (d: DaoItem, lv: number) => Math.ceil(d.base * Math.pow(d.grow, lv));
export const offlineCapHours = (s: GameState) => 24 + 6 * L(s, 'd12');
export const offlineRate = (s: GameState) => 1 + 0.1 * L(s, 'd3');

// ---------- log / toasts ----------

export function addLog(s: GameState, text: string, kind?: LogEntry['kind']): GameState {
  const d = new Date();
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  return { ...s, log: [{ id: Math.random(), text, time, kind }, ...s.log].slice(0, 6) };
}
const addToast = (s: GameState, title: string, name: string, desc: string): GameState =>
  ({ ...s, toasts: [...(s.toasts || []), { id: Math.random(), title, name, desc, at: Date.now() }].slice(-3) });

export const TOAST_MS = 3600;

// ---------- achievements ----------

export interface Achievement { id: string; cat: string; name: string; desc: string; test: (s: GameState) => boolean }

export const A: Achievement[] = (() => {
  const list: Achievement[] = [];
  const add = (cat: { id: string; name: string; desc: (v: number) => string }, items: [number, string][], test: (s: GameState, v: number) => boolean) =>
    items.forEach(([v, name], i) => list.push({ id: cat.id + i, cat: cat.name, name, desc: cat.desc(v), test: s => test(s, v) }));
  const sumOwned = (s: GameState) => s.owned.reduce((x, y) => x + (y || 0), 0);
  const sumUp = (s: GameState) => Object.values(s.upgrades || {}).reduce<number>((x, y) => x + (y === true ? 1 : (y || 0) as number), 0);
  const sumDao = (s: GameState) => Object.values(s.dao || {}).reduce((x, y) => x + (y || 0), 0);
  add({ id: 'qe', name: '元氣', desc: v => `累計 ${fAny(v)}` }, [[1e3, '氣感初生'], [1e11, '小有積蓄'], [1e19, '靈氣充盈'], [1e27, '氣海如淵'], [1e35, '靈氣外溢'], [1e43, '天地異象'], [1e51, '吞天納地'], [1e59, '氣貫長虹'], [1e67, '星河倒灌'], [1e75, '萬古長青'], [1e83, '混沌初開'], [1e91, '大道無垠']], (s, v) => s.allTime >= v);
  add({ id: 'qr', name: '產出', desc: v => `每秒產出 ${fAny(v)}` }, [[10, '細水長流'], [1e8, '源源不絕'], [1e16, '江河奔流'], [1e24, '百川歸海'], [1e32, '潮生潮落'], [1e40, '天河傾瀉'], [1e48, '星海翻湧'], [1e56, '造化無窮']], (s, v) => derive(s).rate >= v);
  add({ id: 'qc', name: '運氣', desc: v => `運氣 ${fmt(v)} 次` }, [[500, '勤修不輟'], [2000, '持之以恆'], [5000, '鐵杵磨針'], [10000, '走火邊緣'], [25000, '入魔不悔']], (s, v) => s.clicks >= v);
  add({ id: 'qg', name: '功法', desc: v => `本境界功法合計 ${v} 層` }, [[50, '博覽群經'], [100, '功法百層'], [200, '學究天人'], [400, '萬卷在胸'], [700, '一代宗師']], (s, v) => sumOwned(s) >= v);
  add({ id: 'qs', name: '功法', desc: v => `單一功法修習 ${v} 層` }, [[50, '專精一道'], [100, '登峰造極'], [200, '前無古人']], (s, v) => Math.max(...s.owned) >= v);
  add({ id: 'qu', name: '秘訣', desc: v => `本境界秘訣合計 ${v} 層` }, [[10, '略有心得'], [30, '觸類旁通'], [60, '融會貫通'], [100, '秘傳萬卷']], (s, v) => sumUp(s) >= v);
  add({ id: 'qm', name: '經脈', desc: v => `打通 ${v} 條經脈` }, [[1, '一脈貫通'], [3, '三脈齊開'], [6, '半身通透'], [9, '九脈歸流'], [12, '十二重樓']], (s, v) => (s.xue || 0) >= v * 5);
  add({ id: 'qj', name: '境界', desc: v => `踏入${realmName(v)}` }, [[1, '築基成功'], [2, '結成金丹'], [3, '元嬰初成'], [4, '化神歸元'], [5, '煉虛合道'], [6, '合體大成'], [7, '大乘在望'], [8, '天劫將至'], [9, '羽化登仙'], [10, '玄之又玄'], [11, '金仙不朽'], [12, '太乙歸一'], [13, '大羅天上'], [14, '混元證道']], (s, v) => s.realm >= v);
  add({ id: 'qk', name: '關卡', desc: v => `完成「${GT[v]!.title}」` }, [[1, '道基九重'], [2, '金丹九轉'], [3, '元嬰大成'], [4, '六識通明'], [5, '五行歸元'], [6, '四象合一'], [7, '八卦圓融'], [8, '萬劫不磨'], [9, '三花聚頂'], [10, '五氣朝元'], [11, '九竅玲瓏'], [12, '七星連珠'], [13, '八極歸一'], [14, '三才證道']], (s, v) => s.realm > v || gl(s, v) >= GT[v]!.items.length);
  add({ id: 'qt', name: '轉世', desc: v => `轉世 ${v} 次` }, [[1, '輪迴'], [3, '三世修行'], [5, '五世同參'], [10, '十世善人'], [25, '萬世不滅']], (s, v) => s.collapses >= v);
  add({ id: 'qf', name: '道果', desc: v => `累計獲得 ${v} 枚道果` }, [[10, '道果初結'], [50, '碩果累累'], [200, '道果滿園'], [1000, '萬果歸宗']], (s, v) => (s.embersEarned || 0) >= v);
  add({ id: 'qd', name: '道境', desc: v => `道境合計 ${v} 層` }, [[5, '道心初定'], [20, '道境漸深'], [50, '道法自然'], [100, '與道同遊']], (s, v) => sumDao(s) >= v);
  return list;
})();

export function achN(s: GameState) { return A.filter(a => (s.ach || {})[a.id]).length; }

export function checkAch(s: GameState): GameState {
  let ns = s;
  for (const a of A) if (!ns.ach[a.id] && a.test(ns)) {
    ns = addLog({ ...ns, ach: { ...ns.ach, [a.id]: true } }, `達成成就：${a.name}。修煉速度永久 +0.5%。`, 'ach');
    ns = addToast(ns, '成就達成', a.name, a.desc + ' · 修煉速度永久 +0.5%');
  }
  return ns;
}

// ---------- reincarnation (轉世) ----------

export interface GainRow { label: string; note: string; value: string; color: string }

export function gainParts(s: GameState): { total: number; rows: GainRow[] } {
  const r = s.realm, ok = r >= 3;
  const rp = ok ? 1 + 0.25 * (r - 3) : 0;
  const base = s.ltY || s.lifetime || 1, ratio = (s.lifetime || 0) / base;
  const lp = ok ? Math.max(0, Math.floor(Math.log10(Math.max(1, ratio)) / 8)) * 0.5 : 0;
  const nextLt = base * Math.pow(10, (lp * 2 + 1) * 8);
  let gc = 0; for (let k = 3; k <= LAST; k++) gc += gl(s, k);
  const gp = ok ? gc * 0.05 : 0;
  const raw = rp + lp + gp, mult = Math.pow(1.1, L(s, 'd5'));
  const total = Math.floor(raw * mult);
  const fx = (v: number) => '+' + (Number.isInteger(v) ? v : v.toFixed(2));
  const rows = [
    { label: '境界', note: ok ? `${realmName(r)} · 元嬰 1 枚，之後每境界 +0.25` : '踏入元嬰期得 1 枚，之後每境界 +0.25', v: rp },
    { label: '元嬰後修為', note: ok ? `踏入元嬰後累積修為每翻 1億 倍 +0.5 · 下一枚於本世 ${fAny(nextLt)}` : '踏入元嬰後開始計算', v: lp },
    { label: '高階關卡', note: `元嬰期起每過一關 +0.05 · 已過 ${gc} 關`, v: gp },
  ];
  return { total, rows: rows.map(x => ({ label: x.label, note: x.note, value: fx(x.v), color: x.v > 0 ? '#ece8e1' : '#6f6a62' })) };
}
export const gainOf = (s: GameState) => gainParts(s).total;
export const canPrestige = (s: GameState) => gainOf(s) >= 1 && s.realm >= 3;

export function canBreak(s: GameState) {
  const r = s.realm;
  if (r >= LAST) return false;
  return r === 0 ? (s.xue || 0) >= 60 : gl(s, r) >= GT[r]!.items.length && G.every((_, i) => (s.owned[i] || 0) > 0);
}

// ---------- actions ----------

const earn = (s: GameState, g: number): GameState =>
  ({ ...s, light: s.light + g, lifetime: s.lifetime + g, allTime: s.allTime + g, rq: (s.rq || 0) + g });

/** Advance the simulation by dt seconds and expire old toasts. */
export function tick(s: GameState, dt: number, now: number): GameState | null {
  const g = derive(s).rate * dt;
  const old = s.toasts || [], tt = old.filter(t => now - t.at < TOAST_MS);
  if (!g && tt.length === old.length) return null;
  return checkAch({ ...earn(s, g), toasts: tt });
}

export function gather(s: GameState): GameState {
  return checkAch({ ...earn(s, derive(s).click), clicks: s.clicks + 1 });
}

export function buyGen(s: GameState, i: number): GameState | null {
  const k = s.owned[i] || 0, n = buyN(s, i), c = costN(i, k, n, s);
  if (c > s.light) return null;
  const owned = [...s.owned]; owned[i] = k + n;
  let ns: GameState = { ...s, light: s.light - c, owned };
  if (k === 0) ns = addLog(ns, `開始修習「${R[s.realm].gens[i][0]}」。`);
  return checkAch(ns);
}

export function buyUp(s: GameState, u: Upgrade): GameState | null {
  const lv = uLv(s, u), c = uCost(s, u);
  if (s.light < c) return null;
  return addLog({ ...s, light: s.light - c, upgrades: { ...s.upgrades, [u.id]: lv + 1 } }, `參悟「${u.name}」至第 ${lv + 1} 層。`);
}

export function buyPill(s: GameState, k: number): GameState | null {
  const lv = pLv(s, k), c = pCost(s, k);
  if (lv >= PB[k].max || s.light < c) return null;
  return addLog({ ...s, light: s.light - c, pills: { ...(s.pills || {}), ['p' + k]: lv + 1 } }, `服下${PL[s.realm][k]}（第 ${lv + 1} 顆）。`);
}

export function buyZhen(s: GameState): GameState | null {
  const lv = s.zhen || 0, c = zCost(s);
  if (lv >= ZMAX || s.light < c) return null;
  return addLog({ ...s, light: s.light - c, zhen: lv + 1 }, `${ZN[s.realm]}加固至第 ${lv + 1} 重。`);
}

export function buyDao(s: GameState, d: DaoItem): GameState | null {
  const lv = L(s, d.id), c = daoCost(d, lv);
  if (lv >= d.max || s.embers < c) return null;
  return addLog({ ...s, embers: s.embers - c, dao: { ...s.dao, [d.id]: lv + 1 } }, `道境精進：${d.name} 第 ${lv + 1} 層。`, 'ember');
}

export function openXue(s: GameState): GameState | null {
  const k = s.xue || 0;
  if (k >= 60 || s.light < xueCost(k, s)) return null;
  const m = M[Math.floor(k / 5)];
  const ns: GameState = { ...s, light: s.light - xueCost(k, s), xue: k + 1 };
  return (k + 1) % 5 === 0 ? addLog(ns, `打通了${m.name}！元氣 ×1.15。`, 'ach') : addLog(ns, `衝開${m.name}第 ${k % 5 + 1} 穴。`);
}

export function openGate(s: GameState): GameState | null {
  const r = s.realm, g = GT[r]; if (!g) return null;
  const j = gl(s, r); if (j >= g.items.length) return null;
  const c = gateCost(r, j, s); if (s.light < c) return null;
  const gates = [...(s.gates || [])]; gates[r] = j + 1;
  const done = j + 1 === g.items.length;
  const ns = addLog({ ...s, light: s.light - c, gates }, `${g.verb}「${g.items[j]}」，元氣 ×1.15。`, done ? 'ach' : undefined);
  return done ? addToast(ns, '關卡圓滿', g.title, '已可突破至下一境界') : ns;
}

export function breakthrough(s: GameState): GameState | null {
  if (!canBreak(s)) return null;
  const nr = s.realm + 1, nm = realmName(nr);
  let ns: GameState = { ...s, realm: nr, rq: 0, light: 0, owned: G.map(() => 0), upgrades: {}, pills: {}, zhen: 0, ...(nr === 3 ? { ltY: s.lifetime || 1 } : {}) };
  ns = addLog(ns, `突破成功，踏入${nm}！${QN[nr - 1]}凝練為「${QN[nr]}」，1 ${QN[nr]} = 1億 ${QN[nr - 1]}。`, 'ember');
  ns = addToast(ns, '境界突破', nm, `${QN[nr - 1]}凝練為「${QN[nr]}」· 功法與秘訣煥然一新`);
  return checkAch(ns);
}

export function prestige(s: GameState): GameState | null {
  const gain = gainOf(s);
  if (!canPrestige(s)) return null;
  return checkAch(addLog({
    ...s, light: 0, lifetime: 0, owned: G.map((_, i) => i === 0 ? 10 * L(s, 'd6') : 0), upgrades: {}, xue: 5 * L(s, 'd10'), realm: 0, rq: 0, gates: [], ltY: 0, pills: {}, zhen: 0,
    embers: s.embers + gain, embersEarned: (s.embersEarned || 0) + gain, collapses: s.collapses + 1,
  }, `轉世重修，帶著 ${gain} 枚道果投胎。前世記憶有點模糊。`, 'ember'));
}

/** Credit offline progress for `secs` seconds away (capped by 道境). */
export function applyOffline(s: GameState, secsAway: number): { state: GameState; secs: number; earned: number } {
  const secs = Math.min(secsAway, offlineCapHours(s) * 3600);
  const earned = derive(s).rate * secs * offlineRate(s);
  return { state: earn(s, earned), secs, earned };
}
