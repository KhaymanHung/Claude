"""自然恢復統計：從狀態列的數值變化推算恢復間隔（tick）和每次恢復量。

判斷方式：生命、法力、移動力、內力任何一項增加，而且最近 5 秒沒有戰鬥、
也沒有剛下過吃喝或施法之類的指令，就記為一次自然恢復。
間隔＝相鄰兩次恢復的時間差；誤差最多是狀態列更新的間隔（休息時每 2 秒看一次）。
"""

import csv
import datetime as dt
import statistics
import time
from pathlib import Path

KEYS = ("hp", "mana", "mv", "power")
LABEL = {"hp": "生命", "mana": "法力", "mv": "移動力", "power": "內力"}
POS_LABEL = {"sleeping": "睡覺", "resting": "休息", "standing": "站著"}
# 這些指令可能讓數值上升，不算自然恢復
NOT_REGEN = ("eat", "drink", "quaff", "cast", "c ", "recite", "use", "zap", "brandish", "full", "heal", "refresh")


class RegenTracker:
    def __init__(self, csv_path: Path | None = None):
        self.last: dict[str, int] = {}
        self.events: list[dict] = []          # {t, pos, gains, interval}
        self.position = "standing"
        self.hungry = False                    # 由 Bot 依遊戲訊息設定
        self.thirsty = False
        self.last_event: float | None = None
        self.last_self_cmd = 0.0               # 最後一次送出可能補血的指令
        self.csv_path = csv_path

    def on_command(self, cmd: str) -> None:
        c = cmd.strip().lower()
        if c in ("sleep", "sl"):
            self.position = "sleeping"
        elif c in ("rest", "re"):
            self.position = "resting"
        elif c in ("wake", "stand", "wa", "st"):
            self.position = "standing"
        if c.startswith(NOT_REGEN):
            self.last_self_cmd = time.monotonic()

    def on_stats(self, values: dict, last_combat: float) -> None:
        now = time.monotonic()
        gains = {}
        for k in KEYS:
            if k not in values:
                continue
            old = self.last.get(k)
            if old is not None and values[k] > old:
                gains[k] = values[k] - old
            self.last[k] = values[k]
        if not gains:
            return
        if now - last_combat < 5 or now - self.last_self_cmd < 5:
            self.last_event = None                 # 被戰鬥或補品打斷，重新起算
            return
        interval = now - self.last_event if self.last_event else None
        self.last_event = now
        ev = {"t": now, "pos": self.position, "gains": gains, "interval": interval,
              "need": ("飢餓" if self.hungry else "") + ("口渴" if self.thirsty else "")}
        self.events.append(ev)
        self._write(ev)

    def _write(self, ev: dict) -> None:
        if not self.csv_path:
            return
        new = not self.csv_path.exists()
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["時間", "狀態", "飢渴", "間隔秒", "生命", "法力", "移動力", "內力"])
            w.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), POS_LABEL.get(ev["pos"], ev["pos"]), ev["need"],
                        f"{ev['interval']:.1f}" if ev["interval"] else ""] + [ev["gains"].get(k, "") for k in KEYS])

    def report(self) -> str:
        if not self.events:
            return "還沒有觀察到自然恢復。休息或睡覺一陣子後再看（狀態列要開著）。"
        lines = ["自然恢復統計（間隔誤差約 2 秒；第一次恢復沒有間隔可算）："]
        intervals = [e["interval"] for e in self.events if e["interval"]]
        if intervals:
            lines.append(f"　全部：{len(intervals)} 筆間隔，中位數 {statistics.median(intervals):.1f} 秒，"
                         f"最短 {min(intervals):.1f}、最長 {max(intervals):.1f}")
        groups = []
        for pos in ("sleeping", "resting", "standing"):
            for need in sorted({e.get("need", "") for e in self.events if e["pos"] == pos}):
                groups.append((pos, need))
        for pos, need in groups:
            evs = [e for e in self.events if e["pos"] == pos and e.get("need", "") == need]
            if not evs:
                continue
            iv = [e["interval"] for e in evs if e["interval"]]
            part = f"　{POS_LABEL[pos]}{'（' + need + '）' if need else ''}：{len(evs)} 次"
            if iv:
                part += f"，間隔中位數 {statistics.median(iv):.1f} 秒"
            gains = []
            for k in KEYS:
                g = [e["gains"][k] for e in evs if k in e["gains"]]
                if g:
                    gains.append(f"{LABEL[k]} +{statistics.mean(g):.0f}")
            if gains:
                part += "，平均每次 " + "、".join(gains)
            lines.append(part)
        return "\n".join(lines)
