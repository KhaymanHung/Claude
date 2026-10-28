import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';
import { D, PB, QH, QN, ZMAX } from './game/data';
import { fmt, fmtTime, fq } from './game/format';
import {
  START_LOG, addLog, applyOffline, canPrestige, daoCost, derive, emB, fresh, gainOf, gainParts, gather, L,
  offlineCapHours, offlineRate, pCost, pLv, prestige, realmName, tick, uCost, upgradesOf, zCost, type GameState,
} from './game/logic';
import { loadGame, saveGame, wipeSave } from './game/save';
import { CultivatePanel, type Floater } from './components/CultivatePanel';
import { DaoTab, PillsTab, RecordsTab, SourcesTab, UpgradesTab } from './components/TabPanels';
import { amber, btnColors, dim, ember, mono, muted, text, type Act } from './components/ui';

type Tab = 'cultivate' | 'sources' | 'upgrades' | 'pills' | 'dao' | 'records';

// Dev-only tweaks: ?speed=10 (or 100) speeds up time, ?floating=0 hides click numbers.
const params = new URLSearchParams(location.search);
const SPEED = Number(params.get('speed')) || 1;
const FLOATING = params.get('floating') !== '0';

const MOBILE_QUERY = '(max-width: 720px), (pointer: coarse) and (max-width: 1024px)';
const initialGame = () => addLog(fresh(), START_LOG);

