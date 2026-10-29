"""四度空間（MERC 2.2）練功與解謎助手 — 主程式。

用法：python main.py [設定檔路徑]   （預設 config.toml）

控制指令（以 # 開頭，不會送到伺服器）：
  練功
    #auto              用 config.toml 的 [hunt] 開始狩獵（再輸入一次就停止）
    #farm <名稱>       用攻略的練功設定開始狩獵，例如 #farm 泰洛市；#farm list 列出全部
    #stop              停止狩獵、走路線
    #status            顯示狀態、擊殺數、每小時經驗
  攻略
    #find <關鍵字>     搜尋區域、解謎、技能、裝備，例如 #find 元素之戒
    #area <名稱>       區域資訊與路線
    #skill <名稱>      技能或法術：記憶量、前置、學習對象，例如 #skill 降龍
    #item <名稱>       裝備的屬性與取得方式
    #goto <名稱或路線> 走過去，例如 #goto 魔谷、#goto map3 s6e7n
    #learn <技能> [pay] 自動走到教這個技能的雕像學會並練到十分熟練（要先 #map 勇者學校）；
                       Lv1 練習免費，之後要花錢的練習只在加 pay 時才做，例如 #learn infravision
  解謎
    #quest <名稱>      開始解謎並顯示第一步；#quest list 列出全部；#quest stop 結束
    #next              執行目前這一步並前進（自己處理的步驟就是「完成，下一步」）
    #next all          自動一步接一步，遇到要你自己處理的步驟或出問題才停
    #skip [n]          跳過這一步（或跳 n 步）
    #step [n]          重新顯示目前步驟（或跳到第 n 步）
  實地探索（結果存到 data/live/）
    #survey            收集 score、commands、skills all、spells all、area 等指令的輸出
    #survey help       再對每個技能和 help 主題查 help（很久，可隨時 #map stop）
    #map [房間數]      從回城點走遍附近房間記錄地圖（預設 200 間）；#map stop 停止
    #map <地點或路線> [房間數] [深度]
                       先走到那裡再探索附近，例如 #map 勇者學校 80 10、#map map3 s5wnd2s 60
    #regen             自然恢復統計：每次恢復間隔幾秒、睡覺／休息／站著各恢復多少
  其他
    #record            開始記錄你輸入的指令；#record save <名稱> 存成路線；#record stop 放棄
    #reload            重新讀取設定檔和攻略資料（不需斷線）
    #help              顯示說明
    #quit              離開程式
其他文字會直接當遊戲指令送出；狩獵或解謎中也可以手動下指令。
"""

import asyncio
import datetime as dt
import getpass
import os
import sys
import threading
import tomllib
from pathlib import Path

from mudbot.bot import Bot
from mudbot.connection import MudConnection
from mudbot.explorer import Explorer
from mudbot.guide import Guide
from mudbot.hunter import Hunter
from mudbot.learner import Learner
from mudbot.runner import QuestRunner, Recorder, Walker

HELP = __doc__.split("控制指令")[1].split("\n", 1)[1]
ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


class Logger:
    def __init__(self, log_dir: str):
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        self.base = Path(log_dir) / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.file = open(self.base.with_suffix(".log"), "a", encoding="utf-8")

    def write(self, text: str) -> None:
        self.file.write(text)
        self.file.flush()

    def info(self, msg: str) -> None:
        print(f"\x1b[36m{msg}\x1b[0m", flush=True)
        self.write(f"\n{dt.datetime.now():%H:%M:%S} {msg}\n")

    def echo(self, msg: str) -> None:
        print(f"\x1b[33m{msg}\x1b[0m", flush=True)
        self.write(msg + "\n")


