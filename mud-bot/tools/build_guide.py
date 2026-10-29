"""產生整理版攻略：docs/parts/*.md（敘述）＋ data/（區域、解謎、技能、裝備）→ docs/四度空間攻略.md

用法：python tools/build_guide.py [--docx]
  --docx  另外用 pandoc 轉出 docs/四度空間攻略.docx（需要安裝 pandoc）
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mudbot.guide import Guide  # noqa: E402

PARTS = ROOT / "docs" / "parts"
OUT = ROOT / "docs" / "四度空間攻略.md"
NO_DATA = ["聖鬥士海皇篇", "鴉片戰爭", "拂曉的亮星", "新世紀福音戰士", "太空飛行世界", "恐龍公園", "鞏恩城", "童話世界"]


def cell(v) -> str:
    return str(v if v is not None else "").replace("|", "／").replace("\n", " ")


def width(s: str) -> int:
    """顯示寬度：中文字算 2。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def table(headers, rows) -> str:
    """Markdown 表格。分隔線的長度依內容比例調整，轉成 Word 時欄寬才會合理。"""
    rows = [[cell(c) for c in r] for r in rows]
    widths = []
    for i, h in enumerate(headers):
        w = max([width(h)] + [width(r[i]) for r in rows if i < len(r)])
        widths.append(max(7, min(w, 28)))
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("-" * w for w in widths) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def code(cmds) -> str:
    return "`" + " ; ".join(cmds).replace("`", "'") + "`"


