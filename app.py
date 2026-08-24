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
    wp_names = ["无"] + [w.get("name_cn") or w.get("name") for w in wps]
    wp_ids = {w.get("name_cn") or w.get("name"): str(w.get("id")) for w in wps}

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

# ---------- 侧边栏配置 ----------
with st.sidebar:
    st.header("⚙️ 配置参数")

    character_name = st.selectbox("角色", char_names)
    constellation = st.slider("命座等级", 0, 6, 0)
    skill_type = st.selectbox("技能类型", list(SKILL_OPTIONS.keys()))
    talent_level = st.slider("天赋等级", 1, 13, 10)

    st.divider()
    weapon_name = st.selectbox("武器", wp_names)
    artifact_2 = st.selectbox("圣遗物2件套", art_names)
    artifact_4 = st.selectbox("圣遗物4件套", art_names)

    # 2.2 圣遗物套装效果展示
    st.markdown("**📜 套装效果**")
    if artifact_2 != "无":
        e2_a, _ = get_artifact_effect(art_ids.get(artifact_2))
        st.caption(f"**{artifact_2}** · 2件套")
        st.write(e2_a or "（暂无描述）")
    if artifact_4 != "无":
        e2_b, e4_b = get_artifact_effect(art_ids.get(artifact_4))
        st.caption(f"**{artifact_4}** · 2件套")
        st.write(e2_b or "（暂无描述）")
        st.caption(f"**{artifact_4}** · 4件套")
        st.write(e4_b or "（暂无描述）")

    st.divider()
    enemy_level = st.slider("敌人等级", 1, 100, 90)
    enemy_res = st.slider("敌人抗性", 0.0, 1.0, 0.1, step=0.05)

    reaction = st.selectbox("反应类型", list(REACTION_OPTIONS.keys()))

    st.divider()
    st.subheader("🎯 优化参数")
    total_rolls = st.slider("总有效词条数", 15, 45, 30)
    min_cr = st.slider("最小暴击率要求", 0.2, 0.8, 0.2, step=0.05)

    st.subheader("📿 主词条")
    sands = st.selectbox("时之沙主词条", list(MAIN_SANDS.keys()))
    goblet = st.selectbox("空之杯主词条", list(MAIN_GOBLET.keys()))
    circlet = st.selectbox("理之冠主词条", list(MAIN_CIRCLET.keys()))

    # 2.3 队伍配置常驻（不限于月反应）
    st.divider()
    st.subheader("👥 队伍配置")
    st.caption("选择 2-4 名角色用于月反应加权与元素共鸣（可留空）")
    team_members = []
    for i in range(4):
        member = st.selectbox(f"队伍成员 {i+1}", ["无"] + char_names, key=f"team_{i}")
        team_members.append(char_ids.get(member) if member != "无" else None)

    optimize_btn = st.button("🚀 开始优化", type="primary")

# ---------- 主界面 ----------
if optimize_btn:
    # 参数校验
    active_members = [m for m in team_members if m]
    if REACTION_OPTIONS[reaction] in ("lunar_charged", "lunar_crystallize", "lunar_bloom") and len(active_members) < 1:
        st.error("⚠️ 月反应间接伤害需要配置至少1名队伍成员！")
    elif min_cr > 0.95:
        st.error("⚠️ 最小暴击率要求过高（>95%），可能无法找到可行解，请降低。")
    else:
        with st.spinner("正在搜索最优属性分配..."):
            try:
                char_id = char_ids[character_name]
                input_params = OptimizationInput(
                    character_id=char_id,
                    constellation_level=constellation,
                    talent_level=talent_level,
                    skill_type=SKILL_OPTIONS[skill_type],
                    enemy_level=enemy_level,
                    enemy_res=enemy_res,
                    reaction_type=REACTION_OPTIONS[reaction],
                    weapon_id=wp_ids.get(weapon_name) if weapon_name != "无" else None,
                    artifact_set_2=art_ids.get(artifact_2) if artifact_2 != "无" else None,
                    artifact_set_4=art_ids.get(artifact_4) if artifact_4 != "无" else None,
                    total_substat_rolls=total_rolls,
                    min_crit_rate=min_cr,
                    main_stats={
                        "sands": MAIN_SANDS[sands],
                        "goblet": MAIN_GOBLET[goblet],
                        "circlet": MAIN_CIRCLET[circlet],
                    },
                    team_members=team_members,
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
    st.info("👈 在左侧配置参数后，点击「🚀 开始优化」按钮查看结果。")
    st.markdown(
        """
        ### 使用说明
        1. 选择角色、武器、圣遗物套装
        2. 设置敌人等级/抗性与反应类型
        3. 设定总词条数与最小暴击率要求
        4. 选择主词条（时之沙/空之杯/理之冠）
        5. 点击优化，自动搜索最优副词条分配

        **月反应**需配置至少1名队伍成员；队伍配置常驻于侧边栏底部，用于月反应加权与元素共鸣。
        """
    )
