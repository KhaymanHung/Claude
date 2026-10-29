"""學技能：#learn <技能>。

1. 從 data/statues.toml 找哪座雕像教這個技能。
2. 在實地地圖（#map 記錄的房間內容）找那座雕像在哪間房間，沿地圖走過去。
3. look statue 確認真的有教，learn statue <技能>。
   遊戲說「你得先學 X 喔」就先去學 X（最多三層），再回來學。
4. 一直 prac 到「十分熟練」。Lv1 練習免費；之後要花美拉，除非下 #learn <技能> pay，否則只練免費的。
5. 最後打 practice，報告剩下的記憶點數。
"""

import re
import tomllib
from pathlib import Path

LEARNED = re.compile(r"教會你\s*(.+?)\s*這個技能")
NEED_FIRST = re.compile(r"你得先學\s*(\S+?)\s*喔")
NO_MEMORY = re.compile(r"記憶容量不夠")
NOT_YOURS = re.compile(r"這不是你所能學的技能")
NO_TEACHER = re.compile(r"你要向誰學習")
MASTERED = re.compile(r"十分熟練")
PRACTICED = re.compile(r"你練習\s*.+?\s*這個技能|熟練度到達\s*(\d+)")
FREE = re.compile(r"免費的優待")
COST = re.compile(r"你只要花費\s*(\d+)\s*美拉")
MEMORY_LEFT = re.compile(r"你還剩下\s*(\d+)\s*點的記憶容量")
KNOWN = re.compile(r"\[\s*([a-z][a-z _'-]*?)\s*\]熟練度:\s*(\d+)")


class Learner:
    def __init__(self, bot, guide, explorer, data_dir: Path):
        self.bot, self.guide, self.explorer = bot, guide, explorer
        f = Path(data_dir) / "statues.toml"
        self.statues = tomllib.loads(f.read_text(encoding="utf-8")).get("statue", []) if f.exists() else []
        self.memory_left: int | None = None

    def start(self, name: str, pay: bool = False, done=None) -> None:
        async def run():
            ok = await self.learn(name, pay)
            if done:
                done(ok)
        self.explorer._start(run(), "學技能")

    # ---------- 查資料 ----------
    def resolve(self, name: str) -> tuple[str, str]:
        """技能的（英文, 中文）。找不到資料就照原樣。"""
        s = self.guide.find_skill(name)
        if s:
            return s["en"], s.get("zh", "")
        for st in self.statues:                   # 雕像清單裡也有中英對照
            for en, zh in zip(st["skills"], st.get("zh", [])):
                if name in (en, zh):
                    return en, zh
        return name, ""

    def teachers(self, en: str) -> list[str]:
        return [st["name"] for st in self.statues if en in st["skills"]]

    def statue_rooms(self, statue: str) -> list[str]:
        """地圖上看得到這座雕像的房間，近的排前面。"""
        rooms = self.explorer.rooms
        hits = [rid for rid, r in rooms.items() if any(statue in line for line in r.get("contents", []))]
        return sorted(hits, key=lambda rid: len(rooms[rid].get("path") or [0] * 999))

    async def known(self) -> dict[str, int]:
        text = await self.bot.capture("practice")
        m = MEMORY_LEFT.search(text)
        if m:
            self.memory_left = int(m.group(1))
        return {k.strip(): int(v) for k, v in KNOWN.findall(text)}

    # ---------- 主流程 ----------
    async def learn(self, name: str, pay: bool = False, depth: int = 0) -> bool:
        b, ex = self.bot, self.explorer
        en, zh = self.resolve(name)
        label = f"{zh}（{en}）" if zh else en
        if depth > 3:
            b.log(f"[學技能] {label} 的前置技能太多層，請手動處理")
            return False
        await b.ensure_prompt()
        have = await self.known()
        if en not in have:
            teachers = self.teachers(en)
            if not teachers:
                b.log(f"[學技能] 資料裡沒有雕像教 {label}。如果要解謎才能學，用 #quest 查；或把 look statue 的畫面給 Claude")
                return False
            if not ex.rooms:
                ex._load_map()
            if ex.current is None:
                await ex.locate()
            ok = False
            for statue in teachers:
                rooms = self.statue_rooms(statue)
                if not rooms:
                    continue
                for rid in rooms:
                    ex.state = f"學技能：走到 {statue}（{ex.rooms[rid]['name']}）"
                    if rid != ex.current and not await ex._goto(rid):
                        continue
                    board = await b.capture("look statue")
                    if en not in board:
                        continue                      # 同名的雕像（例如三座牧師巨像）教的不一樣
                    r = await self._learn_here(en, label, pay, depth)
                    if r is None:                     # 要先學別的，學完回來再試一次
                        if not await ex._goto(rid):
                            return False
                        r = await self._learn_here(en, label, pay, depth, retry=True)
                    if not r:
                        return False
                    ok = True
                    break
                if ok:
                    break
            if not ok:
                names = "、".join(teachers)
                b.log(f"[學技能] 地圖上找不到教 {label} 的雕像（{names}）。先到勇者學校跑 #map 勇者學校 80 10，記下雕像位置再試")
                return False
        else:
            b.log(f"[學技能] 已經會 {label}（熟練度 {have[en]}），直接練習")
        await self._practice(en, label, pay)
        await self.known()
        if self.memory_left is not None:
            b.log(f"[學技能] {label} 完成，記憶點數剩 {self.memory_left}")
        return True

    async def _learn_here(self, en, label, pay, depth, retry=False):
        """在雕像前 learn。回傳 True 學會；False 學不了；None 要先學前置技能（已經去學了）。"""
        b = self.bot
        text = await b.capture(f"learn statue {en}")
        if LEARNED.search(text):
            b.log(f"[學技能] 學會 {label}")
            return True
        m = NEED_FIRST.search(text)
        if m and not retry:
            pre = m.group(1)
            b.log(f"[學技能] {label} 要先學 {pre}，先去學")
            if not await self.learn(pre, pay, depth + 1):
                return False
            return None
        if NO_MEMORY.search(text):
            b.log(f"[學技能] 記憶點數不夠學 {label}（打 practice 看剩多少）")
        elif NOT_YOURS.search(text):
            b.log(f"[學技能] 遊戲說「這不是你所能學的技能」：{label} 可能要解謎、等級或屬性才能學")
        else:
            first = next((l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith(("<", ">"))), "")
            b.log(f"[學技能] 學不了 {label}：{first[:60]}")
        return False

    async def _practice(self, en, label, pay):
        b = self.bot
        for i in range(15):
            self.explorer.state = f"學技能：練習 {label} 第 {i + 1} 次"
            text = await b.capture(f"prac {en}")
            m = COST.search(text)
            spent = int(m.group(1)) if m else 0
            if MASTERED.search(text):
                b.log(f"[學技能] {label} 已練到十分熟練")
                return
            if not PRACTICED.search(text):
                first = next((l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith(("<", ">"))), "")
                b.log(f"[學技能] 不能再練 {label}：{first[:60]}")
                return
            if not FREE.search(text) and not pay:
                b.log(f"[學技能] 練習 {label} 要花錢了（這次 {spent} 美拉），先停下來；要繼續花錢練就用 #learn {en} pay")
                return
