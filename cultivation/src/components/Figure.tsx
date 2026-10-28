import { memo, useEffect, useRef, type CSSProperties } from 'react';
import { GT, M } from '../game/data';

const amber = 'oklch(0.82 0.13 78)';
const glow = 'drop-shadow(0 0 3px oklch(0.85 0.13 78))';
const lay: CSSProperties = { position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' };

type Pt = [number, number];
const bez = (p0: Pt, c: Pt, p1: Pt, t: number): Pt =>
  [(1 - t) * (1 - t) * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0], (1 - t) * (1 - t) * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]];

const CORE = ['M365 28 L365 525', 'M365 185 Q320 192 262 205 M365 185 Q410 192 468 205'];
const LINES = M.map(m => { const [p0, c1, p1, c2, p2] = m.pts; return 'M' + p0 + ' Q' + c1 + ' ' + p1 + ' Q' + c2 + ' ' + p2; });
/** Five acupoint positions along each meridian. */
const DOTS: Pt[][] = M.map(m => {
  const [p0, c1, p1, c2, p2] = m.pts;
  return ([[p0, c1, p1, .3], [p0, c1, p1, .7], [p1, c2, p2, .25], [p1, c2, p2, .6], [p1, c2, p2, .95]] as [Pt, Pt, Pt, number][]).map(([a, c, b, t]) => bez(a, c, b, t));
});
const POINTS: Pt[] = [[360, 62], [365, 250], [365, 420]];

/** Pale-silver 元氣 particles drifting around the figure. */
const Particles = memo(function Particles() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    interface P { x: number; y: number; a: number; sp: number; r: number; ph: number; life: number; max: number }
    const P: P[] = [];
    const spawn = (c: HTMLCanvasElement): P => ({ x: Math.random() * c.clientWidth, y: Math.random() * c.clientHeight, a: Math.random() * 6.28, sp: .15 + Math.random() * .45, r: .5 + Math.random() * 1.5, ph: Math.random() * 6.28, life: 0, max: 400 + Math.random() * 600 });
    let raf = 0;
    const loop = () => {
      const c = ref.current;
      if (c) {
        const dpr = window.devicePixelRatio || 1, w = c.clientWidth, hh = c.clientHeight;
        if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(hh * dpr); }
        const x = c.getContext('2d')!;
        x.setTransform(dpr, 0, 0, dpr, 0, 0);
        x.clearRect(0, 0, w, hh);
        while (P.length < 70) P.push(spawn(c));
        for (let i = 0; i < P.length; i++) {
          const p = P[i];
          p.a += (Math.random() - .5) * .35;
          p.x += Math.cos(p.a) * p.sp; p.y += Math.sin(p.a) * p.sp - .08;
          p.life++; p.ph += .05;
          if (p.life > p.max || p.x < -10 || p.x > w + 10 || p.y < -10 || p.y > hh + 10) { P[i] = spawn(c); continue; }
          const fade = Math.min(1, p.life / 60, (p.max - p.life) / 60);
          const al = fade * (.35 + .45 * (.5 + .5 * Math.sin(p.ph)));
          x.beginPath(); x.arc(p.x, p.y, p.r, 0, 6.283);
          x.fillStyle = `rgba(222,228,238,${al})`;
          x.shadowColor = 'rgba(210,220,235,.8)'; x.shadowBlur = 4;
          x.fill();
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} style={{ position: 'absolute', left: -40, top: -40, width: 'calc(100% + 80px)', height: 'calc(100% + 80px)', pointerEvents: 'none' }} />;
});

function Flow({ d, i, on, lv, dur }: { d: string; i: number; on: boolean; lv: number; dur: string }) {
  return <>
    <path d={d} strokeWidth={2.4} strokeOpacity={on ? 0.4 : 0.16} />
    {on && <path d={d} strokeWidth={5} strokeOpacity={0.55 + lv * 0.45} strokeDasharray="8 32" style={{ animation: `qiFlow ${dur} linear infinite`, animationDelay: `${-i * 0.37}s`, filter: glow }} />}
  </>;
}

