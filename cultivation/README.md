# 修真 Cultivation（網頁版）

以 Vite + React + TypeScript 實作的修仙放置遊戲，依 Claude Design 設計稿 `Cultivation.dc.html` 移植，不再依賴 `support.js`。遊戲規則與數值說明見 [`GAME.md`](GAME.md)。

## 執行

```
npm install
npm run dev       # 開發伺服器
npm run build     # 輸出至 dist/，可直接放上 GitHub Pages 或包進 Capacitor
npm run preview   # 預覽 build 結果
```

`vite.config.ts` 使用相對路徑 `base: './'`，`dist/` 放在任何子目錄都能執行。

## 測試用參數

- `?speed=10`、`?speed=100`：遊戲速度倍率（原型的 gameSpeed 調整選項）
- `?floating=0`：關閉點擊飄字

## 結構

| 路徑 | 說明 |
|---|---|
| `src/game/data.ts` | 境界、功法、關卡、丹陣、道境、經脈座標等靜態資料 |
| `src/game/logic.ts` | 純函式遊戲規則：產出計算、花費、成就、轉世與各項動作 |
| `src/game/format.ts` | 數字量詞（萬…無量大數）與單位換算 |
| `src/game/save.ts` | localStorage 存讀檔，沿用 `cultivation-save-v1` 格式，並遷移舊版 `lumen-save-v1` |
| `src/components/Figure.tsx` | 人形、經脈 SVG、關卡弧線與體外元氣粒子 |
| `src/components/CultivatePanel.tsx` | 修煉區：元氣、點擊、經脈／關卡、境界突破、紀錄 |
| `src/components/TabPanels.tsx` | 功法、秘訣、丹陣、道境、成就分頁 |
| `src/App.tsx` | 版面、計時、存檔、開始畫面、手機版分頁列、提示與離線收益視窗 |
| `public/assets/` | 人形剪影與開始畫面背景 |

存檔格式與原型相同，原型的進度可直接在網頁版繼續（同一網域下）。
