"""
update_weapon_names.py

更新 data/weapons.json 的官方中文武器名，并生成图标映射表 data/icons.json。

数据源说明：
- meropide 的 weapons_meropide.json 无武器 ID 与英文名（仅中文名/稀有度/面板文本），
  无法可靠匹配，仅用于交叉核对数量。
- 因此采用 Project Amber/Yatta API（gi.yatta.moe/api/v2/chs/weapon），
  其条目键即真实游戏 weaponId，可直接按 ID 精确映射（与圣遗物 setId 方案一致）。

产物：
1. data/weapons.json —— name_cn 字段修复
2. data/icons.json   —— {avatar: {id: 图标名}, weapon: {...}, relic: {setId: 图标名}}
   图片直链模板：https://enka.network/ui/{图标名}.png
"""

import json
import os
import shutil
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache")


def backup(path):
    if os.path.exists(path):
        bak = path + ".bak"
        shutil.copy2(path, bak)
        print(f"  [备份] {os.path.basename(path)} -> {os.path.basename(bak)}")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def fetch_yatta(kind, api_path):
    """下载 Yatta 数据（优先使用本地缓存）"""
    cache_path = os.path.join(CACHE, f"yatta_{kind}.json")
    if os.path.exists(cache_path):
        return load_json(cache_path)
    url = f"https://gi.yatta.moe/api/v2/chs/{api_path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    items = data["data"]["items"]
    os.makedirs(CACHE, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"  [下载] Yatta {kind} -> {cache_path}（{len(items)} 条）")
    return items


def main():
    print("=" * 60)
    print("一、修复 data/weapons.json 的 name_cn")
    yatta_w = fetch_yatta("weapon", "weapon")

    wp_path = os.path.join(DATA, "weapons.json")
    backup(wp_path)
    weapons = load_json(wp_path)

    matched = unmatched = 0
    for w in weapons:
        info = yatta_w.get(str(w["id"]))
        if info and info.get("name"):
            w["name_cn"] = info["name"]
            matched += 1
        else:
            unmatched += 1
            print(f"  [!] 无匹配: id={w['id']}（保留原值 {w['name_cn']!r}）")
    print(f"  匹配成功 {matched}/{len(weapons)}，未匹配 {unmatched}")
    save_json(weapons, wp_path)

    # 交叉核对 meropide 数量
    try:
        mp = load_json(os.path.join(DATA, "meropide", "weapons_meropide.json"))
        mp_items = mp["items"] if isinstance(mp, dict) else mp
        mp_names = {m["name"] for m in mp_items}
        named = {w["name_cn"] for w in weapons}
        missing = mp_names - named
        print(f"  [i] meropide 收录 {len(mp_items)} 把武器，其中本地未覆盖: "
              f"{sorted(missing) if missing else '无'}")
    except Exception as e:
        print(f"  [i] 跳过 meropide 交叉核对: {e}")

    print("=" * 60)
    print("二、生成 data/icons.json（enka CDN 图标映射）")
    yatta_a = fetch_yatta("avatar", "avatar")

    icons = {
        "avatar": {uid: it["icon"] for uid, it in yatta_a.items() if it.get("icon")},
        "weapon": {wid: it["icon"] for wid, it in yatta_w.items() if it.get("icon")},
        "relic": {},
    }

    # 圣遗物图标名来自本地缓存的 ReliquaryExcelConfigData（icon 形如 UI_RelicIcon_{setId}_5）
    rq_path = os.path.join(ROOT, ".cache", "raw", "ReliquaryExcelConfigData.json")
    if os.path.exists(rq_path):
        for x in load_json(rq_path):
            icon = x.get("icon") or ""
            if icon.startswith("UI_RelicIcon_"):
                sid = str(x.get("setId") or "")
                if not sid:
                    continue
                old = icons["relic"].get(sid)
                # 同一套装有多条记录（不同星级后缀），优先保留尾号最大的
                if old is None or icon.rsplit("_", 1)[-1] > old.rsplit("_", 1)[-1]:
                    icons["relic"][sid] = icon
        print(f"  relic 图标: {len(icons['relic'])} 个套装")
    else:
        print("  [WARN] 缺少 ReliquaryExcelConfigData.json，relic 图标留空")

    save_json(icons, os.path.join(DATA, "icons.json"))
    n_avatar = len(icons["avatar"])
    n_weapon = len(icons["weapon"])
    print(f"  完成: avatar {n_avatar} / weapon {n_weapon} -> data/icons.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
