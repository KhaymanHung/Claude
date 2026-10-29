"""照攻略執行：走路線（#goto）、逐步解謎（#quest / #next）、記錄路線（#record）。"""

import asyncio
import json
import time
from pathlib import Path

from .guide import Guide, is_direction


class Walker:
    """依序送出路線指令。移動指令會檢查有沒有「走不過去」，有問題就停下來。"""

    def __init__(self, bot, move_wait: float = 1.2, cmd_wait: float = 0.6):
        self.bot = bot
        self.move_wait = move_wait
        self.cmd_wait = cmd_wait
        self.task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def stop(self) -> None:
        if self.running:
            self.task.cancel()

    async def walk(self, cmds: list[str], label: str = "") -> bool:
        """回傳 True 表示全部送完；False 表示中途停下。"""
        b = self.bot
        total = len(cmds)
        for i, c in enumerate(cmds, 1):
            if c == "recall" and await b.at_home():
                b.log("[路線] 已經在回城點，跳過 recall")
                continue
            if is_direction(c):
                r = await b.send_expect(c, ["no_exit", "exhausted", "still_fighting", "died", "sleeping", "prompt"], self.move_wait)
                if r and r != "prompt":
                    reason = {"no_exit": "走不過去", "exhausted": "移動力不夠", "still_fighting": "正在戰鬥",
                              "died": "角色死亡", "sleeping": "正在睡覺"}[r]
                    print("\a", end="", flush=True)
                    b.log(f"[路線] {label} 第 {i}/{total} 步「{c}」{reason}，已停止。處理好後可以用 #next 重來這一步，或手動繼續。")
                    return False
            else:
                await b.send_expect(c, ["prompt"], self.cmd_wait * 3)
        return True

    def start(self, cmds: list[str], label: str, done=None) -> None:
        if self.running:
            self.bot.log("[路線] 上一段還在走，請先 #stop")
            return

        async def run():
            ok = await self.walk(cmds, label)
            if ok:
                self.bot.log(f"[路線] {label} 完成（{len(cmds)} 個指令）")
            if done:
                done(ok)

        self.task = asyncio.create_task(run())


class QuestRunner:
    """一步一步解謎：#quest 名稱 開始，#next 執行目前這一步並前進。"""

    def __init__(self, bot, guide: Guide, walker: Walker):
        self.bot, self.guide, self.walker = bot, guide, walker
        self.quest: dict | None = None
        self.steps: list[dict] = []
        self.index = 0
        self.learner = None                # main.py 設定；步驟有 learn = "技能" 時用來學技能
        self.run_all = False               # #next all：自動一步接一步，遇到要自己處理的步驟才停

    def load(self, q: dict) -> None:
        self.quest = q
        self.steps = []
        if q.get("route"):
            self.steps.append({"title": "前往" + (q.get("area") or q["name"]), "do": list(q["route"]),
                               "note": q.get("route_note", "")})
        elif q.get("route_note"):
            self.steps.append({"title": "前往", "manual": True, "note": q["route_note"]})
        self.steps.extend(q.get("steps", []))
        self.index = 0
        self.bot.log(self.guide.quest_overview(q))
        if not self.steps:
            self.bot.log("（這個謎題沒有逐步資料，只有上面的說明。）")
            return
        self.bot.log("步驟：" + "　".join(f"{i}.{s['title']}" for i, s in enumerate(self.steps, 1)))
        self.show()

    def show(self) -> None:
        if not self.quest:
            self.bot.log("目前沒有進行中的解謎，用 #quest <名稱> 開始")
            return
        if self.index >= len(self.steps):
            self.bot.log(f"[解謎] {self.quest['name']} 的步驟都走完了！")
            return
        s = self.steps[self.index]
        lines = [f"[解謎] {self.quest['name']} 第 {self.index + 1}/{len(self.steps)} 步：{s['title']}"]
        if s.get("note"):
            lines.append("　" + s["note"].replace("\n", "\n　"))
        if s.get("learn"):
            lines.append(f"　學技能：{s['learn']}（自動走到雕像前學並練習）")
            lines.append("　輸入 #next 執行這一步，#next all 自動做到需要你處理的步驟，#skip 跳過")
        elif s.get("do"):
            cmds = self.guide.expand(s["do"])
            lines.append("　指令：" + " ; ".join(s["do"]) + (f"（展開後 {len(cmds)} 個）" if len(cmds) != len(s["do"]) else ""))
            lines.append("　輸入 #next 執行這一步，#skip 跳過")
        elif s.get("manual"):
            lines.append("　這一步要你自己處理，完成後輸入 #next")
        else:
            lines.append("　輸入 #next 繼續")
        self.bot.log("\n".join(lines))

    def next(self, run_all: bool = False) -> None:
        self.run_all = run_all
        if not self.quest:
            self.bot.log("目前沒有進行中的解謎，用 #quest <名稱> 開始")
            return
        if self.index >= len(self.steps):
            self.show()
            return
        s = self.steps[self.index]

        def done(ok):
            if not ok:
                self.run_all = False
                return
            self.index += 1
            self.show()
            if self.run_all and self.index < len(self.steps) and not self.steps[self.index].get("manual") \
                    and not self.steps[self.index].get("pause"):
                self.next(run_all=True)
            else:
                self.run_all = False

        if s.get("learn") and self.learner:
            self.learner.start(s["learn"], bool(s.get("pay")), done)
        elif s.get("do") and not s.get("manual"):
            cmds = self.guide.expand(s["do"])
            self.walker.start(cmds, f"{self.quest['name']}：{s['title']}", done)
        else:
            self.run_all = False
            self.index += 1
            self.show()

    def skip(self, n: int = 1) -> None:
        if self.quest:
            self.index = max(0, min(len(self.steps), self.index + n))
            self.show()

    def goto_step(self, n: int) -> None:
        if self.quest:
            self.index = max(0, min(len(self.steps), n - 1))
            self.show()

    def stop(self) -> None:
        if self.quest:
            self.bot.log(f"[解謎] 結束 {self.quest['name']}")
        self.walker.stop()
        self.quest = None