def start_input_thread(loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
    """另開執行緒讀鍵盤輸入（Windows 上 asyncio 無法直接非同步讀 stdin）。"""
    def run():
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                line = "#quit"
            loop.call_soon_threadsafe(q.put_nowait, line)
            if line == "#quit":
                return
    threading.Thread(target=run, daemon=True).start()


class Commands:
    """處理 # 開頭的控制指令。"""

    def __init__(self, bot, hunter, guide, walker, quests, recorder, config_path, log, explorer=None):
        self.explorer = explorer
        self.bot, self.hunter, self.guide = bot, hunter, guide
        self.walker, self.quests, self.recorder = walker, quests, recorder
        self.config_path, self.log = config_path, log

    def handle(self, line: str) -> None:
        cmd, _, arg = line[1:].partition(" ")
        arg = arg.strip()
        fn = getattr(self, "do_" + cmd.lower(), None)
        if not fn:
            self.log("未知的控制指令，輸入 #help 查看說明")
            return
        try:
            fn(arg)
        except Exception as e:                       # 指令錯誤不要讓程式當掉
            self.log(f"指令執行失敗：{e!r}")

    # --- 練功 ---
    def busy(self, what: str) -> bool:
        """狩獵和走路線不能同時進行。"""
        if self.hunter.running:
            self.log(f"正在狩獵，要{what}請先 #stop")
            return True
        return False

    def do_auto(self, arg):
        if self.hunter.running:
            self.hunter.stop()
        else:
            self.walker.stop()
            self.hunter.preset = ""
            self.hunter.apply_config(load_config(self.config_path))
            self.hunter.start()

    def do_farm(self, arg):
        g = self.guide
        if not arg or arg == "list":
            self.log("練功設定：\n" + "\n".join(
                f"　{h['name']}（{h['area']}，Lv{h.get('level', '?')}）目標：{'、'.join(h['targets'])}"
                + ("　有巡邏路線" if h['name'] in g.user_routes or h.get('patrol') else "") for h in g.hunts))
            return
        h = g.find_hunt(arg)
        if not h:
            self.log(f"找不到「{arg}」的練功設定，輸入 #farm list 看全部")
            return
        patrol = g.user_routes.get(h["name"]) or h.get("patrol", [])
        self.hunter.stop("改用練功設定") if self.hunter.running else None
        self.walker.stop()
        self.hunter.apply_config(load_config(self.config_path))
        self.hunter.configure(h["name"], h["targets"], h.get("approach", []), patrol)
        if h.get("kill_command"):                  # 練功設定可以指定招式，例如 f saulin、f lohan
            self.hunter.kill_command = h["kill_command"]
        if h.get("on_start"):
            self.hunter.on_start = list(h["on_start"])
        note = "" if patrol else "。攻略沒有巡邏路線，會在到達的那一格清怪並等重生；可以用 #record 記錄巡邏路線，存成同樣的名稱"
        self.log(f"[練功] {h['name']}：走 {' → '.join(h.get('approach', []))}，目標 {'、'.join(h['targets'])}{note}")
        self.hunter.start()

    def do_stop(self, arg):
        self.hunter.stop()
        self.walker.stop()
        self.explorer.stop()

    # --- 實地探索 ---
    def do_survey(self, arg):
        if self.busy("收集資料"):
            return
        skills = [s["en"] for s in self.guide.skills] if arg == "help" else []
        self.log("[探索] 開始收集資料" + ("（含 help）" if skills else ""))
        self.explorer.survey(with_help=bool(skills), skills=skills)

    def do_regen(self, arg):
        self.log(self.bot.regen.report())

    def do_map(self, arg):
        if arg == "stop":
            self.explorer.stop()
            return
        if self.busy("探索地圖"):
            return
        # #map [房間數]　或　#map <地點或路線> [房間數] [深度]
        words = arg.split()
        nums = []
        while words and words[-1].isdigit() and len(nums) < 2:
            nums.insert(0, int(words.pop()))
        place = " ".join(words)
        n = nums[0] if nums else (200 if not place else 80)
        depth = nums[1] if len(nums) > 1 else (40 if not place else 12)
        if not place:
            self.log(f"[探索] 從目前位置（或回城點）開始探索，最多 {n} 間房間；遇到戰鬥會逃跑回城")
            self.explorer.map(max_rooms=n, max_depth=depth)
            return
        from mudbot.guide import SPEEDWALK
        raw = all(SPEEDWALK.match(p) or p in self.guide.places for p in place.split())
        found = None if raw else self.guide.route_for(place)
        label, route = found if found else (place, [place])
        cmds = self.guide.expand(route)
        self.log(f"[探索] {label}：先走 {' → '.join(route)}（{len(cmds)} 個指令），再探索附近 {depth} 步內最多 {n} 間房間")
        self.explorer.map(max_rooms=n, max_depth=depth, route=cmds, label=label)

    def do_status(self, arg):
        self.log(self.hunter.status())
        if self.quests.quest:
            self.log(f"解謎：{self.quests.quest['name']} 第 {self.quests.index + 1}/{len(self.quests.steps)} 步")
        if self.explorer.running:
            self.log(self.explorer.state)
        if self.recorder.on:
            self.log(f"記錄中：已記 {len(self.recorder.cmds)} 個指令")

    # --- 攻略 ---
    def do_find(self, arg):
        if not arg:
            self.log("用法：#find <關鍵字>")
            return
        res = self.guide.search(arg)
        if not res:
            self.log(f"找不到「{arg}」")
            return
        self.log(f"「{arg}」的搜尋結果（{len(res)} 筆）：\n" + "\n".join(f"　[{k}] {n}　{s}" for k, n, s in res)
                 + "\n用 #area、#quest、#skill、#item 加名稱看詳細內容")

    def do_area(self, arg):
        a = self.guide.find_area(arg) if arg else None
        self.log(self.guide.area_text(a) if a else f"找不到區域「{arg}」，可以試試 #find {arg}")

    def do_skill(self, arg):
        s = self.guide.find_skill(arg) if arg else None
        self.log(self.guide.skill_text(s) if s else f"找不到技能「{arg}」，可以試試 #find {arg}")

    def do_spell(self, arg):
        self.do_skill(arg)

    def do_item(self, arg):
        it = self.guide.find_item(arg) if arg else None
        self.log(self.guide.item_text(it) if it else f"找不到裝備「{arg}」，可以試試 #find {arg}")

    def do_goto(self, arg):
        if not arg:
            self.log("用法：#goto <區域、解謎或路線>，例如 #goto 魔谷 或 #goto map3 s6e7n")
            return
        if self.busy("走路線"):
            return
        found = self.guide.route_for(arg)
        label, route = found if found else (arg, [arg])
        cmds = self.guide.expand(route)
        self.log(f"[路線] {label}：{' → '.join(route)}（{len(cmds)} 個指令）")
        self.walker.start(cmds, label)

    # --- 解謎 ---
    def do_quest(self, arg):
        if not arg:
            self.quests.show()
        elif arg == "list":
            self.log("解謎列表：" + "、".join(q["name"] for q in self.guide.quests))
        elif arg == "stop":
            self.quests.stop()
        else:
            q = self.guide.find_quest(arg)
            if q:
                self.quests.load(q)
            else:
                self.log(f"找不到解謎「{arg}」，輸入 #quest list 看全部")

    def do_next(self, arg):
        if not self.busy("執行解謎步驟"):
            self.quests.next(run_all=(arg == "all"))

    def do_learn(self, arg):
        words = arg.split()
        pay = bool(words) and words[-1] == "pay"
        name = " ".join(words[:-1] if pay else words)
        if not name:
            self.log("用法：#learn <技能>，例如 #learn infravision 或 #learn 夜視術")
            return
        if self.busy("學技能"):
            return
        self.learner.start(name, pay)

    def do_skip(self, arg):
        self.quests.skip(int(arg) if arg.isdigit() else 1)

    def do_step(self, arg):
        self.quests.goto_step(int(arg)) if arg.isdigit() else self.quests.show()

    # --- 其他 ---
    def do_record(self, arg):
        sub, _, name = arg.partition(" ")
        if sub == "save":
            if not name.strip():
                self.log("用法：#record save <名稱>")
            else:
                self.recorder.save(name.strip(), self.guide)
        elif sub == "stop":
            self.recorder.stop()
        else:
            self.recorder.start()

    def do_reload(self, arg):
        new = load_config(self.config_path)
        self.bot.apply_config(new)
        self.hunter.apply_config(new)
        self.guide.reload()
        self.log("設定與攻略資料已重新載入：" + self.guide.counts())

    def do_help(self, arg):
        self.log(HELP)


async def main(config_path: Path) -> None:
    if os.name == "nt":
        os.system("")  # 讓 Windows 主控台顯示 ANSI 顏色

    cfg = load_config(config_path)
    log = Logger(cfg.get("bot", {}).get("log_dir", "logs"))

    password = ""
    if cfg.get("login", {}).get("enabled"):
        password = os.environ.get("MUD_PASSWORD") or getpass.getpass("角色密碼：")

    srv = cfg["server"]
    raw_log = log.base.with_suffix(".raw.log") if cfg.get("bot", {}).get("raw_log", True) else None
    conn = MudConnection(srv["host"], int(srv["port"]), srv.get("encoding", "cp950"), raw_log)
    bot = Bot(cfg, password, conn, log.info, log.echo)
    guide = Guide(ROOT / cfg.get("bot", {}).get("data_dir", "data"))
    bot.regen.csv_path = guide.dir / "live" / "regen.csv"
    hunter = Hunter(bot, cfg)
    hunter.expand = guide.expand
    walker = Walker(bot)
    quests = QuestRunner(bot, guide, walker)
    recorder = Recorder(bot, guide.dir / "user_routes.toml")
    explorer = Explorer(bot, guide.dir / "live", cfg.get("hunt", {}).get("recall_command", "recall"))
    explorer.expand = guide.expand
    explorer._load_map()                        # 載入實地地圖，回城時優先沿地圖走回去
    hunter.navigator = explorer
    learner = Learner(bot, guide, explorer, guide.dir)
    quests.learner = learner
    commands = Commands(bot, hunter, guide, walker, quests, recorder, config_path, log.info, explorer)
    commands.learner = learner

    log.info(f"攻略資料：{guide.counts()}")
    log.info(f"紀錄檔：{log.base.with_suffix('.log')}" + (f"、原始封包 {raw_log}" if raw_log else ""))
    log.info(f"連線到 {srv['host']}:{srv['port']} ...")
    try:
        await conn.connect()
    except OSError as e:
        log.info(f"連線失敗：{e}")
        return
    log.info("已連線。輸入 #help 查看控制指令。")

    user_q: asyncio.Queue = asyncio.Queue()
    start_input_thread(asyncio.get_running_loop(), user_q)

    async def reader():
        while True:
            text = await conn.read()
            if text is None:
                log.info("伺服器已斷線。")
                return
            print(text, end="", flush=True)
            log.write(text)
            bot.feed(text)

    async def user_input():
        while True:
            line = (await user_q.get()).strip()
            log.write(f"\n[輸入] {line}\n")
            if line == "#quit":
                return
            if line.startswith("#"):
                commands.handle(line)
            else:
                recorder.feed(line)
                await bot.send(line)

    tasks = [
        asyncio.create_task(reader()),
        asyncio.create_task(user_input()),
        asyncio.create_task(bot.sender()),
    ]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    hunter.stop("程式結束") if hunter.running else None
    walker.stop()
    for t in tasks:
        t.cancel()
    await conn.close()
    log.info("程式結束。")


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "config.toml")
    try:
        asyncio.run(main(path))
    except KeyboardInterrupt:
        pass