export default function App() {
  const [loaded] = useState(loadGame);
  const [s, setS] = useState<GameState>(() => loaded?.state ?? initialGame());
  const [started, setStarted] = useState(false);
  const [offline, setOffline] = useState<{ secs: number; earned: number } | null>(null);
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  const [tab, setTab] = useState<Tab>(() => (window.matchMedia(MOBILE_QUERY).matches ? 'cultivate' : 'sources'));
  const [achOpen, setAchOpen] = useState<Record<string, boolean>>({});
  const [confirm, setConfirm] = useState(false);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [floaters, setFloaters] = useState<Floater[]>([]);
  const tabTouched = useRef(false);
  const orbRef = useRef<HTMLDivElement>(null);

  const stateRef = useRef(s);
  stateRef.current = s;
  const startedRef = useRef(false);

  const act: Act = useCallback(fn => setS(prev => fn(prev) ?? prev), []);

  // Responsive layout: switch to the mobile tab bar under 720px (or touch under 1024px).
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = () => {
      setMobile(prevMobile => {
        if (mq.matches && !prevMobile && !tabTouched.current) setTab('cultivate');
        return mq.matches;
      });
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // Simulation and autosave run only after the title screen is dismissed.
  useEffect(() => {
    if (!started) return;
    let last = performance.now();
    const timer = setInterval(() => {
      const now = performance.now(), dt = (now - last) / 1000 * SPEED;
      last = now;
      act(st => tick(st, dt, Date.now()));
    }, 100);
    const save = () => saveGame(stateRef.current);
    const saveTimer = setInterval(save, 5000);
    window.addEventListener('beforeunload', save);
    return () => { clearInterval(timer); clearInterval(saveTimer); window.removeEventListener('beforeunload', save); save(); };
  }, [started, act]);

  const startGame = () => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (loaded) {
      const res = applyOffline(stateRef.current, (Date.now() - loaded.savedAt) / 1000);
      setS(res.state);
      if (res.secs > 10 && res.earned > 0) setOffline({ secs: res.secs, earned: res.earned });
    }
    setStarted(true);
  };

  const onGather = (e: MouseEvent) => {
    const rect = orbRef.current?.getBoundingClientRect();
    const x = rect && e.clientX ? e.clientX - rect.left : 120, y = rect && e.clientY ? e.clientY - rect.top : 120;
    const click = derive(stateRef.current).click;
    act(gather);
    if (!FLOATING) return;
    const id = Math.random();
    setFloaters(f => [...f, { id, x, y, text: '+' + fq(click, stateRef.current.realm) }].slice(-20));
    setTimeout(() => setFloaters(f => f.filter(fl => fl.id !== id)), 900);
  };

  const onPrestige = () => {
    if (!canPrestige(s)) return;
    if (!confirm) { setConfirm(true); setTimeout(() => setConfirm(false), 3000); return; }
    setConfirm(false);
    act(prestige);
  };

  const onWipe = () => {
    if (!confirmWipe) { setConfirmWipe(true); setTimeout(() => setConfirmWipe(false), 3000); return; }
    wipeSave();
    setConfirmWipe(false); setConfirm(false); setOffline(null); setTab(mobile ? 'cultivate' : 'sources');
    setS(initialGame());
  };

  const selectTab = (id: Tab) => { tabTouched.current = true; setTab(id); };

  // ---------- derived view values ----------
  const d = derive(s), r = s.realm, unitColor = `oklch(0.8 0.12 ${QH[r]})`;
  const T: Tab = !mobile && tab === 'cultivate' ? 'sources' : tab;
  const gain = gainOf(s), canRe = canPrestige(s), gp = gainParts(s);

  const upBadge = upgradesOf(r).filter(u => u.req(s) && s.light >= uCost(s, u)).length;
  const pillBadge = [0, 1].filter(k => pLv(s, k) < PB[k].max && s.light >= pCost(s, k)).length + ((s.zhen || 0) < ZMAX && s.light >= zCost(s) ? 1 : 0);
  const daoBadge = D.filter(x => L(s, x.id) < x.max && s.embers >= daoCost(x, L(s, x.id))).length;
  const tabs: [Tab, string, number][] = [
    ...(mobile ? [['cultivate', '修煉', 0] as [Tab, string, number]] : []),
    ['sources', '功法', 0], ['upgrades', '秘訣', upBadge], ['pills', '丹陣', pillBadge], ['dao', '道境', daoBadge], ['records', '成就', 0],
  ];
  const showLeft = !mobile || T === 'cultivate', showRight = !mobile || T !== 'cultivate';

  return (
    <div style={{ minHeight: '100vh', boxSizing: 'border-box', padding: 'clamp(20px,4vw,48px)', maxWidth: 1240, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 32, overflowX: 'clip' }}>
      {!started && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 40, background: "#11100e url('./assets/title.png') center/cover no-repeat", display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', padding: '0 24px max(56px,8vh)' }}>
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg,rgba(17,16,14,0) 45%,rgba(17,16,14,.55) 75%,rgba(17,16,14,.85) 100%)', pointerEvents: 'none' }} />
          <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22, animation: 'lumenIn 900ms ease' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <h1 style={{ margin: 0, fontSize: 'clamp(48px,9vw,88px)', fontWeight: 700, letterSpacing: '.2em', color: '#fff8ea', textShadow: '0 2px 24px rgba(0,0,0,.45),0 0 40px oklch(0.85 0.1 80 / .5)' }}>修真</h1>
              <span style={{ fontFamily: "'Schibsted Grotesk',sans-serif", fontSize: 'clamp(13px,1.6vw,16px)', letterSpacing: '.5em', color: '#f3ead8', textShadow: '0 1px 8px rgba(0,0,0,.5)' }}>CULTIVATION</span>
            </div>
            <button className="start-btn" onClick={startGame} style={{ minHeight: 52, minWidth: 220, padding: '0 36px', borderRadius: 999, border: '1px solid oklch(0.85 0.1 80 / .9)', background: 'rgba(17,16,14,.55)', backdropFilter: 'blur(6px)', color: '#fff8ea', fontSize: 18, fontWeight: 600, letterSpacing: '.3em', cursor: 'pointer', boxShadow: '0 0 28px oklch(0.85 0.12 80 / .35)' }}>
              {loaded ? '繼續修煉' : '開始遊戲'}
            </button>
          </div>
        </div>
      )}

      <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, borderBottom: '1px solid rgba(236,232,225,.1)', paddingBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, letterSpacing: '-.02em' }}>修真</h1>
          <span style={{ fontSize: 14, fontWeight: 600, color: amber, border: '1px solid oklch(0.82 0.13 78 / .5)', borderRadius: 6, padding: '2px 8px' }}>{realmName(r)}</span>
          {!mobile && <span style={{ color: muted, fontSize: 14 }}>一款打坐就能變強的放置遊戲，比真正修煉輕鬆一點。</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontFamily: mono, fontSize: 14 }}>
          <span style={{ color: muted }}>道果</span>
          <span style={{ color: ember, fontWeight: 500 }}>{fmt(s.embers)}</span>
          <span style={{ color: muted }}>· 修煉速度 +{Math.round((emB(s) - 1) * 100)}%</span>
        </div>
      </header>

      <main style={{ display: 'flex', flexWrap: 'wrap', gap: 40, alignItems: 'flex-start' }}>
        {showLeft && <CultivatePanel s={s} d={d} act={act} orbRef={orbRef} floaters={floaters} onGather={onGather} />}

        {showRight && (
          <section style={{ flex: '1.4 1 440px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 20 }}>
            {mobile && (
              <div style={{ position: 'sticky', top: 0, zIndex: 5, background: '#11100e', padding: '8px 0 10px', borderBottom: '1px solid rgba(236,232,225,.1)', display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: mono, fontSize: 26, fontWeight: 500 }}>{fq(s.light, r)}</span>
                <span style={{ color: unitColor, fontWeight: 700 }}>{QN[r]}</span>
                <span style={{ color: muted, fontSize: 13 }}>· 每秒 {fq(d.rate, r)}</span>
              </div>
            )}
            {!mobile && (
              <nav style={{ display: 'flex', gap: 4, borderBottom: '1px solid rgba(236,232,225,.1)' }}>
                {tabs.map(([id, label, badge]) => (
                  <button key={id} onClick={() => selectTab(id)} style={{ background: 'none', border: 'none', borderBottom: `2px solid ${T === id ? amber : 'transparent'}`, marginBottom: -1, padding: '10px 14px', color: T === id ? text : muted, fontSize: 15, fontWeight: 600, cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center' }}>
                    {label}
                    {badge > 0 && <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 500, background: amber, color: '#11100e', borderRadius: 10, padding: '1px 7px' }}>{badge}</span>}
                  </button>
                ))}
              </nav>
            )}

            {T === 'sources' && <SourcesTab s={s} d={d} act={act} mobile={mobile} />}
            {T === 'upgrades' && <UpgradesTab s={s} act={act} />}
            {T === 'records' && <RecordsTab s={s} open={achOpen} onToggle={cat => setAchOpen(o => ({ ...o, [cat]: !o[cat] }))} />}
            {T === 'pills' && <PillsTab s={s} act={act} />}
            {T === 'dao' && <DaoTab s={s} act={act} />}

            <div style={{ marginTop: 12, border: '1px solid rgba(236,232,225,.1)', borderRadius: 12, padding: 20, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '1 1 240px' }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: ember }}>轉世</span>
                <span style={{ fontSize: 14, color: muted, textWrap: 'pretty' }}>
                  {r < 3 ? `需踏入元嬰期才能轉世（目前：${realmName(r)}）。剛踏入元嬰期就轉世可得 1 枚道果，修得越深得越多。` : '散去境界、經脈、功法與秘訣，從練氣重新修起。每枚道果永久增加 10% 修煉速度。'}
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', marginTop: 8 }}>
                  {gp.rows.map(g => (
                    <div key={g.label} style={{ display: 'grid', gridTemplateColumns: '72px minmax(0,1fr) auto', gap: 10, alignItems: 'baseline', padding: '5px 0', borderTop: '1px solid rgba(236,232,225,.06)', fontSize: 13 }}>
                      <span style={{ color: g.color }}>{g.label}</span>
                      <span style={{ color: dim }}>{g.note}</span>
                      <span style={{ fontFamily: mono, color: g.color }}>{g.value}</span>
                    </div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0 0', borderTop: '1px solid rgba(236,232,225,.14)', fontSize: 14 }}>
                    <span style={{ color: muted }}>天命所歸 ×{fmt(Math.pow(1.1, L(s, 'd5')))} · 此時轉世可得</span>
                    <span style={{ fontFamily: mono, fontSize: 18, color: ember, fontWeight: 500 }}>{gain} 道果</span>
                  </div>
                </div>
              </div>
              <button onClick={onPrestige} style={{ minHeight: 44, padding: '0 18px', borderRadius: 8, ...btnColors(canRe, ember), fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                {!canRe ? '尚未達成' : confirm ? '再點一次確認' : `轉世，獲得 ${gain}`}
              </button>
            </div>
          </section>
        )}
      </main>

      {mobile && <>
        <div style={{ height: 64 }} />
        <nav style={{ position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 15, background: '#1a1916', borderTop: '1px solid rgba(236,232,225,.12)', display: 'flex', paddingBottom: 'env(safe-area-inset-bottom)' }}>
          {tabs.map(([id, label, badge]) => (
            <button key={id} onClick={() => selectTab(id)} style={{ flex: 1, minHeight: 56, background: 'none', border: 'none', borderTop: `2px solid ${T === id ? amber : 'transparent'}`, color: T === id ? text : muted, fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, position: 'relative' }}>
              {label}
              {badge > 0 && <span style={{ position: 'absolute', top: 6, right: 'calc(50% - 26px)', fontFamily: mono, fontSize: 10, background: amber, color: '#11100e', borderRadius: 8, padding: '0 5px' }}>{badge}</span>}
            </button>
          ))}
        </nav>
      </>}

      <footer style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: dim, fontSize: 13, borderTop: '1px solid rgba(236,232,225,.1)', paddingTop: 16 }}>
        <span>進度自動儲存。離線期間以 {Math.round(offlineRate(s) * 100)}% 速率累積，最多 {offlineCapHours(s)} 小時。</span>
        <button className="wipe-btn" onClick={onWipe} style={{ background: 'none', border: 'none', color: dim, fontSize: 13, cursor: 'pointer', textDecoration: 'underline' }}>
          {confirmWipe ? '再點一次清除所有進度' : '清除存檔'}
        </button>
      </footer>

      <div style={{ position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 20, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center', pointerEvents: 'none' }}>
        {(s.toasts || []).map(t => (
          <div key={t.id} style={{ background: '#1a1916', border: '1px solid oklch(0.82 0.13 78 / .6)', borderRadius: 12, padding: '14px 20px', display: 'flex', gap: 14, alignItems: 'center', boxShadow: '0 0 32px oklch(0.82 0.13 78 / .25),0 8px 24px rgba(0,0,0,.4)', animation: 'achIn 500ms cubic-bezier(.2,1.4,.4,1)' }}>
            <span style={{ width: 12, height: 12, borderRadius: '50%', background: amber, boxShadow: '0 0 12px oklch(0.85 0.13 78)', flex: 'none' }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span style={{ fontSize: 12, color: amber, letterSpacing: '.08em' }}>{t.title}</span>
              <span style={{ fontSize: 17, fontWeight: 700 }}>{t.name}</span>
              <span style={{ fontSize: 13, color: muted }}>{t.desc}</span>
            </div>
          </div>
        ))}
      </div>

      {offline && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(10,9,8,.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 10 }}>
          <div style={{ background: '#1a1916', border: '1px solid rgba(236,232,225,.12)', borderRadius: 14, padding: 28, maxWidth: 360, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <span style={{ fontSize: 13, color: muted }}>你離開了 {fmtTime(offline.secs)}</span>
            <span style={{ fontFamily: mono, fontSize: 36, fontWeight: 500 }}>+{fq(offline.earned, r)} {QN[r]}</span>
            <span style={{ fontSize: 14, color: muted }}>已入體。閉關期間修為未曾停歇。</span>
            <button onClick={() => setOffline(null)} style={{ minHeight: 44, border: 'none', borderRadius: 8, background: amber, color: '#11100e', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>收下</button>
          </div>
        </div>
      )}
    </div>
  );
}