class Recorder:
    """記錄你手動輸入的指令，存成可以重複使用的路線。"""

    def __init__(self, bot, path: Path):
        self.bot = bot
        self.path = path
        self.on = False
        self.cmds: list[str] = []

    def start(self) -> None:
        self.on, self.cmds = True, []
        self.bot.log("[記錄] 開始記錄你輸入的指令。走完後輸入 #record save <名稱>，放棄輸入 #record stop")

    def feed(self, cmd: str) -> None:
        if self.on and cmd and not cmd.startswith("#"):
            self.cmds.append(cmd)

    def stop(self) -> None:
        self.on = False
        self.bot.log(f"[記錄] 停止（未儲存，共 {len(self.cmds)} 個指令）")

    def save(self, name: str, guide: Guide) -> None:
        if not self.cmds:
            self.bot.log("[記錄] 沒有記到任何指令")
            return
        cmds = compress(self.cmds)
        routes = dict(guide.user_routes)
        routes[name] = cmds
        with self.path.open("w", encoding="utf-8") as f:
            f.write("# 用 #record 記錄的自訂路線。可以直接編輯；名稱和 [[hunt]] 相同時，#farm 會拿來當巡邏路線\n")
            for n, c in routes.items():
                f.write(f"\n[[route]]\nname = {json.dumps(n, ensure_ascii=False)}\ncommands = {json.dumps(c, ensure_ascii=False)}\n")
        guide.reload()
        self.on = False
        self.bot.log(f"[記錄] 已存成「{name}」：{' '.join(cmds)}")


def compress(cmds: list[str]) -> list[str]:
    """連續的方向指令合併成 3w2s 這種寫法。"""
    out, run = [], ""
    last, count = "", 0

    def flush():
        nonlocal run, last, count
        if last:
            run += (str(count) if count > 1 else "") + last
        last, count = "", 0

    for c in cmds:
        c2 = c.strip().lower()
        c2 = {"north": "n", "south": "s", "east": "e", "west": "w", "up": "u", "down": "d"}.get(c2, c2)
        if c2 in set("nsewud"):
            if c2 == last:
                count += 1
            else:
                flush()
                last, count = c2, 1
        else:
            flush()
            if run:
                out.append(run)
                run = ""
            out.append(c.strip())
    flush()
    if run:
        out.append(run)
    return out
