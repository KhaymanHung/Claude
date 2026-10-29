"""核心：逐行處理遊戲輸出、解析狀態列、自動登入、觸發器、等待特定訊息、限速送指令。"""

import asyncio
import re
import time
from dataclasses import dataclass

from .connection import strip_ansi
from .regen import RegenTracker


@dataclass
class Trigger:
    name: str
    pattern: re.Pattern
    send: list
    auto_only: bool = True
    hits: int = 0


class Stats:
    """從狀態列（prompt）或 score 抓到的 hp / mana / mv。"""

    KEYS = ("hp", "maxhp", "mana", "maxmana", "mv", "maxmv", "power", "maxpower")

    def __init__(self):
        self.values: dict[str, int] = {}

    def update(self, m: re.Match) -> None:
        for k, v in m.groupdict().items():
            if k in self.KEYS and v is not None:
                self.values[k] = int(v)

    def ratio(self, key: str) -> float | None:
        cur, mx = self.values.get(key), self.values.get("max" + key)
        if cur is None or not mx:
            return None
        return cur / mx

    def text(self) -> str:
        parts = []
        for k in ("hp", "mana", "mv", "power"):
            if k in self.values:
                mx = self.values.get("max" + k)
                parts.append(f"{k} {self.values[k]}" + (f"/{mx}" if mx else ""))
        return "　".join(parts) or "（尚未抓到狀態列）"


