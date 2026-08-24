"""
Meropide 数据与现有数据对比验证脚本
====================================
验证内容：
  1. 抽查 3 个角色（神里绫华/胡桃/纳西妲）：Lv90 面板 + 天赋倍率 vs AnimeGameData
  2. 伤害公式常数对比：formulas.json 提取的权威数值 vs src/constants.py
  3. 圣遗物套装效果文本抽查（炽烈的炎之魔女）

运行：python compare_meropide.py
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MP = os.path.join(BASE, "data", "meropide")
DATA = os.path.join(BASE, "data")


def load(fn, where=DATA):
    with open(os.path.join(where, fn), encoding="utf-8") as f:
        return json.load(f)


def check_characters(chars_mp):
    print("=" * 60)
    print("1) 角色抽查（Lv90 面板 + 天赋倍率）")
    chars_local = load("characters.json")
    skills = load("skills.json")
    mp_by_name = {c["name"]: c for c in chars_mp}
    depots = {d["depot_id"]: d for d in skills["skill_depots"]}
    groups = {g["group_id"]: g for g in skills["proud_skill_groups"]}

    def local_params(char_local):
        vals = set()
        depot = depots.get(char_local.get("skill_depot_id"), {})
        for sk in depot.get("skills", []):
            g = groups.get(sk.get("proud_skill_group_id"))
            if g:
                for lv in g["levels"]:
                    for p in lv.get("param_list", []):
                        try:
                            vals.add(round(float(p), 4))
                        except (TypeError, ValueError):
                            pass
        return vals

    ok_chars = 0
    for name in ["神里绫华", "胡桃", "纳西妲"]:
        loc = next((c for c in chars_local if c.get("name_cn") == name), None)
        mp = mp_by_name.get(name)
        if not loc or not mp:
            print(f"  [SKIP] {name}: 本地={bool(loc)} meropide={bool(mp)}")
            continue
        s90 = mp["stats_by_level"].get("90", {})
        l90 = loc.get("stats_90", {})
        panel_ok = all(abs(s90.get(k, 0) - l90.get(k, 0)) < 1 for k in ("hp", "atk", "def"))

        pool = local_params(loc)
        hits, miss = [], []
        # 本地 skills.json 参数可能以不同刻度存储（原值/百分号值/小数），自动匹配
        scales = [100.0, 1.0, 0.01]
        for t in mp["talents"]:
            if t["skill_type"] not in ("元素战技", "元素爆发"):
                continue
            for row in t["rows"]:
                m = re.match(r"^(\d+(?:\.\d+)?)%$", row["value_text"].strip())
                if m:
                    pct_val = float(m.group(1))
                    hit = any(
                        any(abs(pct_val * s - x) < 0.05 for x in pool)
                        for s in scales)
                    (hits if hit else miss).append(f"{t['skill_name']}/{row['label']}={pct_val}%")

        print(f"  {name}: Lv90面板 {'一致' if panel_ok else '不一致!'} "
              f"(mp {s90.get('hp')}/{s90.get('atk')}/{s90.get('def')} | "
              f"local {l90.get('hp')}/{l90.get('atk')}/{l90.get('def')})")
        print(f"    天赋倍率命中 {len(hits)} / 未命中 {len(miss)}"
              + (f"；未命中: {miss[:4]}" if miss else ""))
        ok_chars += panel_ok
    return ok_chars


def check_formulas(forms):
    print("=" * 60)
    print("2) 伤害公式常数 vs src/constants.py")
    sys.path.insert(0, BASE)
    from src import constants as K
    formula_doc = next((f for f in forms if f["title"] == "伤害公式"), None)
    issues = []
    if not formula_doc:
        print("  [MISS] 未找到伤害公式文档")
        return issues

    tables = formula_doc["tables"]

    def find_table(*kws):
        for t in tables:
            flat = " ".join(c for row in t for c in row)
            if all(k in flat for k in kws):
                return t
        return None

    def table_map(t):
        return {row[0]: row[1] for row in t[1:] if len(row) >= 2} if t else {}

    # 2.1 反应基础值 Lv90 vs LEVEL_COEFFICIENT
    rbv = float(table_map(find_table("反应基础值")).get("90", 0))
    ok = abs(rbv - K.LEVEL_COEFFICIENT) < 0.01
    print(f"  反应基础值(90): meropide={rbv} vs LEVEL_COEFFICIENT={K.LEVEL_COEFFICIENT}"
          f" -> {'一致' if ok else '不一致!'}")
    if not ok:
        issues.append(f"LEVEL_COEFFICIENT={K.LEVEL_COEFFICIENT} 应为 {rbv}")

    # 2.2 增幅/融化方向校验（meropide 表键可能为合并格式："水打火 / 火打冰"）
    amp_raw = find_table("增幅基础系数")
    amp_pairs = {}
    if amp_raw:
        for row in amp_raw[1:]:
            if len(row) >= 2:
                try:
                    val = float(row[1])
                except ValueError:
                    continue
                for name in re.split(r"\s*/\s*", row[0]):
                    amp_pairs[name.strip()] = val
    print(f"  meropide 增幅基础系数表: {amp_pairs}")
    CN = {"水": "Hydro", "火": "Pyro", "冰": "Cryo"}
    truth = {"水打火": 2.0, "火打冰": 2.0, "火打水": 1.5, "冰打火": 1.5}
    for k, v in truth.items():
        got_mp = amp_pairs.get(k)
        a, b = k[0], k[2]  # 形如 "水打火"：a=攻击方, b=被击方
        got_ours = K.AMPLIFY_COEFF.get((CN[a], CN[b]))
        ok = (got_mp == v) and (got_ours == v)
        print(f"  {a}打{b}: 权威={v} 现有代码={got_ours} -> {'一致' if ok else '不一致!'}")
        if got_ours != v:
            issues.append(f"AMPLIFY_COEFF ({CN[a]},{CN[b]})={got_ours} 应为 {v}")

    # 2.3 剧变/激化/月曜基础系数（记录权威值）
    for label, kw in [("剧变", "剧变基础系数"), ("激化", "激化基础系数"),
                      ("月曜", "月曜基础系数")]:
        tm = table_map(find_table(kw))
        print(f"  meropide {label}基础系数: {tm}")

    lunar_direct_truth = {"月感电": ("lunar_charged", 3.0),
                          "月结晶": ("lunar_crystallize", 1.6),
                          "月绽放": ("lunar_bloom", 1.0)}
    lm = table_map(find_table("月曜基础系数"))
    for k, (key, v) in lunar_direct_truth.items():
        cur = K.LUNAR_REACTION_COEFF.get(key, {}).get("direct")
        mpv = float(lm.get(k, 0))
        if cur != v or abs(mpv - v) > 1e-9:
            issues.append(f"LUNAR direct {k}: 代码={cur} 权威={mpv}")
    print(f"  LUNAR_REACTION_COEFF.direct 校验: "
          f"{'一致' if not any('LUNAR' in i for i in issues) else '存在差异'}")

    # 2.4 公式结构核对（基于 KaTeX 内嵌 LaTeX 源码）
    doc = " ".join(formula_doc.get("latex", []))
    checks = [
        ("抗性分段含 R/2 项", bool(re.search(r"\\dfrac\{R\}\{2\}|1\s*-\s*R/2|1 - \\dfrac\{R\}", doc))),
        ("抗性高抗段含 4R", bool(re.search(r"4\s*\*?\s*R|4R", doc))),
        ("精通剧变 16/(精通+2000) 结构", bool(re.search(r"2000", doc)) and bool(re.search(r"16", doc))),
        ("精通增幅 2.78/(精通+1400) 结构", bool(re.search(r"2\.78", doc)) and bool(re.search(r"1400", doc))),
        ("防御区含 减防 与 无视防御",
         ("减防" in formula_doc["content"]) and ("无视防御" in formula_doc["content"])),
        ("月反应直伤公式存在", any("月曜" in l for l in formula_doc.get("latex", []))),
    ]
    for label, okk in checks:
        print(f"  公式结构 [{label}]: {'符合' if okk else '未匹配(需人工复核)'}")
    return issues


def check_artifacts(arts_mp):
    print("=" * 60)
    print("3) 圣遗物套装效果抽查（炽烈的炎之魔女）")
    witch_mp = next((a for a in arts_mp if a["set_name"] == "炽烈的炎之魔女"), None)
    arts_local = load("artifacts.json")
    witch_lo = next((a for a in arts_local if "魔女" in str(a.get("name_cn", ""))
                     or "魔女" in str(a.get("name", ""))), None)
    if witch_mp:
        print(f"  meropide 2件套: {witch_mp['set_2_effect']}")
        print(f"  meropide 4件套: {witch_mp['set_4_effect'][:100]}...")
    else:
        print("  [MISS] meropide 未收录该套装")
    if witch_lo:
        lo_desc = {e.get("level"): e.get("desc") for e in witch_lo.get("effects", [])}
        print(f"  本地 2件套描述: {lo_desc.get(0)}")
        print(f"  本地 4件套描述: {(lo_desc.get(1) or '')[:100]}...")
    else:
        print("  [MISS] 本地未找到该套装")


def main():
    chars_mp = load("characters_meropide.json", MP)["items"]
    arts_mp = load("artifacts_meropide.json", MP)["items"]
    forms = load("formulas.json", MP)["items"]

    ok_chars = check_characters(chars_mp)
    issues = check_formulas(forms)
    check_artifacts(arts_mp)

    print("=" * 60)
    print(f"角色面板抽查通过: {ok_chars}/3")
    if issues:
        print(f"\n发现 {len(issues)} 处差异:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("\n所有自动核对项均一致。")


if __name__ == "__main__":
    main()