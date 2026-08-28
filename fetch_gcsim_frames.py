# -*- coding: utf-8 -*-
"""
从 genshin.gcsim (github.com/genshinsim/gcsim) 抓取角色动作帧数据，
转换为「每步占用秒数」，写入 data/action_frames.json。

为什么需要它：
    本仓库的 meropide / gensri 数据包含技能倍率、冷却、能量，但没有「每次动作的动画时长」。
    gcsim 的 action.go 里有 normalframes / skillframes / burstframes 等常量（单位：游戏帧，60fps），
    正好补全这一环：动作秒数 = 帧数 / 60。

用法（在**有网络**的机器上运行）：
    python fetch_gcsim_frames.py

说明 / 注意：
    - gcsim 采用 GPL-3.0 许可证。本脚本仅「解析并转换」其公开的帧数据为自己的数据文件，
      不复制其源码；请保留本文件顶部的来源署名以符合要求。
    - 帧数随版本变动，请定期重跑以保持准确。
    - GCSIM_REPO 下的目录结构为 internal/characters/<element>/<key>/action.go；
      下方 MAP 将本仓库的 character_id 映射到 (元素目录, gcsim key)。
      如需更多角色，按需扩展 MAP 即可。

输出格式（data/action_frames.json）：
    {
      "<character_id>": {
        "normal": 0.75, "skill": 0.6, "burst": 1.5, "charged": 1.0
      },
      ...
    }
"""
import json
import os
import re
import sys
import urllib.request

GCSIM_RAW = "https://raw.githubusercontent.com/genshinsim/gcsim/main/internal/characters/{element}/{key}/action.go"

# 本仓库 character_id -> (gcsim 元素目录, gcsim key)
# 元素目录：pyro / hydro / cryo / electro / anemo / geo / dendro / physical
MAP = {
    "10000016": ("pyro", "diluc"),
    "10000002": ("cryo", "ayaka"),
    "10000006": ("electro", "lisa"),
    "10000014": ("hydro", "barbara"),
    "10000046": ("pyro", "hutao"),
    "10000022": ("hydro", "xingqiu"),
    "10000043": ("geo", "zhongli"),
    "10000035": ("anemo", "kazuha"),
    "10000052": ("electro", "raiden"),
    "10000030": ("pyro", "xiangling"),
    "10000041": ("pyro", "bennett"),
    "10000053": ("electro", "yae"),
    "10000037": ("pyro", "yanfei"),
    "10000072": ("dendro", "nahida"),
    "10000087": ("hydro", "furina"),
    "10000107": ("cryo", "shenhe"),
    "10000063": ("anemo", "wanderer"),
    "10000079": ("dendro", "alhaitham"),
    "10000121": ("hydro", "neuvillette"),
    "10000109": ("cryo", "ganyu"),
    "10000083": ("electro", "keqing"),
    "10000026": ("pyro", "amber"),
    "10000069": ("cryo", "chongyun"),
}

# 帧常量名 -> 我们的 skill_type
FRAME_KEY_MAP = {
    "normal": "normal",
    "skill": "skill",
    "burst": "burst",
    "charge": "charged",
    "charged": "charged",
    "plunge": "plunge",
    "highplunge": "highplunge",
    "lowplunge": "lowplunge",
    "aim": "aim",
}

FRAME_RE = re.compile(r"(\w*frames)\s*=\s*(\d+)")


def fetch_one(element, key):
    url = GCSIM_RAW.format(element=element, key=key)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8", "ignore")
    out = {}
    for name, val in FRAME_RE.findall(text):
        base = name.replace("frames", "").lower()
        skill = FRAME_KEY_MAP.get(base)
        if skill:
            out[skill] = int(val) / 60.0
    return out


def main():
    out = {}
    ok, fail = 0, 0
    for cid, (element, key) in MAP.items():
        try:
            frames = fetch_one(element, key)
            if frames:
                out[cid] = frames
                ok += 1
                print(f"[ok] {cid} ({element}/{key}): {frames}")
            else:
                fail += 1
                print(f"[skip] {cid} ({element}/{key}): 未解析到帧常量")
        except Exception as e:
            fail += 1
            print(f"[err] {cid} ({element}/{key}): {e}")

    here = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.join(here, "data", "action_frames.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n完成：成功 {ok}，失败/跳过 {fail}。已写入 {dest}")


if __name__ == "__main__":
    main()
