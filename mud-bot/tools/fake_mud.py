"""模擬 MERC 2.2 伺服器，用來在沒有連上四度空間時測試程式。

用法：
  1. 開一個視窗執行：python tools/fake_mud.py
  2. 另一個視窗執行：python main.py   （config.toml 的 host 用 127.0.0.1、port 7777）
  3. 連上後輸入 #auto

地圖（對應 config.toml 的預設路線 n, n, e）：
  神殿（回城點）─北→ 廣場 ─北→ 森林（老鼠 rat）─東→ 洞穴（主動攻擊的哥布林 goblin）
神殿往其他方向（w、s、e、u、d）會進入「荒野」：每個方向都走得通，用來測試 #goto 和 #quest 的長路線。
節奏比真正的 MUD 快（每秒一回合），方便測試。
"""

import asyncio
import random

ENC = "cp950"
ROUND = 1.0      # 戰鬥回合秒數
TICK = 2.0       # 回復秒數

ROOMS = {
    0: ("Temple of Mota", {"n": 1}),
    1: ("Market Square", {"s": 0, "n": 2}),
    2: ("Dark Forest", {"s": 1, "e": 3}),
    3: ("Goblin Cave", {"w": 2}),
    100: ("荒野", {d: 100 for d in "nsewud"}),
}
ROOMS[0][1].update({d: 100 for d in "wseud"})
SPAWNS = {  # 房間: (關鍵字, 名稱, hp, 傷害範圍, 經驗, 主動攻擊, 重生秒數)
    2: ("rat", "the rat", 25, (1, 4), 40, False, 6),
    3: ("goblin", "the goblin", 60, (5, 14), 150, True, 10),
}
DIRS = {"north": "n", "south": "s", "east": "e", "west": "w", "up": "u", "down": "d"}


class Mob:
    def __init__(self, room):
        self.kw, self.name, self.maxhp, self.dmg, self.exp, self.aggro, self.respawn = SPAWNS[room]
        self.hp = self.maxhp


