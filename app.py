"""
原神伤害计算器 - Streamlit 网页界面（多模式导航版）

启动: streamlit run app.py

结构（meropide / gensri 风格：左侧导航 + 内容区）：
  - 首页：hero + 模式卡片导航
  - 伤害优化：队伍配置（成员1为主力）+ 战斗/优化参数 + 结果
  - 队伍DPS：联合优化整队轮换 DPS
  - 反应速查：meropide 权威公式表 + 小计算器
  - 数据速查：角色 / 武器 / 圣遗物浏览

解决的 4 个痛点：
  1. 导航扁平、功能难找 → 左侧固定导航 + 首页卡片
  2. 4 名成员用折叠面板（expander）难用 → 改为 tab 切换
  3. 选角色要手填基础面板 → 选角色/武器后自动载入基础面板（角色基础攻击 + 武器基础攻击）
  4. 缺少反应/数据参考 → 新增「反应速查」「数据速查」两个模式
"""
import os
import sys
import base64
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

from src import (
    Character,
    DamageOptimizer,
    OptimizationInput,
    data_loader,
)
from src.team_dps import Rotation, PRESET_ROTATIONS
from src.team_optimizer import TeamDPSOptimizer, TeamDPSOptimizationInput
from src import constants

st.set_page_config(page_title="原神伤害计算器", layout="wide", initial_sidebar_state="expanded")

# 确保 nav_mode session_state 键存在（最稳妥的 setdefault 写法，位于主流程最顶部）
st.session_state.setdefault("nav_mode", "首页")

# ============================================================================
# 样式（meropide 极简风格 + 左侧导航）
# ============================================================================
_CSS_GLASS_CORE = """
<style>
:root{--bg:transparent;--card:rgba(255,255,255,0.50);--text:#1A1A2E;--text-2:#6B7280;--border:rgba(255,255,255,0.30);--accent:#4F46E5}
[data-testid="stAppViewContainer"],[data-testid="stAppViewContainer"]>div{background:transparent!important;box-shadow:none!important}
[data-testid="stHeader"]{background:transparent!important}
.stApp{background-image:url("app/static/furina_rain_bg.webp");background-color:transparent!important;background-size:cover;background-position:center;background-attachment:fixed;background-repeat:no-repeat}
section.main>div.block-container{background:rgba(255,255,255,0.35)!important;backdrop-filter:blur(16px) saturate(160%);-webkit-backdrop-filter:blur(16px) saturate(160%);border-radius:12px;border:1px solid rgba(255,255,255,0.30);box-shadow:0 4px 24px rgba(0,0,0,0.04)}
[data-testid="stSidebar"]{background:rgba(255,255,255,0.12)!important;backdrop-filter:blur(20px) saturate(180%)!important;-webkit-backdrop-filter:blur(20px) saturate(180%)!important;border-right:1px solid rgba(255,255,255,0.25)!important;box-shadow:2px 0 20px rgba(0,0,0,0.06)!important}
[data-testid="stSidebar"] section{background:transparent!important}
[data-testid="stSidebar"] .stMarkdown,[data-testid="stSidebar"] .stSelectbox label,[data-testid="stSidebar"] .stTextInput label,[data-testid="stSidebar"] .stMultiSelect label,[data-testid="stSidebar"] .stNumberInput label{color:#1A1A2E!important;font-weight:500!important;text-shadow:0 1px 2px rgba(255,255,255,0.7)}
</style>"""
st.markdown(_CSS_GLASS_CORE, unsafe_allow_html=True)
_CSS_GLASS_WIDGETS = """
<style>
[data-testid="stSelectbox"]>div,[data-testid="stMultiSelect"]>div{background:rgba(255,255,255,0.25)!important;backdrop-filter:blur(8px)!important;-webkit-backdrop-filter:blur(8px)!important;border:1px solid rgba(255,255,255,0.40)!important;border-radius:8px!important;transition:background 0.2s!important}
[data-testid="stSelectbox"]>div:hover,[data-testid="stMultiSelect"]>div:hover{background:rgba(255,255,255,0.38)!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{background:rgba(255,255,255,0.25)!important;backdrop-filter:blur(8px)!important;-webkit-backdrop-filter:blur(8px)!important;border:1px solid rgba(255,255,255,0.40)!important;border-radius:8px!important;color:#1A1A2E!important;transition:all 0.2s!important}
[data-testid="stTextInput"] input:focus,[data-testid="stNumberInput"] input:focus{background:rgba(255,255,255,0.42)!important;border-color:#6C63FF!important;box-shadow:0 0 0 2px rgba(108,99,255,0.15)!important}
/* 下拉选项列表：半透明白色毛玻璃，文字清晰（不改底层选择框） */
[data-baseweb="menu"]{background:rgba(255,255,255,0.92)!important;backdrop-filter:blur(16px) saturate(150%)!important;-webkit-backdrop-filter:blur(16px) saturate(150%)!important;border-radius:10px!important;border:1px solid rgba(255,255,255,0.35)!important;box-shadow:0 8px 24px rgba(0,0,0,0.10)!important}
[data-baseweb="option"]{color:#1A1A2E!important}
[data-baseweb="option"]:hover,[data-baseweb="option"][aria-selected="true"]{background:rgba(108,99,255,0.10)!important;color:#1A1A2E!important}
/* 命座滑块区域：半透明白色毛玻璃，文字清晰 */
[data-testid="stSlider"]{background:rgba(255,255,255,0.45)!important;backdrop-filter:blur(12px)!important;-webkit-backdrop-filter:blur(12px)!important;border:1px solid rgba(255,255,255,0.35)!important;border-radius:8px!important;padding:14px 16px 4px!important}
[data-testid="stSlider"] label{color:#1A1A2E!important;font-weight:500!important}
[data-testid="stSlider"] .stSliderTrack{background:rgba(108,99,255,0.18)!important;border-radius:4px!important}
[data-testid="stSlider"] .stSliderThumb{background:#6C63FF!important;box-shadow:0 2px 8px rgba(108,99,255,0.35)!important}
.stButton button,[data-testid="stBase"] button{background:linear-gradient(135deg,#6C63FF,#4F46E5)!important;color:white!important;border:none!important;border-radius:8px!important;font-weight:500!important;box-shadow:0 4px 14px rgba(79,70,229,0.25)!important;transition:all 0.2s!important}
.stButton button:hover,[data-testid="stBase"] button:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(79,70,229,0.35)!important}
</style>"""
st.markdown(_CSS_GLASS_WIDGETS, unsafe_allow_html=True)

_CSS_GLASS_EXTRA = """
<style>
h1,h2,h3{color:var(--text)!important;font-weight:600!important}
h1,h2,h3,.stMarkdown p,label,span,div{color:var(--text)}
.stExpander,[data-testid="stExpander"]{border:1px solid rgba(255,255,255,0.30)!important;border-radius:6px!important;box-shadow:none!important;background:rgba(255,255,255,0.45);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
[data-testid="stVerticalBlockBorderWrapper"]{background:rgba(255,255,255,0.42)!important;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border:1px solid rgba(255,255,255,0.35)!important;border-radius:8px!important}
.stImage img,[data-testid="stImage"] img{border:none!important;border-radius:4px!important}
.icon-fallback{display:flex;align-items:center;justify-content:center;background:var(--bg);border:1px solid var(--border);border-radius:4px}
.stTable td,.stTable th,[data-testid="stTable"] td,[data-testid="stTable"] th{border:none!important;padding:0.25rem 0.6rem!important;font-size:0.85rem}
thead tr th{color:var(--text-2)!important;font-weight:500!important}
hr{border-color:rgba(255,255,255,0.35);margin:0.75rem 0}
.hero{background:rgba(255,255,255,0.35);border:1px solid rgba(255,255,255,0.35);border-radius:14px;padding:28px 32px;margin-bottom:20px;backdrop-filter:blur(14px)}
.hero h1{font-size:1.9rem;margin:0 0 6px}
.hero p{color:var(--text-2);margin:0;font-size:1rem}
.mode-card{background:rgba(255,255,255,0.35);border:1px solid rgba(255,255,255,0.35);border-radius:12px;padding:18px 18px 14px;height:100%;backdrop-filter:blur(12px);transition:transform .12s ease,box-shadow .12s ease}
.mode-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(79,70,229,0.15)}
.mode-card .mc-icon{font-size:1.7rem}
.mode-card .mc-title{font-weight:600;font-size:1.05rem;margin:8px 0 4px;color:var(--text)}
.mode-card .mc-desc{color:var(--text-2);font-size:0.85rem;line-height:1.5}
</style>"""
st.markdown(_CSS_GLASS_EXTRA, unsafe_allow_html=True)


# ============================================================================
# 数据准备
# ============================================================================
_CHAR_EXCLUDE_KEYWORDS = ["试用", "测试", "Side_", "NPC", "未实装", "模特"]


