import { LAST, QN } from './data';

/** Value of one unit of realm r, in base 元氣. */
export const Q = (r: number) => Math.pow(1e8, r || 0);

const UNITS = ['萬', '億', '兆', '京', '垓', '秭', '穰', '溝', '澗', '正', '載', '極', '恆河沙', '阿僧祇', '那由他', '不可思議', '無量大數'];

/** Chinese large-number format: 萬, 億, 兆 … 無量大數, each step ×1萬. */
export function fmt(n: number): string {
  if (n < 10000) return n < 10 && n % 1 ? n.toFixed(1) : Math.floor(n).toLocaleString('zh-TW');
  let i = -1;
  while (n >= 10000 && i < UNITS.length - 1) { n /= 10000; i++; }
  return (n < 10 ? n.toFixed(2) : n < 100 ? n.toFixed(1) : Math.floor(n)) + UNITS[i];
}

/** Format a base-元氣 amount in the given realm's unit (number only). */
export const fq = (n: number, realm: number) => fmt(n / Q(realm));

/** Format a base-元氣 amount in whichever unit fits best, with the unit name. */
export function fAny(n: number): string {
  let k = 0;
  while (k < LAST && n >= Q(k + 1)) k++;
  return fmt(n / Q(k)) + ' ' + QN[k];
}

export function fmtTime(sec: number): string {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return h ? `${h} 小時 ${m} 分` : m ? `${m} 分鐘` : `${Math.floor(sec)} 秒`;
}
