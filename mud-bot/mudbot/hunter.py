"""巡邏狩獵狀態機（MERC / Diku 系打怪練功）。

流程：
  回城（recall）→ 沿著路線一格一格走
  每到一格：依序對每個目標關鍵字 kill，直到「They aren't here」
  戰鬥中：每回合看狀態列，血量太低就 flee
  移動前：hp / mv / mana 不夠就 sleep，補滿再 wake 繼續
  任何「位置不確定」的狀況（逃跑、走不過去、戰鬥超時）→ 回城重新走路線
  角色死亡、無法回城、連續出問題太多次 → 停止並發出提示音
"""

import asyncio
import time

from .guide import is_direction

OPPOSITE = {
    "n": "s", "s": "n", "e": "w", "w": "e", "u": "d", "d": "u",
    "north": "south", "south": "north", "east": "west", "west": "east",
    "up": "down", "down": "up",
    "ne": "sw", "sw": "ne", "nw": "se", "se": "nw",
}


class Stop(Exception):
    """停止狩獵，需要人處理。"""


class Recover(Exception):
    """位置或狀況不確定，回城後重新走路線。"""


class Hunter:
    def __init__(self, bot, cfg: dict):
        self.bot = bot
        self.task: asyncio.Task | None = None
        self.state = "停止"
        self.kills = 0
        self.flees = 0
        self.recoveries = 0
        self.started_at = 0.0
        self.exp_at_start = 0
        self.preset = ""                # 目前使用的練功設定名稱（#farm）
        self.expand = lambda route: list(route)   # main.py 會換成攻略的路線展開
        self.navigator = None           # main.py 會設成 Explorer，用實地地圖走回回城點，少用 recall
        self.apply_config(cfg)

    def apply_config(self, cfg: dict) -> None:
        h = cfg.get("hunt", {})
        self.targets = list(h.get("targets", []))
        self.path = list(h.get("path", []))
        self.approach = list(h.get("approach", []))   # 從回城點走到練功區（沿路不打怪）
        self.path_mode = h.get("path_mode", "pingpong")
        self.start_with_recall = h.get("start_with_recall", True)
        self.on_start = list(h.get("on_start", []))
        self.after_kill = list(h.get("after_kill", []))
        self.max_kills_per_room = int(h.get("max_kills_per_room", 5))

        self.kill_command = h.get("kill_command", "kill")
        self.flee_command = h.get("flee_command", "flee")
        self.recall_command = h.get("recall_command", "recall")
        self.rest_command = h.get("rest_command", "sleep")
        self.wake_command = h.get("wake_command", "wake")
        self.poll_command = h.get("poll_command", "")

        self.flee_below = float(h.get("flee_below", 0.3))
        self.after_flee = h.get("after_flee", "recall")
        self.rest_below = {
            "hp": float(h.get("rest_hp_below", 0.5)),
            "mana": float(h.get("rest_mana_below", 0.0)),
            "mv": float(h.get("rest_mv_below", 0.2)),
        }
        self.resume_above = float(h.get("resume_above", 0.95))

        self.kill_wait = float(h.get("kill_wait", 4))
        self.move_wait = float(h.get("move_wait", 1.5))
        self.fight_timeout = float(h.get("fight_timeout", 90))
        self.fight_quiet = float(h.get("fight_quiet", 8))
        self.rest_poll = float(h.get("rest_poll", 10))
        self.max_rest = float(h.get("max_rest", 900))
        self.max_recoveries = int(h.get("max_recoveries", 5))
        self.respawn_wait = float(h.get("respawn_wait", 20))   # 沒有巡邏路線時，清完一輪等幾秒再打

    # ---------- 對外控制 ----------
    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self) -> None:
        if self.running:
            return
        problems = []
        if not self.targets:
            problems.append("[hunt] targets 沒有設定目標")
        if problems:
            self.bot.log("無法開始：" + "；".join(problems))
            return
        self.kills = self.flees = self.recoveries = 0
        self.started_at = time.monotonic()
        self.exp_at_start = self.bot.exp_gained
        self.bot.auto = True
        self.task = asyncio.create_task(self._run())
        self.bot.log("[狩獵] 開始")

    def configure(self, name: str, targets: list[str], approach: list[str], patrol: list[str]) -> None:
        """套用攻略裡的練功設定（#farm）。"""
        self.preset = name
        self.targets = list(targets)
        self.approach = list(approach)
        self.path = list(patrol)
        self.start_with_recall = True

    def _log_drop(self, who: str, loot: list[tuple[str, str]]) -> None:
        """把打死怪後撿到的東西記到 data/live/drops.csv（時間、練功地點、怪、指令、遊戲回應）。"""
        import csv
        from pathlib import Path
        f = Path(getattr(self, "drops_path", "data/live/drops.csv"))
        f.parent.mkdir(parents=True, exist_ok=True)
        new = not f.exists()
        try:
            with f.open("a", encoding="utf-8-sig", newline="") as fp:
                w = csv.writer(fp)
                if new:
                    w.writerow(["時間", "練功地點", "怪", "指令", "回應"])
                for cmd, text in loot:
                    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.lstrip().startswith("<")]
                    w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), getattr(self, "preset", ""), who, cmd, " / ".join(lines)])
        except OSError as e:
            self.bot.log(f"[掉落] 無法寫入 {f}：{e}")

    def stop(self, why: str = "手動停止") -> None:
        if self.running:
            self.task.cancel()
        self.bot.auto = False
        self.bot.clear_queue()
        self.state = "停止"
        self.bot.log(f"[狩獵] 停止：{why}")

    def status(self) -> str:
        lines = [f"狩獵：{self.state}　狀態列：{self.bot.stats.text()}"]
        where = f"練功設定：{self.preset}　" if self.preset else ""
        lines.append(f"{where}目標：{'、'.join(self.targets) or '（無）'}　巡邏：{' '.join(self.path) or '（原地等重生）'}")
        if self.started_at:
            mins = max((time.monotonic() - self.started_at) / 60, 0.01)
            exp = self.bot.exp_gained - self.exp_at_start
            lines.append(
                f"本次：{mins:.0f} 分鐘，擊殺 {self.kills}，經驗 {exp}（每小時約 {exp / mins * 60:.0f}），"
                f"逃跑 {self.flees}，回城重來 {self.recoveries}，升級 {self.bot.levels}"
            )
        return "\n".join(lines)

    # ---------- 主迴圈 ----------
    async def _run(self) -> None:
        b = self.bot
        try:
            await b.ensure_prompt()
            for c in self.on_start + b.refresh_commands:
                await b.send(c)
            await asyncio.sleep(1)
            need_recall = self.start_with_recall
            while True:
                try:
                    if need_recall:
                        await self._recall()
                        await self._approach()
                    need_recall = True
                    await self._patrol()
                except Recover as e:
                    self.recoveries += 1
                    b.log(f"[狩獵] {e} → 回城重新走路線（第 {self.recoveries} 次）")
                    if self.recoveries > self.max_recoveries:
                        raise Stop(f"連續出狀況超過 {self.max_recoveries} 次")
        except Stop as e:
            print("\a", end="", flush=True)        # 提示音
            b.log(f"[狩獵] 停止：{e}，請手動檢查")
        except asyncio.CancelledError:
            raise
        except Exception as e:                     # 程式錯誤也不要讓整個程式當掉
            print("\a", end="", flush=True)
            b.log(f"[狩獵] 程式錯誤，已停止：{e!r}")
        finally:
            self.state = "停止"
            b.auto = False

    def _route(self) -> list[str]:
        path = self.expand(self.path)
        if self.path_mode == "pingpong" and all(is_direction(c) for c in path):
            back = [OPPOSITE.get(s, s) for s in reversed(path)]
            return path + back
        return path

    async def _approach(self) -> None:
        """從回城點走到練功區，沿路不打怪（被攻擊才打）。"""
        cmds = self.expand(self.approach)
        for i, c in enumerate(cmds, 1):
            self.state = f"前往練功區 {i}/{len(cmds)}：{c}"
            await self._ensure_ready()
            await self._move(c)

    async def _patrol(self) -> None:
        if not self.path:                          # 沒有巡邏路線：原地清怪、等重生
            while True:
                await self._clear_room()
                self.recoveries = 0
                await self._ensure_ready()
                self.state = f"等待重生（最多 {self.respawn_wait:.0f} 秒）"
                await self.bot.expect(["respawn"], self.respawn_wait)
        while True:
            await self._clear_room()
            route = self._route()
            for i, step in enumerate(route, 1):
                await self._ensure_ready()
                self.state = f"移動 {i}/{len(route)}：{step}"
                await self._move(step)
                await self._clear_room()
            self.recoveries = 0                    # 完整走完一圈，重設失敗次數
            if self.path_mode == "recall" or not all(is_direction(c) for c in route):
                await self._recall()
                await self._approach()

    # ---------- 各種動作 ----------
    def _in_combat(self, since: float = 0.0) -> bool:
        last = self.bot.last_combat
        return last > since and time.monotonic() - last < 4

    async def _clear_room(self) -> None:
        b = self.bot
        for kw in self.targets:
            for _ in range(self.max_kills_per_room):
                await self._ensure_ready()
                self.state = f"攻擊 {kw}"
                r = await b.send_expect(
                    f"{self.kill_command} {kw}",
                    ["no_target", "not_attackable", "target_dead", "died", "combat", "still_fighting", "sleeping"],
                    self.kill_wait,
                )
                if r in (None, "no_target", "not_attackable"):
                    break
                if r == "died":
                    raise Stop("角色死亡")
                if r == "sleeping":
                    await b.send(self.wake_command)
                    continue
                await self._fight(kw, dead=(r == "target_dead"))
        if self._in_combat():                      # 被主動怪攻擊
            await self._fight("主動攻擊的怪")

    async def _fight(self, who: str, dead: bool = False) -> None:
        b = self.bot
        start = time.monotonic()
        while True:
            if dead:
                self.kills += 1
                dead_at = time.monotonic()
                b.log(f"[擊殺] {who}（共 {self.kills}）")
                loot = []
                for c in self.after_kill:
                    loot.append((c, await b.capture(c, timeout=4, quiet=1.0)))
                self._log_drop(who, loot)
                if b.last_combat > dead_at + 0.3:  # 房間裡還有別的怪在打你
                    dead = False
                    who = "其他怪"
                    continue
                return
            self.state = f"戰鬥：{who}（{b.stats.text()}）"
            hp = b.stats.ratio("hp")
            if hp is not None and hp < self.flee_below:
                await self._flee(hp)
            r = await b.expect(["target_dead", "died", "flee_ok", "not_fighting"], 1.0)
            now = time.monotonic()
            if r == "died":
                raise Stop("角色死亡")
            if r == "target_dead":
                dead = True
                continue
            if r == "flee_ok":
                raise Recover("已經逃離戰鬥")
            if r == "not_fighting":
                return
            if now - start > self.fight_quiet and now - b.last_combat > self.fight_quiet:
                return                             # 怪跑了或戰鬥已結束
            if now - start > self.fight_timeout:
                raise Recover("戰鬥太久")

    async def _flee(self, hp: float) -> None:
        b = self.bot
        self.state = "逃跑"
        b.log(f"[逃跑] 血量剩 {hp:.0%}，低於 {self.flee_below:.0%}")
        for _ in range(10):
            r = await b.send_expect(self.flee_command, ["flee_ok", "flee_fail", "died", "not_fighting"], 3)
            if r == "died":
                raise Stop("角色死亡")
            if r in ("flee_ok", "not_fighting"):
                break
        else:
            raise Stop("一直逃不掉")
        self.flees += 1
        if self.after_flee == "stop":
            raise Stop("逃跑成功，依設定停止")
        await asyncio.sleep(1)
        raise Recover("逃跑後位置不確定")

    async def _move(self, step: str) -> None:
        b = self.bot
        if not is_direction(step):                 # look painting、talk wizard help 這類指令
            await b.send_expect(step, ["prompt"], 2)
            return
        for _ in range(3):
            r = await b.send_expect(step, ["no_exit", "exhausted", "still_fighting", "died", "sleeping", "prompt"], self.move_wait)
            if r in (None, "prompt"):
                return                             # 沒有錯誤訊息就當作走成功
            if r == "died":
                raise Stop("角色死亡")
            if r == "exhausted":
                await self._rest(force=True)
            elif r == "still_fighting":
                await self._fight("擋路的怪")
            elif r == "sleeping":
                await b.send(self.wake_command)
            else:
                raise Recover(f"走不過去：{step}")
        raise Recover(f"一直無法移動：{step}")

    async def _recall(self) -> None:
        b = self.bot
        self.state = "回城"
        if self.navigator is not None:             # 有實地地圖：能走回去就不 recall（recall 會讓移動力減半）
            await self.navigator.go_home()
            return
        if await b.at_home():
            return
        for _ in range(3):
            r = await b.send_expect(self.recall_command, ["recall_fail", "died", "still_fighting", "sleeping"], 3)
            if r is None:
                await asyncio.sleep(1)
                return
            if r == "died":
                raise Stop("角色死亡")
            if r == "sleeping":
                await b.send(self.wake_command)
            elif r == "still_fighting":
                await self._fight("回城時的怪")
            else:
                await asyncio.sleep(3)
        raise Stop("無法回城")

    def _needs_rest(self) -> bool:
        for key, th in self.rest_below.items():
            r = self.bot.stats.ratio(key)
            if th > 0 and r is not None and r < th:
                return True
        return False

    def _rested(self) -> bool:
        for key, th in self.rest_below.items():
            if key != "hp" and th <= 0:
                continue
            r = self.bot.stats.ratio(key)
            if r is not None and r < self.resume_above:
                return False
        return True

    async def _ensure_ready(self) -> None:
        if self.bot.need_shopping and not self._in_combat():
            await self.bot.shop(self.expand)
            raise Recover("購買補給後回城，重新走路線")
        if self._in_combat():                      # 正在被打：先打完（或逃跑）再說
            await self._fight("正在攻擊你的怪")
        if self._needs_rest():
            await self._rest()

    async def _rest(self, force: bool = False) -> None:
        b = self.bot
        start = time.monotonic()
        b.log(f"[休息] {b.stats.text()}")
        await b.send(self.rest_command)
        while True:
            self.state = f"休息（{b.stats.text()}）"
            await asyncio.sleep(self.rest_poll)
            if self._in_combat(since=start):        # 睡覺時被攻擊
                b.log("[休息] 被攻擊，起來戰鬥")
                await b.send(self.wake_command)
                await self._fight("偷襲的怪")
                await b.send(self.rest_command)
                continue
            await b.send(self.poll_command)        # 送空行讓伺服器回一次狀態列
            await asyncio.sleep(0.5)
            if self._rested() and not (force and time.monotonic() - start < self.rest_poll):
                break
            if time.monotonic() - start > self.max_rest:
                b.log("[休息] 休息太久，先繼續")
                break
        await b.send(self.wake_command)
        b.log(f"[休息] 完成：{b.stats.text()}")