@st.cache_data
def load_options():
    chars = data_loader.get_characters()
    valid_chars = [
        c for c in chars
        if (c.get("name_cn") or c.get("name"))
        and not any(
            kw in (c.get("name_cn") or c.get("name", ""))
            for kw in _CHAR_EXCLUDE_KEYWORDS
        )
    ]
    valid_chars.sort(
        key=lambda c: (c.get("name_cn") or c.get("name", "")).encode("gbk", "ignore")
    )

    char_names = [c.get("name_cn") or c.get("name") for c in valid_chars]
    char_ids = {c.get("name_cn") or c.get("name"): str(c.get("id")) for c in valid_chars}

    wps = data_loader.get_weapons()
    valid_wps = [w for w in wps if w.get("name_cn") and not w["name_cn"].startswith("Weapon_")]
    wp_names = ["无"] + [w.get("name_cn") or w.get("name") for w in valid_wps]
    wp_ids = {w.get("name_cn") or w.get("name"): str(w.get("id")) for w in valid_wps}
    wp_by_type = {}
    for w in valid_wps:
        cn = data_loader.get_weapon_type(str(w.get("id")))
        if cn:
            wp_by_type.setdefault(cn, []).append(
                (w.get("name_cn") or w.get("name"), str(w.get("id")))
            )
    char_wtypes = {
        str(c.get("id")): data_loader.get_character_weapon_type(str(c.get("id")))
        for c in valid_chars
    }

    arts = data_loader.get_artifacts()
    valid_arts = [a for a in arts if (a.get("name_cn") or a.get("name"))]
    art_names = ["无"] + [a.get("name_cn") or a.get("name") for a in valid_arts]
    art_ids = {a.get("name_cn") or a.get("name"): str(a.get("set_id")) for a in valid_arts}

    return char_names, char_ids, wp_names, wp_ids, art_names, art_ids, char_wtypes, wp_by_type


char_names, char_ids, wp_names, wp_ids, art_names, art_ids, char_wtypes, wp_by_type = load_options()


@st.cache_data
def get_artifact_effect(set_id):
    """读取指定套装的 2件套/4件套效果描述，返回 (e2, e4)"""
    if not set_id or set_id == "无":
        return "", ""
    art = data_loader.find_artifact_set(set_id)
    if not art:
        return "", ""
    e2, e4 = "", ""
    for eff in art.get("effects", []):
        if eff.get("pieces") == 2:
            e2 = eff.get("desc", "") or ""
        elif eff.get("pieces") == 4:
            e4 = eff.get("desc", "") or ""
    name_cn = art.get("name_cn") or ""
    mp = data_loader.find_meropide_artifact(name_cn) if name_cn else None
    if mp:
        if (mp.get("set_2_effect") or "").strip():
            e2 = mp["set_2_effect"].strip()
        if (mp.get("set_4_effect") or "").strip():
            e4 = mp["set_4_effect"].strip()
    return e2, e4


@st.cache_data
def get_weapon_base_atk(wid):
    """武器 90 级基础攻击力（用于自动载入基础面板）"""
    if not wid or wid == "无":
        return 0.0
    w = data_loader.find_weapon_by_name(wid)
    return float(w.get("base_atk_90") or 0.0) if w else 0.0


@st.cache_data
def get_character_base_stats(cid):
    """角色 90 级基础面板（用于自动载入基础面板）"""
    if not cid:
        return None
    ch = Character(cid)
    return {
        "base_atk": float(ch.base_atk),
        "base_crit_rate": float(ch.base_crit_rate),
        "base_crit_dmg": float(ch.base_crit_dmg),
        "elemental_mastery": float(ch.elemental_mastery),
    }


# ---------- 图片 / 天赋 / 固有天赋辅助 ----------

@st.cache_data(show_spinner=False)
def _fetch_image(url):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _fetch_image_first(urls):
    for url in urls:
        data = _fetch_image(url)
        if data:
            return data
    return None


def show_icon(kind, obj_id, width=56, suffix=""):
    urls = (
        data_loader.get_icon_url_candidates(kind, obj_id, default_suffix=suffix)
        if obj_id
        else []
    )
    data = _fetch_image_first(tuple(urls)) if urls else None
    if data:
        st.image(data, width=width)
    else:
        st.markdown(
            "<div class='icon-fallback' style='width:%dpx;height:%dpx'></div>"
            % (width, int(width * 0.6)),
            unsafe_allow_html=True,
        )


@st.cache_data(show_spinner=False)
def get_talent_display_cached(char_id):
    return data_loader.get_talent_display(char_id)


@st.cache_data(show_spinner=False)
def load_passive_skills_cached(char_id):
    return data_loader.load_passive_skills(char_id)


def render_talent_info(char_id):
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
    """渲染固有天赋开关列表，返回完整效果结构（已合并启用项）。"""
    effects = {
        "modifiers": {}, "conversions": [], "er_scalings": [],
        "talent_multipliers": {}, "extra_hits": [], "damage_amps": [],
        "stack_context": {}, "active_states": {}, "res_shreds": [],
    }
    char_states = list(data_loader.get_character_states(char_id))
    _all_passives = load_passive_skills_cached(char_id) or []
    for _p in _all_passives:
        for _s in data_loader.detect_required_states(
            _p.get("description") or "", char_states
        ):
            if _s not in char_states:
                char_states.append(_s)
    if char_states:
        with st.expander("状态标签触发判定", expanded=False):
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
        desc = (p.get("description") or "").strip()
        st.markdown(desc.replace("\n", "  \n"), unsafe_allow_html=False)
        if not enabled:
            continue
        if parsed["unparsed"] and not (
            parsed.get("conversion") or parsed.get("er_scaling")
        ):
            st.caption("　↳ 已启用（复杂机制类，暂不参与数值计算）")
            continue

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
                    f"　↳ 血量条件{'满足' if cond_ok else '未满足'}"
                    f"（当前 {hp_now}% / 要求 ≤{ht * 100:g}%）"
                )
            else:
                cond_ok = st.checkbox(
                    "视为满足触发条件", value=True,
                    key=f"cond_{member_idx}_{char_id}_{i}",
                )
            if not cond_ok:
                continue

        for attr, val in parsed["modifiers"].items():
            effects["modifiers"][attr] = effects["modifiers"].get(attr, 0.0) + val
        rs = parsed.get("res_shred")
        if rs:
            entry = {k: v for k, v in rs.items() if k != "text"}
            if entry not in effects["res_shreds"]:
                effects["res_shreds"].append(entry)
            elems = [entry.get("element"), entry.get("element2")]
            elem_txt = "/".join(e for e in elems if e) or "全部元素"
            st.caption(
                f"　↳ 敌人减抗已计入：{elem_txt}抗性 -{entry.get('value', 0) * 100:g}%"
            )
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
    "超激化": "aggravate",
    "蔓激化": "spread",
    "月感电": "lunar_charged",
    "月结晶": "lunar_crystallize",
    "月绽放": "lunar_bloom",
    "星超导": "stellar_superconduct",
    "星扩散(直伤)": "star_swirl_direct",
    "星扩散(风涡)": "star_swirl",
}

REACTION_GROUPS = {
    "无": ["无"],
    "增幅反应": ["蒸发", "融化"],
    "剧变反应": ["超载", "超导", "扩散", "碎冰", "感电"],
    "激化反应": ["超激化", "蔓激化"],
    "月曜反应": ["月感电", "月结晶", "月绽放"],
    "星烁反应": ["星超导", "星扩散(直伤)", "星扩散(风涡)"],
}

SKILL_OPTIONS = {"普通攻击": "normal", "元素战技": "skill", "元素爆发": "burst", "重击": "charged"}

MAIN_SANDS = {"攻击%": "atk_percent", "生命%": "hp_percent", "元素精通": "em", "元素充能%": "er"}
MAIN_GOBLET = {"元素伤害%": "elemental_dmg", "攻击%": "atk_percent", "生命%": "hp_percent"}
MAIN_CIRCLET = {"暴击伤害%": "crit_dmg", "暴击率%": "crit_rate", "攻击%": "atk_percent"}

SKILL_TYPE_KEYS = {"normal": "normal", "skill": "skill", "burst": "burst", "charged": "normal"}
parse_effect = data_loader.parse_effect


def searchable_select(label, all_options, key, default_index=0):
    """带搜索过滤的下拉选择框。返回选中的选项字符串；无匹配时返回 None。"""
    term = st.text_input(f"搜索{label}", key=f"{key}_search").strip().lower()
    if term:
        filtered = [o for o in all_options if term in str(o).lower()]
    else:
        filtered = list(all_options)
    if not filtered:
        st.caption(f"无匹配「{term}」的{label}，请调整搜索词")
        return None
    if key in st.session_state and st.session_state[key] not in filtered:
        del st.session_state[key]
    idx = min(default_index, len(filtered) - 1)
    return st.selectbox(label, filtered, index=idx, key=key)