class Bot:
    def __init__(self, cfg: dict, password: str, conn, log, echo):
        self.conn, self.log, self.echo = conn, log, echo
        self.password = password
        self.auto = False
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stats = Stats()
        self.regen = RegenTracker()            # main.py 會設定存檔位置
        self.last_combat = 0.0          # 最後一次看到戰鬥訊息的時間
        self.exp_gained = 0
        self.need_shopping = False             # 吃喝時發現身上沒東西了
        self.busy = False                      # 探索進行中（自動吃喝只在狩獵或探索時做）
        self._last_supply = 0.0
        self.levels = 0
        self._buffer = ""
        self._partial_seen = ""
        self._waiters: list = []
        self._capture: list | None = None     # capture() 期間收集的輸出
        self._capture_time = 0.0
        self.pager = re.compile(r"按\s*ENTER\s*繼續|\(c\)繼續顯示|--More--|\[Hit Return|請按.*(Enter|RETURN)|按任意鍵|\[q\]uit", re.I)
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0

        lg = cfg.get("login", {})
        self.login_enabled = lg.get("enabled", False)
        self.login_user = lg.get("username", "")
        self.login_steps = [(s["prompt"], s.get("send", "")) for s in lg.get("steps", [])]
        self.login_stage = 0
        self.apply_config(cfg)

    def apply_config(self, cfg: dict) -> None:
        """套用（或 #reload 重新套用）設定。登入設定只在啟動時讀一次。"""
        self.command_interval = float(cfg.get("bot", {}).get("command_interval", 0.5))
        st = cfg.get("status", {})
        self.stat_patterns = [re.compile(p) for p in st.get("patterns", [])]
        self.refresh_commands = list(st.get("refresh", ["score"]))
        # 設定狀態列的完整指令。注意：不帶參數的 prompt 是開關，會把狀態列關掉
        self.prompt_command = st.get("prompt_command", "")
        self.home_room = st.get("home_room", "市中心")   # recall 回到的房間名稱
        self.msg = {k: re.compile(v) for k, v in cfg.get("messages", {}).items() if v}
        if "pager" in self.msg:                  # 設定檔可以自訂分頁提示
            self.pager = self.msg.pop("pager")
        sp = cfg.get("supplies", {})
        self.supplies = {
            "enabled": sp.get("enabled", False),
            "eat": list(sp.get("eat", [])), "drink": list(sp.get("drink", [])),
            "shop_route": list(sp.get("shop_route", [])), "buy": list(sp.get("buy", [])),
            "after_buy": list(sp.get("after_buy", [])),
        }
        self.triggers = [
            Trigger(
                name=t.get("name", t["pattern"]),
                pattern=re.compile(t["pattern"]),
                send=list(t.get("send", [])),
                auto_only=t.get("auto_only", True),
            )
            for t in cfg.get("triggers", [])
        ]

    # ---------- 送指令 ----------
    async def send(self, cmd: str, secret: bool = False) -> None:
        """送出一個指令；所有指令共用同一個間隔限制，避免洗頻。"""
        async with self._send_lock:
            wait = self._last_send + self.command_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await self.conn.send(cmd, secret)
            self.regen.on_command(cmd)
            self._last_send = time.monotonic()
        self.echo("> ********" if secret else f"> {cmd}")

    def enqueue(self, cmd: str, secret: bool = False) -> None:
        self.queue.put_nowait((cmd, secret))

    def clear_queue(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    async def sender(self) -> None:
        while True:
            cmd, secret = await self.queue.get()
            if not self.conn.connected:
                return
            await self.send(cmd, secret)

    # ---------- 等待訊息 ----------
    def _register(self, names):
        """登記要等的訊息。特殊名稱 "prompt" 表示等到下一次狀態列（代表伺服器這次的回應結束了）。"""
        pats = {n: self.msg[n] for n in names if n in self.msg}
        if "prompt" in names:
            pats["prompt"] = None
        fut = asyncio.get_running_loop().create_future()
        w = (pats, fut)
        self._waiters.append(w)
        return w

    def _resolve_prompt(self) -> None:
        for pats, fut in list(self._waiters):
            if "prompt" in pats and not fut.done():
                fut.set_result("prompt")

    async def _await(self, w, timeout: float):
        try:
            return await asyncio.wait_for(w[1], timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            if w in self._waiters:
                self._waiters.remove(w)

    async def expect(self, names, timeout: float) -> str | None:
        """等待 [messages] 裡某幾種訊息出現，回傳訊息名稱；逾時回傳 None。"""
        return await self._await(self._register(names), timeout)

    async def send_expect(self, cmd: str, names, timeout: float) -> str | None:
        """送出指令並等待回應（先登記再送出，才不會漏掉很快回來的訊息）。"""
        w = self._register(names)
        await self.send(cmd)
        return await self._await(w, timeout)

    async def capture(self, cmd: str, timeout: float = 8, quiet: float = 1.5) -> str:
        """送出指令並收集回應，直到出現狀態列（或安靜 quiet 秒）。分頁提示會自動按 Enter。"""
        self._capture = []
        self._capture_time = time.monotonic()
        w = self._register(["prompt"])
        await self.send(cmd)
        start = time.monotonic()
        try:
            while True:
                r = await self._await(w, 0.3) if not w[1].done() else "prompt"
                now = time.monotonic()
                if r == "prompt":
                    await asyncio.sleep(0.3)          # 收尾：同一批輸出可能還沒到齊
                    break
                if self._capture and now - self._capture_time > quiet:
                    break
                if now - start > timeout:
                    break
                if w not in self._waiters:            # _await 逾時會移除，重新登記
                    w = self._register(["prompt"])
            return "\n".join(self._capture).strip("\n")
        finally:
            self._capture = None
            if w in self._waiters:
                self._waiters.remove(w)

    def _page_continue(self) -> None:
        """分頁提示：把提示前的文字留下，自動按 Enter 看下一頁。"""
        before = self.pager.split(self._buffer)[0]
        before = re.sub(r"\[[^\[]*$", "", before).rstrip()
        if before:
            self._capture.append(before)
        self._buffer = ""
        self._capture_time = time.monotonic()      # 還有下一頁，延長等待時間
        self.enqueue("")

    def _check_supplies(self, line: str) -> None:
        m, rg = self.msg, self.regen
        if "hungry" in m and m["hungry"].search(line):
            rg.hungry = True
            self._supply("eat")
        if "thirsty" in m and m["thirsty"].search(line):
            rg.thirsty = True
            self._supply("drink")
        if "not_hungry" in m and m["not_hungry"].search(line):
            rg.hungry = False
        if "not_thirsty" in m and m["not_thirsty"].search(line):
            rg.thirsty = False
        if "no_item" in m and m["no_item"].search(line) and time.monotonic() - self._last_supply < 5:
            if not self.need_shopping:
                self.log("[補給] 身上沒有食物或水了，等一下會回城購買")
            self.need_shopping = True

    def _supply(self, kind: str) -> None:
        """飢餓或口渴時自動吃喝（只在狩獵、探索時；30 秒內不重複）。"""
        sp = self.supplies
        if not (sp["enabled"] and (self.busy or self.auto)) or time.monotonic() - self._last_supply < 30:
            return
        self._last_supply = time.monotonic()
        cmds = sp[kind]
        if cmds:
            self.log(f"[補給] {'飢餓' if kind == 'eat' else '口渴'}，{' ; '.join(cmds)}")
            for c in cmds:
                self.enqueue(c)

    async def shop(self, expand) -> None:
        """回城走到商店買食物和水，再回城。expand 是攻略的路線展開函式。"""
        sp = self.supplies
        now = time.monotonic()
        if now - getattr(self, "_last_shop", -1e9) < 600:   # 10 分鐘內又要買：可能買不到或指令有誤
            self.log("[補給] 10 分鐘內又缺補給，先停止自動購買；請檢查 config.toml 的 [supplies]")
            sp["enabled"] = False
            self.need_shopping = False
            return
        self._last_shop = now
        if not sp["shop_route"] or not sp["buy"]:
            self.log("[補給] config.toml 的 [supplies] 沒有設定商店路線或購買指令，無法自動購買")
            self.need_shopping = False
            return
        self.log("[補給] 回城購買食物和水")
        for c in expand(sp["shop_route"]):
            if c == "recall" and await self.at_home():
                continue                           # 已經在回城點，不必 recall（recall 會讓移動力減半）
            await self.capture(c)
        for c in sp["buy"] + sp["after_buy"]:
            await self.capture(c)
        self.need_shopping = False                 # 買完不 recall，由狩獵或探索自己找路回去
        self.regen.hungry = self.regen.thirsty = False
        for c in sp["eat"] + sp["drink"]:
            await self.capture(c)
        self.log("[補給] 購買完成")

    async def at_home(self) -> bool:
        """look 一下，看是不是已經在回城點（是的話就不必 recall）。"""
        from .explorer import parse_room
        r = parse_room(await self.capture("look"))
        return bool(r and r["name"] == self.home_room)

    async def ensure_prompt(self) -> None:
        """送出設定狀態列的指令，確保狀態列是開著的。"""
        if self.prompt_command:
            await self.capture(self.prompt_command)

    # ---------- 處理伺服器輸出 ----------
    def feed(self, text: str) -> None:
        self._buffer += strip_ansi(text).replace("\r", "")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            seen, self._partial_seen = self._partial_seen, ""
            # 上一次沒換行的狀態列已經處理過，這次不要再算一次
            self._line(line, skip=len(seen) if seen and line.startswith(seen) else 0)
        if self._buffer:                      # 沒有換行的狀態列或登入提示
            if self._capture is not None and self.pager.search(self._buffer):
                self._page_continue()
                return
            if self._buffer != self._partial_seen and self._parse_stats(self._buffer):
                self._partial_seen = self._buffer
            if self._login(self._buffer):
                self._buffer = self._partial_seen = ""

    def _parse_stats(self, text: str) -> bool:
        found = False
        for p in self.stat_patterns:
            m = p.search(text)
            if m:
                self.stats.update(m)
                found = True
        if found:
            self.regen.on_stats(self.stats.values, self.last_combat)
            self._resolve_prompt()
        return found

    def _login(self, text: str) -> bool:
        if not self.login_enabled or self.login_stage >= len(self.login_steps):
            return False
        prompt, send = self.login_steps[self.login_stage]
        if prompt not in text:
            return False
        self.login_stage += 1
        secret = "$password" in send
        self.enqueue(send.replace("$user", self.login_user).replace("$password", self.password), secret)
        return True

    def _line(self, line: str, skip: int = 0) -> None:
        self._login(line)
        if self._capture is not None:
            if self.pager.search(line):
                self._buffer, saved = line, self._buffer
                self._page_continue()
                self._buffer = saved
                return
            self._capture.append(line[skip:])
            self._capture_time = time.monotonic()
        m = self.msg
        if "combat" in m and m["combat"].search(line):
            self.last_combat = time.monotonic()
        if "exp" in m and (mm := m["exp"].search(line)):
            try:
                self.exp_gained += int(mm.group("n"))
            except (IndexError, TypeError, ValueError):
                pass
        self._check_supplies(line)
        if "level_up" in m and m["level_up"].search(line):
            self.levels += 1
            self.log("[升級] 恭喜升級！更新最大值")
            for c in self.refresh_commands:
                self.enqueue(c)

        for pats, fut in list(self._waiters):
            if fut.done():
                continue
            for name, pat in pats.items():
                if pat is not None and pat.search(line):
                    fut.set_result(name)
                    break

        self._parse_stats(line[skip:])       # 放在比對訊息之後，錯誤訊息才會比狀態列先被看到
        for t in self.triggers:
            if t.auto_only and not self.auto:
                continue
            if t.pattern.search(line):
                t.hits += 1
                self.log(f"[觸發] {t.name} → {', '.join(t.send)}")
                for c in t.send:
                    self.enqueue(c)
