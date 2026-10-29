# 進度紀錄

最後更新：2026-10-29 13:40（第二輪）

## 已完成

- 練功程式：巡邏／原地狩獵、逃跑、休息、回城、自動登入（`main.py`、`mudbot/`）
- 攻略資料化：58 個解謎、96 個區域、186 個技能法術、290 件裝備、7 組練功設定（`data/`）
- 攻略指令：`#find` `#area` `#skill` `#item` `#goto` `#quest`／`#next` `#farm` `#record`
- 整理版攻略文件：`docs/四度空間攻略.md`、`.docx`（`python tools/build_guide.py --docx` 重新產生）
- **新增（未在真實伺服器測試）**：實地探索工具 `mudbot/explorer.py`
  - `#survey`：把 score、commands、skills all、spells all、area、help 等輸出存到 `data/live/survey/`
  - `#survey help`：對每個技能和 help 主題查 help，存到 `data/live/help/`
  - `#map [房間數]`：從回城點走遍附近房間，存到 `data/live/map.json`、`map.md`；遇到戰鬥會逃跑回城

- 12:10 修正：遊戲的分頁提示「[(c)繼續顯示 … 或按 ENTER 繼續]:」現在會自動按 Enter，並等全部顯示完才送下一個指令（`mudbot/bot.py`）
- 12:20 修正：`#map` 遇到「你精疲力竭了」會先睡到移動力補滿再重走；移動力低於 40% 就先休息；之前因為太累被記成走不通的出口，下次 `#map` 會重新探索
- 12:30 修正：`#survey` 不再送不帶參數的 `prompt`（那是開關，會把狀態列關掉）；`config.toml` 新增 `prompt_command`，探索和狩獵開始前會先送一次
- 12:35 修正：自動登入改用實際的中文提示（請輸入你在本遊戲中所使用的名字／請輸入密碼）
- 12:45 修正：上次寫回時 bot.py、explorer.py、hunter.py 沒有真的更新，已重新寫入並核對大小；`#map` 修正房間路線記錄（之前除了回城點都是空的），載入舊地圖時會自動重算
- 待查：有些房間名稱顯示成亂碼（例如「������(A)」），可能需要把 `config.toml` 的 encoding 改成 `big5hkscs`
- 新增原始封包紀錄 `logs/*.raw.log`（`config.toml` 的 `raw_log`），每包資料有時間、方向（<< 收到、>> 送出）、位元組數，保留顏色碼和無法解碼的位元組，密碼遮住；telnet 指令被切在兩包之間時不再遺失
- 給 Claude 的備忘：寫回電腦時要用新的暫存路徑（例如 /mnt/user-data/outputs/v時間/），同一路徑會被快取成舊內容；寫完要核對檔案大小
- 新增自然恢復統計（`mudbot/regen.py`）：狀態列數值上升且非戰鬥時記一次恢復，算間隔與恢復量，分睡覺／休息／站著與是否飢渴；`#regen` 查看，存到 `data/live/regen.csv`；休息時每 2 秒看一次狀態列；狀態列的內力也會讀取
- 新增補給（`config.toml` 的 `[supplies]`）：飢餓／口渴自動吃喝，沒東西了回城購買（10 分鐘內重複會自動停用）。新角色沒錢，預設用 create food／create spring
- 待確認：飢餓、口渴、沒有物品的實際中文訊息；變出來的食物和泉水的關鍵字（目前猜 mushroom、spring）；/ws 商店賣什麼
- 實際角色資料：Runchar Lv1，屬性全 18，記憶容量 800，0 美拉，生命 158、法力 61、移動力 93、內力 47；help 目錄有 begin、cmds、setup、map、area、quests 等
- 新增 `#quest 新手開局`（`data/quests/00_新手開局.toml`）：Lv1 免費學補給、回復、拳法 → 新手之旅升到 Lv9 → 格鬥天堂；`#survey` 改抓 help begin／setup／cmds 等新手說明
- 更正：學技能會扣記憶點數（攻略說 Lv1 免費是錯的）；`#quest 新手開局` 改成 800 點內的分配（678 點、保留 122），攻略文件已同步修正
- 使用者決定：屬性維持 18 18 18 18 18，等 Lv60、技能組合確定後再 changebody（全 18 時換不會降熟練度）；`#quest 新手開局` 已拿掉 changebody 步驟
- 減少 recall（recall 會讓目前移動力減半）：已在回城點就跳過；探索、狩獵回城時先 look 定位，地圖上找得到路就走回去，找不到才 recall；買完補給不再 recall；探索遇到單向路會照實際更正地圖。回城點名稱設定在 `config.toml` 的 `[status] home_room`（預設「市中心」）
- 13:10 依紀錄 20261029_123610.log 查帳：實際剩 130 點（計畫 122）。強力治療（cure serious）實際 5 點（攻略寫 8），魔法彈（magic missile）沒學（找不到教的雕像）。已學 17 項共 670 點。`data/skills.toml` 的記憶量已用遊戲列表更正 12 項；`#quest 新手開局` 改成新計畫：先學呼風喚雨術（control weather）＋舞空術（fly）、療毒術（cure poison）、復明術（cure blindness）、偵測邪惡術（detect evil）共 95 點，保留 35 點；並記錄各雕像教什麼。
- 使用者要求：列出技能、物品、NPC 名稱時一律寫成「中文（英文）」。
- 13:20 依紀錄 20261029_125406.log：使用者已學魔法彈（magic missile，火系巫師巨像）、呼風喚雨術、舞空術、療毒術、復明術、偵測邪惡術，剩 40 點；Lv1 prac 免費可練到「十分熟練」（71～81）。上限變成生命 339、法力 414、移動力 373、內力 150
- 修正亂碼：色碼夾在中文字兩個位元組中間（`mudbot/connection.py` 的 ColorSplitFixer）；舊地圖有亂碼會自動重新探索
- `#map` 新增：房間內容分成怪／NPC 和物品，新怪打 consider、有怪的房間打 list，輸出 `data/live/npcs.md`、`npcs.json`、`items.json`；`#survey help` 也查 commands 裡的所有指令
- 狩獵：打死怪後的 after_kill 輸出記到 `data/live/drops.csv`
- `config.toml`：補上飢餓、口渴、走不通的中文訊息；補給改成 create food → get food → eat food、create spring → drink spring ×5；停用英文的吃喝觸發
- 計畫寫在 `docs/計畫.md`；全部 23 座雕像教的技能在攻略〈入門與升級〉
- 13:40 新增 `#map <地點或路線> [房間數] [深度]`（先走到起點、路線也記進地圖，只探索起點那一側）；`#learn <技能> [pay]`（`mudbot/learner.py`，用地圖找雕像、處理「你得先學」、練到十分熟練）；`data/statues.toml`（22 座雕像教的技能）；解謎步驟支援 `learn = "技能"`、`pause = true`，`#next all` 自動連續執行；`#quest 學大地之斬`（`data/quests/05_學大地之斬.toml`）；練功設定可指定 kill_command、on_start（已填 f saulin／f lohan、agg 100）
- `docs/計畫.md` 改成逐步表格：每一步寫從哪裡開始、輸入什麼、跑完怎麼確認，含升級路線
- 待測（真實伺服器）：`#map 勇者學校 80 10`、`#learn`、`look painting` 是否會移動、learn statue earthslice 的回應
- 待測：記憶容量每級增加多少；戰鬥、怪死、逃跑、死亡的中文訊息（新手之旅時收集）

## 限制

- Claude 的雲端環境連不到 `void7777.ddns.net`，必須在你的電腦上執行程式。

## 下一步（下次連線時）

1. 在電腦上執行 `python main.py`，自己建立新角色並登入（密碼自己設，不要給 Claude）。
2. 在遊戲裡設定狀態列：`prompt <生命%h/%H 法力%m/%M 移動力%v/%V 內力%p/%P>`
3. 依序輸入：`#survey` → 等它說完成 → `#map 100`（新角色很弱，先別設太大）→ 有空再跑 `#survey help`
4. 告訴 Claude 跑完了。Claude 會讀 `data/live/` 和 `logs/`，然後：
   - 把中文遊戲訊息補進 `config.toml` 的 `[messages]`（殺不到、怪死、逃跑、走不過去、死亡…）
   - 用實際的 skills／spells 清單和 help 修正 `data/skills.toml`
   - 用實際地圖修正區域路線，補上練功區的巡邏路線
   - 重新產生攻略文件
5. 如果 `#map` 一開始就說「看不懂房間的出口格式」，把 `look` 的畫面貼給 Claude。
