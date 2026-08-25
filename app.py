"""
原神伤害计算器 - Streamlit 网页界面
启动: streamlit run app.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

from src import (
    Character,
    DamageOptimizer,
    OptimizationInput,
    data_loader,
)

st.set_page_config(page_title="原神伤害计算器", layout="wide")
st.title("🎮 原神伤害计算器 · 属性配平工具")

# ---------- 数据准备 ----------
# 角色下拉框排除关键词（与 fetch_data.py 保持一致）
_CHAR_EXCLUDE_KEYWORDS = ["试用", "测试", "Side_", "NPC", "未实装", "模特"]


@st.cache_data
def load_options():
    chars = data_loader.get_characters()
    # 仅保留 name_cn 非空且不含排除关键词的正式角色
    valid_chars = [
        c for c in chars
        if (c.get("name_cn") or c.get("name"))
        and not any(
            kw in (c.get("name_cn") or c.get("name", ""))
            for kw in _CHAR_EXCLUDE_KEYWORDS
        )
    ]
    # 按中文名拼音（GBK 编码序）排序，无需第三方库
    valid_chars.sort(
        key=lambda c: (c.get("name_cn") or c.get("name", "")).encode("gbk", "ignore")
    )

    char_names = [c.get("name_cn") or c.get("name") for c in valid_chars]
    char_ids = {c.get("name_cn") or c.get("name"): str(c.get("id")) for c in valid_chars}

    wps = data_loader.get_weapons()
    # 过滤仍未获得中文名的测试/未实装武器（name_cn 为 Weapon_XXXXX 占位符）
    valid_wps = [w for w in wps if w.get("name_cn") and not w["name_cn"].startswith("Weapon_")]
    wp_names = ["无"] + [w.get("name_cn") or w.get("name") for w in valid_wps]
    wp_ids = {w.get("name_cn") or w.get("name"): str(w.get("id")) for w in valid_wps}

    arts = data_loader.get_artifacts()
    # 过滤无名称的坏数据条目（如内部测试套装 set_id=15004 等）
    valid_arts = [a for a in arts if (a.get("name_cn") or a.get("name"))]
    art_names = ["无"] + [a.get("name_cn") or a.get("name") for a in valid_arts]
    art_ids = {a.get("name_cn") or a.get("name"): str(a.get("set_id")) for a in valid_arts}

    return char_names, char_ids, wp_names, wp_ids, art_names, art_ids


char_names, char_ids, wp_names, wp_ids, art_names, art_ids = load_options()


@st.cache_data
def get_artifact_effect(set_id):
    """读取指定套装的 2件套/4件套效果描述，返回 (e2, e4)

    数据源优先级：
      1. meropide 权威套装文案（artifacts_meropide.json 的 set_2_effect/set_4_effect）
      2. 本地 artifacts.json 的 effects 数组（pieces==2/4 的 desc）
    """
    if not set_id or set_id == "无":
        return "", ""
    art = data_loader.find_artifact_set(set_id)
    if not art:
        return "", ""
    e2, e4 = "", ""
    # 本地数据解析
    for eff in art.get("effects", []):
        if eff.get("pieces") == 2:
            e2 = eff.get("desc", "") or ""
        elif eff.get("pieces") == 4:
            e4 = eff.get("desc", "") or ""
    # meropide 权威文案覆盖（文本更完整准确；如魔女套本地 4 件套为劣质占位符）
    name_cn = art.get("name_cn") or ""
    mp = data_loader.find_meropide_artifact(name_cn) if name_cn else None
    if mp:
        if (mp.get("set_2_effect") or "").strip():
            e2 = mp["set_2_effect"].strip()
        if (mp.get("set_4_effect") or "").strip():
            e4 = mp["set_4_effect"].strip()
    return e2, e4


# ---------- 图片 / 天赋 / 固有天赋辅助 ----------

@st.cache_data(show_spinner=False)
def _fetch_image(url):
    """下载图片字节（服务端缓存，失败返回 None）"""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read()
    except Exception:
        return None


def show_icon(kind, obj_id, width=72, suffix=""):
    """显示图标（enka CDN）；未知 id 或加载失败时显示占位符"""
    url = data_loader.get_icon_url(kind, obj_id, default_suffix=suffix) if obj_id else ""
    data = _fetch_image(url) if url else None
    if data:
        st.image(data, width=width)
    else:
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:center;"
            f"width:{width}px;height:{int(width * 1.15)}px;background:#262730;"
            "border-radius:6px;font-size:22px;color:#666'>⚠️</div>",
            unsafe_allow_html=True,
        )


@st.cache_data(show_spinner=False)
def get_talent_display_cached(char_id):
    return data_loader.get_talent_display(char_id)


@st.cache_data(show_spinner=False)
def load_passive_skills_cached(char_id):
    return data_loader.load_passive_skills(char_id)


def render_talent_info(char_id):
    """显示 Meropide 权威文案的普攻/E/Q 倍率摘要"""
    talents = get_talent_display_cached(char_id)
    if not talents:
        st.caption("（Meropide 数据中暂无天赋详情）")
        return
    for t in talents[:3]:
        name = t.get("skill_name", "")
        stype = t.get("skill_type", "")
        rows = t.get("rows") or []
        parts = [f"{r.get('label', '')}: {r.get('value_text', '')}" for r in rows[:2]]
        parts += [
            f"{r.get('label', '')}: {r.get('value_text', '')}"
            for r in rows
            if ("冷却" in r.get("label", "") or "能量" in r.get("label", "")) and len(parts) < 4
        ]
        st.markdown(f"**{stype}·{name}**: " + " ｜ ".join(parts))


def render_passive_toggles(char_id, member_idx):
    """
    渲染固有天赋开关列表，返回完整效果结构：
    {modifiers{}, conversions[], er_scalings[]}（均已合并启用项）。
    条件型天赋：
      - 血量阈值类 → 提供「当前生命值%」滑块，按实际数值判定是否生效；
      - 其他条件   → 「视为满足触发条件」开关。
    """
    effects = {
        "modifiers": {}, "conversions": [], "er_scalings": [],
        "talent_multipliers": {}, "extra_hits": [], "damage_amps": [],
        "stack_context": {}, "active_states": {},
    }
    # ---- 状态标签触发判定（夜魂/魔导/星超导/星扩散/月兆）----
    # 开关列表 = 角色固有标签 ∪ 各天赋描述中检测到的依赖状态
    char_states = list(data_loader.get_character_states(char_id))
    _all_passives = load_passive_skills_cached(char_id) or []
    for _p in _all_passives:
        for _s in data_loader.detect_required_states(
            _p.get("description") or "", char_states
        ):
            if _s not in char_states:
                char_states.append(_s)
    if char_states:
        with st.expander("🔖 状态标签触发判定", expanded=False):
            st.caption("关闭某状态后，依赖该状态的固有天赋将不参与计算")
            for s in char_states:
                effects["active_states"][s] = st.checkbox(
                    f"状态「{s}」已触发", value=True,
                    key=f"state_{member_idx}_{char_id}_{s}",
                )
    passives = load_passive_skills_cached(char_id)
    if not passives:
        st.caption("（Meropide 数据中暂无该角色的固有天赋）")
        return effects
    for i, p in enumerate(passives):
        parsed = parse_effect(p.get("description", ""))
        label = p.get("name", f"天赋{i + 1}")
        enabled = st.checkbox(label, value=True, key=f"pass_{member_idx}_{char_id}_{i}")
        # 完整显示天赋描述全文（不截断；长文本换行保留）
        desc = (p.get("description") or "").strip()
        prefix = "☑ " if enabled else "☐ "
        st.markdown(prefix + desc.replace("\n", "  \n"), unsafe_allow_html=False)
        if not enabled:
            continue
        if parsed["unparsed"] and not (
            parsed.get("conversion") or parsed.get("er_scaling")
        ):
            st.caption("　↳ 已启用（复杂机制类，暂不参与数值计算）")
            continue

        # ---- 条件判定 ----
        if parsed["conditional"]:
            ht = parsed.get("hp_threshold")
            if ht is not None:
                hp_now = st.slider(
                    f"　当前生命值%（天赋要求 ≤{ht * int(100) / 100:g}%）",
                    0, 100, min(int(ht * 100), 100),
                    key=f"hps_{member_idx}_{char_id}_{i}",
                )
                cond_ok = (hp_now / 100.0) <= ht
                st.caption(
                    f"　↳ 血量条件{'✅ 满足' if cond_ok else '❌ 未满足'}"
                    f"（当前 {hp_now}% / 要求 ≤{ht * 100:g}%）"
                )
            else:
                cond_ok = st.checkbox(
                    "视为满足触发条件", value=True,
                    key=f"cond_{member_idx}_{char_id}_{i}",
                )
            if not cond_ok:
                continue

        # ---- 数值合并 ----
        for attr, val in parsed["modifiers"].items():
            effects["modifiers"][attr] = effects["modifiers"].get(attr, 0.0) + val
        if parsed.get("conversion"):
            conv = {k: v for k, v in parsed["conversion"].items() if k != "text"}
            effects["conversions"].append(conv)
            c = parsed["conversion"]
            st.caption(
                f"　↳ 属性转换已计入：{_CONV_CN.get(c['from'], c['from'])}"
                f" × {c['ratio'] * 100:g}% → 攻击力"
            )
        if parsed.get("er_scaling"):
            sc = {k: v for k, v in parsed["er_scaling"].items() if k != "text"}
            effects["er_scalings"].append(sc)
            s = parsed["er_scaling"]
            st.caption(
                f"　↳ 充能转化已计入：超出100%的充能每1% → "
                f"+{s['per_unit'] * 100:g}% 元素伤害加成"
            )
        # ---- 机制型天赋数值（v3）----
        tm = parsed.get("talent_multiplier")
        if tm:
            for k, tiers in tm.get("skill_types", {}).items():
                prev = effects["talent_multipliers"].get(k) or []
                effects["talent_multipliers"][k] = (
                    [max(a, b) for a, b in zip(prev + [0.0] * len(tiers), tiers)]
                    if prev else list(tiers)
                )
                n = len(tiers)
                stacks = st.slider(
                    f"　层数（{k}，{ '/'.join(f'{t*100:g}%' for t in tiers) }）",
                    1, n, n, key=f"stk_{member_idx}_{char_id}_{i}_{k}",
                )
                effects["stack_context"][k] = stacks
            st.caption("　↳ 技能倍率层数提升已计入（按当前层数档位）")
        eh = parsed.get("extra_hit")
        if eh:
            if eh not in effects["extra_hits"]:
                effects["extra_hits"].append(dict(eh))
            st.caption(
                f"　↳ 额外一段伤害已计入：{_CONV_CN.get(eh['source'], eh['source'])}"
                f" × {eh['ratio'] * 100:g}%"
            )
        da = parsed.get("damage_amp")
        if da:
            if da not in effects["damage_amps"]:
                effects["damage_amps"].append(dict(da))
            st.caption(
                f"　↳ 全伤害增幅已计入：每 {da['per_points']:g} 点"
                f"{_CONV_CN.get(da['source'], da['source'])} → +{da['per_bonus'] * 100:g}%"
                f"（至多 +{da['cap'] * 100:g}%）"
            )
    return effects


_CONV_CN = {"hp": "生命值上限", "atk": "攻击力", "def": "防御力", "em": "元素精通"}


REACTION_OPTIONS = {
    "无": None,
    "蒸发": "vaporize",
    "融化": "melt",
    "超载": "overload",
    "超导": "superconduct",
    "扩散": "swirl",
    "碎冰": "shatter",
    "感电": "electrocharged",
    "蔓激化": "aggravate",
    "超激化": "spread",
    "月感电": "lunar_charged",
    "月结晶": "lunar_crystallize",
    "月绽放": "lunar_bloom",
    "星超导": "stellar_superconduct",
}

SKILL_OPTIONS = {"普通攻击": "normal", "元素战技": "skill", "元素爆发": "burst", "重击": "charged"}

MAIN_SANDS = {"攻击%": "atk_percent", "生命%": "hp_percent", "元素精通": "em", "元素充能%": "er"}
MAIN_GOBLET = {"元素伤害%": "elemental_dmg", "攻击%": "atk_percent", "生命%": "hp_percent"}
MAIN_CIRCLET = {"暴击伤害%": "crit_dmg", "暴击率%": "crit_rate", "攻击%": "atk_percent"}

SKILL_TYPE_KEYS = {"normal": "normal", "skill": "skill", "burst": "burst", "charged": "normal"}
parse_effect = data_loader.parse_effect


def searchable_select(label, all_options, key, default_index=0):
    """带搜索过滤的下拉选择框：上方搜索框实时过滤下方选项列表

    返回选中的选项字符串；无匹配项时返回 None。
    """
    term = st.text_input(f"🔍 搜索{label}", key=f"{key}_search").strip().lower()
    if term:
        filtered = [o for o in all_options if term in str(o).lower()]
    else:
        filtered = list(all_options)
    if not filtered:
        st.caption(f"⚠️ 无匹配「{term}」的{label}，请调整搜索词")
        return None
    # 过滤后当前已选值不在列表中时，重置选择避免异常
    if key in st.session_state and st.session_state[key] not in filtered:
        del st.session_state[key]
    idx = min(default_index, len(filtered) - 1)
    return st.selectbox(label, filtered, index=idx, key=key)


def member_config_panel(idx):
    """单个队伍成员配置面板（expander），返回成员配置 dict"""
    with st.expander(
        f"{'🧑‍🎤' if idx == 0 else '👤'} 成员{idx + 1}" + ("（主力）" if idx == 0 else ""),
        expanded=(idx == 0),
    ):
        col_pic, col_sel = st.columns([1, 4])
        with col_sel:
            cname = searchable_select(
                "角色", ["无"] + char_names, f"m{idx}_char",
                default_index=1 if idx == 0 else 0,
            )
            if cname is None:
                cname = "无"
            cid = char_ids.get(cname) if cname != "无" else None
            # 固有状态标签（只读，如 夜魂 / 月兆 / 魔导）
            if cid:
                char_states = data_loader.get_character_states(cid)
                if char_states:
                    st.caption(f"🔖 {' · '.join(char_states)}")
        with col_pic:
            show_icon("avatar", cid)

        cfg = {
            "character_id": cid,
            "constellation_level": 0,
            "weapon_id": None, "refinement": 1,
            "artifact_set_2": None, "artifact_set_4": None,
            "talent_levels": {"normal": 10, "skill": 10, "burst": 10},
            "panel": {}, "passive_modifiers": {}, "passive_effects": {},
            "states": [],
            "display_name": cname if cid else None,
        }
        if not cid:
            return cfg
        cfg["states"] = data_loader.get_character_states(cid)

        cfg["constellation_level"] = st.slider("命座等级", 0, 6, 0, key=f"m{idx}_cons")

        # ---- 武器（名称 + 图片）----
        col_wpic, col_wsel = st.columns([1, 4])
        with col_wsel:
            wname = searchable_select("武器", wp_names, f"m{idx}_wp")
            if wname is None:
                wname = "无"
        wid = wp_ids.get(wname) if wname != "无" else None
        with col_wpic:
            show_icon("weapon", wid)
        cfg["weapon_id"] = wid
        if wid:
            cfg["refinement"] = st.slider("精炼等级", 1, 5, 1, key=f"m{idx}_ref")

        # ---- 圣遗物（2件套/4件套独立选择 + 效果展示）----
        col_apic, col_asel = st.columns([1, 4])
        with col_asel:
            a2 = searchable_select("圣遗物 2件套", art_names, f"m{idx}_a2")
            if a2 is None:
                a2 = "无"
        sid2 = art_ids.get(a2) if a2 != "无" else None
        with col_apic:
            show_icon("relic", sid2, suffix="_5")
        a4 = searchable_select("圣遗物 4件套", art_names, f"m{idx}_a4")
        if a4 is None:
            a4 = "无"
        sid4 = art_ids.get(a4) if a4 != "无" else None
        cfg["artifact_set_2"], cfg["artifact_set_4"] = sid2, sid4

        # 按实际选择分别显示对应件套描述；同套装同时选 2+4 时完整展示
        if sid2:
            e2, _ = get_artifact_effect(sid2)
            st.caption(f"**📜 {a2} · 2件套**")
            st.write(e2 or "（暂无描述）")
        if sid4:
            _, e4 = get_artifact_effect(sid4)
            st.caption(f"**📜 {a4} · 4件套**")
            st.write(e4 or "（暂无描述）")

        # ---- 天赋等级（3 个滑块）+ Meropide 天赋信息 ----
        st.markdown("**🎯 天赋等级**")
        tl = st.columns(3)
        cfg["talent_levels"]["normal"] = tl[0].slider("普攻", 1, 13, 10, key=f"m{idx}_tn")
        cfg["talent_levels"]["skill"] = tl[1].slider("E技能", 1, 13, 10, key=f"m{idx}_ts")
        cfg["talent_levels"]["burst"] = tl[2].slider("Q技能", 1, 13, 10, key=f"m{idx}_tb")

        with st.expander("📊 天赋信息（Meropide 权威文案）", expanded=(idx == 0)):
            render_talent_info(cid)

        # ---- 固有天赋开关 ----
        st.markdown("**✨ 固有天赋**")
        pe = render_passive_toggles(cid, idx)
        cfg["passive_modifiers"] = pe["modifiers"]
        cfg["passive_effects"] = pe

        # ---- 面板属性输入（不含副词条的基础值；主词条无需单独设置）----
        st.markdown("**📈 面板属性**")
        pc = st.columns(6)
        atk = pc[0].number_input("攻击力", 0, 5000, 1500, key=f"m{idx}_atk")
        cr = pc[1].number_input("暴击率%", 0.0, 100.0, 5.0, key=f"m{idx}_cr")
        cd = pc[2].number_input("暴击伤害%", 0.0, 300.0, 50.0, key=f"m{idx}_cd")
        em = pc[3].number_input("元素精通", 0, 1000, 0, key=f"m{idx}_em")
        lb = pc[4].number_input("月反应加成%", 0.0, 100.0, 0.0, key=f"m{idx}_lb")
        erp = pc[5].number_input(
            "充能加成%（超出基础的充能效率部分，如200%总充能填100）",
            0.0, 400.0, 0.0, key=f"m{idx}_er",
        )
        cfg["panel"] = {
            "atk": float(atk), "crit_rate_pct": float(cr),
            "crit_dmg_pct": float(cd), "em": float(em),
            "lunar_bonus_pct": float(lb), "er_pct": float(erp),
        }
    return cfg


# ---------- 页面布局 ----------
main_col, side_col = st.columns([3, 1])

with main_col:
    st.subheader("👥 队伍配置")
    st.caption("成员1 为伤害计算主力；其余成员用于月反应加权与元素共鸣（可留空）。"
               "圣遗物主词条已含在面板数值中，无需单独设置。")
    team_configs = [member_config_panel(i) for i in range(4)]

    # ---- 队伍动态状态（初辉/满辉，按月兆角色数量自动计算）----
    lunar_count = sum(
        1 for c in team_configs
        if c.get("character_id") and "月兆" in c.get("states", [])
    )
    state_lines = [f"**👥 队伍状态**　月兆角色数量：{lunar_count}"]
    if lunar_count >= 1:
        state_lines.append("🟡 **初辉已激活**")
    if lunar_count >= 2:
        state_lines.append("🟢 **满辉已激活**")
    st.markdown("　|　".join(state_lines))

with side_col:
    with st.container(border=True):
        st.header("⚙️ 战斗与优化参数")
        enemy_level = st.slider("敌人等级", 1, 100, 90)
        enemy_res = st.slider("敌人抗性", 0.0, 1.0, 0.1, step=0.05)
        reaction = st.selectbox("反应类型", list(REACTION_OPTIONS.keys()))
        skill_type = st.selectbox("主力技能类型", list(SKILL_OPTIONS.keys()))

        st.divider()
        st.subheader("🎯 优化参数")
        total_rolls = st.slider("总有效词条数", 15, 45, 30)
        min_cr = st.slider("最小暴击率要求", 0.2, 0.8, 0.2, step=0.05)
        sands = st.selectbox("时之沙主词条", list(MAIN_SANDS.keys()))
        goblet = st.selectbox("空之杯主词条", list(MAIN_GOBLET.keys()))
        circlet = st.selectbox("理之冠主词条", list(MAIN_CIRCLET.keys()))
        optimize_btn = st.button("🚀 开始优化", type="primary")

# ---------- 主界面 ----------
if optimize_btn:
    active_members = [c for c in team_configs if c and c.get("character_id")]
    main_cfg = team_configs[0]

    if not main_cfg.get("character_id"):
        st.error("⚠️ 请先在「成员1」中选择主力角色！")
    elif REACTION_OPTIONS[reaction] in (
        "lunar_charged", "lunar_crystallize", "lunar_bloom"
    ) and len(active_members) < 1:
        st.error("⚠️ 月反应间接伤害需要配置至少1名队伍成员！")
    elif min_cr > 0.95:
        st.error("⚠️ 最小暴击率要求过高（>95%），可能无法找到可行解，请降低。")
    else:
        character_name = main_cfg["display_name"]
        talent_key = SKILL_TYPE_KEYS[SKILL_OPTIONS[skill_type]]
        with st.spinner("正在搜索最优属性分配..."):
            try:
                input_params = OptimizationInput(
                    character_id=main_cfg["character_id"],
                    constellation_level=main_cfg["constellation_level"],
                    talent_level=main_cfg["talent_levels"][talent_key],
                    skill_type=SKILL_OPTIONS[skill_type],
                    enemy_level=enemy_level,
                    enemy_res=enemy_res,
                    reaction_type=REACTION_OPTIONS[reaction],
                    weapon_id=main_cfg["weapon_id"],
                    artifact_set_2=main_cfg["artifact_set_2"],
                    artifact_set_4=main_cfg["artifact_set_4"],
                    total_substat_rolls=total_rolls,
                    min_crit_rate=min_cr,
                    main_stats={
                        "sands": MAIN_SANDS[sands],
                        "goblet": MAIN_GOBLET[goblet],
                        "circlet": MAIN_CIRCLET[circlet],
                    },
                    panel_inputs={
                        k: v for k, v in main_cfg["panel"].items()
                        if k != "lunar_bonus_pct"
                    },
                    passive_modifiers=main_cfg["passive_modifiers"],
                    passive_effects=main_cfg["passive_effects"],
                    team_configs=team_configs,
                )

                optimizer = DamageOptimizer(input_params)
                result = optimizer.optimize()

                col1, col2 = st.columns([1, 1])

                with col1:
                    st.subheader("📊 最优属性分配")
                    os_stats = result.optimal_stats
                    alloc = result.allocation
                    total_alloc = sum(alloc.values()) or 1
                    stats_df = pd.DataFrame({
                        "属性": ["攻击力加成", "暴击率", "暴击伤害", "元素精通"],
                        "最优值": [
                            f"{os_stats['atk_percent']*100:.1f}%",
                            f"{os_stats['crit_rate']*100:.1f}%",
                            f"{os_stats['crit_dmg']*100:.1f}%",
                            f"{os_stats['em']:.0f}",
                        ],
                        "分配词条数": [
                            alloc.get("atk_percent", 0),
                            alloc.get("crit_rate", 0),
                            alloc.get("crit_dmg", 0),
                            alloc.get("em", 0),
                        ],
                        "占比": [
                            f"{alloc.get('atk_percent',0)/total_alloc*100:.0f}%",
                            f"{alloc.get('crit_rate',0)/total_alloc*100:.0f}%",
                            f"{alloc.get('crit_dmg',0)/total_alloc*100:.0f}%",
                            f"{alloc.get('em',0)/total_alloc*100:.0f}%",
                        ],
                    })
                    st.table(stats_df)

                    # 导出结果
                    export_data = {
                        "character": character_name,
                        "optimal_stats": {k: round(v, 4) for k, v in os_stats.items()},
                        "allocation": alloc,
                        "max_damage": round(result.max_damage, 2),
                    }
                    st.download_button(
                        "📥 下载优化结果 (JSON)",
                        data=__import__("json").dumps(export_data, ensure_ascii=False, indent=2),
                        file_name="optimization_result.json",
                        mime="application/json",
                    )

                with col2:
                    st.subheader("💥 伤害预期")
                    st.metric("最大期望伤害", f"{result.max_damage:,.2f}")

                    st.write("**乘区明细：**")
                    bd = result.damage_breakdown
                    breakdown_rows = []
                    if "base_damage" in bd:
                        breakdown_rows.append(("基础伤害区", f"{bd['base_damage']:.2f}"))
                    if "dmg_bonus_factor" in bd:
                        breakdown_rows.append(("× 增伤区", f"{bd['dmg_bonus_factor']:.4f}"))
                    if "def_factor" in bd:
                        breakdown_rows.append(("× 防御区", f"{bd['def_factor']:.4f}"))
                    if "res_factor" in bd:
                        breakdown_rows.append(("× 抗性区", f"{bd['res_factor']:.4f}"))
                    if "crit_factor" in bd:
                        breakdown_rows.append(("× 暴击区", f"{bd['crit_factor']:.4f}"))
                    if "reaction_factor" in bd:
                        breakdown_rows.append(("× 反应区", f"{bd['reaction_factor']:.4f}"))
                    if "final_damage" in bd:
                        breakdown_rows.append(("= 最终伤害", f"{bd['final_damage']:.2f}"))

                    for label, val in breakdown_rows:
                        st.write(f"- {label}: **{val}**")

                st.subheader("💡 培养建议")
                st.info(result.suggestion)

                if result.history:
                    st.subheader("📈 优化收敛曲线")
                    hist_df = pd.DataFrame(result.history).set_index("iteration")
                    st.line_chart(hist_df, use_container_width=True)

            except Exception as e:
                st.error(f"❌ 优化失败: {e}")
else:
    st.info("👆 配置好队伍与参数后，点击「🚀 开始优化」按钮查看结果。")
    st.markdown(
        """
        ### 使用说明
        1. 在「成员1」选择主力角色、武器、圣遗物套装，勾选固有天赋
        2. 输入各成员面板属性（不含副词条的基础值）
        3. 右侧设置敌人等级/抗性、反应类型、主力技能类型
        4. 设定总词条数与最小暴击率要求，选择主词条
        5. 点击优化，自动搜索最优副词条分配

        **固有天赋**：勾选后自动叠加对应加成；条件型天赋可控制是否视为满足触发条件。
        **月反应**需配置至少1名队伍成员；队伍成员独立配置，互不影响。
        """
    )