class Builder:
    def __init__(self):
        self.g = Guide(ROOT / "data")

    # ---------- 區域 ----------
    def gen_areas(self):
        g = self.g
        rows = []
        for a in g.areas:
            qs = [q["name"] for q in g.quests if q.get("area") == a["name"]]
            route = " → ".join(a.get("route", [])) or ""
            rows.append([a["name"], a.get("level", ""), a.get("author", ""), f"`{route}`" if route else "", "、".join(qs)])
        out = ["## 區域列表", table(["區域", "等級", "作者", "路線", "解謎"], rows), "", "## 區域說明"]
        for a in g.areas:
            if a.get("note") or a.get("aliases"):
                line = f"- **{a['name']}**"
                if a.get("aliases"):
                    line += f"（{'、'.join(a['aliases'])}）"
                if a.get("note"):
                    line += "：" + a["note"]
                out.append(line)
        out += ["", "## 練功設定（#farm）",
                "攻略裡有寫目標怪物和走法的練功區。巡邏路線攻略沒有寫，可以第一次去時用 `#record` 記錄。", "",
                table(["名稱", "區域", "等級", "走法", "目標"],
                      [[h["name"], h["area"], h.get("level", ""), "`" + " → ".join(h.get("approach", [])) + "`", "、".join(h["targets"])]
                       for h in g.hunts])]
        return "\n".join(out)

    def gen_rnote(self):
        return table(["區域", "房間"], [[a, "、".join(r)] for a, r in self.g.rnote.items()])

    # ---------- 解謎 ----------
    def gen_quests(self):
        g = self.g
        out = ["# 解謎攻略",
               "每個謎題依「路線、需要、獎勵、注意、步驟、提示」整理。步驟中標示**自己處理**的是打王、走迷宮、等時間這類需要判斷的部分；"
               "其他步驟的指令可以在練功程式裡用 `#quest 名稱` 和 `#next` 逐步送出。", "",
               "## 解謎索引", table(["解謎", "區域", "主要獎勵"],
                                   [[f"[{q['name']}](#{anchor(q['name'])})", q.get("area", ""), "、".join(q.get("rewards", [])[:2])]
                                    for q in g.quests])]
        for q in g.quests:
            out.append(self.quest_md(q))
        out += ["## 尚無攻略的區域", "原攻略列了以下區域但沒有內容：" + "、".join(NO_DATA) + "。"]
        return "\n\n".join(out)

    def quest_md(self, q):
        parts = [f"## {q['name']}"]
        if q.get("intro"):
            parts.append(f"*{q['intro']}*")
        meta = []
        if q.get("area"):
            meta.append(f"- **區域**：{q['area']}" + (f"（等級 {q['level']}）" if q.get("level") else ""))
        if q.get("route"):
            meta.append("- **路線**：" + code(q["route"]))
        if q.get("route_note"):
            meta.append(("- **路線說明**：" if q.get("route") else "- **路線**：") + q["route_note"])
        for label, key in (("需要", "needs"), ("獎勵", "rewards")):
            if q.get(key):
                meta.append(f"- **{label}**：" + "；".join(q[key]))
        if q.get("note"):
            meta.append("- **注意**：" + q["note"])
        if meta:
            parts.append("\n".join(meta))
        for t in q.get("tables", []):            # 表格放在步驟前面（步驟常會說「依上表」）
            block = [f"**{t['title']}**"]
            if t.get("note"):
                block.append(t["note"])
            block.append(table(t["headers"], t["rows"]))
            parts.append("\n\n".join(block))
        if q.get("steps"):
            lines = ["**步驟**", ""]
            for i, s in enumerate(q["steps"], 1):
                note = (s.get("note") or "").strip().replace("\n", " ")
                tag = "（自己處理）" if s.get("manual") else ""
                line = f"{i}. **{s['title']}**{tag}"
                if note:
                    line += "：" + note
                if s.get("do"):
                    line += "\n   指令：" + code(s["do"])
                lines.append(line)
            parts.append("\n".join(lines))
        for t in q.get("tips", []):
            parts.append(f"**{t['title']}**\n\n" + "\n".join(f"- {x}" for x in t["items"]))
        return "\n\n".join(parts)

    # ---------- 技能 ----------
    def gen_skill_tables(self):
        g = self.g
        out = []
        for kind, title in (("skill", "## 技能 (Skill)"), ("spell", "## 法術 (Spell)")):
            out.append(title)
            groups = {}
            for s in g.skills:
                if s["kind"] == kind:
                    groups.setdefault(s.get("group", "其他"), []).append(s)
            for grp, ss in groups.items():
                out.append(f"### {grp}")
                last = "內力" if kind == "skill" else "花費法力"
                key = "gain_power" if kind == "skill" else "cost_mana"
                rows = [[s.get("zh", ""), s["en"], s.get("memory", ""), s.get("delay", ""), s.get("cycle", ""),
                         s.get("gain_hp", ""), s.get("gain_mana", ""), s.get("gain_mv", ""), s.get(key, ""),
                         s.get("requires", "")] for s in ss]
                out.append(table(["名稱", "英文", "記憶量", "協調性", "週期", "HP", "MA", "MV", last, "前置需求"], rows))
        return "\n\n".join(out)

    def gen_exclusive(self):
        return "以下技能之間互相衝突，無法同時學習：\n\n" + "\n".join(f"- {e}" for e in self.g.exclusive)

    def gen_teachers(self):
        rows = []
        for s in self.g.skills:
            if s.get("teacher"):
                q = self.g.find_quest(s["quest"]) if s.get("quest") else None
                rows.append([f"{s.get('zh', '')} {s['en']}", s["teacher"], s.get("teacher_note", ""), q["name"] if q else ""])
        return table(["技能", "學習對象", "條件", "相關解謎"], rows)

    def gen_quest_skills(self):
        quest = ["scan", "bless", "remove curse", "protection", "sanctuary", "curse", "blindness", "faerie fire", "dispel magic",
                 "control weather", "fly", "cure light", "cure serious", "refresh", "cure poison", "detect poison",
                 "cure blindness", "heal", "know alignment", "detect hidden", "infravision", "detect magic", "detect invis",
                 "locate object", "identify", "remove nodrop", "invis"]
        attr = ["create water", "create spring", "create food", "continual light", "faerie fog", "lore", "magic missile",
                "rockblast", "ventriloquate"]

        def rows(names):
            out = []
            for n in names:
                s = self.g.find_skill(n)
                out.append([s.get("zh", "") if s else "", n, s.get("memory", "") if s else ""])
            return out
        return ("**解謎常用**\n\n" + table(["名稱", "英文", "記憶點數"], rows(quest))
                + "\n\n**記憶點數少、可以順便加屬性上限的小技能**\n\n" + table(["名稱", "英文", "記憶點數"], rows(attr)))

    def gen_skill_desc(self):
        out = []
        for kind, title in (("skill", "### 技能"), ("spell", "### 法術")):
            out.append(title)
            for s in sorted((s for s in self.g.skills if s["kind"] == kind), key=lambda s: s["en"]):
                if not (s.get("desc") or s.get("usage")):
                    continue
                line = f"- **{s.get('zh', '')} {s['en'].upper()}**"
                if s.get("usage"):
                    line += f"　`{s['usage']}`"
                if s.get("desc"):
                    line += "：" + s["desc"]
                out.append(line)
        return "\n".join(out)

    # ---------- 裝備 ----------
    def gen_prices(self):
        rows = [[it["name"], it.get("en", ""), it["price"]] for it in self.g.items if it.get("price")]
        return table(["物品", "關鍵字", "參考金額"], rows)

    def gen_baby_table(self):
        rows = []
        items = [it for it in self.g.items if it.get("type") == "baby"]
        items.sort(key=lambda it: int(it["level"]) if str(it.get("level", "")).isdigit() else 99)
        for it in items:
            rows.append([it.get("level", ""), it["name"], it.get("en", ""), it.get("slot", ""), it.get("stats", ""),
                         "、".join(it.get("sources", [])), "★" * it["difficulty"] if it.get("difficulty") else "",
                         "；".join(it.get("notes", []))])
        return ("合併原攻略的〈低等裝備參考〉與〈Baby EQ 一覽表〉。難度★越多越難拿。\n\n"
                + table(["LV", "名稱", "英文", "部位", "屬性", "所在區域", "難度", "備註"], rows))

    def gen_baby_items(self):
        return "各 Baby EQ 的等級、屬性與取得地點整理在〈裝備〉一章的「Baby EQ 一覽」。"

    def gen_clan(self):
        rows = [[it["name"], it.get("en", ""), "、".join(s.replace("幫派：", "") for s in it.get("sources", []))]
                for it in self.g.items if it.get("type") == "clan"]
        extra = ("其他已知幫派：明教、大清帝國軍、吞食萬物的黑洞（love seed）。"
                 "另外收集到的 Clan EQ 還有：喵喵鈴鐺 (cat ring)、卡羚的手套 (gloves)、穿雲龍紋脛甲 (a leggings)、"
                 "鎖喉龍麟 (dragon scale)、夢幻音樂卡 (dream music card)、朋友會標記 (fellowship medallion)、邱淑貞 (Chi Woman)。")
        return table(["信物", "關鍵字", "幫派"], rows) + "\n\n" + extra

    # ---------- 組合 ----------
    def build(self) -> str:
        chapters = []
        for p in sorted(PARTS.glob("*.md")):
            text = p.read_text(encoding="utf-8")
            text = re.sub(r"<!-- gen:(\w+) -->", lambda m: getattr(self, "gen_" + m.group(1))(), text)
            chapters.append(text.strip())
            if p.name.startswith("07_"):
                chapters.append(self.gen_quests())
        body = "\n\n".join(chapters)
        toc = ["## 目錄", ""]
        for m in re.finditer(r"^# (.+)$", body, re.M):
            if m.start() == 0:
                continue
            toc.append(f"- [{m.group(1)}](#{anchor(m.group(1))})")
        first, rest = body.split("\n", 1)
        return first + "\n\n" + "\n".join(toc) + "\n\n" + rest.strip() + "\n"