# ============================================================================
# 成员配置面板（4 名成员 → tab；选角色/武器自动载入基础面板）
# ============================================================================
def member_config_panel(idx):
    """单个队伍成员配置面板，返回成员配置 dict。

    痛点修复：
      - 外层由调用方用 st.tabs 包裹（不再用 expander）
      - 选角色并（可选）选武器后，自动把面板输入框填入
        角色 90 级基础攻击 + 武器 90 级基础攻击、基础暴击/暴伤、基础精通，
        玩家只需在此起点上微调，无需从零手填。
    """
    col_pic, col_sel = st.columns([1, 4])
    with col_sel:
        cname = searchable_select(
            "角色", ["无"] + char_names, f"m{idx}_char",
            default_index=1 if idx == 0 else 0,
        )
        if cname is None:
            cname = "无"
        cid = char_ids.get(cname) if cname != "无" else None
        if cid:
            char_states = data_loader.get_character_states(cid)
            wtype = char_wtypes.get(cid) or data_loader.get_character_weapon_type(cid)
            _tags = []
            if char_states:
                _tags.append(f"🔖 {' · '.join(char_states)}")
            if wtype:
                _tags.append(f"⚔️ {wtype}")
            if _tags:
                st.caption("  ".join(_tags))
    with col_pic:
        show_icon("avatar", cid)

    cfg = {
        "character_id": cid,
        "constellation_level": 0,
        "weapon_id": None, "refinement": 1,
        "artifact_set_2": None, "artifact_set_4": None,
        "is_double_two_piece": False,
        "talent_levels": {"normal": 10, "skill": 10, "burst": 10},
        "panel": {}, "passive_modifiers": {}, "passive_effects": {},
        "states": [],
        "display_name": cname if cid else None,
    }
    if not cid:
        # 无角色时清空自动载入标记
        st.session_state[f"m{idx}_auto_base_for"] = None
        return cfg
    cfg["states"] = data_loader.get_character_states(cid)

    cfg["constellation_level"] = st.slider("命座等级", 0, 6, 0, key=f"m{idx}_cons")

    # ---- 武器（名称 + 图片，仅显示匹配武器类型）----
    wtype = char_wtypes.get(cid) or data_loader.get_character_weapon_type(cid)
    if wtype:
        scoped = wp_by_type.get(wtype)
        if scoped:
            wp_names_sel = ["无"] + [n for n, _ in scoped]
            wp_ids_sel = {n: i for n, i in scoped}
        else:
            wp_names_sel = wp_names
            wp_ids_sel = wp_ids
            st.caption(f"该武器类型「{wtype}」暂无匹配武器，显示全部武器。")
    else:
        wp_names_sel = wp_names
        wp_ids_sel = wp_ids
        st.caption("未知武器类型，显示全部武器。")
    col_wpic, col_wsel = st.columns([1, 4])
    with col_wsel:
        wname = searchable_select("武器", wp_names_sel, f"m{idx}_wp")
        if wname is None:
            wname = "无"
    wid = wp_ids_sel.get(wname) if wname != "无" else None
    with col_wpic:
        show_icon("weapon", wid, width=48)
    cfg["weapon_id"] = wid
    if wid:
        cfg["refinement"] = st.slider("精炼等级", 1, 5, 1, key=f"m{idx}_ref")
        _wp_effect = data_loader.get_weapon_effect(wid, cfg["refinement"])
        if _wp_effect:
            st.caption(f"**{wname}** 被动效果")
            st.write(_wp_effect)
        else:
            st.caption(f"{wname} 无特殊被动效果")

    # ---- 圣遗物（四件套 / 2+2 分支选择）----
    col_apic, col_asel = st.columns([1, 4])
    with col_asel:
        is_22 = st.checkbox("2+2 组合（两个两件套）", key=f"m{idx}_a22")
    cfg["is_double_two_piece"] = is_22
    if is_22:
        with col_asel:
            aA = searchable_select("圣遗物套装①（触发其2件套）", art_names, f"m{idx}_a2")
            if aA is None:
                aA = "无"
            aB = searchable_select("圣遗物套装②（触发其2件套）", art_names, f"m{idx}_a4")
            if aB is None:
                aB = "无"
        sidA = art_ids.get(aA) if aA != "无" else None
        sidB = art_ids.get(aB) if aB != "无" else None
        with col_apic:
            show_icon("relic", sidA, width=48, suffix="_5")
        cfg["artifact_set_2"], cfg["artifact_set_4"] = sidA, sidB
        for nm, sid in ((aA, sidA), (aB, sidB)):
            if sid:
                e2, _ = get_artifact_effect(sid)
                st.caption(f"**{nm} · 2件套**")
                st.write(e2 or "（暂无描述）")
    else:
        with col_asel:
            a4 = searchable_select("圣遗物四件套（自动附带2件套效果）", art_names, f"m{idx}_a4")
            if a4 is None:
                a4 = "无"
        sid4 = art_ids.get(a4) if a4 != "无" else None
        with col_apic:
            show_icon("relic", sid4, width=48, suffix="_5")
        cfg["artifact_set_2"], cfg["artifact_set_4"] = None, sid4
        if sid4:
            e2, e4 = get_artifact_effect(sid4)
            st.caption(f"**{a4} · 四件套（2件套 + 4件套效果同时生效）**")
            st.write("**2件套：** " + (e2 or "（暂无描述）"))
            st.write("**4件套：** " + (e4 or "（暂无描述）"))

    # ---- 天赋等级 + Meropide 天赋信息 ----
    st.markdown("**天赋等级**")
    tl = st.columns(3)
    cfg["talent_levels"]["normal"] = tl[0].slider("普攻", 1, 13, 10, key=f"m{idx}_tn")
    cfg["talent_levels"]["skill"] = tl[1].slider("E技能", 1, 13, 10, key=f"m{idx}_ts")
    cfg["talent_levels"]["burst"] = tl[2].slider("Q技能", 1, 13, 10, key=f"m{idx}_tb")

    with st.expander("天赋信息（Meropide 权威文案）", expanded=(idx == 0)):
        render_talent_info(cid)

    # ---- 固有天赋开关 ----
    st.markdown("**固有天赋**")
    pe = render_passive_toggles(cid, idx)
    cfg["passive_modifiers"] = pe["modifiers"]
    cfg["passive_effects"] = pe

    # ---- 面板属性输入（自动载入基础面板，痛点修复 #3）----
    st.markdown("**面板属性**（已自动载入基础面板，可在此微调）")
    # 自动载入：角色基础攻击 + 武器基础攻击；基础暴击/暴伤/精通
    _auto_for = f"{cid}|{wid}"
    if st.session_state.get(f"m{idx}_auto_base_for") != _auto_for:
        st.session_state[f"m{idx}_auto_base_for"] = _auto_for
        base = get_character_base_stats(cid) or {
            "base_atk": 1000.0, "base_crit_rate": 0.05,
            "base_crit_dmg": 0.5, "elemental_mastery": 0.0,
        }
        _w_atk = get_weapon_base_atk(wid)
        st.session_state[f"m{idx}_atk"] = int(round(base["base_atk"] + _w_atk))
        st.session_state[f"m{idx}_cr"] = round(base["base_crit_rate"] * 100, 1)
        st.session_state[f"m{idx}_cd"] = round(base["base_crit_dmg"] * 100, 1)
        st.session_state[f"m{idx}_em"] = int(base["elemental_mastery"])

    pc1, pc2 = st.columns(2)
    with pc1:
        atk = st.number_input(
            "攻击力（角色基础+武器基础，不含圣遗物）", 0, 5000,
            value=st.session_state.get(f"m{idx}_atk", 1500), key=f"m{idx}_atk",
        )
        cr = st.number_input(
            "暴击率%", 0.0, 100.0,
            value=st.session_state.get(f"m{idx}_cr", 5.0), key=f"m{idx}_cr",
        )
        cd = st.number_input(
            "暴击伤害%", 0.0, 300.0,
            value=st.session_state.get(f"m{idx}_cd", 50.0), key=f"m{idx}_cd",
        )
    with pc2:
        em = st.number_input(
            "元素精通", 0, 1000,
            value=st.session_state.get(f"m{idx}_em", 0), key=f"m{idx}_em",
        )
        ed = st.number_input("元素伤害加成%", 0.0, 300.0, 0.0, key=f"m{idx}_ed",
                             help="杯子主词条+天赋等提供的元素伤害加成（如46.6%火伤杯填46.6）")
        lb = st.number_input("月反应加成%", 0.0, 100.0, 0.0, key=f"m{idx}_lb")
    erp = st.number_input(
        "充能加成%（超出基础的充能效率部分，如200%总充能填100）",
        0.0, 400.0, 0.0, key=f"m{idx}_er",
    )
    cfg["panel"] = {
        "atk": float(atk), "crit_rate_pct": float(cr),
        "crit_dmg_pct": float(cd), "em": float(em),
        "elemental_dmg_bonus_pct": float(ed),
        "lunar_bonus_pct": float(lb), "er_pct": float(erp),
    }
    return cfg


