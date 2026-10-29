# 攻略資料格式

程式和 `docs/四度空間攻略.md` 都從這個資料夾讀資料。改完之後：
- 程式裡輸入 `#reload` 就會套用
- 執行 `python tools/build_guide.py --docx` 重新產生攻略文件

| 檔案 | 內容 |
|---|---|
| `areas.toml` | 區域（等級、作者、路線、說明）、路線捷徑 `[places]`、rnote 房間、練功設定 `[[hunt]]` |
| `quests/*.toml` | 解謎，一個 `[[quest]]` 一個謎題，可以放在任何一個檔案 |
| `skills.toml` | 技能與法術：記憶量、協調性、週期、增加的上限、前置、用法、學習對象 |
| `items.toml` | 裝備：關鍵字、部位、等級、屬性、參考價、取得方式、出現在哪些配裝 |
| `user_routes.toml` | 你用 `#record` 記錄的自訂路線（自動產生，也可以手動編輯） |

## 路線寫法

路線是一串字串，每一項可以是：

| 寫法 | 展開結果 |
|---|---|
| `"/3w2s"` | recall、w、w、w、s、s |
| `"map2"`、`"map3"` | `[places]` 裡定義的捷徑 |
| `"e;n;n;w"` | 用分號分開的多個指令 |
| `"3w 2s 5e"` | 空白分開、全部都是方向時會逐一展開 |
| `"talk wizard help"` | 一般指令，原樣送出 |
| 自訂路線名稱 | `user_routes.toml` 裡的路線 |

## 解謎格式

```toml
[[quest]]
id = "five-elements"          # 英文代號
name = "五行世界"             # #quest 用的名稱
aliases = ["五行", "元素之戒"] # 其他叫法，#quest 和 #find 都找得到
area = "五行世界"             # 對應 areas.toml 的區域名稱
route = ["/3nw2nen3w2d3n2en2u2n2w"]   # 會自動變成第一步「前往」
route_note = "文字說明的路線"         # 沒有固定走法時用
needs = ["必備物品或技能"]
rewards = ["獎勵"]
note = "注意事項"

[[quest.steps]]
title = "拿木劍"
note = "這一步的說明"
do = ["2n", "enter", "w", "say 有沒有人在啊?"]   # #next 會依序送出

[[quest.steps]]
title = "打小金"
manual = true                 # 要自己處理的步驟，程式只顯示 note
note = "dispel magic + dark，打到紅血時 wear 木劍"

[[quest.tables]]              # 附表（可選）
title = "表格標題"
headers = ["欄 1", "欄 2"]
rows = [["a", "b"]]

[[quest.tips]]                # 提示（可選）
title = "打法"
items = ["第一點", "第二點"]
```

## 練功設定格式

```toml
[[hunt]]
name = "泰洛市"                # #farm 用的名稱
area = "泰洛市"
level = "12-24"
targets = ["beast", "mimic", "lizard"]   # kill 後面接的關鍵字，前面的先打
approach = ["map3", "s6e3s3w"]           # 從回城點走到練功區，沿路不打怪
patrol = []                              # 巡邏路線；空的表示原地清怪等重生
```

`user_routes.toml` 裡如果有和練功設定同名的路線，`#farm` 會優先拿它當巡邏路線。