class Player:
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer
        self.hp, self.maxhp = 100, 100
        self.mana, self.maxmana = 50, 50
        self.mv, self.maxmv = 400, 400
        self.exp = 0
        self.room = 0
        self.pos = "standing"      # standing / resting / sleeping
        self.fighting: Mob | None = None
        self.mobs = {room: Mob(room) for room in SPAWNS}
        self.alive = True

    def out(self, text=""):
        if text:
            self.w.write((text + "\r\n").encode(ENC))

    def prompt(self):
        self.w.write(f"\r\n<{self.hp}/{self.maxhp}hp {self.mana}/{self.maxmana}m {self.mv}/{self.maxmv}mv> ".encode(ENC))

    def mob_here(self):
        return self.mobs.get(self.room)

    def look(self):
        name, exits = ROOMS[self.room]
        self.out(name)
        self.out(f"[Exits: {' '.join(exits)}]")
        m = self.mob_here()
        if m:
            self.out(f"{m.name.capitalize()} is here.")
            if m.aggro and not self.fighting:
                self.out(f"{m.name.capitalize()} screams and attacks you!")
                self.fighting = m

    def kill_mob(self, m):
        self.out(f"{m.name.capitalize()} is DEAD!!")
        self.out(f"You receive {m.exp} experience points.")
        self.exp += m.exp
        self.fighting = None
        room = next(r for r, x in self.mobs.items() if x is m)
        self.mobs[room] = None
        asyncio.get_running_loop().call_later(m.respawn, self.respawn, room)

    def respawn(self, room):
        if self.mobs.get(room) is None:
            self.mobs[room] = Mob(room)

    async def combat_loop(self):
        while self.alive:
            await asyncio.sleep(ROUND)
            m = self.fighting
            if not m:
                continue
            dmg = random.randint(8, 15)
            m.hp -= dmg
            self.out(f"Your slash {'wounds' if dmg < 12 else 'mauls'} {m.name}.")
            if m.hp <= 0:
                self.kill_mob(m)
            else:
                hit = random.randint(*m.dmg)
                if random.random() < 0.1:
                    hit *= 2
                self.hp -= hit
                if self.pos == "sleeping":
                    self.pos = "standing"
                    self.out("You wake up!")
                self.out(f"{m.name.capitalize()}'s claw {'scratches' if hit < 6 else 'wounds'} you.")
                if self.hp <= 0:
                    self.out("You have been KILLED!!")
                    self.alive = False
            self.prompt()
            await self.w.drain()

    async def regen_loop(self):
        while self.alive:
            await asyncio.sleep(TICK)
            if self.fighting:
                continue
            gain = {"sleeping": 12, "resting": 6}.get(self.pos, 1)
            self.hp = min(self.maxhp, self.hp + gain)
            self.mv = min(self.maxmv, self.mv + gain)
            self.mana = min(self.maxmana, self.mana + gain)

    def command(self, line):
        parts = line.split(maxsplit=1)
        if not parts:
            return
        cmd, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
        cmd = DIRS.get(cmd, cmd)
        asleep = self.pos == "sleeping"

        if cmd in ("n", "s", "e", "w", "u", "d"):
            if asleep:
                return self.out("In your dreams, or what?")
            if self.fighting:
                return self.out("No way!  You are still fighting!")
            exits = ROOMS[self.room][1]
            if cmd not in exits:
                return self.out("Alas, you cannot go that way.")
            if self.mv < 3:
                return self.out("You are too exhausted.")
            self.mv -= 3
            self.room = exits[cmd]
            self.pos = "standing"
            self.look()
        elif cmd == "kill":
            if asleep:
                return self.out("In your dreams, or what?")
            if self.fighting:
                return self.out("You do the best you can!")
            m = self.mob_here()
            if not m or m.kw != arg.strip().lower():
                return self.out("They aren't here.")
            self.fighting = m
            self.out(f"You attack {m.name}!")
            self.out(f"Your slash hits {m.name}.")
        elif cmd == "flee":
            if not self.fighting:
                return self.out("You aren't fighting anyone.")
            if random.random() < 0.3:
                return self.out("PANIC! You couldn't escape!")
            self.fighting = None
            self.room = random.choice(list(ROOMS[self.room][1].values()))
            self.exp -= 10
            self.out("You flee from combat!  You lose 10 exps.")
            self.look()
        elif cmd == "recall":
            if asleep:
                return self.out("In your dreams, or what?")
            if self.fighting and random.random() < 0.5:
                return self.out("You failed!")
            self.fighting = None
            self.room = 0
            self.out("You pray for transportation!")
            self.look()
        elif cmd in ("sleep", "rest"):
            if self.fighting:
                return self.out("No way!  You are still fighting!")
            self.pos = "sleeping" if cmd == "sleep" else "resting"
            self.out("You go to sleep." if cmd == "sleep" else "You rest.")
        elif cmd in ("wake", "stand"):
            self.pos = "standing"
            self.out("You wake and stand up." if asleep else "You stand up.")
        elif cmd == "score":
            self.out(f"You have {self.hp}/{self.maxhp} hit, {self.mana}/{self.maxmana} mana, "
                     f"{self.mv}/{self.maxmv} movement, 3 practices.  Exp {self.exp}.")
        elif cmd == "look":
            self.look()
        elif cmd in ("get", "sacrifice", "sac"):
            self.out("You get some coins from the corpse." if cmd == "get" else "Mota gives you one gold coin for your sacrifice.")
        elif cmd == "quit":
            self.out("Alas, all good things must come to an end.")
            self.alive = False
        else:
            self.out("Huh?")


async def handle(reader, writer):
    async def ask(text):
        writer.write(text.encode(ENC))
        await writer.drain()
        return (await reader.readline()).decode(ENC, "replace").strip()

    writer.write("Welcome to Fake Merc 2.2!\r\n".encode(ENC))
    name = await ask("By what name do you wish to be known? ")
    await ask("Password: ")
    await ask("\r\nWelcome to Merc Diku Mud.\r\n[Hit RETURN to continue]")
    p = Player(reader, writer)
    p.out(f"Welcome back, {name}.")
    p.look()
    p.prompt()
    await writer.drain()
    tasks = [asyncio.create_task(p.combat_loop()), asyncio.create_task(p.regen_loop())]
    try:
        while p.alive:
            raw = await reader.readline()
            if not raw:
                break
            p.command(raw.decode(ENC, "replace").strip())
            p.prompt()
            await writer.drain()
    finally:
        for t in tasks:
            t.cancel()
        writer.close()


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 7777)
    print("模擬 MERC 伺服器已在 127.0.0.1:7777 啟動，按 Ctrl+C 結束")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