interface Props { rate: number; xue: number; realm: number; gatesDone: number }

/** Seated cultivator with meridians, acupoints, gate arc and halo. */
export function Figure({ rate, xue, realm, gatesDone }: Props) {
  const opened = Math.floor(xue / 5);
  const lv = Math.min(1, Math.log10(rate + 1) / 6);
  const dur = [2.4, 1.6, 1.1, 0.7][Math.min(3, Math.floor(lv * 4))] + 's';
  const gate = GT[realm];

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <svg viewBox="0 0 740 622" style={lay}>
        <defs>
          <radialGradient id="qiHalo">
            <stop offset="0%" stopColor="oklch(0.85 0.13 78)" stopOpacity={0.3 + lv * 0.4} />
            <stop offset="100%" stopColor="oklch(0.6 0.12 60)" stopOpacity={0} />
          </radialGradient>
        </defs>
        <circle cx={365} cy={320} r={270 + lv * 70} fill="url(#qiHalo)" style={{ animation: 'qiPulse 4s ease-in-out infinite' }} />
      </svg>
      <Particles />
      <img src="./assets/cultivator-v2.png" alt="" draggable={false} style={{ ...lay, objectFit: 'contain' }} />
      <svg viewBox="0 0 740 622" style={lay}>
        <g fill="none" stroke={amber} strokeLinecap="round">
          {CORE.map((d, i) => <Flow key={'c' + i} d={d} i={i} on lv={lv} dur={dur} />)}
          {LINES.map((d, i) => <Flow key={i} d={d} i={i} on={i < opened} lv={lv} dur={dur} />)}
        </g>
        {DOTS.map((row, i) => row.map(([x, y], j) => {
          const k = i * 5 + j, on = xue > k, nx = xue === k;
          return <circle key={`d${i}-${j}`} cx={x} cy={y} r={on ? 4.5 : nx ? 5 : 3.2}
            fill={on ? 'oklch(0.9 0.1 85)' : nx ? '#ece8e1' : 'rgba(236,232,225,.25)'}
            style={on ? { filter: glow } : nx ? { animation: 'qiPulse 1.2s ease-in-out infinite', filter: 'drop-shadow(0 0 4px #fff)' } : undefined} />;
        }))}
        {gate && gate.items.map((it, j) => {
          const n = gate.items.length;
          const ang = Math.PI * (1.12 + 0.76 * (n === 1 ? .5 : j / (n - 1)));
          const x = 365 + Math.cos(ang) * 330, y = 330 + Math.sin(ang) * 300, on = j < gatesDone, nx = j === gatesDone;
          return (
            <g key={'gt' + j}>
              <circle cx={x} cy={y} r={on ? 13 : nx ? 12 : 9} fill={on ? 'oklch(0.8 0.13 35)' : nx ? '#ece8e1' : 'rgba(236,232,225,.12)'}
                stroke={on ? 'none' : 'rgba(236,232,225,.35)'} strokeWidth={2}
                style={on ? { filter: 'drop-shadow(0 0 8px oklch(0.8 0.13 35))' } : nx ? { animation: 'qiPulse 1.2s ease-in-out infinite' } : undefined} />
              <text x={x} y={y - 22} textAnchor="middle" fontSize={22} fill={on ? 'oklch(0.85 0.1 40)' : '#6f6a62'} style={{ fontFamily: "'Noto Sans TC',sans-serif" }}>
                {it.replace(/重道基|重天劫|轉$/, m => m === '轉' ? '轉' : '')}
              </text>
            </g>
          );
        })}
        {POINTS.map(([x, y], i) => (
          <circle key={'p' + i} cx={x} cy={y} r={i === 2 ? 16 + lv * 14 : 9} fill={i === 2 ? 'oklch(0.9 0.1 85)' : amber}
            style={{ animation: `qiPulse ${2 + i * 0.6}s ease-in-out infinite`, filter: 'drop-shadow(0 0 6px oklch(0.85 0.13 78))' }} />
        ))}
      </svg>
    </div>
  );
}