def anchor(title: str) -> str:
    """GitHub 風格的標題錨點。"""
    a = title.strip().lower()
    a = re.sub(r"[^\w一-鿿\- ]", "", a)
    return a.replace(" ", "-")


def main():
    text = Builder().build()
    text = re.sub(r"\n{3,}", "\n\n", text)
    OUT.write_text(text, encoding="utf-8")
    print(f"已產生 {OUT.relative_to(ROOT)}（{len(text):,} 字元）")
    if "--docx" in sys.argv:
        if not shutil.which("pandoc"):
            print("找不到 pandoc，略過 docx")
            return
        docx = OUT.with_suffix(".docx")
        # Word 版：用 Word 自己的目錄，去掉 Markdown 目錄、文件標題和頁內連結
        plain = text.split("\n", 1)[1]                       # 標題改放在文件屬性
        plain = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", plain)   # 頁內連結在 Word 裡沒用
        tmp = OUT.with_name("_docx_source.md")
        tmp.write_text(plain, encoding="utf-8")
        try:
            subprocess.run(["pandoc", str(tmp), "-f", "markdown-subscript-superscript-citations-tex_math_dollars-smart", "-o", str(docx), "--columns=40",
                            "-M", "title=四度空間 7777 攻略（整理版）"], check=True)
        finally:
            tmp.unlink(missing_ok=True)
        print(f"已產生 {docx.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
