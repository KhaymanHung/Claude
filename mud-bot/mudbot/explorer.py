"""實地探索：在真正的伺服器上收集指令、技能、說明文件和地圖，存到 data/live/。

#survey        跑一輪資訊指令（score、commands、skills all、spells all、area…），每個指令的輸出各存一個檔
#survey help   對已知的技能法術和 help 目錄裡的主題逐一查 help，存到 data/live/help/
#map [房間數]  從回城點開始走遍附近的房間，記錄房間名稱、出口、敘述、看到的怪和物品
#map stop      停止探索（已走過的部分會存檔）
"""

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

DIR_WORDS = {
    "北": "n", "南": "s", "東": "e", "西": "w", "上": "u", "下": "d",
    "north": "n", "south": "s", "east": "e", "west": "w", "up": "u", "down": "d",
}
REVERSE = {"n": "s", "s": "n", "e": "w", "w": "e", "u": "d", "d": "u"}
TIRED = re.compile(r"精疲力竭|too exhausted|移動力不足|走不動")
EXIT_RE = re.compile(r"\[\s*(?:出口|exits?)\s*[:：]?\s*([^\]]*)\]", re.I)
DIR_TOKEN = re.compile(r"north|south|east|west|up|down|[北南東西上下]", re.I)

SURVEY_CMDS = [
    "score", "affects", "equipment", "inventory", "worth", "level", "practice", "train",
    "skills", "skills all", "spells", "spells all", "commands", "socials",
    "help", "help begin", "help cmds", "help setup", "help notice", "help rule", "help map", "help area", "help quests",
    "help mud_intro", "help void_intro", "help changebody", "help train", "help practice", "help learn", "help cancel",
    "area", "areas", "who", "where", "time", "weather", "config", "channels", "alias",
    "quests", "news", "info", "wizlist", "look", "exits", "scan",
]


def safe_name(s: str) -> str:
    return re.sub(r"[^\w一-鿿-]+", "_", s).strip("_")[:60] or "_"


def parse_room(text: str) -> dict | None:
    """從移動或 look 的輸出解析房間；找不到出口行就回傳 None。"""
    lines = [l.rstrip() for l in text.split("\n")]
    lines = [l for l in lines if l.strip()]
    idx = next((i for i, l in enumerate(lines) if EXIT_RE.search(l)), None)
    if idx is None:
        return None
    raw = EXIT_RE.search(lines[idx]).group(1)
    exits = []
    for tok in re.split(r"[\s,、，]+", raw.strip()):
        t = tok.strip("()（）[]<>*").lower()
        d = t if t in REVERSE else DIR_WORDS.get(t)
        if not d:                                   # 例如「北(關)」
            m = DIR_TOKEN.search(tok)
            d = DIR_WORDS.get(m.group(0).lower()) if m else None
        if d and d not in exits:
            exits.append(d)
    head = lines[:idx]
    # 房間名稱：出口行之前、看起來像名稱的第一行（短、不是句子）
    name = next((l.strip() for l in head if len(l.strip()) <= 30), head[0].strip() if head else "（無名）")
    start = head.index(next(l for l in head if l.strip() == name)) if name in [l.strip() for l in head] else 0
    desc = " ".join(l.strip() for l in head[start + 1:])
    contents = [l.strip() for l in lines[idx + 1:]]
    return {"name": name, "exits": exits, "exits_raw": raw.strip(), "desc": desc, "contents": contents}


TAG_RE = re.compile(r"^(?:\(\s*[^()]{0,12}\)\s*)+")
LEVEL_RE = re.compile(r"\[等級:\s*(\d+)\s*\]")
MOB_HINT = re.compile(r"(這兒|這裡|你|著|站|坐|躺|睡|走|看)")


def classify(line: str) -> dict | None:
    """把房間裡看到的一行分類成怪／NPC（mob）、物品（item）或其他（玩家、訊息）。
    這個遊戲的怪和物品都寫成「描述/關鍵字」；結尾是句子（有「這兒」「你」等字）的通常是怪。"""
    text = TAG_RE.sub("", line.strip())
    lv = LEVEL_RE.search(text)
    text = LEVEL_RE.sub("", text).strip()
    if "/" in text:
        desc, kw = text.rsplit("/", 1)
        desc, kw = desc.strip(), kw.strip()
        if not kw or len(kw) > 40:
            return None
        kind = "mob" if desc.endswith((".", "。", "!", "！")) and MOB_HINT.search(desc) and not lv else "item"
        return {"kind": kind, "name": desc, "kw": kw, "level": int(lv.group(1)) if lv else None}
    m = re.match(r"^(.+?)\(([A-Za-z][\w \-']*)\)\s*(.*)$", text)
    if m:
        return {"kind": "mob", "name": m.group(1).strip(), "kw": m.group(2).strip(), "level": None}
    return None


