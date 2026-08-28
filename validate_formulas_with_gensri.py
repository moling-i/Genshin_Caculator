# -*- coding: utf-8 -*-
"""
Gensri.wiki 公式校验脚本
========================
将 data/gensri/game_mechanics.json（gensri.wiki 权威数据）与本项目
src/constants.py / src/calculator.py 的公式实现逐项对比，
生成差异报告 data/gensri/validation_report.md。

用法：
    python validate_formulas_with_gensri.py
    （若提示缺少数据文件，先运行 python fetch_gensri.py）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src import constants as K  # noqa: E402

DATA_FILE = ROOT / "data" / "gensri" / "game_mechanics.json"
REPORT_FILE = ROOT / "data" / "gensri" / "validation_report.md"

# 剧变反应中文名 -> 项目内部键
TRANSFORMATIVE_CN_MAP = {
    "碎冰反应": "shatter", "超/烈绽放反应": "hyperbloom", "超载反应": "overload",
    "绽放反应": "bloom", "感电反应": "electrocharged", "超导反应": "superconduct",
    "扩散反应": "swirl", "燃烧反应": "burning",
}


def load_gensri():
    if not DATA_FILE.exists():
        print("[error] 缺少 data/gensri/game_mechanics.json，请先运行: python fetch_gensri.py")
        sys.exit(1)
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def find_table(gm: dict, keyword: str):
    for tb in gm.get("tables", []):
        if any(keyword in h for h in tb.get("headers", [])):
            return tb
    return None


def table_to_map(tb) -> dict:
    out = {}
    if not tb:
        return out
    for row in tb["rows"]:
        cells = [c for c in row if c]
        if len(cells) >= 2:
            try:
                out[cells[0]] = float(cells[-1])
            except ValueError:
                pass
    return out


def main():
    gm = load_gensri()
    checks = []          # (类别, 对比项, gensri值, 项目值, 状态)

    def add(category, item, gval, pval, force_ok=False):
        ok = force_ok or (
            gval is not None and pval is not None and abs(float(gval) - float(pval)) < 1e-6
        )
        checks.append((category, item,
                       "-" if gval is None else gval,
                       "-" if pval is None else pval,
                       "✅ 一致" if ok else ("⚠️ 无法核对" if gval is None else "❌ 不一致")))

    # ---- 1. 等级系数 ----
    lv = gm.get("level_coefficients", {})
    add("等级系数", "90级等级系数", lv.get("90"), K.LEVEL_COEFFICIENT)
    add("等级系数", "1级等级系数", lv.get("1"), 17.165)

    # ---- 2. 增幅反应 ----
    amp = gm["formulas"]["amplifying_reaction"]["coefficients"]
    pairs = [("melt_pyro_on_cryo_火打冰", ("Pyro", "Cryo"), "融化·火打冰"),
             ("melt_cryo_on_pyro_冰打火", ("Cryo", "Pyro"), "融化·冰打火"),
             ("vaporize_hydro_on_pyro_水打火", ("Hydro", "Pyro"), "蒸发·水打火"),
             ("vaporize_pyro_on_hydro_火打水", ("Pyro", "Hydro"), "蒸发·火打水")]
    for key, kpair, label in pairs:
        add("增幅反应", label, amp.get(key), K.AMPLIFY_COEFF[kpair])

    # ---- 3. 激化反应 ----
    qk = gm["formulas"]["quicken_reaction"]["coefficients"]
    calc_src = (ROOT / "src" / "calculator.py").read_text(encoding="utf-8")
    add("激化反应", "超激化系数(aggravate)", qk.get("aggravate_超激化"), K.AGGRAVATE_COEFF)
    add("激化反应", "蔓激化系数(spread)", qk.get("spread_蔓激化"), K.SPREAD_COEFF)
    split_ok = "AGGRAVATE_COEFF" in calc_src and "SPREAD_COEFF" in calc_src
    add("激化反应", "calculator 已按超/蔓分型取系数",
        1.0 if split_ok else 0.0, 1.0, force_ok=split_ok)

    # ---- 4. 剧变反应 ----
    trans_table = table_to_map(find_table(gm, "V5.2.0"))
    for cn_name, key in TRANSFORMATIVE_CN_MAP.items():
        gval = next((v for name, v in trans_table.items() if name == cn_name), None)
        add("剧变反应", f"{cn_name} -> {key}", gval, K.TRANSFORMATIVE_COEFF.get(key))
    mult_ok = "TRANSFORMATIVE_COEFF.get" in calc_src
    add("剧变反应", "calculator 已乘反应系数", 1.0 if mult_ok else 0.0, 1.0, force_ok=mult_ok)

    # ---- 5. 月曜反应 ----
    weights = gm["formulas"]["lunar_reaction"].get("contribution_weights")
    same = weights is not None and len(weights) == len(K.LUNAR_INDIRECT_WEIGHTS) and \
        all(abs(a - b) < 1e-9 for a, b in zip(weights, K.LUNAR_INDIRECT_WEIGHTS))
    add("月曜反应", "贡献权重(0.6/0.3/0.05/0.05)",
        weights, list(K.LUNAR_INDIRECT_WEIGHTS), force_ok=same)
    lun_table = table_to_map(find_table(gm, "雷暴云"))
    for key, coeff_cn in (("lunar_charged", "月感电"), ("lunar_crystallize", "月结晶")):
        fallback = gm["formulas"]["lunar_reaction"]["coefficients"].get(f"{key}_{coeff_cn}")
        gval = next((v for name, v in lun_table.items() if coeff_cn in name), fallback)
        add("月曜反应", f"{coeff_cn} 反应系数", gval, K.LUNAR_REACTION_COEFF[key]["indirect"])
        add("月曜反应", f"{coeff_cn} 直伤月乘区", gval, K.LUNAR_REACTION_COEFF[key]["direct"])

    # ---- 6. 抗性区 / 防御区 / 精通乘区（gensri 页面为公式图片，人工核对标记）----
    add("抗性区", "分段: RES<0→1-RES/2; 0~0.75→1-RES; >0.75→1/(4RES+1)",
        None, "constants.resistance_factor")
    add("防御区", "(角色等级+100)/(角色等级+100+怪物等级+100)", None,
        "constants.defense_factor")
    add("精通乘区", "增幅2.78EM/(EM+1400)；剧变/月曜16EM/(EM+2000)；激化5EM/(EM+1200)",
        None, "constants.em_bonus_*")

    # ---- 输出报告 ----
    lines = [
        "# Gensri.wiki 公式校验差异报告", "",
        f"- 数据来源：{gm.get('url')}（抓取日期 {gm.get('fetch_date')}）",
        "- 对比对象：`src/constants.py` / `src/calculator.py`",
        "- 注：gensri 明确标注「前玉衡杯提供的反应系数以及贡献权重有误，以此处为准」，"
        "月曜反应系数与贡献权重以 Gensri 为准。", "",
        "| 类别 | 对比项 | Gensri 值 | 项目值 | 状态 |",
        "|------|--------|-----------|--------|------|",
    ]
    for cat, item, gv, pv, st in checks:
        lines.append(f"| {cat} | {item} | {gv} | {pv} | {st} |")
    bad = [c for c in checks if c[4].startswith("❌")]
    warn = [c for c in checks if c[4].startswith("⚠️")]
    lines += ["", "## 结论", "",
              f"- ❌ 不一致：{len(bad)} 项",
              f"- ⚠️ 无法自动核对（页面为公式图片，需人工比对）：{len(warn)} 项",
              f"- ✅ 一致：{len(checks) - len(bad) - len(warn)} 项"]
    if bad:
        lines += ["", "### 需修正项", ""]
        lines += [f"- [{c[0]}] {c[1]}：Gensri={c[2]}，项目={c[3]}" for c in bad]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n[ok] 报告已写入 {REPORT_FILE}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()