# ============================================================================
# 战斗 / 优化 / 星反应 参数
# ============================================================================
def render_battle_params():
    """渲染敌人 / 反应 / 主力技能 / 星反应参数，返回参数字典。"""
    st.subheader("战斗与优化参数")
    enemy_level = st.slider("敌人等级", 1, 100, 90)
    enemy_res = st.slider("敌人抗性", 0.0, 1.0, 0.1, step=0.05)
    reaction_group = st.selectbox("反应类别", list(REACTION_GROUPS.keys()))
    reaction_opts = REACTION_GROUPS[reaction_group]
    if len(reaction_opts) == 1:
        reaction = reaction_opts[0]
    else:
        reaction = st.selectbox("反应类型", reaction_opts, key="reaction_detail")
    skill_type = st.selectbox("主力技能类型", list(SKILL_OPTIONS.keys()))

    star_cfg = {}
    _rt = REACTION_OPTIONS.get(reaction)
    if _rt in ("stellar_superconduct", "star_swirl", "star_swirl_direct"):
        with st.expander("⭐ 星反应参数", expanded=True):
            if _rt == "stellar_superconduct":
                star_cfg["stellar_stacks"] = st.slider(
                    "星超导附着次数(0/6/12)", 0, 12, 0, step=1,
                    key="star_stellar_stacks",
                )
            if _rt in ("star_swirl", "star_swirl_direct"):
                star_cfg["star_base_boost"] = st.slider(
                    "星扩散/星超导基础提升%", 0.0, 40.0, 14.0, step=1.0,
                    key="star_base_boost",
                ) / 100.0
            if _rt == "star_swirl":
                star_cfg["star_vortex_level"] = st.slider(
                    "星扩散风涡等级(1-6)", 1, 6, 3, step=1,
                    key="star_vortex_level",
                )

    st.divider()
    st.subheader("词条分配方案")
    total_rolls = st.slider("可用有效词条数", 10, 45, 30)
    st.markdown("**候选词条类型**（勾选后系统会在这些属性间分配词条，通过对比伤害找最优分配）")
    sc1, sc2, sc3, sc4 = st.columns(4)
    _sub_atk  = sc1.checkbox("攻击力%", value=True,  key="sub_atk")
    _sub_cr   = sc2.checkbox("暴击率", value=True,   key="sub_cr")
    _sub_cd   = sc3.checkbox("暴击伤害", value=True,  key="sub_cd")
    _sub_em   = sc4.checkbox("元素精通", value=False,  key="sub_em")
    allowed_substats = []
    if _sub_atk: allowed_substats.append("atk_percent")
    if _sub_cr:  allowed_substats.append("crit_rate")
    if _sub_cd:  allowed_substats.append("crit_dmg")
    if _sub_em:  allowed_substats.append("em")
    if not allowed_substats:
        st.warning("请至少勾选一种词条类型")

    min_cr = st.slider("最小暴击率要求", 0.2, 0.8, 0.2, step=0.05)
    sands = st.selectbox("时之沙主词条", list(MAIN_SANDS.keys()))
    goblet = st.selectbox("空之杯主词条", list(MAIN_GOBLET.keys()))
    circlet = st.selectbox("理之冠主词条", list(MAIN_CIRCLET.keys()))

    return {
        "enemy_level": enemy_level, "enemy_res": enemy_res,
        "reaction": reaction, "skill_type": skill_type,
        "star_cfg": star_cfg, "total_rolls": total_rolls, "min_cr": min_cr,
        "sands": sands, "goblet": goblet, "circlet": circlet,
        "allowed_substats": allowed_substats,
    }


# ============================================================================
# 队伍 DPS 轮换编排
# ============================================================================
_REACTION_REV = {v: k for k, v in REACTION_OPTIONS.items()}
if "tdps_rotation" not in st.session_state:
    st.session_state["tdps_rotation"] = [
        s.to_dict() for s in PRESET_ROTATIONS["玛薇卡火神队（示例）"].steps
    ]


def render_rotation_editor():
    st.subheader("⚔️ 队伍DPS 轮换编排（联合优化的输入）")
    st.caption("每个步骤指定：哪个成员出手、用哪个技能、打几段、站场几秒、是否触发反应。"
               "秒数留 0 时自动按默认值。")
    preset_names = ["（自定义）"] + list(PRESET_ROTATIONS.keys())
    preset = st.selectbox("载入主流配队轮换示例", preset_names, key="tdps_preset")
    if preset != "（自定义）" and st.button("载入该示例轮换", key="tdps_load"):
        st.session_state["tdps_rotation"] = [
            s.to_dict() for s in PRESET_ROTATIONS[preset].steps
        ]
        st.rerun()

    _rot = st.session_state["tdps_rotation"]
    _num = st.number_input("步骤数", min_value=0, max_value=30, value=len(_rot), step=1, key="tdps_num")
    while len(_rot) < _num:
        _rot.append({"character_index": 0, "skill_type": "normal", "hit_count": 1,
                     "field_seconds": None, "reaction_type": None, "is_crit": False, "label": ""})
    while len(_rot) > _num:
        _rot.pop()
    st.session_state["tdps_rotation"] = _rot

    _steps_out = []
    _SK = ["normal", "skill", "burst", "charged"]
    for i, _stp in enumerate(_rot):
        c1, c2, c3, c4, c5 = st.columns([1.0, 1.4, 0.9, 1.1, 2.2])
        with c1:
            _ci = st.selectbox("成员", [1, 2, 3, 4], index=int(_stp.get("character_index", 0)), key=f"tdps_ci_{i}")
        with c2:
            _sk = st.selectbox("技能", _SK, index=_SK.index(_stp.get("skill_type", "normal")), key=f"tdps_sk_{i}")
        with c3:
            _hc = st.number_input("段数", 1, 12, int(_stp.get("hit_count", 1)), key=f"tdps_hc_{i}")
        with c4:
            _fs = st.number_input("秒数(0=自动)", 0.0, 30.0, float(_stp.get("field_seconds") or 0.0), step=0.5, key=f"tdps_fs_{i}")
        with c5:
            _opts = ["（无）"] + list(REACTION_OPTIONS.keys())
            _cur = _REACTION_REV.get(_stp.get("reaction_type")) if _stp.get("reaction_type") else "（无）"
            _rk = st.selectbox("反应", _opts, index=_opts.index(_cur) if _cur in _opts else 0, key=f"tdps_rk_{i}")
        _steps_out.append({
            "character_index": int(_ci) - 1,
            "skill_type": _sk,
            "hit_count": int(_hc),
            "field_seconds": (None if _fs == 0 else _fs),
            "reaction_type": (None if _rk == "（无）" else REACTION_OPTIONS[_rk]),
            "is_crit": False,
            "label": f"成员{_ci}·{_sk}",
        })
    return _steps_out


