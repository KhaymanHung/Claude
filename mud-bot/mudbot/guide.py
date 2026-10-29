"""攻略資料：載入 data/ 底下的區域、解謎、技能、裝備，提供查詢與路線展開。"""

import re
import tomllib
from pathlib import Path

DIRS = set("nsewud")
SPEEDWALK = re.compile(r"^/?(\d*[nsewud])+$|^/$", re.I)
FULL_DIRS = {"north": "n", "south": "s", "east": "e", "west": "w", "up": "u", "down": "d"}


def is_direction(cmd: str) -> bool:
    c = cmd.strip().lower()
    return c in DIRS or c in FULL_DIRS


def expand_speedwalk(token: str) -> list[str]:
    """把 /3w2s 這種寫法展開成 recall、w、w、w、s、s。"""
    out = []
    t = token.strip().lower()
    if t.startswith("/"):
        out.append("recall")
        t = t[1:]
    for n, d in re.findall(r"(\d*)([nsewud])", t):
        out.extend([d] * int(n or 1))
    return out


def norm(s: str) -> str:
    return re.sub(r"[\s·・.\-_'()（）{}]", "", s).lower()


class Guide:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.reload()

    # ---------- 載入 ----------
    def reload(self) -> None:
        d = self.dir
        areas = self._load(d / "areas.toml")
        self.places: dict[str, list[str]] = areas.get("places", {})
        self.rnote: dict[str, list[str]] = areas.get("rnote", {})
        self.areas: list[dict] = areas.get("area", [])
        self.hunts: list[dict] = areas.get("hunt", [])
        self.quests: list[dict] = []
        for f in sorted((d / "quests").glob("*.toml")):
            self.quests.extend(self._load(f).get("quest", []))
        sk = self._load(d / "skills.toml")
        self.skills: list[dict] = sk.get("skill", [])
        self.exclusive: list[str] = sk.get("exclusive", [])
        self.items: list[dict] = self._load(d / "items.toml").get("item", [])
        user = self._load(d / "user_routes.toml")
        self.user_routes: dict[str, list[str]] = {r["name"]: r["commands"] for r in user.get("route", [])}

    @staticmethod
    def _load(path: Path) -> dict:
        if not path.exists():
            return {}
        with path.open("rb") as f:
            return tomllib.load(f)

    def counts(self) -> str:
        return (f"區域 {len(self.areas)}、解謎 {len(self.quests)}、技能法術 {len(self.skills)}、"
                f"裝備 {len(self.items)}、練功設定 {len(self.hunts)}、自訂路線 {len(self.user_routes)}")

    # ---------- 路線 ----------
    def expand(self, route, depth: int = 0) -> list[str]:
        """把路線（清單或字串）展開成逐一送出的指令。"""
        if depth > 5:
            raise ValueError("路線捷徑互相引用太多層")
        if isinstance(route, str):
            route = [route]
        out: list[str] = []
        for entry in route:
            for part in re.split(r"\s*(?:→|->|;)\s*", entry.strip()):
                if not part:
                    continue
                if part in self.places:
                    out.extend(self.expand(self.places[part], depth + 1))
                elif part in self.user_routes:
                    out.extend(self.expand(self.user_routes[part], depth + 1))
                elif SPEEDWALK.match(part):
                    out.extend(expand_speedwalk(part))
                elif all(SPEEDWALK.match(p) or p in self.places for p in part.split()) and " " in part:
                    for p in part.split():
                        out.extend(self.expand(p, depth + 1))
                else:
                    out.append(part)
        return out

    def route_for(self, name: str) -> tuple[str, list[str]] | None:
        """名稱可以是區域、解謎、練功設定或自訂路線；找不到就當作直接輸入的路線。"""
        if name in self.user_routes:
            return f"自訂路線 {name}", self.user_routes[name]
        a = self.find_area(name)
        if a and a.get("route"):
            return f"區域 {a['name']}", a["route"]
        q = self.find_quest(name)
        if q and q.get("route"):
            return f"解謎 {q['name']}", q["route"]
        h = self.find_hunt(name)
        if h and h.get("approach"):
            return f"練功 {h['name']}", h["approach"]
        return None

    # ---------- 查詢 ----------
    @staticmethod
    def _names(x: dict, *keys) -> list[str]:
        out = []
        for k in keys:
            v = x.get(k)
            if isinstance(v, list):
                out.extend(v)
            elif v:
                out.append(v)
        return out

    def _find(self, coll, name, keys):
        n = norm(name)
        for x in coll:                                   # 完全相同優先
            if any(norm(v) == n for v in self._names(x, *keys)):
                return x
        for x in coll:                                   # 再找包含
            if any(n and n in norm(v) for v in self._names(x, *keys)):
                return x
        return None

    def find_area(self, name):
        return self._find(self.areas, name, ("name", "aliases"))

    def find_quest(self, name):
        return self._find(self.quests, name, ("name", "id", "aliases"))

    def find_hunt(self, name):
        h = self._find(self.hunts, name, ("name",))
        if h:
            return h
        a = self.find_area(name)
        if a:
            return next((x for x in self.hunts if x["area"] == a["name"]), None)
        return None

    def find_skill(self, name):
        return self._find(self.skills, name, ("en", "zh"))

    def find_item(self, name):
        return self._find(self.items, name, ("name", "en"))

    def search(self, kw: str, limit: int = 30) -> list[tuple[str, str, str]]:
        """全文搜尋，回傳 (類別, 名稱, 摘要)。"""
        n = norm(kw)
        if not n:
            return []
        res = []

        def hit(*texts):
            return any(n in norm(t) for t in texts if isinstance(t, str))

        for a in self.areas:
            if hit(a["name"], *a.get("aliases", []), a.get("note", "")):
                res.append(("區域", a["name"], f"等級 {a.get('level', '?')}"))
        for q in self.quests:
            blob = [q["name"], q.get("id", ""), *q.get("aliases", []), *q.get("rewards", []), *q.get("needs", []),
                    q.get("note", ""), q.get("intro", "")]
            steps = [s.get("note", "") + " ".join(s.get("do", [])) for s in q.get("steps", [])]
            tables = [" ".join(" ".join(r) for r in t.get("rows", [])) for t in q.get("tables", [])]
            if hit(*blob):
                res.append(("解謎", q["name"], "獎勵：" + "、".join(q.get("rewards", [])[:3]) if q.get("rewards") else q.get("area", "")))
            elif hit(*steps, *tables):
                res.append(("解謎", q["name"], "步驟或表格中提到"))
        for s in self.skills:
            if hit(s["en"], s.get("zh", ""), s.get("teacher", "")):
                kind = "技能" if s["kind"] == "skill" else "法術"
                res.append((kind, f"{s.get('zh', '')} {s['en']}", f"記憶量 {s.get('memory', '?')}" + (f"，向 {s['teacher']} 學" if s.get("teacher") else "")))
        for it in self.items:
            if hit(it["name"], it.get("en", ""), it.get("stats", ""), *it.get("sources", [])):
                src = "、".join(it.get("sources", [])[:2])
                res.append(("裝備", it["name"] + (f" ({it['en']})" if it.get("en") else ""), (it.get("stats") or "") + (f"｜{src}" if src else "")))
        return res[:limit]

    # ---------- 技能樹 ----------
    def prereq_chain(self, skill: dict, seen=None) -> list[dict]:
        """依前置需求往回找，回傳要先學的技能（由淺到深）。"""
        seen = seen if seen is not None else set()
        out = []
        req = skill.get("requires", "")
        for part in re.split(r"\s*\+\s*|、|，", re.sub(r"（.*?）|\(.*?\)", "", req)):
            part = part.strip()
            if not part:
                continue
            s = next((x for x in self.skills if x["en"] == part.lower()), None)
            if s and s["en"] not in seen:
                seen.add(s["en"])
                out.extend(self.prereq_chain(s, seen))
                out.append(s)
        return out

    def exclusive_of(self, skill: dict) -> list[str]:
        en = skill["en"]
        return [e for e in self.exclusive if re.search(rf"\b{re.escape(en)}\b", e, re.I)]

    # ---------- 顯示 ----------
    def area_text(self, a: dict) -> str:
        lines = [f"【區域】{a['name']}　等級 {a.get('level', '?')}" + (f"　作者 {a['author']}" if a.get("author") else "")]
        if a.get("aliases"):
            lines.append("　別名：" + "、".join(a["aliases"]))
        if a.get("route"):
            lines.append("　路線：" + " → ".join(a["route"]) + "（#goto " + a["name"] + "）")
        if a.get("note"):
            lines.append("　" + a["note"])
        qs = [q["name"] for q in self.quests if q.get("area") == a["name"]]
        if qs:
            lines.append("　解謎：" + "、".join(qs))
        hs = [h["name"] for h in self.hunts if h["area"] == a["name"]]
        if hs:
            lines.append("　練功：" + "、".join(f"#farm {h}" for h in hs))
        rn = self.rnote.get(a["name"])
        if rn:
            lines.append("　rnote 房間：" + "、".join(rn))
        return "\n".join(lines)

    def skill_text(self, s: dict) -> str:
        kind = "技能" if s["kind"] == "skill" else "法術"
        lines = [f"【{kind}】{s.get('zh', '')} {s['en']}" + (f"（{s['group']}）" if s.get("group") else "")]
        nums = []
        for k, label in (("memory", "記憶量"), ("delay", "協調性"), ("cycle", "週期"), ("cost_mana", "花費法力")):
            if k in s:
                nums.append(f"{label} {s[k]}")
        gains = [f"{label}+{s[k]}" for k, label in (("gain_hp", "HP"), ("gain_mana", "MA"), ("gain_mv", "MV"), ("gain_power", "內力"))
                 if s.get(k) not in (None, 0, "0", "")]
        if nums:
            lines.append("　" + "　".join(nums))
        if gains:
            lines.append("　練滿增加：" + " ".join(gains))
        if s.get("usage"):
            lines.append("　用法：" + s["usage"])
        if s.get("requires"):
            lines.append("　前置：" + s["requires"])
        chain = self.prereq_chain(s)
        if chain:
            total = sum(x.get("memory", 0) for x in chain if isinstance(x.get("memory"), int))
            mine = s.get("memory") if isinstance(s.get("memory"), int) else 0
            lines.append("　學習順序：" + " → ".join(f"{x.get('zh', '')}({x.get('memory', '?')})" for x in chain)
                         + f" → {s.get('zh', '')}　共約 {total + mine} 點")
        if s.get("teacher"):
            lines.append("　學習對象：" + s["teacher"] + (f"（{s['teacher_note']}）" if s.get("teacher_note") else ""))
        if s.get("quest"):
            q = self.find_quest(s["quest"])
            if q:
                lines.append(f"　相關解謎：{q['name']}（#quest {q['name']}）")
        ex = self.exclusive_of(s)
        if ex:
            lines.append("　互斥：" + "；".join(ex))
        if s.get("desc"):
            lines.append("　" + s["desc"])
        return "\n".join(lines)

    def item_text(self, it: dict) -> str:
        lines = [f"【裝備】{it['name']}" + (f"（關鍵字 {it['en']}）" if it.get("en") else "")]
        meta = []
        for k, label in (("slot", "部位"), ("level", "等級"), ("stats", "屬性"), ("price", "參考價"), ("difficulty", "難度")):
            if it.get(k) not in (None, ""):
                v = "★" * it[k] if k == "difficulty" else it[k]
                meta.append(f"{label} {v}")
        if meta:
            lines.append("　" + "　".join(meta))
        if it.get("sources"):
            lines.append("　取得：" + "、".join(it["sources"]))
            for src in it["sources"]:
                q = next((q for q in self.quests if q["name"] in src or q.get("area", "") in src and q.get("area")), None)
                if q:
                    lines.append(f"　相關解謎：{q['name']}（#quest {q['name']}）")
                    break
        if it.get("notes"):
            lines.append("　備註：" + "；".join(it["notes"]))
        if it.get("builds"):
            lines.append("　出現在配裝：" + "、".join(it["builds"]))
        return "\n".join(lines)

    def quest_overview(self, q: dict) -> str:
        lines = [f"【解謎】{q['name']}" + (f"（{q['area']}）" if q.get("area") else "") + (f"　等級 {q['level']}" if q.get("level") else "")]
        if q.get("intro"):
            lines.append("　" + q["intro"])
        if q.get("route"):
            lines.append("　路線：" + " → ".join(q["route"]))
        if q.get("route_note"):
            lines.append("　" + q["route_note"])
        for label, key in (("需要", "needs"), ("獎勵", "rewards")):
            if q.get(key):
                lines.append(f"　{label}：" + "；".join(q[key]))
        if q.get("note"):
            lines.append("　注意：" + q["note"])
        for t in q.get("tables", []):
            lines.append(f"　［表］{t['title']}")
            if t.get("note"):
                lines.append("　　" + t["note"])
            lines.append("　　" + "｜".join(t["headers"]))
            for r in t["rows"]:
                lines.append("　　" + "｜".join(r))
        for t in q.get("tips", []):
            lines.append(f"　［提示］{t['title']}")
            for x in t["items"]:
                lines.append("　　- " + x)
        return "\n".join(lines)
