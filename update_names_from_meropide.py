#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
update_names_from_meropide.py

用权威数据源更新主数据文件的官方中文名：
1. data/characters.json 的 name_cn —— 两级匹配：
   ① name_cn 与 meropide name 精确相等（校验一致性）
   ② 未匹配者按 (元素, 武器类型, 稀有度) 指纹匹配，多候选用名称相似度消歧，
      无法消歧时查 CURATED_MAP（已对照 meropide 称号逐一核实）
   - 旅行者（空/荧）：meropide 按元素分页，按任务要求跳过不处理
2. data/artifacts.json 的 name_cn —— 本地无任何名称且 TextMap 哈希不可解析，
   改用 Project Amber/Yatta API（gi.yatta.moe/api/v2/chs/reliquary），
   其条目键即真实游戏 setId，可直接精确映射；并用 meropide 数据交叉核对。

运行前自动备份原文件为 *.bak。
"""

import difflib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
MP_DIR = os.path.join(DATA, "meropide")

# 本地枚举 -> meropide 中文
ELEMENT_MAP = {
    "Fire": "火", "Water": "水", "Wind": "风", "Electric": "雷",
    "Grass": "草", "Ice": "冰", "Rock": "岩", "None": "物理",
}
WEAPON_MAP = {
    "WEAPON_SWORD_ONE_HAND": "单手剑",
    "WEAPON_CLAYMORE": "双手剑",
    "WEAPON_POLE": "长柄武器",
    "WEAPON_BOW": "弓",
    "WEAPON_CATALYST": "法器",
}
RARITY_MAP = {
    "QUALITY_ORANGE": 5,
    "QUALITY_ORANGE_SP": 5,   # 埃洛伊（联动特殊五星）
    "QUALITY_PURPLE": 4,
    "QUALITY_BLUE": 3,
}

TRAVELER_IDS = {"10000005", "10000007"}  # 空 / 荧

# 指纹碰撞且名称相似度无法消歧的人工核对映射
# （已逐一对照 meropide 页面称号验证：菈乌玛=永月的祀歌、菲林斯=诡灯陌影、
#   伊涅芙=轰隆雷鸣波、奈芙尔=湮沙的秘闻）
CURATED_MAP = {
    "10000119": "菈乌玛",   # Lauma（草 法器 5★）
    "10000120": "菲林斯",   # Flins（雷 长柄武器 5★）
    "10000116": "伊涅芙",   # 伊涅法 Ineffa（雷 长柄武器 5★）
    "10000122": "奈芙尔",   # 妮菲尔（草 法器 5★）
    "10000126": "兹白",     # Zibai（岩 单手剑 5★，与旅行者（岩）指纹相同，按名称判定）
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup(path):
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  [备份] {path} -> {bak}")


# ==================== 角色 ====================

def char_fingerprint(element, weapon_type, quality):
    return (
        ELEMENT_MAP.get(str(element).split(".")[-1], element),
        WEAPON_MAP.get(weapon_type, weapon_type),
        RARITY_MAP.get(quality, quality),
    )


def update_characters():
    print("=" * 60)
    print("一、更新 data/characters.json 的 name_cn")
    chars_path = os.path.join(DATA, "characters.json")
    backup(chars_path)

    chars = load_json(chars_path)
    mp_chars = load_json(os.path.join(MP_DIR, "characters_meropide.json"))["items"]
    mp_by_name = {m["name"]: m for m in mp_chars}

    exact = fixed_by_fp = fixed_curated = skipped_traveler = failed = 0
    fp_changes = []
    pending = []
    for c in chars:
        cn = c.get("name_cn") or ""
        if str(c["id"]) in TRAVELER_IDS or str(c.get("element")) == "None":
            skipped_traveler += 1
            continue
        if cn in mp_by_name:
            exact += 1
            continue
        pending.append(c)

    # 指纹匹配：候选池 = meropide 中未被精确匹配占用的条目；
    # 唯一候选直接采用；多候选时用名称相似度消歧；仍无法判定则查 CURATED_MAP
    local_names = {c.get("name_cn") for c in chars}
    mp_pool = [m for m in mp_chars if m["name"] not in local_names]
    used_mp_names = set()
    for c in pending:
        cid = str(c["id"])
        old = c["name_cn"]
        if cid in CURATED_MAP:
            c["name_cn"] = CURATED_MAP[cid]
            used_mp_names.add(CURATED_MAP[cid])
            fixed_curated += 1
            fp_changes.append((cid, old, c["name_cn"], "人工核对"))
            continue
        fp = char_fingerprint(c["element"], c["weapon_type"], c["quality"])
        cands = [m for m in mp_pool
                 if char_fingerprint(m["element"], m["weapon_type"], int(m["rarity"])) == fp
                 and m["name"] not in used_mp_names]
        if not cands:
            failed += 1
            print(f"  [跳过] id={cid} {old}: 指纹 {fp} 无候选")
            continue
        if len(cands) == 1:
            m = cands[0]
            how = "指纹唯一"
        else:
            ranked = sorted(cands, key=lambda m: -difflib.SequenceMatcher(
                None, old.lower(), m["name"]).ratio())
            best, second = ranked[0], ranked[1]
            b_sim = difflib.SequenceMatcher(None, old.lower(), best["name"]).ratio()
            s_sim = difflib.SequenceMatcher(None, old.lower(), second["name"]).ratio()
            if b_sim > s_sim:
                m, how = best, f"相似度消歧 ({b_sim:.2f}>{s_sim:.2f})"
            else:
                failed += 1
                print(f"  [跳过] id={cid} {old}: 候选 {[m['name'] for m in cands]} 无法消歧")
                continue
        c["name_cn"] = m["name"]
        used_mp_names.add(m["name"])
        fixed_by_fp += 1
        fp_changes.append((cid, old, m["name"], how))

    save_json(chars, chars_path)
    print(f"  精确一致: {exact} 个")
    print(f"  旅行者(空/荧): 跳过 {skipped_traveler} 个（meropide 为元素分页，保持原状）")
    print(f"  指纹/消歧修正: {fixed_by_fp} 个，人工核对修正: {fixed_curated} 个")
    for cid, old, new, how in fp_changes:
        print(f"    {cid}: {old} -> {new}  [{how}]")
    if failed:
        print(f"  [!] 未解决: {failed} 个（需人工指定映射）")


# ==================== 圣遗物 ====================


def update_artifacts():
    print("=" * 60)
    print("二、更新 data/artifacts.json 的 name_cn")
    arts_path = os.path.join(DATA, "artifacts.json")
    backup(arts_path)

    arts = load_json(arts_path)
    mp_arts = load_json(os.path.join(MP_DIR, "artifacts_meropide.json"))["items"]

    # 权威数据源：Project Amber/Yatta API（以真实游戏 setId 为键的官方中文名）
    # 本地缓存缺失时自动下载
    yatta_path = os.path.join(ROOT, ".cache", "yatta_reliquary.json")
    if not os.path.exists(yatta_path):
        import urllib.request
        url = "https://gi.yatta.moe/api/v2/chs/reliquary"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        items = data["data"]["items"]
        with open(yatta_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        print(f"  [下载] Yatta reliquary 数据 -> {yatta_path}（{len(items)} 个套装）")
    yatta = load_json(yatta_path)

    mp_names = {m["set_name"] for m in mp_arts}
    matched = 0
    missing_in_yatta = []
    not_on_meropide = []
    for a in arts:
        sid = str(a["set_id"])
        info = yatta.get(sid)
        if not info or not info.get("name"):
            missing_in_yatta.append(a["set_id"])
            continue
        name = info["name"]
        a["name_cn"] = name
        matched += 1
        if name not in mp_names:
            not_on_meropide.append(f"{sid}:{name}")

    print(f"  匹配成功: {matched} / {len(arts)}（数据源：gi.yatta.moe 官方数据）")
    if missing_in_yatta:
        print(f"  [!] Yatta 无此 setId（疑似内部测试套装）: {missing_in_yatta}")
    if not_on_meropide:
        print(f"  [i] 有名称但 meropide 未收录: {not_on_meropide}")
    # 反向核对：meropide 收录但本地没有的套装
    local_names = {a.get("name_cn") for a in arts}
    extra_mp = [m["set_name"] for m in mp_arts if m["set_name"] not in local_names]
    if extra_mp:
        print(f"  [i] meropide 收录但本地无对应 setId: {extra_mp}")
    save_json(arts, arts_path)


# ==================== 主流程 ====================

if __name__ == "__main__":
    update_characters()
    update_artifacts()
    print("=" * 60)
    print("完成。原文件已备份为 *.bak；如需回滚直接改回文件名即可。")