# ============================================================================
# 模式 1：首页
# ============================================================================
def render_home():
    st.markdown(
        """
        <div class="hero">
            <h1>原神伤害计算器</h1>
            <p>基于 Meropide / gensri 权威数据的伤害与配队优化工具 · 选择下方模式开始</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cards = [
        ("🎯", "伤害优化", "选角色自动载入面板，搜索最优副词条分配，给出期望伤害与乘区明细。", "伤害优化"),
        ("👥", "队伍DPS", "编排整队轮换，联合优化 4 名成员词条，追求最高整队 DPS。", "队伍DPS"),
        ("⚡", "反应速查", "Meropide 权威反应公式表 + 小计算器，秒算各类反应伤害系数。", "反应速查"),
        ("📚", "数据速查", "浏览角色 / 武器 / 圣遗物基础数值与套装效果。", "数据速查"),
    ]
    cols = st.columns(2)
    for i, (icon, title, desc, mode) in enumerate(cards):
        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="mode-card">
                    <div class="mc-icon">{icon}</div>
                    <div class="mc-title">{title}</div>
                    <div class="mc-desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"进入「{title}」", key=f"home_{mode}", use_container_width=True):
                st.session_state["_pending_nav"] = mode
                st.rerun()
    st.divider()
    st.caption(
        "说明：角色/武器基础数值来自本地数据（data/*.json），天赋与套装权威文案来自 Meropide。"
        "圣遗物主词条已含于面板数值中，无需单独设置。"
    )


# ============================================================================
# 模式 2：伤害优化
# ============================================================================
def render_optimizer():
    st.subheader("伤害优化")
    st.caption("成员1 为伤害计算主力；其余成员用于月反应加权与元素共鸣（可留空）。"
               "选角色后会自动载入基础面板（角色+武器基础攻击、基础暴击/暴伤）。")

    member_tabs = st.tabs([f"成员{i+1}" + ("（主力）" if i == 0 else "") for i in range(4)])
    team_configs = []
    for i in range(4):
        with member_tabs[i]:
            team_configs.append(member_config_panel(i))

    # 队伍动态状态（初辉/满辉，按月兆角色数量自动计算）
    lunar_count = sum(
        1 for c in team_configs
        if c.get("character_id") and "月兆" in c.get("states", [])
    )
    state_lines = [f"**队伍状态**　月兆角色数量：{lunar_count}"]
    if lunar_count >= 1:
        state_lines.append("**初辉已激活**")
    if lunar_count >= 2:
        state_lines.append("**满辉已激活**")
    st.markdown("　|　".join(state_lines))

    # 参数 + 运行按钮
    with st.container(border=True):
        p = render_battle_params()
        optimize_btn = st.button("开始优化", type="primary")

    if optimize_btn:
        _run_optimizer(team_configs, p)


def _run_optimizer(team_configs, p):
    active_members = [c for c in team_configs if c and c.get("character_id")]
    main_cfg = team_configs[0]

    if not main_cfg.get("character_id"):
        st.error("请先在「成员1」中选择主力角色！")
        return
    _rt = REACTION_OPTIONS[p["reaction"]]
    if _rt in ("lunar_charged", "lunar_crystallize", "lunar_bloom", "star_swirl") and len(active_members) < 1:
        st.error("月/星反应间接伤害需要配置至少1名队伍成员！")
        return
    if p["min_cr"] > 0.95:
        st.error("最小暴击率要求过高（>95%），可能无法找到可行解，请降低。")
        return

    character_name = main_cfg["display_name"]
    talent_key = SKILL_TYPE_KEYS[p["skill_type"]]
    with st.spinner("正在搜索最优属性分配..."):
        try:
            progress_bar = st.progress(0.0, text="优化搜索进行中...")

            def _update_progress(done, total):
                progress_bar.progress(
                    min(1.0, done / max(total, 1)),
                    text=f"优化搜索进行中... {done}/{total} 次迭代",
                )

            input_params = OptimizationInput(
                character_id=main_cfg["character_id"],
                constellation_level=main_cfg["constellation_level"],
                talent_level=main_cfg["talent_levels"][talent_key],
                skill_type=p["skill_type"],
                enemy_level=p["enemy_level"],
                enemy_res=p["enemy_res"],
                reaction_type=_rt,
                weapon_id=main_cfg["weapon_id"],
                stellar_stacks=p["star_cfg"].get("stellar_stacks", 0),
                star_base_boost=p["star_cfg"].get("star_base_boost", 0.0),
                star_vortex_level=p["star_cfg"].get("star_vortex_level", 1),
                artifact_set_2=main_cfg["artifact_set_2"],
                artifact_set_4=main_cfg["artifact_set_4"],
                is_double_two_piece=main_cfg.get("is_double_two_piece", False),
                total_substat_rolls=p["total_rolls"],
                min_crit_rate=p["min_cr"],
                allowed_substats=p.get("allowed_substats") or None,
                main_stats={
                    "sands": MAIN_SANDS[p["sands"]],
                    "goblet": MAIN_GOBLET[p["goblet"]],
                    "circlet": MAIN_CIRCLET[p["circlet"]],
                },
                panel_inputs={k: v for k, v in main_cfg["panel"].items()},
                passive_modifiers=main_cfg["passive_modifiers"],
                passive_effects=main_cfg["passive_effects"],
                team_configs=team_configs,
            )

            optimizer = DamageOptimizer(input_params)
            result = optimizer.optimize(progress_callback=_update_progress)
            progress_bar.empty()

            col1, col2 = st.columns([1, 1])
            with col1:
                st.subheader("最优属性分配")
                os_stats = result.optimal_stats
                alloc = result.allocation
                total_alloc = sum(alloc.values()) or 1

                def _alloc_cell(key):
                    n = alloc.get(key, 0)
                    return f"{n}词条 · {n / total_alloc * 100:.0f}%"

                stats_df = pd.DataFrame({
                    "属性": ["攻击力加成", "暴击率", "暴击伤害", "元素精通"],
                    "最优值": [
                        f"{os_stats['atk_percent']*100:.1f}%",
                        f"{os_stats['crit_rate']*100:.1f}%",
                        f"{os_stats['crit_dmg']*100:.1f}%",
                        f"{os_stats['em']:.0f}",
                    ],
                    "词条分配": [
                        _alloc_cell("atk_percent"),
                        _alloc_cell("crit_rate"),
                        _alloc_cell("crit_dmg"),
                        _alloc_cell("em"),
                    ],
                })
                st.table(stats_df)

                export_data = {
                    "character": character_name,
                    "optimal_stats": {k: round(v, 4) for k, v in os_stats.items()},
                    "allocation": alloc,
                    "max_damage": round(result.max_damage, 2),
                }
                st.download_button(
                    "下载优化结果 (JSON)",
                    data=json.dumps(export_data, ensure_ascii=False, indent=2),
                    file_name="optimization_result.json",
                    mime="application/json",
                )

            with col2:
                st.subheader("伤害预期")
                st.metric("最大期望伤害", f"{result.max_damage:,.2f}")

                st.write("**乘区明细：**")
                bd = result.damage_breakdown
                breakdown_rows = []
                if "base_damage" in bd:
                    breakdown_rows.append(("基础伤害区", bd['base_damage'], False))
                if "dmg_bonus_factor" in bd:
                    breakdown_rows.append(("增伤区", bd['dmg_bonus_factor'], True))
                if "def_factor" in bd:
                    breakdown_rows.append(("防御区", bd['def_factor'], True))
                if "res_factor" in bd:
                    breakdown_rows.append(("抗性区", bd['res_factor'], True))
                if "crit_factor" in bd:
                    breakdown_rows.append(("暴击区", bd['crit_factor'], True))
                if "reaction_factor" in bd:
                    breakdown_rows.append(("反应区", bd['reaction_factor'], True))

                if breakdown_rows:
                    html = '<div style="background:#f8f9fa;border-radius:8px;padding:14px 18px;font-size:0.88rem">'
                    html += '<table style="width:100%;border-collapse:collapse">'
                    for label, val, is_mult in breakdown_rows:
                        color = "#8b5cf6" if is_mult else "#6b7280"
                        prefix = "× " if is_mult else ""
                        formatted = f"{prefix}{val:.4f}" if is_mult else f"{prefix}{val:,.2f}"
                        html += (
                            f'<tr>'
                            f'<td style="padding:4px 0;color:#374151;width:40%">{label}</td>'
                            f'<td style="padding:4px 0;font-weight:600;color:{color};text-align:right">'
                            f'{formatted}</td></tr>'
                        )
                    if "final_damage" in bd:
                        html += (
                            '<tr><td colspan="2" style="border-top:2px solid #d1d5db;padding-top:6px">'
                            f'<span style="font-weight:700;font-size:1rem;color:#059669">'
                            f'最终伤害：{bd["final_damage"]:,.2f}</span></td></tr>'
                        )
                    html += '</table></div>'
                    st.markdown(html, unsafe_allow_html=True)

            st.subheader("培养建议")
            st.info(result.suggestion)

            # ---- Top-N 词条分配排行榜 ----
            if result.top_allocations:
                st.subheader("词条分配排行榜（Top 方案对比）")
                _rank_data = []
                _cn = {"atk_percent": "攻击%", "crit_rate": "暴击率", "crit_dmg": "暴击伤害", "em": "元素精通"}
                for rank_i, ta in enumerate(result.top_allocations):
                    a = ta["alloc"]
                    parts = []
                    for k in ["atk_percent", "crit_rate", "crit_dmg", "em"]:
                        if a[k] > 0:
                            parts.append(f"{_cn[k]} {a[k]}词条")
                    _rank_data.append({
                        "排名": f"#{rank_i+1}",
                        "分配": " · ".join(parts) if parts else "全0",
                        "伤害": f"{ta['damage']:,.2f}",
                    })
                st.dataframe(pd.DataFrame(_rank_data), use_container_width=True, hide_index=True)

            if result.history:
                st.subheader("优化收敛曲线")
                hist_df = pd.DataFrame(result.history).set_index("iteration")
                st.line_chart(hist_df, use_container_width=True)

        except Exception as e:
            st.error(f"优化失败: {e}")


# ============================================================================
# 模式 3：队伍 DPS
# ============================================================================
def render_team_dps():
    st.subheader("队伍DPS 联合优化")
    st.caption("联合搜索全队 4 名成员的副词条分配，使整队轮换 DPS 最高。"
               "轮换步骤在下方「队伍DPS 轮换编排」中编辑。")

    member_tabs = st.tabs([f"成员{i+1}" for i in range(4)])
    team_configs = []
    for i in range(4):
        with member_tabs[i]:
            team_configs.append(member_config_panel(i))

    tdps_steps = render_rotation_editor()

    with st.container(border=True):
        st.subheader("队伍DPS 优化参数")
        member_rolls = st.slider("每名成员总词条数", 10, 45, 20)
        team_iters = st.slider("随机搜索迭代数", 500, 8000, 2500, step=500)
        team_refine = st.slider("局部细化迭代数", 200, 3000, 1000, step=200)
        enemy_level = st.slider("敌人等级", 1, 100, 90, key="tdps_enemy_level")
        enemy_res = st.slider("敌人抗性", 0.0, 1.0, 0.1, step=0.05, key="tdps_enemy_res")
        team_dps_btn = st.button("🚀 开始队伍DPS优化", type="primary")

    if team_dps_btn:
        active = [c for c in team_configs if c and c.get("character_id")]
        if not active:
            st.error("请先在「成员1~4」中配置至少一名队伍成员！")
            return
        if not tdps_steps:
            st.error("轮换步骤不能为空！请在上方「队伍DPS 轮换编排」中添加步骤。")
            return

        char_names_disp = [c.get("display_name") for c in team_configs]
        with st.spinner("联合搜索全队词条分配..."):
            try:
                progress_bar = st.progress(0.0, text="联合优化进行中...")

                def _update_progress(done, total):
                    progress_bar.progress(
                        min(1.0, done / max(total, 1)),
                        text=f"联合优化进行中... {done}/{total} 次迭代",
                    )

                rotation = Rotation(tdps_steps)
                main_ms = {
                    "sands": MAIN_SANDS["攻击%"],
                    "goblet": MAIN_GOBLET["元素伤害%"],
                    "circlet": MAIN_CIRCLET["暴击伤害%"],
                }
                inp = TeamDPSOptimizationInput(
                    team_configs=team_configs,
                    rotation=rotation,
                    total_substat_rolls_per_member=[member_rolls] * 4,
                    main_stats_per_member=[main_ms] * 4,
                    enemy_level=enemy_level,
                    enemy_res=enemy_res,
                    star_params={},
                )
                opt = TeamDPSOptimizer(inp)
                res = opt.optimize(
                    iterations=team_iters,
                    refine_iterations=team_refine,
                    progress_callback=_update_progress,
                )
                progress_bar.empty()

                st.metric("最大队伍 DPS", f"{res.max_dps:,.1f}")
                st.caption(
                    f"轮换总时长 {res.result['total_time']:.1f}s，共 {len(rotation.steps)} 步；"
                    f"每名成员按 {member_rolls} 词条联合优化"
                )

                pc = res.result["per_character"]
                _active_idx = [i for i in range(4) if team_configs[i].get("character_id")]
                _df = pd.DataFrame({
                    "成员": [f"成员{i+1} {char_names_disp[i] or ''}" for i in _active_idx],
                    "总伤害": [pc[i] for i in _active_idx],
                })
                st.bar_chart(_df.set_index("成员"))

                st.subheader("全队最优词条分配")
                for i in _active_idx:
                    a = res.allocations[i]
                    st.write(
                        f"**成员{i+1} · {char_names_disp[i]}**："
                        f"攻击% {a['atk_percent']} · 暴击率 {a['crit_rate']} · "
                        f"暴击伤害 {a['crit_dmg']} · 精通 {a['em']} "
                        f"（共 {sum(a.values())} 词条）"
                    )

                with st.expander("分步伤害明细"):
                    _rows = [
                        {"步骤": s["label"], "伤害": round(s["damage"], 1), "秒数": s["time"]}
                        for s in res.result["per_step"]
                    ]
                    st.table(pd.DataFrame(_rows))

                if res.history:
                    st.subheader("收敛曲线")
                    st.line_chart(pd.DataFrame(res.history).set_index("iteration"))
            except Exception as e:
                st.error(f"队伍DPS优化失败: {e}")


# ============================================================================
# 模式 4：反应速查（Meropide 权威公式表 + 小计算器）
# ============================================================================
# 反应基础值（仅与角色等级有关）
LEVEL_BASE = {70: 765.64, 80: 1077.44, 90: 1446.85, 95: 1561.46, 100: 1674.81}


def reaction_base_value(level):
    ks = sorted(LEVEL_BASE)
    if level <= ks[0]:
        return LEVEL_BASE[ks[0]]
    if level >= ks[-1]:
        return LEVEL_BASE[ks[-1]]
    for i in range(len(ks) - 1):
        a, b = ks[i], ks[i + 1]
        if a <= level <= b:
            t = (level - a) / (b - a)
            return LEVEL_BASE[a] + t * (LEVEL_BASE[b] - LEVEL_BASE[a])


# 反应系数速查表（来自 constants.py / meropide 权威值）
REACTION_COEFF_TABLE = [
    ("增幅基础系数", "水打火 / 火打冰", "2", "蒸发(水→火) / 融化(冰→火)"),
    ("增幅基础系数", "火打水 / 冰打火", "1.5", "蒸发(火→水) / 融化(火→冰)"),
    ("激化基础系数", "超激化", "1.15", "雷元素触发"),
    ("激化基础系数", "蔓激化", "1.25", "草元素触发"),
    ("剧变基础系数", "燃烧", "0.25", ""),
    ("剧变基础系数", "扩散", "0.6", ""),
    ("剧变基础系数", "超导", "1.5", ""),
    ("剧变基础系数", "感电", "2", ""),
    ("剧变基础系数", "绽放", "2", ""),
    ("剧变基础系数", "超载", "2.75", ""),
    ("剧变基础系数", "碎冰", "3", ""),
    ("剧变基础系数", "烈绽放 / 超绽放", "3", ""),
    ("月曜基础系数", "月绽放", "1", ""),
    ("月曜基础系数", "月感电", "3", ""),
    ("月曜基础系数", "月结晶", "1.6", ""),
    ("星烁基础系数", "直伤星扩散", "1", ""),
    ("星烁基础系数", "反应星扩散·冰", "2（风旋1/2级）；3（风旋≥3级）", ""),
    ("星烁基础系数", "反应星扩散·风", "0.75", ""),
]

REACTION_EM_FORMULA = [
    ("剧变反应精通增益", "16 × EM / (EM + 2000)"),
    ("增幅反应精通增益", "2.78 × EM / (EM + 1400)"),
    ("激化固定增伤精通增益", "5 × EM / (EM + 1200)"),
    ("月曜 / 星烁精通增益", "6 × EM / (EM + 2000)"),
]

# 计算器用反应项：(标签, 类别, 系数)
REACTION_CALC = [
    ("蒸发（水打火）", "amplify", 2.0),
    ("蒸发（火打水）", "amplify", 1.5),
    ("融化（冰打火）", "amplify", 1.5),
    ("融化（火打冰）", "amplify", 2.0),
    ("超激化", "quicken", 1.15),
    ("蔓激化", "quicken", 1.25),
    ("超载", "transform", 2.75),
    ("超导", "transform", 1.5),
    ("扩散", "transform", 0.6),
    ("碎冰", "transform", 3.0),
    ("感电", "transform", 2.0),
    ("燃烧", "transform", 0.25),
    ("绽放", "transform", 2.0),
    ("超绽放", "transform", 3.0),
    ("烈绽放", "transform", 3.0),
    ("月感电", "lunar", 3.0),
    ("月结晶", "lunar", 1.6),
    ("月绽放", "lunar", 1.0),
    ("星超导（直伤）", "stellar_sc", None),
    ("星扩散·风（反应）", "stellar_wind", 0.75),
    ("星扩散·冰（反应）", "stellar_ice", None),
    ("星扩散（直伤）", "stellar_direct", 1.0),
]


def render_reaction_ref():
    st.subheader("反应速查")
    st.caption("数据来源：Meropide《伤害公式》权威页面。下列公式与系数均对照 meropide / gensri 校验。")

    tab_formula, tab_calc = st.tabs(["📐 公式与系数表", "🧮 反应小计算器"])

    with tab_formula:
        st.markdown("**普通伤害**：`伤害 = (倍率 × 属性 × 普通大权区 + 普通羽毛区 + 激化固定增伤) × (1 + 暴击率×暴击伤害) × (1 + 普通增伤) × 抗性系数 × 防御系数 × 增幅系数`")
        st.markdown("**剧变伤害**：`剧变伤害 = (反应基础值 × 剧变基础系数 × (1 + 16×EM/(EM+2000) + 剧变增伤) + 剧变羽毛区) × 抗性系数`")
        st.markdown("**激化固定增伤**：`反应基础值 × 激化基础系数 × (1 + 5×EM/(EM+1200) + 激化增伤)`")
        st.markdown("**增幅系数**：`增幅基础系数 × (1 + 2.78×EM/(EM+1400) + 增幅增伤)`")
        st.markdown("**月曜/星烁精通增益**：`6×EM/(EM+2000)`（与剧变结构相同，改用月曜/星烁基础系数）")

        st.divider()
        st.markdown("**反应基础值（仅与角色等级有关）**")
        base_df = pd.DataFrame(
            [("70", "765.64"), ("80", "1077.44"), ("90", "1446.85"),
             ("95", "1561.46"), ("100", "1674.81")],
            columns=["等级", "反应基础值"],
        )
        st.table(base_df)

        st.markdown("**反应系数速查**")
        coeff_df = pd.DataFrame(
            [(a, b, c, d) for a, b, c, d in REACTION_COEFF_TABLE],
            columns=["类型", "反应", "系数", "备注"],
        )
        st.table(coeff_df)

        st.markdown("**精通增益公式**")
        em_df = pd.DataFrame(
            [(a, b) for a, b in REACTION_EM_FORMULA],
            columns=["增益类型", "公式"],
        )
        st.table(em_df)

        st.markdown("**抗性系数** `H = 1-R (0≤R<75%)；1-R/2 (R<0)；1/(1+4R) (R≥75%)`")
        st.markdown("**防御系数** `(角色等级+100) / ((角色等级+100) + (怪物等级+100)×(1-减防)×(1-无视防御))`")

    with tab_calc:
        st.markdown("选择一个反应，输入角色等级 / 元素精通 / 敌人抗性，快速估算其伤害系数。")
        rlabel = st.selectbox("反应类型", [r[0] for r in REACTION_CALC])
        rcfg = next(r for r in REACTION_CALC if r[0] == rlabel)
        rcat, rcoeff = rcfg[1], rcfg[2]

        c1, c2, c3 = st.columns(3)
        with c1:
            level = st.slider("角色等级", 70, 100, 90, key="rc_level")
        with c2:
            em = st.number_input("元素精通 EM", 0, 2000, 0, key="rc_em")
        with c3:
            res = st.slider("敌人抗性", -1.0, 1.0, 0.1, step=0.05, key="rc_res")

        # 额外增伤（对应公式中的 剧变增伤 / 增幅增伤 / 月曜增伤 / 星烁增伤）
        bonus = st.number_input(
            "额外增伤%（剧变/增幅/月曜/星烁增伤）", 0.0, 200.0, 0.0, key="rc_bonus"
        ) / 100.0

        base = reaction_base_value(level)
        res_factor = constants.resistance_factor(res)

        out_lines = []
        result_val = None
        if rcat == "amplify":
            val = rcoeff * (1 + constants.em_bonus_amplifying(em) + bonus)
            out_lines.append(f"增幅系数 = {rcoeff} × (1 + {constants.em_bonus_amplifying(em):.4f} + {bonus:.4f}) = **{val:.4f}**")
            result_val = val
        elif rcat == "quicken":
            val = base * rcoeff * (1 + 5 * em / (em + 1200) + bonus)
            out_lines.append(f"激化固定增伤 = {base:.2f} × {rcoeff} × (1 + {5*em/(em+1200):.4f} + {bonus:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "transform":
            val = (base * rcoeff * (1 + constants.em_bonus_transformative(em) + bonus)) * res_factor
            out_lines.append(f"剧变伤害(未×抗性前) = {base:.2f} × {rcoeff} × (1 + {constants.em_bonus_transformative(em):.4f} + {bonus:.4f}) = {base*rcoeff*(1+constants.em_bonus_transformative(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "lunar":
            val = (base * rcoeff * (1 + constants.em_bonus_lunar(em) + bonus)) * res_factor
            out_lines.append(f"月曜反应伤害(未×抗性前) = {base:.2f} × {rcoeff} × (1 + {constants.em_bonus_lunar(em):.4f} + {bonus:.4f}) = {base*rcoeff*(1+constants.em_bonus_lunar(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "stellar_direct":
            val = (base * rcoeff * (1 + constants.em_bonus_star(em) + bonus)) * res_factor
            out_lines.append(f"直伤星烁伤害(未×抗性前) = {base:.2f} × {rcoeff} × (1 + {constants.em_bonus_star(em):.4f} + {bonus:.4f}) = {base*rcoeff*(1+constants.em_bonus_star(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "stellar_wind":
            val = (base * rcoeff * (1 + constants.em_bonus_star(em) + bonus)) * res_factor
            out_lines.append(f"反应星扩散·风伤害(未×抗性前) = {base:.2f} × {rcoeff} × (1 + {constants.em_bonus_star(em):.4f} + {bonus:.4f}) = {base*rcoeff*(1+constants.em_bonus_star(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "stellar_ice":
            vortex = st.slider("风旋等级系数(1-6)", 1, 6, 3, key="rc_vortex")
            ice_coeff = 3.0 if vortex >= 3 else 2.0
            val = (base * ice_coeff * (1 + constants.em_bonus_star(em) + bonus)) * res_factor
            out_lines.append(f"反应星扩散·冰系数(风旋{vortex}级) = {ice_coeff}")
            out_lines.append(f"伤害(未×抗性前) = {base:.2f} × {ice_coeff} × (1 + {constants.em_bonus_star(em):.4f} + {bonus:.4f}) = {base*ice_coeff*(1+constants.em_bonus_star(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val
        elif rcat == "stellar_sc":
            stacks = st.slider("星超导附着层数(0-12)", 0, 12, 0, step=1, key="rc_stacks")
            sp = constants.stellar_superconduct_params(stacks)
            sc_coeff = sp["reaction_coef"]
            val = (base * sc_coeff * (1 + constants.em_bonus_star(em) + bonus)) * res_factor
            out_lines.append(f"星超导系数(层数{stacks}) = {sc_coeff}（雷/冰伤加成 {sp['dmg_bonus']*100:.0f}%）")
            out_lines.append(f"伤害(未×抗性前) = {base:.2f} × {sc_coeff} × (1 + {constants.em_bonus_star(em):.4f} + {bonus:.4f}) = {base*sc_coeff*(1+constants.em_bonus_star(em)+bonus):.2f}")
            out_lines.append(f"× 抗性系数({res_factor:.4f}) = **{val:.2f}**")
            result_val = val

        for ln in out_lines:
            st.markdown(ln)
        if result_val is not None:
            st.metric("估算结果", f"{result_val:,.2f}")


# ============================================================================
# 模式 5：数据速查（角色 / 武器 / 圣遗物浏览）
# ============================================================================
@st.cache_data
def get_weapon_browse():
    wps = data_loader.get_weapons()
    out = []
    for w in wps:
        if not w.get("name_cn") or w["name_cn"].startswith("Weapon_"):
            continue
        out.append({
            "id": str(w.get("id")),
            "name_cn": w.get("name_cn"),
            "weapon_type": data_loader.get_weapon_type(str(w.get("id"))),
            "rank": w.get("rank"),
            "base_atk_90": w.get("base_atk_90"),
            "sub_stat": w.get("sub_stat"),
            "desc": (w.get("desc") or "").strip(),
        })
    out.sort(key=lambda x: (x["name_cn"] or "").encode("gbk", "ignore"))
    return out


@st.cache_data
def get_artifact_browse():
    arts = data_loader.get_artifacts()
    out = [a for a in arts if (a.get("name_cn") or a.get("name"))]
    out.sort(key=lambda x: (x.get("name_cn") or x.get("name") or "").encode("gbk", "ignore"))
    return out


_ELEMENT_CN = {"Fire": "火", "Water": "水", "Grass": "草", "Electric": "雷",
               "Ice": "冰", "Wind": "风", "Rock": "岩", "None": "物理"}


def render_data_browse():
    st.subheader("数据速查")
    st.caption("浏览角色 / 武器 / 圣遗物的基础数值与套装效果（数据来自本地 data/*.json）。")

    tab_char, tab_wp, tab_art = st.tabs(["角色", "武器", "圣遗物"])

    with tab_char:
        cname = searchable_select("角色", char_names, "db_char")
        if cname:
            cid = char_ids.get(cname)
            ch = Character(cid)
            c1, c2 = st.columns([1, 4])
            with c1:
                show_icon("avatar", cid, width=96)
            with c2:
                elem = _ELEMENT_CN.get(ch.element, ch.element)
                wtype = char_wtypes.get(cid) or data_loader.get_character_weapon_type(cid)
                st.markdown(f"**{cname}**  ｜  {elem}元素  ｜  {wtype or '？'}")
                if ch.states:
                    st.caption("🔖 " + " · ".join(ch.states))
                st.markdown(
                    f"基础攻击 `{ch.base_atk:.0f}` ｜ 基础生命 `{ch.base_hp:.0f}` ｜ "
                    f"基础防御 `{ch.base_def:.0f}` ｜ 暴击 `{ch.base_crit_rate*100:.1f}%` ｜ "
                    f"暴伤 `{ch.base_crit_dmg*100:.1f}%`"
                )
            with st.expander("天赋信息（Meropide 权威文案）", expanded=True):
                render_talent_info(cid)

    with tab_wp:
        wp_list = get_weapon_browse()
        wp_options = [w["name_cn"] for w in wp_list]
        wsel = searchable_select("武器", wp_options, "db_wp")
        if wsel:
            w = next(x for x in wp_list if x["name_cn"] == wsel)
            c1, c2 = st.columns([1, 4])
            with c1:
                show_icon("weapon", w["id"], width=96)
            with c2:
                st.markdown(f"**{w['name_cn']}**  ｜  {w['weapon_type'] or '？'} ｜  "
                            f"{'★' * int(w['rank'] or 0)}")
                st.markdown(f"90级基础攻击 `{w['base_atk_90']}` ｜ 副属性 `{w['sub_stat'] or '无'}`")
            st.caption(f"{w['desc']}")
            eff = data_loader.get_weapon_effect(w["id"], 1)
            if eff:
                st.markdown("**被动效果**")
                st.write(eff)

    with tab_art:
        art_list = get_artifact_browse()
        art_options = [a.get("name_cn") or a.get("name") for a in art_list]
        asel = searchable_select("圣遗物套装", art_options, "db_art")
        if asel:
            aid = art_ids.get(asel)
            art = data_loader.find_artifact_set(aid) if aid else None
            if art:
                c1, c2 = st.columns([1, 4])
                with c1:
                    show_icon("relic", aid, width=96, suffix="_5")
                with c2:
                    st.markdown(f"**{asel}**")
                e2, e4 = get_artifact_effect(aid)
                if e2:
                    st.markdown("**2件套**")
                    st.write(e2)
                if e4:
                    st.markdown("**4件套**")
                    st.write(e4)


def _scan_local_bg_images():
    """扫描 Steam 壁纸工作坊路径，返回 [(文件名, 完整路径)] 的可选背景列表。"""
    _base = r"E:\SteamLibrary\steamapps\workshop\content\431960\3305687727"
    _imgs = []
    if os.path.isdir(_base):
        for _fn in os.listdir(_base):
            if _fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
                _imgs.append((_fn, os.path.join(_base, _fn)))
    _imgs.sort()
    return _imgs


def _scan_local_videos():
    """扫描 Steam 壁纸工作坊路径，返回 [(文件名, 完整路径)] 的可选视频列表。"""
    _base = r"E:\SteamLibrary\steamapps\workshop\content\431960\3305687727"
    _vids = []
    if os.path.isdir(_base):
        for _fn in os.listdir(_base):
            if _fn.lower().endswith((".mp4", ".webm", ".ogg", ".mov")):
                _vids.append((_fn, os.path.join(_base, _fn)))
    _vids.sort()
    return _vids


# ============================================================================
# 左侧导航 + 模式分发
# ============================================================================
MODES = ["首页", "伤害优化", "队伍DPS", "反应速查", "数据速查"]

with st.sidebar:
    st.markdown("### 🎮 原神伤害计算器")
    st.session_state.setdefault("nav_mode", "首页")
    # 处理首页卡片跳转（deferred，避免与 widget key 冲突）
    if "_pending_nav" in st.session_state:
        st.session_state["nav_mode"] = st.session_state.pop("_pending_nav")
    nav_mode = st.radio("导航", MODES, index=MODES.index(st.session_state["nav_mode"]),
                        key="nav_mode")
    st.divider()
    with st.expander("背景设置", expanded=False):
        bg_mode = st.radio("选择背景", ["简约渐变", "深色渐变", "Steam 壁纸", "视频背景", "自定义图片"],
 horizontal=True)
        uploaded_bg = None
        local_bg_path = None
        video_path = None
        if bg_mode == "自定义图片":
            uploaded_bg = st.file_uploader("上传背景图", type=["jpg", "jpeg", "png", "webp"])
        elif bg_mode == "Steam 壁纸":
            _imgs = _scan_local_bg_images()
            if _imgs:
                _sel = st.selectbox("选择壁纸", [n for n, _ in _imgs])
                local_bg_path = dict(_imgs)[_sel]
            else:
                st.caption("未在 Steam 壁纸目录找到图片文件")
        elif bg_mode == "视频背景":
            _vids = _scan_local_videos()
            _custom = st.text_input("或手动输入视频文件路径", placeholder=r"E:\...\furina_loop.mp4")
            if _custom and os.path.isfile(_custom):
                video_path = _custom
            elif _vids:
                _sel = st.selectbox("选择视频", [n for n, _ in _vids])
                video_path = dict(_vids)[_sel]
            else:
                st.caption("未在默认目录找到视频，请手动填写导出后的视频路径")

# 模式分发
if nav_mode == "首页":
    render_home()
elif nav_mode == "伤害优化":
    render_optimizer()
elif nav_mode == "队伍DPS":
    render_team_dps()
elif nav_mode == "反应速查":
    render_reaction_ref()
elif nav_mode == "数据速查":
    render_data_browse()

# ---------- 动态背景（跟随侧边栏「背景设置」，置于文件尾以覆盖静态默认样式） ----------
# 毛玻璃覆盖层：图片/视频背景时自动附加，保证文字在复杂背景上清晰可读
_GLASS_OVERLAY = (
    "section.main > div.block-container {"
    " background: rgba(255, 255, 255, 0.35) !important;"
    " backdrop-filter: blur(16px) saturate(160%);"
    " -webkit-backdrop-filter: blur(16px) saturate(160%);"
    " border-radius: 12px;"
    " border: 1px solid rgba(255, 255, 255, 0.30);"
    " box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);"
    "}"
)
_bg_html = ""
if bg_mode == "自定义图片" and uploaded_bg is not None:
    _bg_data_url = (
        f"data:{uploaded_bg.type or 'image/png'};base64,"
        + base64.b64encode(uploaded_bg.getvalue()).decode()
    )
    _bg_css = (
        ".stApp {"
        f"background-image: url(\"{_bg_data_url}\");"
        "background-size: cover; background-position: center;"
        "background-attachment: fixed; background-repeat: no-repeat;}"
    ) + _GLASS_OVERLAY
elif bg_mode == "Steam 壁纸" and local_bg_path and os.path.exists(local_bg_path):
    try:
        with open(local_bg_path, "rb") as _f:
            _bg_bytes = _f.read()
        _ext = os.path.splitext(local_bg_path)[1].lower().lstrip(".")
        _mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                 "png": "image/png", "webp": "image/webp",
                 "gif": "image/gif", "bmp": "image/bmp"}.get(_ext, "image/jpeg")
        _bg_data_url = f"data:{_mime};base64," + base64.b64encode(_bg_bytes).decode()
        _bg_css = (
            ".stApp {"
            f"background-image: url(\"{_bg_data_url}\");"
            "background-size: cover; background-position: center;"
            "background-attachment: fixed; background-repeat: no-repeat;}"
        ) + _GLASS_OVERLAY
    except Exception:
        _bg_css = ""
elif bg_mode == "视频背景" and video_path and os.path.exists(video_path):
    try:
        with open(video_path, "rb") as _f:
            _vbytes = _f.read()
        _vext = os.path.splitext(video_path)[1].lower().lstrip(".")
        _vmime = {"mp4": "video/mp4", "webm": "video/webm",
                  "ogg": "video/ogg", "mov": "video/mp4"}.get(_vext, "video/mp4")
        _vurl = f"data:{_vmime};base64," + base64.b64encode(_vbytes).decode()
        # 让 .stApp 透明，视频固定在最底层铺满视口，主内容区加毛玻璃
        _bg_css = (
            ".stApp { background: transparent !important; }"
            "video.bg-video { position: fixed; top: 0; left: 0;"
            " width: 100vw; height: 100vh; object-fit: cover; z-index: -1; }"
        ) + _GLASS_OVERLAY
        _bg_html = (
            f'<video class="bg-video" autoplay loop muted playsinline>'
            f'<source src="{_vurl}" type="{_vmime}"></video>'
        )
    except Exception:
        _bg_css = ""
        _bg_html = ""
elif bg_mode == "深色渐变":
    _bg_css = (
        ".stApp {"
        "background-image: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);}"
    )
elif bg_mode == "简约渐变":
    _bg_css = (
        ".stApp {"
        "background-image: url(\"app/static/furina_rain_bg.webp\");"
        "background-color: transparent !important;"
        "background-size: cover; background-position: center;"
        "background-attachment: fixed; background-repeat: no-repeat;}"
    ) + (
        "section.main > div.block-container {"
        " background: rgba(255, 255, 255, 0.35) !important;"
        " backdrop-filter: blur(16px) saturate(160%);"
        " -webkit-backdrop-filter: blur(16px) saturate(160%);"
        " border-radius: 12px;"
        " border: 1px solid rgba(255, 255, 255, 0.30);"
        " box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);}"
    )
else:
    _bg_css = ""

if _bg_css:
    st.markdown(f"<style>{_bg_css}</style>", unsafe_allow_html=True)
if _bg_html:
    st.markdown(_bg_html, unsafe_allow_html=True)
