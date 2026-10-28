import type { MouseEvent, ReactNode, RefObject } from 'react';
import { G, GT, LAST, M, QH, QN } from '../game/data';
import { fmt, fq } from '../game/format';
import {
  breakthrough, canBreak, gateCost, gl, gSum, openGate, openXue, realmName, xueCost,
  type Derived, type GameState,
} from '../game/logic';
import { Figure } from './Figure';
import { amber, btnColors, dim, ember, mono, muted, text, type Act } from './ui';

export interface Floater { id: number; x: number; y: number; text: string }

interface Props {
  s: GameState; d: Derived; act: Act;
  orbRef: RefObject<HTMLDivElement>; floaters: Floater[];
  onGather: (e: MouseEvent) => void;
}

const actionBtn = (ok: boolean) => ({
  minHeight: 44, minWidth: 220, borderRadius: 8, ...btnColors(ok), cursor: 'pointer',
  display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 1, padding: '6px 16px',
});

function Pill({ color, border, title, children }: { color: string; border: string; title?: string; children: ReactNode }) {
  return <span title={title} style={{ fontSize: 12, padding: '3px 9px', borderRadius: 10, border: `1px solid ${border}`, color }}>{children}</span>;
}

/** Track state colors: done (ember), current (bright), locked (dim). */
const trackColors = (done: boolean, cur: boolean) => ({
  color: done ? ember : cur ? text : dim,
  border: done ? 'oklch(0.8 0.13 35 / .6)' : cur ? 'oklch(0.82 0.13 78 / .7)' : 'rgba(236,232,225,.1)',
});

function Meridians({ s, act }: { s: GameState; act: Act }) {
  const xue = s.xue || 0, opened = Math.floor(xue / 5);
  const cost = xue < 60 ? xueCost(xue, s) : 0, ok = xue < 60 && s.light >= cost;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: muted }}>已打通經脈 <span style={{ color: text, fontFamily: mono }}>{opened} / 12</span> · 穴脈加成 <span style={{ color: ember, fontFamily: mono }}>×{((1 + 0.03 * xue) * Math.pow(1.15, opened)).toFixed(2)}</span></span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', maxWidth: 360 }}>
        {M.map((m, i) => {
          const p = Math.max(0, Math.min(5, xue - i * 5)), done = p === 5, cur = !done && i === opened;
          return <Pill key={m.name} {...trackColors(done, cur)} title={done ? '已打通' : cur ? '正在衝穴' : '尚未打通'}>{done || !cur ? m.name : `${m.name} ${p}/5`}</Pill>;
        })}
      </div>
      {xue < 60
        ? <button onClick={() => act(openXue)} style={actionBtn(ok)}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>衝開{M[opened].name}第 {xue % 5 + 1} 穴</span>
            <span style={{ fontFamily: mono, fontSize: 12 }}>{fmt(cost)} 元氣</span>
          </button>
        : <span style={{ fontSize: 13, color: ember }}>十二經脈已全數打通。</span>}
      <span style={{ fontSize: 12, color: dim, textAlign: 'center', maxWidth: 340, textWrap: 'pretty' }}>每個穴道元氣 +3%，打通整條經脈再 ×1.15。轉世後需重新打通。</span>
    </div>
  );
}

function Gates({ s, act }: { s: GameState; act: Act }) {
  const r = s.realm, g = GT[r]!, j = gl(s, r), n = g.items.length, done = j >= n;
  const cost = done ? 0 : gateCost(r, j, s), ok = !done && s.light >= cost;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: muted }}>{g.title} <span style={{ color: text, fontFamily: mono }}>{j} / {n}</span> · 關卡加成 <span style={{ color: ember, fontFamily: mono }}>×{Math.pow(1.15, gSum(s)).toFixed(2)}</span></span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center', maxWidth: 360 }}>
        {g.items.map((it, k) => <Pill key={it} {...trackColors(k < j, k === j)}>{it}</Pill>)}
      </div>
      {!done
        ? <button onClick={() => act(openGate)} style={actionBtn(ok)}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{g.verb}「{g.items[j]}」</span>
            <span style={{ fontFamily: mono, fontSize: 12 }}>{fq(cost, r)} {QN[r]}</span>
          </button>
        : <span style={{ fontSize: 13, color: ember }}>「{g.title}」已圓滿。</span>}
      <span style={{ fontSize: 12, color: dim, textAlign: 'center', maxWidth: 340, textWrap: 'pretty' }}>每過一關，修煉速度 ×1.15。轉世後需重新闖關。</span>
    </div>
  );
}

