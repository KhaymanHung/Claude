import { D, G, MS, PB, PL, QN, R, ZMAX, ZN } from '../game/data';
import { fAny, fmt, fq, Q } from '../game/format';
import {
  A, achN, buyDao, buyGen, buyN, buyPill, buyUp, buyZhen, costN, daoCost, L, msB, pCost, pLv, realmName,
  uCost, uLv, upgradesOf, zCost, type BuyMode, type Derived, type GameState,
} from '../game/logic';
import { amber, buyBtn, dim, ember, line, mono, muted, rowGrid, text, type Act } from './ui';

const sub = { color: muted, fontSize: 13 } as const;

export function SourcesTab({ s, d, act, mobile }: { s: GameState; d: Derived; act: Act; mobile: boolean }) {
  const r = s.realm;
  const visible = G.map((g, i) => i === 0 || (s.owned[i - 1] || 0) > 0 || (s.owned[i] || 0) > 0 || (s.rq || 0) >= g.cost * 0.5 * Q(r));
  const nextIdx = visible.indexOf(false);
  const modes: [BuyMode, string][] = [['1', '×1'], ['10', '×10'], ['max', '最大']];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <span style={{ color: muted, fontSize: 14 }}>功法會在你做別的事時持續吐納{QN[r]}。</span>
        <div style={{ display: 'flex', gap: 2, background: '#1a1916', borderRadius: 8, padding: 3 }}>
          {modes.map(([id, label]) => (
            <button key={id} onClick={() => act(st => ({ ...st, mode: id }))} style={{ border: 'none', borderRadius: 6, padding: '5px 10px', fontFamily: mono, fontSize: 12, cursor: 'pointer', background: s.mode === id ? '#2c2a25' : 'transparent', color: s.mode === id ? text : muted }}>{label}</button>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {G.map((_, i) => {
          if (!visible[i]) return null;
          const [name, desc] = R[r].gens[i], k = s.owned[i] || 0;
          const n = buyN(s, i), c = costN(i, k, n, s);
          return (
            <div key={i} style={rowGrid(mobile ? '10px' : '18px')}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, containerType: 'inline-size' }}>
                <div style={{ display: 'flex', flexWrap: 'nowrap', alignItems: 'baseline', gap: 8, whiteSpace: 'nowrap', overflow: 'hidden' }}>
                  <span style={{ fontSize: 'clamp(12px,6cqi,17px)', fontWeight: 600, flex: 'none' }}>{name}</span>
                  <span style={{ color: muted, fontSize: 'clamp(10px,4cqi,13px)', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{desc}</span>
                </div>
                <div style={{ color: muted, fontSize: 'clamp(9px,3.6cqi,12px)', fontFamily: mono, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fq(d.each[i], r)}/秒（每個）· 合計 {fq(d.each[i] * k, r)}/秒</div>
                <div style={{ color: amber, fontSize: 'clamp(9px,3.4cqi,11px)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>每 10 層產出 ×{MS}（目前 ×{fmt(msB(k))}，再 {10 - k % 10} 層）</div>
              </div>
              <div style={{ fontFamily: mono, fontSize: mobile ? 20 : 26, fontWeight: 500, minWidth: 32, textAlign: 'right' }}>{k}</div>
              <button onClick={() => act(st => buyGen(st, i))} style={buyBtn(s.light >= c, mobile ? 96 : 132)}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>升級 ×{n}</span>
                <span style={{ fontFamily: mono, fontSize: 12 }}>{fq(c, r)}</span>
              </button>
            </div>
          );
        })}
        {nextIdx > -1 && (
          <div style={{ padding: '16px 0', borderTop: '1px solid rgba(236,232,225,.08)', color: dim, fontSize: 14, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <span>更高深的功法</span>
            <span style={{ fontFamily: mono }}>於 本境界累積 {fmt(G[nextIdx].cost * 0.5)} {QN[r]} 出現</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function UpgradesTab({ s, act }: { s: GameState; act: Act }) {
  const all = upgradesOf(s.realm);
  const avail = all.filter(u => u.req(s)).map(u => ({ u, c: uCost(s, u), lv: uLv(s, u) })).sort((a, b) => a.c - b.c);
  const owned = all.reduce((a, u) => a + uLv(s, u), 0);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <span style={{ color: muted, fontSize: 14 }}>本境界共參悟 {owned} 層。秘訣沒有層數上限，每層價格遞增；突破境界或轉世後會重置。</span>
      {avail.length === 0 && <div style={{ padding: '32px 0', color: dim, fontSize: 15 }}>目前沒有可參悟的秘訣。修習更多功法後會陸續出現。</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 10 }}>
        {avail.map(({ u, c, lv }) => {
          const ok = s.light >= c;
          return (
            <button key={u.id} className="upgrade-card" onClick={() => act(st => buyUp(st, u))} style={{ textAlign: 'left', borderRadius: 10, border: `1px solid ${ok ? amber : line}`, background: '#1a1916', color: text, padding: 14, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 6, opacity: ok ? 1 : 0.55 }}>
              <span style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline', width: '100%' }}>
                <span style={{ fontSize: 15, fontWeight: 600 }}>{u.name}</span>
                <span style={{ fontFamily: mono, fontSize: 11, color: muted, flex: 'none' }}>第 {lv} 層</span>
              </span>
              <span style={{ fontSize: 13, color: muted }}>{u.desc}（每層）</span>
              <span style={{ fontFamily: mono, fontSize: 12, color: amber }}>{fq(c, s.realm)} {QN[s.realm]}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function PillsTab({ s, act }: { s: GameState; act: Act }) {
  const r = s.realm, zlv = s.zhen || 0, zc = zCost(s), zok = zlv < ZMAX && s.light >= zc;
  const item = { display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 } as const;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>丹藥</span>
        <span style={{ ...sub, textWrap: 'pretty' }}>本境界專用丹藥。突破境界後藥力不再適用，會重置並換成新境界的丹藥。</span>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {[0, 1].map(k => {
            const lv = pLv(s, k), mx = PB[k].max, c = pCost(s, k), full = lv >= mx, ok = !full && s.light >= c;
            return (
              <div key={k} style={rowGrid(14, 14)}>
                <div style={item}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{PL[r][k]}</div>
                  <div style={sub}>{k === 0 ? '修煉速度 +25%（每顆）' : r ? '突破關卡花費 −6%（每顆）' : '衝穴花費 −6%（每顆）'}</div>
                </div>
                <div style={{ fontFamily: mono, fontSize: 13, color: muted }}>{lv} / {mx}</div>
                <button onClick={() => act(st => buyPill(st, k))} style={buyBtn(ok, 110)}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{full ? '已滿' : '服用'}</span>
                  <span style={{ fontFamily: mono, fontSize: 12 }}>{full ? '藥力已飽和' : `${fq(c, r)} ${QN[r]}`}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>陣法</span>
        <span style={{ ...sub, textWrap: 'pretty' }}>陣法需與境界相配。突破後舊陣法鎮不住新境界的{QN[r]}，會失效並需改布更高階的陣法。</span>
        <div style={rowGrid(14, 14)}>
          <div style={item}>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{ZN[r]}</div>
            <div style={sub}>修煉速度 ×1.1（每重）· 目前 ×{Math.pow(1.1, zlv).toFixed(2)}</div>
          </div>
          <div style={{ fontFamily: mono, fontSize: 13, color: muted }}>{zlv} / {ZMAX} 重</div>
          <button onClick={() => act(buyZhen)} style={buyBtn(zok, 110, ember)}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{zlv >= ZMAX ? '已圓滿' : '加固'}</span>
            <span style={{ fontFamily: mono, fontSize: 12 }}>{zlv >= ZMAX ? '' : `${fq(zc, r)} ${QN[r]}`}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export function DaoTab({ s, act }: { s: GameState; act: Act }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <span style={{ color: muted, fontSize: 14, textWrap: 'pretty' }}>道境不會因轉世而重置。花費道果不會減少修煉速度加成（依累計獲得 {fmt(s.embersEarned || 0)} 枚計算）。</span>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {D.map(d => {
          const lv = L(s, d.id), c = daoCost(d, lv), maxed = lv >= d.max, ok = !maxed && s.embers >= c;
          return (
            <div key={d.id} style={rowGrid(18)}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                <div style={{ fontSize: 17, fontWeight: 600 }}>{d.name}</div>
                <div style={sub}>{d.desc}（每層）</div>
              </div>
              <div style={{ fontFamily: mono, fontSize: 13, color: muted, textAlign: 'right' }}>{d.max === Infinity ? `${lv} 層` : `${lv} / ${d.max} 層`}</div>
              <button onClick={() => act(st => buyDao(st, d))} style={buyBtn(ok, 132, ember)}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{maxed ? '圓滿' : '精進'}</span>
                <span style={{ fontFamily: mono, fontSize: 12 }}>{maxed ? '已圓滿' : `${c} 道果`}</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function RecordsTab({ s, open, onToggle }: { s: GameState; open: Record<string, boolean>; onToggle: (cat: string) => void }) {
  const n = achN(s);
  const stats = [
    ['累計修為', fAny(s.allTime)], ['本世', fAny(s.lifetime)], ['境界', realmName(s.realm)], ['運氣次數', fmt(s.clicks)],
    ['轉世次數', String(s.collapses)], ['成就', `${n}/${A.length}`], ['成就加成', `+${(n * 0.5).toFixed(1)}%`],
  ];
  const groups: { name: string; list: typeof A }[] = [];
  for (const a of A) { let g = groups.find(x => x.name === a.cat); if (!g) groups.push(g = { name: a.cat, list: [] }); g.list.push(a); }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 10 }}>
        {stats.map(([label, value]) => (
          <div key={label} style={{ background: '#1a1916', borderRadius: 10, padding: 14, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 12, color: muted }}>{label}</span>
            <span style={{ fontFamily: mono, fontSize: 20 }}>{value}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {groups.map(g => {
          const done = g.list.filter(a => s.ach[a.id]).length, isOpen = !!open[g.name];
          return (
            <div key={g.name} style={{ display: 'flex', flexDirection: 'column', borderTop: '1px solid rgba(236,232,225,.08)' }}>
              <button onClick={() => onToggle(g.name)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 0', background: 'none', border: 'none', color: text, cursor: 'pointer', textAlign: 'left', minHeight: 44 }}>
                <span style={{ fontFamily: mono, fontSize: 12, color: muted, width: 12 }}>{isOpen ? '▾' : '▸'}</span>
                <span style={{ fontSize: 15, fontWeight: 600, flex: 1 }}>{g.name}</span>
                <span style={{ fontFamily: mono, fontSize: 13, color: done === g.list.length ? amber : muted }}>{done} / {g.list.length}</span>
              </button>
              {isOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', padding: '0 0 10px 24px' }}>
                  {g.list.map(a => (
                    <div key={a.id} style={{ display: 'flex', flexWrap: 'wrap', columnGap: 12, alignItems: 'baseline', padding: '7px 0', opacity: s.ach[a.id] ? 1 : 0.4 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', flex: 'none', background: s.ach[a.id] ? amber : '#3a3732', alignSelf: 'center' }} />
                      <span style={{ fontSize: 14, fontWeight: 600 }}>{a.name}</span>
                      <span style={{ fontSize: 13, color: muted }}>{a.desc}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