def room_id(r: dict) -> str:
    key = r["name"] + "|" + "".join(sorted(r["exits"])) + "|" + r["desc"][:40]
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:10]


class Explorer:
    def __init__(self, bot, out_dir: Path, recall_command: str = "recall"):
        self.bot = bot
        self.out = Path(out_dir)
        self.recall_command = recall_command
        self.task: asyncio.Task | None = None
        self.rooms: dict[str, dict] = {}
        self.home: str | None = None
        self.current: str | None = None
        self.state = "閒置"
        self.expand = lambda r: list(r)        # main.py 會換成攻略的路線展開
        self.probe = True                      # 探索時對新看到的怪打 consider、有怪的房間打 list（看是不是商店）
        self.npcs: dict[str, dict] = {}        # 關鍵字 → 名稱、出現房間、consider 結果
        self.items: dict[str, dict] = {}       # 關鍵字 → 名稱、出現房間、等級

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def stop(self) -> None:
        if self.running:
            self.task.cancel()

    def _start(self, coro, label):
        if self.running:
            self.bot.log("[探索] 上一個探索還在進行，請先 #map stop")
            return

        async def run():
            self.bot.busy = True
            try:
                await coro
            except asyncio.CancelledError:
                self.bot.log(f"[探索] {label} 已停止")
                raise
            except Exception as e:
                self.bot.log(f"[探索] {label} 發生錯誤：{e!r}")
            finally:
                self.bot.busy = False
                if self.rooms:
                    self.save_map()
                self.state = "閒置"

        self.task = asyncio.create_task(run())

    # ---------- 資訊指令 ----------
    def survey(self, with_help: bool = False, skills: list[str] = ()) -> None:
        self._start(self._survey(with_help, list(skills)), "資訊收集")

    async def _survey(self, with_help, skills):
        d = self.out / "survey"
        d.mkdir(parents=True, exist_ok=True)
        await self.bot.ensure_prompt()
        cmds = list(SURVEY_CMDS)
        index = []
        for i, c in enumerate(cmds, 1):
            self.state = f"資訊收集 {i}/{len(cmds)}：{c}"
            text = await self.bot.capture(c)
            (d / f"{safe_name(c)}.txt").write_text(f"> {c}\n{text}\n", encoding="utf-8")
            index.append((c, len(text.splitlines())))
        await self.bot.ensure_prompt()
        (d / "_index.txt").write_text("\n".join(f"{c}\t{n} 行" for c, n in index), encoding="utf-8")
        self.bot.log(f"[探索] 資訊收集完成，{len(cmds)} 個指令，存在 {d}")
        if with_help:
            await self._help(skills)

    async def _help(self, skills):
        d = self.out / "help"
        d.mkdir(parents=True, exist_ok=True)
        topics = list(dict.fromkeys(skills))
        idx = self.out / "survey" / "help.txt"
        if idx.exists():                               # help 目錄裡列出的主題
            for w in re.findall(r"\b[a-zA-Z][a-zA-Z_'-]{2,}\b", idx.read_text(encoding="utf-8")):
                if w.lower() not in ("help", "the", "and", "for", "you", "type"):
                    topics.append(w.lower())
        cmds = self.out / "survey" / "commands.txt"
        if cmds.exists():                              # commands 列出的每個指令（autoloot、deposit、eqstock…）
            body = cmds.read_text(encoding="utf-8").split("\n", 1)[-1]
            topics += [w.lower() for w in re.findall(r"\b[a-zA-Z][a-zA-Z_]{1,}\b", body)]
        topics = list(dict.fromkeys(topics))[:800]
        for i, t in enumerate(topics, 1):
            self.state = f"查 help {i}/{len(topics)}：{t}"
            f = d / f"{safe_name(t)}.txt"
            if f.exists():
                continue
            text = await self.bot.capture(f"help {t}")
            f.write_text(f"> help {t}\n{text}\n", encoding="utf-8")
        self.bot.log(f"[探索] help 收集完成，{len(topics)} 個主題，存在 {d}")

    # ---------- 地圖 ----------
    def map(self, max_rooms: int = 200, max_depth: int = 40, route: list[str] | None = None, label: str = "") -> None:
        """route 有給的話：先照路線走到那裡（路線也記進地圖），只探索那裡往外 max_depth 步以內的房間。"""
        self._load_map()
        self._start(self._map(max_rooms, max_depth, route, label), "地圖探索")

    async def _walk_route(self, cmds: list[str]) -> bool:
        """照路線走，每到一間房間就記進地圖。開門、對話等不會移動的指令，併進下一步的出口（例如 open e;e）。"""
        from .guide import is_direction
        b = self.bot
        pending: list[str] = []
        for i, c in enumerate(cmds, 1):
            self.state = f"地圖探索：前往起點 {i}/{len(cmds)}：{c}"
            if c == "recall":
                await self.go_home()
                pending = []
                continue
            r, text = await self._move(c)
            if not await self._safe(text, self.last_move):
                b.log(f"[探索] 前往起點時遇到戰鬥（第 {i} 步「{c}」），停止")
                return False
            rid = room_id(r) if r else None
            if r and (rid != self.current or is_direction(c)):
                key = ";".join(pending + [c])
                before = self.current
                prev = self.rooms.get(before, {}).get("path") if before else None
                new = self._add(r, prev + [key] if prev is not None else None)
                if before in self.rooms:
                    self.rooms[before]["exits"][key] = new
                if self.probe and "probed" not in self.rooms[new]:
                    self.rooms[new]["probed"] = True
                    await self._probe(new)
                self.current, pending = new, []
            elif is_direction(c):
                first = next((l for l in text.split("\n") if l.strip()), "")
                b.log(f"[探索] 前往起點時第 {i} 步「{c}」走不過去：{first[:40]}，停止")
                return False
            else:
                pending.append(c)                     # 不會移動的動作（talk、get、unlock…）
        return True

    def _load_map(self):
        f = self.out / "map.json"
        if f.exists() and not self.rooms:
            data = json.loads(f.read_text(encoding="utf-8"))
            self.rooms, self.home = data.get("rooms", {}), data.get("home")
            self._repath()
            if any("\ufffd" in r["name"] for r in self.rooms.values()):
                self.bot.log("[探索] 舊地圖有亂碼的房間名稱（已修正解碼方式），這次重新探索")
                self.rooms, self.home = {}, None
            for name in ("npcs", "items"):
                g = self.out / f"{name}.json"
                if g.exists():
                    setattr(self, name, json.loads(g.read_text(encoding="utf-8")))
            for room in self.rooms.values():
                for d, v in room["exits"].items():
                    if isinstance(v, str) and (v == "?" or (v.startswith("blocked:") and TIRED.search(v))):
                        room["exits"][d] = None

    async def _look(self, cmd: str = "look") -> tuple[dict | None, str]:
        self.last_move = time.monotonic()
        text = await self.bot.capture(cmd)
        return parse_room(text), text

    def _tired(self, text: str) -> bool:
        m = self.bot.msg.get("exhausted")
        return bool(TIRED.search(text) or (m and m.search(text)))

    async def _move(self, d: str) -> tuple[dict | None, str]:
        """移動一步；精疲力竭時先睡到移動力補滿，再重走一次。
        d 可以是「open e;e」這種組合（路線裡的開門、對話等動作，最後一個才是移動）。"""
        *pre, d = d.split(";")
        for c in pre:
            await self.bot.capture(c)
        for _ in range(3):
            await self._rest_if_needed()
            r, text = await self._look(d)
            if r or not self._tired(text):
                return r, text
            await self._rest(force=True)
        return r, text

    def _add(self, r: dict, path: list[str] | None) -> str:
        rid = room_id(r)
        if path is None:                          # 不知道怎麼走到的房間，之後由 _repath 補
            old = self.rooms[rid].get("path") if rid in self.rooms else None
            path = list(old) if old is not None else None
        if rid not in self.rooms:
            self.rooms[rid] = {"name": r["name"], "exits": {d: None for d in r["exits"]}, "exits_raw": r["exits_raw"],
                               "desc": r["desc"], "contents": r["contents"], "path": path,
                               "first_seen": time.strftime("%Y-%m-%d %H:%M")}
        else:
            room = self.rooms[rid]
            for line in r["contents"]:                 # 怪會走動，累積看過的東西
                if line not in room["contents"]:
                    room["contents"].append(line)
            if path is not None and (room.get("path") is None or len(path) < len(room["path"])):
                room["path"] = path
        return rid

    async def _safe(self, text: str, since: float = 0.0) -> bool:
        """遇到戰鬥就逃跑回城；回傳 False 表示不安全。"""
        b = self.bot
        if b.msg.get("died") and b.msg["died"].search(text):
            raise RuntimeError("角色死亡，停止探索")
        fighting = b.last_combat > since and time.monotonic() - b.last_combat < 3
        if not fighting:
            return True
        b.log("[探索] 遇到戰鬥，逃跑並回城")
        for _ in range(8):
            r = await b.send_expect("flee", ["flee_ok", "not_fighting", "died"], 3)
            if r == "died":
                raise RuntimeError("角色死亡，停止探索")
            if r in ("flee_ok", "not_fighting"):
                break
        if not await self.locate():
            await self.go_home()
        return False

    async def locate(self) -> str | None:
        """look 看自己在哪個房間；地圖裡有記錄就回傳房間代號。"""
        r, _ = await self._look()
        if not r:
            return None
        rid = room_id(r)
        if rid in self.rooms:
            self.current = rid
            return rid
        if not self.rooms and r["name"] == self.bot.home_room:
            return "home"
        return None

    async def go_home(self) -> None:
        """回到回城點。地圖上找得到路就走回去，找不到才 recall（recall 會讓目前的移動力減半）。"""
        b = self.bot
        here = await self.locate()
        if here == "home" or (here and here == self.home):
            self.current = self.home
            return
        path = self._route(here, self.home) if here and self.home else None
        if path is not None:
            for d in path:
                r, text = await self._move(d)
                if not r or not await self._safe(text, self.last_move):
                    break
                rid = room_id(r)
                self.current = rid if rid in self.rooms else None
            if self.current == self.home:
                b.log(f"[探索] 沿地圖走回回城點（{len(path)} 步，省下一次 recall）")
                return
        b.log("[探索] 找不到回去的路，recall（移動力會減半）")
        await b.capture(self.recall_command)
        self.current = self.home

    async def _rest_if_needed(self):
        b = self.bot
        if b.need_shopping:
            await b.shop(self.expand)
            if not await self.locate():
                await self.go_home()
        for key, low in (("hp", 0.6), ("mv", 0.4)):
            r = b.stats.ratio(key)
            if r is not None and r < low:
                await self._rest()
                return

    async def _rest(self, force: bool = False):
        """睡覺直到 hp 和移動力回到 95%（最多 15 分鐘）。"""
        b = self.bot
        b.log(f"[探索] 休息補移動力（{b.stats.text()}）")
        self.state = "休息中"
        await b.capture("sleep")
        start = time.monotonic()
        while time.monotonic() - start < 900:
            await asyncio.sleep(2)                 # 每 2 秒看一次狀態列，順便量自然恢復的間隔
            await b.capture("")
            if all((b.stats.ratio(k) or 1) >= 0.95 for k in ("hp", "mv")):
                break
        await b.capture("wake")
        b.log(f"[探索] 休息完畢（{b.stats.text()}）")

    async def _goto(self, target: str) -> bool:
        """沿已知的房間走到 target；走錯就從目前位置重新規劃，真的不行才回城。"""
        for attempt in range(3):
            path = self._route(self.current, target)
            if path is None and await self.locate():
                path = self._route(self.current, target)
            if path is None:
                await self.go_home()
                path = self._route(self.current, target) or self.rooms[target]["path"]
                if path is None:
                    return False
            ok = True
            for d in path:
                r, text = await self._move(d)
                if not await self._safe(text, self.last_move):
                    ok = False
                    break
                if not r:
                    ok = False
                    break
                before = self.current
                expected = self.rooms.get(before, {}).get("exits", {}).get(d)
                prev = self.rooms.get(before, {}).get("path")
                self.current = self._add(r, prev + [d] if prev is not None else None)
                if before in self.rooms and expected != self.current:
                    self.rooms[before]["exits"][d] = self.current   # 連線跟以為的不一樣（單向路），照實際更正
                    ok = False
                    break
            if ok and self.current == target:
                return True
            await self.locate()                     # 走錯了：看看現在在哪，下一輪從這裡重新規劃
        return False

    def _route(self, src, dst):
        """在已知地圖上找最短路線（只用確認過的連線）。"""
        if src == dst:
            return []
        if src is None or src not in self.rooms:
            return None
        prev = {src: None}
        q = [src]
        while q:
            cur = q.pop(0)
            for d, nxt in self.rooms[cur]["exits"].items():
                if nxt and nxt in self.rooms and nxt not in prev and not self.rooms[nxt].get("danger"):
                    prev[nxt] = (cur, d)
                    if nxt == dst:
                        out = []
                        while prev[nxt]:
                            cur2, d2 = prev[nxt]
                            out.append(d2)
                            nxt = cur2
                        return out[::-1]
                    q.append(nxt)
        return None

    def _repath(self) -> None:
        """從回城點沿已知連線重新計算每間房間的最短路線。"""
        if not self.home or self.home not in self.rooms:
            return
        for room in self.rooms.values():
            room["path"] = None
        self.rooms[self.home]["path"] = []
        q = [self.home]
        while q:
            cur = q.pop(0)
            for d, nxt in self.rooms[cur]["exits"].items():
                if nxt in self.rooms and self.rooms[nxt]["path"] is None:
                    self.rooms[nxt]["path"] = self.rooms[cur]["path"] + [d]
                    q.append(nxt)

    def _in_scope(self, rid: str) -> bool:
        """指定起點探索時，只走起點這一側的房間（路線開頭和起點相同）。"""
        if not getattr(self, "_scope", None):
            return True
        prefix, _ = self._scope
        p = self.rooms[rid].get("path")
        return p is not None and p[:len(prefix)] == prefix

    def _frontier(self, max_depth):
        """還沒走過的出口：(房間, 方向)，依距離排序。"""
        out = []
        for rid, room in self.rooms.items():
            if room.get("danger") or room.get("path") is None or len(room["path"]) >= max_depth:
                continue
            for d, nxt in room["exits"].items():
                if nxt is None:
                    out.append((len(room["path"]), rid, d))
        return sorted(out)

    async def _map(self, max_rooms, max_depth, route=None, label=""):
        b = self.bot
        await b.ensure_prompt()
        self._scope = None
        if self.home and await self.locate() not in (None, "home"):
            b.log("[探索] 從目前位置接著探索（不必 recall）")
        else:
            r, text = await self._look()
            if not r:
                raise RuntimeError("看不懂房間的出口格式，請把 look 的畫面貼給 Claude")
            if r["name"] != b.home_room and not self.home:
                await b.capture(self.recall_command)
                r, text = await self._look()
            if not self.home:
                self.home = self._add(r, [])
            self.current = self.home if room_id(r) == self.home else self._add(r, None)
        if route:
            b.log(f"[探索] 先前往起點 {label or ' '.join(route)}")
            if not await self._walk_route(route):
                self.save_map()
                return
            base = self.rooms[self.current]
            if base.get("path") is None:
                b.log("[探索] 不知道起點離回城點的路線，改成只從這裡往外探索")
                base["path"] = []
            self._scope = (list(base["path"]), max_depth)
            b.log(f"[探索] 到達起點「{base['name']}」，開始探索這附近 {max_depth} 步以內的房間")
            max_depth = len(base["path"]) + max_depth
        explored = 0
        skip = set()
        while explored < max_rooms:
            front = [f for f in self._frontier(max_depth) if (f[1], f[2]) not in skip and self._in_scope(f[1])]
            if not front:
                b.log("[探索] 範圍內的出口都走過了")
                break
            # 優先走目前房間的出口，其次是最近的
            here = [f for f in front if f[1] == self.current]
            _, rid, d = here[0] if here else min(front, key=lambda f: len(self._route(self.current, f[1]) or [0] * 99))
            if rid != self.current and not await self._goto(rid):
                skip.add((rid, d))                        # 這次走不到，先跳過（不寫進地圖，下次再試）
                continue
            self.state = f"地圖探索：已記錄 {len(self.rooms)} 間，目前 {self.rooms[rid]['name']} 往 {d}"
            r, text = await self._move(d)
            if not await self._safe(text, self.last_move):
                self.rooms[rid]["exits"][d] = "danger"
                continue
            if not r:
                if self._tired(text):                    # 休息後還是走不了，下次再試
                    continue
                first = next((l for l in text.split("\n") if l.strip()), "")
                self.rooms[rid]["exits"][d] = "blocked:" + first[:40]
                continue
            path = self.rooms[rid]["path"] + [d]
            is_new = room_id(r) not in self.rooms
            new = self._add(r, path)
            if is_new and self.probe:
                self.rooms[new]["probed"] = True
                await self._probe(new)
            self.rooms[rid]["exits"][d] = new
            back = REVERSE.get(d)
            if back in self.rooms[new]["exits"] and self.rooms[new]["exits"][back] is None:
                self.rooms[new]["exits"][back] = rid       # 先假設可以走回去，_goto 時會驗證
            self.current = new
            explored += 1
            if explored % 20 == 0:
                self.save_map()
                b.log(f"[探索] 已記錄 {len(self.rooms)} 間房間")
        self.save_map()
        b.log(f"[探索] 地圖探索結束，共 {len(self.rooms)} 間房間，存在 {self.out}")

    async def _probe(self, rid: str) -> None:
        """記錄房間裡的怪和物品；新看到的怪打 consider，有怪的房間打 list 看是不是商店。"""
        room = self.rooms[rid]
        where = room["name"] + ("　/" + "".join(room["path"]) if room.get("path") else "")
        mobs = []
        for line in room["contents"]:
            c = classify(line)
            if not c:
                continue
            book = self.npcs if c["kind"] == "mob" else self.items
            e = book.setdefault(c["kw"], {"name": c["name"], "rooms": []})
            if where not in e["rooms"]:
                e["rooms"].append(where)
            if c["level"] is not None:
                e["level"] = c["level"]
            if c["kind"] == "mob":
                mobs.append(c["kw"])
        for kw in mobs[:3]:
            e = self.npcs[kw]
            if "consider" not in e:
                word = kw.split()[0]
                text = await self.bot.capture(f"consider {word}", timeout=4, quiet=1.0)
                e["consider"] = " / ".join(l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith("<"))[:200]
        if mobs and "shop" not in room:
            text = await self.bot.capture("list", timeout=5, quiet=1.0)
            lines = [l.rstrip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith("<")]
            room["shop"] = lines if len(lines) >= 2 or any(re.search(r"\d", l) for l in lines) else []
            if room["shop"]:
                self.bot.log(f"[探索] 商店：{where}（{len(lines)} 行）")

    def save_map(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "map.json").write_text(json.dumps({"home": self.home, "rooms": self.rooms}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        lines = ["# 實地探索的地圖", "", f"共 {len(self.rooms)} 間房間；路線從回城點出發。", ""]
        for rid, r in sorted(self.rooms.items(), key=lambda x: len(x[1].get("path") or [0] * 999)):
            route = "".join(r["path"]) if r.get("path") else ("（回城點）" if rid == self.home else "（路線未知）")
            exits = "、".join(f"{d}→{self.rooms[n]['name'] if n in self.rooms else n}" for d, n in r["exits"].items())
            lines.append(f"## {r['name']}　`/{route}`")
            lines.append(f"- 出口：{exits or '無'}")
            if r["desc"]:
                lines.append(f"- 敘述：{r['desc'][:120]}")
            cs = [classify(l) for l in r["contents"]]
            mobs = [f"{c['name']}（{c['kw']}）" for c in cs if c and c["kind"] == "mob"]
            items = [f"{c['name']}（{c['kw']}）" for c in cs if c and c["kind"] == "item"]
            other = [l for l, c in zip(r["contents"], cs) if not c]
            if mobs:
                lines.append("- 怪／NPC：" + "；".join(mobs[:12]))
            if items:
                lines.append("- 物品：" + "；".join(items[:12]))
            if other:
                lines.append("- 其他：" + "；".join(other[:6]))
            if r.get("shop"):
                lines.append("- 商店：" + "｜".join(l.strip() for l in r["shop"][:20]))
            lines.append("")
        (self.out / "map.md").write_text("\n".join(lines), encoding="utf-8")
        for name in ("npcs", "items"):
            (self.out / f"{name}.json").write_text(json.dumps(getattr(self, name), ensure_ascii=False, indent=1), encoding="utf-8")
        md = ["# 探索時看到的怪／NPC", "", "| 名稱（關鍵字） | 出現地點 | consider |", "|---|---|---|"]
        for kw, e in sorted(self.npcs.items()):
            md.append(f"| {e['name']}（{kw}） | {'；'.join(e['rooms'][:4])} | {e.get('consider', '')} |")
        md += ["", "# 地上看到的物品", "", "| 名稱（關鍵字） | 等級 | 出現地點 |", "|---|---|---|"]
        for kw, e in sorted(self.items.items()):
            md.append(f"| {e['name']}（{kw}） | {e.get('level', '')} | {'；'.join(e['rooms'][:4])} |")
        (self.out / "npcs.md").write_text("\n".join(md), encoding="utf-8")