function RealmBox({ s, act }: { s: GameState; act: Act }) {
  const r = s.realm, peak = r >= LAST, can = canBreak(s);
  const reqs = peak ? [] : r === 0
    ? [{ text: `打通十二經脈（${Math.floor((s.xue || 0) / 5)}/12）`, ok: (s.xue || 0) >= 60 }]
    : [
        { text: `完成「${GT[r]!.title}」（${gl(s, r)}/${GT[r]!.items.length}）`, ok: gl(s, r) >= GT[r]!.items.length },
        { text: `每部功法至少修習一層（${G.filter((_, i) => (s.owned[i] || 0) > 0).length}/${G.length}）`, ok: G.every((_, i) => (s.owned[i] || 0) > 0) },
      ];
  return (
    <div style={{ border: '1px solid rgba(236,232,225,.1)', borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
        <span style={{ fontSize: 17, fontWeight: 700, color: amber }}>{realmName(r)}</span>
        <span style={{ fontSize: 13, color: muted }}>境界加成 <span style={{ color: text, fontFamily: mono }}>×{fmt(Math.pow(5, r))}</span></span>
      </div>
      <span style={{ fontSize: 13, color: muted, textWrap: 'pretty' }}>
        {!peak ? `下一境界：${realmName(r + 1)} · ${QN[r]}凝練為「${QN[r + 1]}」，修煉速度 ×5，功法與秘訣重置為新項目` : '已證混元道祖，此世修為已到盡頭。轉世可帶著道果重修。'}
      </span>
      {reqs.map(q => (
        <div key={q.text} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: q.ok ? text : muted }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: q.ok ? amber : '#3a3732', flex: 'none' }} />
          <span>{q.text}</span>
        </div>
      ))}
      {!peak && (
        <button onClick={() => act(breakthrough)} style={{ minHeight: 44, borderRadius: 8, ...btnColors(can, ember), fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
          突破至{realmName(r + 1)}
        </button>
      )}
    </div>
  );
}

/** Left column: 元氣 readout, clickable figure, meridians/gates, realm and log. */
export function CultivatePanel({ s, d, act, orbRef, floaters, onGather }: Props) {
  const r = s.realm, unitColor = `oklch(0.8 0.12 ${QH[r]})`;
  return (
    <section style={{ flex: '1 1 340px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 28 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontFamily: mono, fontSize: 'clamp(44px,6vw,64px)', fontWeight: 500, letterSpacing: '-.03em', lineHeight: 1 }}>{fq(s.light, r)}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 8, color: muted, fontSize: 15 }}>
          <span style={{ color: unitColor, fontWeight: 700, fontSize: 18, textShadow: `0 0 12px ${unitColor}` }}>{QN[r]}</span>
          <span>· 每秒 <span style={{ color: text, fontFamily: mono }}>{fq(d.rate, r)}</span></span>
          <span style={{ fontSize: 12, color: dim }}>{r ? `1 ${QN[r]} = 1億 ${QN[r - 1]}` : ''}</span>
        </div>
      </div>

      <div ref={orbRef} style={{ position: 'relative', width: 340, maxWidth: '100%', height: 286, margin: '12px auto', userSelect: 'none' }}>
        <button className="figure-btn" onClick={onGather} aria-label="運轉元氣" style={{ position: 'absolute', inset: 0, border: 'none', padding: 0, background: 'none', cursor: 'pointer' }}>
          <Figure rate={d.rate} xue={s.xue || 0} realm={r} gatesDone={gl(s, r)} />
        </button>
        {floaters.map(f => (
          <div key={f.id} style={{ position: 'absolute', left: f.x, top: f.y, pointerEvents: 'none', fontFamily: mono, fontSize: 18, fontWeight: 500, color: '#fff7e6', textShadow: '0 0 8px rgba(0,0,0,.5)', animation: 'lumenFloat 900ms ease-out forwards' }}>{f.text}</div>
        ))}
      </div>
      <div style={{ textAlign: 'center', color: muted, fontSize: 14, marginTop: -12 }}>
        點擊運轉{QN[r]} · 每次 <span style={{ color: text, fontFamily: mono }}>+{fq(d.click, r)}</span>
      </div>

      {r === 0 ? <Meridians s={s} act={act} /> : GT[r] && <Gates s={s} act={act} />}

      <RealmBox s={s} act={act} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, borderTop: '1px solid rgba(236,232,225,.1)', paddingTop: 18 }}>
        <div style={{ fontSize: 12, letterSpacing: '.08em', textTransform: 'uppercase', color: muted }}>紀錄</div>
        {s.log.map(e => (
          <div key={e.id} style={{ display: 'flex', gap: 12, fontSize: 14, lineHeight: 1.4, animation: 'lumenIn 300ms ease' }}>
            <span style={{ fontFamily: mono, color: dim, flex: 'none' }}>{e.time}</span>
            <span style={{ color: e.kind === 'ach' ? amber : e.kind === 'ember' ? ember : text }}>{e.text}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
