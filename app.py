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
    art_names = ["无"] + [a.get("name_cn") or a.get("name") for a in arts]
    art_ids = {a.get("name_cn") or a.get("name"): str(a.get("set_id")) for a in arts}

    return char_names, char_ids, wp_names, wp_ids, art_names, art_ids


char_names, char_ids, wp_names, wp_ids, art_names, art_ids = load_options()


@st.cache_data
def get_artifact_effect(set_id):
    """从 artifacts.json 读取指定套装的 2件套/4件套效果描述

    注：实际数据结构为 effects 数组（每项含 pieces 与 desc），
    此处兼容读取 pieces==2 / pieces==4 的描述文本。
    """
    if not set_id or set_id == "无":
        return "", ""
    art = data_loader.find_artifact_set(set_id)
    if not art:
        return "", ""
    e2, e4 = "", ""
    for eff in art.get("effects", []):
        if eff.get("pieces") == 2:
            e2 = eff.get("desc", "") or "（暂无描述）"
        elif eff.get("pieces") == 4:
            e4 = eff.get("desc", "") or "（暂无描述）"
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
    渲染固有天赋开关列表，返回已启用天赋合并后的修饰器 dict。
    条件型天赋额外提供「视为满足触发条件」开关。
    """
    passives = load_passive_skills_cached(char_id)
    merged = {}
    if not passives:
        st.caption("（Meropide 数据中暂无该角色的固有天赋）")
        return merged
    for i, p in enumerate(passives):
        parsed = parse_effect(p.get("description", ""))
        label = p.get("name", f"天赋{i + 1}")
        enabled = st.checkbox(label, value=True, key=f"pass_{member_idx}_{char_id}_{i}")
        desc = (p.get("description") or "").strip().replace("\n", " ")
        st.caption(("☑ " if enabled else "☐ ") + (desc[:80] + "…" if len(desc) > 80 else desc))
        if not enabled:
            continue
        if parsed["unparsed"]:
            st.caption("　↳ 已启用（复杂机制类，暂不参与数值计算）")
            continue
        if parsed["conditional"]:
            cond_ok = st.checkbox(
                "视为满足触发条件", value=True,
                key=f"cond_{member_idx}_{char_id}_{i}",
            )
            if not cond_ok:
                continue
        for attr, val in parsed["modifiers"].items():
            merged[attr] = merged.get(attr, 0.0) + val
    return merged


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


def member_config_panel(idx):
    """单个队伍成员配置面板（expander），返回成员配置 dict"""
    with st.expander(
        f"{'🧑‍🎤' if idx == 0 else '👤'} 成员{idx + 1}" + ("（主力）" if idx == 0 else ""),
        expanded=(idx == 0),
    ):
        col_pic, col_sel = st.columns([1, 4])
        with col_sel:
            cname = st.selectbox("角色", ["无"] + char_names,
                                 index=1 if idx == 0 else 0, key=f"m{idx}_char")
        cid = char_ids.get(cname) if cname != "无" else None
        with col_pic:
            show_icon("avatar", cid)

        cfg = {
            "character_id": cid,
            "constellation_level": 0,
            "weapon_id": None, "refinement": 1,
            "artifact_set_2": None, "artifact_set_4": None,
            "talent_levels": {"normal": 10, "skill": 10, "burst": 10},
            "panel": {}, "passive_modifiers": {},
            "display_name": cname if cid else None,
        }
        if not cid:
            return cfg

        cfg["constellation_level"] = st.slider("命座等级", 0, 6, 0, key=f"m{idx}_cons")

        # ---- 武器（名称 + 图片）----
        col_wpic, col_wsel = st.columns([1, 4])
        with col_wsel:
            wname = st.selectbox("武器", wp_names, key=f"m{idx}_wp")
        wid = wp_ids.get(wname) if wname != "无" else None
        with col_wpic:
            show_icon("weapon", wid)
        cfg["weapon_id"] = wid
        if wid:
            cfg["refinement"] = st.slider("精炼等级", 1, 5, 1, key=f"m{idx}_ref")

        # ---- 圣遗物（2件套/4件套独立选择 + 效果展示）----
        col_apic, col_asel = st.columns([1, 4])
        with col_asel:
            a2 = st.selectbox("圣遗物 2件套", art_names, key=f"m{idx}_a2")
        sid2 = art_ids.get(a2) if a2 != "无" else None
        with col_apic:
            show_icon("relic", sid2, suffix="_5")
        a4 = st.selectbox("圣遗物 4件套", art_names, key=f"m{idx}_a4")
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
        cfg["passive_modifiers"] = render_passive_toggles(cid, idx)

        # ---- 面板属性输入（不含副词条的基础值；主词条无需单独设置）----
        st.markdown("**📈 面板属性**")
        pc = st.columns(5)
        atk = pc[0].number_input("攻击力", 0, 5000, 1500, key=f"m{idx}_atk")
        cr = pc[1].number_input("暴击率%", 0.0, 100.0, 5.0, key=f"m{idx}_cr")
        cd = pc[2].number_input("暴击伤害%", 0.0, 300.0, 50.0, key=f"m{idx}_cd")
        em = pc[3].number_input("元素精通", 0, 1000, 0, key=f"m{idx}_em")
        lb = pc[4].number_input("月反应加成%", 0.0, 100.0, 0.0, key=f"m{idx}_lb")
        cfg["panel"] = {
            "atk": float(atk), "crit_rate_pct": float(cr),
            "crit_dmg_pct": float(cd), "em": float(em),
            "lunar_bonus_pct": float(lb),
        }
    return cfg


# ---------- 页面布局 ----------
main_col, side_col = st.columns([3, 1])

with main_col:
    st.subheader("👥 队伍配置")
    st.caption("成员1 为伤害计算主力；其余成员用于月反应加权与元素共鸣（可留空）。"
               "圣遗物主词条已含在面板数值中，无需单独设置。")
    team_configs = [member_config_panel(i) for i in range(4)]

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
