#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原神数据获取脚本 v3.0
==================================================
数据源: DimbreathBot/AnimeGameData（公开镜像仓库，已更新至原神 6.7.0 版本）
  https://github.com/DimbreathBot/AnimeGameData

功能特性:
  1. 版本检测 : 通过 AnimeGameData 仓库 master 分支最新 commit SHA 与本地
                .version 文件对比，版本一致时直接使用缓存，秒级完成。
  2. 缓存机制 : 原始 JSON 缓存于 ./.cache/raw/，解析结果输出到 ./data/。
                仅在版本更新或 --force 时全量重新下载，平时保留缓存。
  3. 中文名   : 使用 TextMapCHS.json 构建 ID → 中文名映射表，角色/技能/武器
                等 name_cn 字段自动填入中文；TextMap 缺失时回退英文代号。
  4. 强制刷新 : 支持 --force / -f 参数，忽略版本检测，全量重新下载。
  5. 详细日志 : 支持 --verbose / -v 参数，输出更详细的日志。

生成的 5 个规范化 JSON 文件（字段结构保持与 v2 一致，供下游伤害计算使用）:
  - data/characters.json      角色基础面板 + 成长曲线 + 中文名
  - data/skills.json          技能倍率表（ProudSkill + 技能关联 + 中文名）
  - data/weapons.json         武器数据 + 成长曲线 + 精炼效果
  - data/artifacts.json       圣遗物套装 + 套装效果 + 主副词条
  - data/constellations.json  角色命座效果

用法:
  python fetch_data.py              版本检测 + 增量更新（推荐）
  python fetch_data.py --force      强制重新下载全部数据（忽略版本检测）
  python fetch_data.py -f
  python fetch_data.py --verbose    输出详细日志
  python fetch_data.py -v

说明:
  - 命座数据实际存储于 AvatarTalentExcelConfigData.json
    （AvatarFetterExcelConfigData.json 仅包含好感度资料档案，无命座效果参数），
    故本脚本下载并使用 AvatarTalent 作为命座数据源。
  - AnimeGameData 为 GenshinData 的社区镜像，ExcelBinOutput 字段结构完全一致，
    无需修改任何解析逻辑，仅更换数据源地址。
"""

import argparse
import json
import os
import re
import sys
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 配置 ====================

REPO = "DimbreathBot/AnimeGameData"
BRANCH = "master"
RAW_URL_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
API_COMMITS_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"

# 下载镜像列表（按优先级排序）。raw.githubusercontent.com 为大文件主源，
# 国内网络不稳定时自动回退到以下镜像。所有镜像均支持 Range 断点续传。
RAW_MIRRORS = [
    RAW_URL_BASE,
    f"https://gh-proxy.com/{RAW_URL_BASE}",
    f"https://ghfast.top/{RAW_URL_BASE}",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
RAW_DIR = os.path.join(CACHE_DIR, "raw")
VERSION_FILE = os.path.join(BASE_DIR, ".version")   # 本地版本文件（commit SHA）

# 需要下载的原始数据文件（位于仓库 ExcelBinOutput/ 目录）
SOURCE_FILES = [
    "AvatarExcelConfigData.json",        # 角色基础数据（ID、基础攻击、突破属性、成长曲线）
    "AvatarCurveExcelConfigData.json",   # 角色成长曲线表
    "AvatarSkillDepotExcelConfigData.json",  # 技能仓库（角色→技能/命座关联）
    "AvatarSkillExcelConfigData.json",   # 技能定义（名称、冷却、能量消耗）
    "AvatarTalentExcelConfigData.json",  # 命座数据（角色命座效果与参数）
    "ProudSkillExcelConfigData.json",    # 天赋倍率表（技能等级→倍率）
    "WeaponExcelConfigData.json",        # 武器数据（基础攻击、副属性）
    "WeaponCurveExcelConfigData.json",   # 武器成长曲线表
    "WeaponLevelExcelConfigData.json",   # 武器等级消耗数据
    "ReliquarySetExcelConfigData.json",  # 圣遗物套装定义（2件/4件套）
    "ReliquaryExcelConfigData.json",     # 圣遗物单件定义（主副词条槽位）
    "EquipAffixExcelConfigData.json",    # 精炼/套装效果参数
    "AvatarPromoteExcelConfigData.json", # 角色突破属性加成
]

# 中文文本映射文件（位于仓库 TextMap/ 目录，约 48MB）—— 下载失败必须报错退出
TEXTMAP_FILENAME = "TextMapCHS.json"

RETRIES = 3          # 网络请求失败重试次数
RETRY_DELAY = 2      # 重试间隔（秒）

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (GenshinCalculator-data-fetcher v3.0)",
    # 默认请求原始内容（不压缩）。部分国内镜像对 Range 请求错误返回 gzip 流，
    # 且流本身损坏会导致 requests 自动解压失败。identity 让服务器返回原始字节。
    "Accept-Encoding": "identity",
})

VERBOSE = False      # 由 --verbose 设置


# ==================== 日志工具 ====================

def log_info(msg: str):
    print(f"[INFO] {msg}")


def log_warn(msg: str):
    print(f"[WARN] {msg}")


def log_debug(msg: str):
    """详细日志，仅在 --verbose 时输出"""
    if VERBOSE:
        print(f"[DEBUG] {msg}")


# ==================== 网络请求（带重试） ====================

def http_get(
    url: str,
    timeout: int = 60,
    stream: bool = False,
    headers: dict | None = None,
):
    """
    发起 GET 请求（可附带 Range 头），失败自动重试 RETRIES 次（间隔 RETRY_DELAY 秒）。
    全部失败则抛出 RuntimeError（不静默跳过）。
    """
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=timeout, stream=stream, headers=headers)
            if r.status_code == 416:
                # Range 超出范围：确定性错误（服务器端文件比本地 tmp 更小或已变化），
                # 重试无意义。直接返回，由上层决定从头下载。
                return r
            if r.status_code in (200, 206):
                return r
            last_err = f"HTTP {r.status_code}"
            log_warn(f"请求 {url} 返回 {r.status_code}")
            if r.status_code in (403, 429):
                log_warn("可能触发 GitHub 速率限制，请稍后重试。")
        except requests.RequestException as e:
            last_err = str(e)
            log_warn(f"请求异常: {e}")
        if attempt < RETRIES:
            log_info(f"重试 {attempt + 1}/{RETRIES}，等待 {RETRY_DELAY}s ...")
            time.sleep(RETRY_DELAY)
    raise RuntimeError(
        f"下载失败（重试 {RETRIES} 次均失败）: {url}\n  最后错误: {last_err}"
    )


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== 版本检测 ====================

def parse_version_from_message(message: str) -> str | None:
    """从 commit message 中提取版本号，例如 'Update to 6.7.0' / '6.7.0' / 'v6.7.0'"""
    if not message:
        return None
    m = re.search(r'(?:v|版本)?\s*(\d+\.\d+(?:\.\d+)?)', message)
    return m.group(1) if m else None


def get_remote_version() -> dict:
    """通过 GitHub API 获取 AnimeGameData 仓库 master 分支最新 commit 信息"""
    r = http_get(API_COMMITS_URL, timeout=30, stream=False)
    data = r.json()
    sha = data.get("sha", "")
    commit = data.get("commit", {})
    message = (commit.get("message", "") or "").split("\n")[0]
    return {
        "sha": sha,
        "short_sha": sha[:7],
        "date": commit.get("committer", {}).get("date", ""),
        "message": message,
        "version": parse_version_from_message(message),
    }


def format_version(ver: dict | None) -> str:
    """显示版本号（优先 v6.7.0 形式，无则用 commit SHA）"""
    if not ver:
        return "无"
    if ver.get("version"):
        return f"v{ver['version']}"
    return f"commit {ver.get('short_sha', '?')}"


def load_local_version() -> dict | None:
    """读取本地 .version 文件（不存在或损坏返回 None）"""
    if not os.path.exists(VERSION_FILE):
        return None
    try:
        return load_json(VERSION_FILE)
    except Exception:
        log_warn(f"本地版本文件 {VERSION_FILE} 损坏，将其忽略")
        return None


def save_local_version(remote_ver: dict):
    """将远程版本信息写入本地 .version 文件"""
    local = dict(remote_ver)
    local["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_json(VERSION_FILE, local)


# ==================== 下载 ====================

def download_raw_file(filename: str, force: bool = False, subdir: str = "ExcelBinOutput") -> dict:
    """
    下载原始 JSON 文件到 .cache/raw/ 并返回解析后的数据。

    - force=True 时总是重新下载；否则仅在缓存缺失时下载。
    - 支持断点续传：若 .tmp 临时文件已存在（上次中断），从已有大小继续下载。
    - 支持多镜像回退：主源（raw.githubusercontent.com）失败后自动依次尝试镜像。
    - 通过 r.raw 原始流读取，避免 requests 对损坏 gzip 流的自动解压失败。
    """
    cache_path = os.path.join(RAW_DIR, filename)

    if not force and os.path.exists(cache_path):
        log_debug(f"使用缓存 {filename}")
        return load_json(cache_path)

    # ---------- 断点续传：检查临时文件 ----------
    # 使用 PID 隔离临时文件名，避免与上次中断残留的进程文件冲突
    tmp_path = cache_path + f".{os.getpid()}.tmp"
    # 清理历史残留（旧版无 PID 的 .tmp + 其他 PID 的 .<pid>.tmp），若被占用则忽略
    for old in __import__("glob").glob(cache_path + ".tmp") + \
               __import__("glob").glob(cache_path + ".*.tmp"):
        try:
            os.remove(old)
            log_debug(f"清理残留临时文件 {old}")
        except OSError:
            pass  # 文件被其他进程占用，忽略
    resume_pos = 0
    if os.path.exists(tmp_path):
        resume_pos = os.path.getsize(tmp_path)
        if resume_pos > 0:
            log_info(f"检测到未完成的下载 {filename}（已有 {resume_pos / 1024 / 1024:.2f} MB），断点续传...")

    url = f"{RAW_URL_BASE}/{subdir}/{filename}"

    # ---------- 尝试主源与镜像（均支持 Range） ----------
    last_err = None
    for base in RAW_MIRRORS:
        mirror = f"{base}/{subdir}/{filename}"
        r = None
        try:
            # 每个镜像尝试前重新计算续传位置（可能上一镜像已写入部分数据）
            if os.path.exists(tmp_path):
                resume_pos = os.path.getsize(tmp_path)
            headers = {"Range": f"bytes={resume_pos}-"} if resume_pos > 0 else None
            log_info(f"下载 {filename} ...")
            r = http_get(mirror, timeout=600, stream=True, headers=headers)

            if r.status_code == 416:
                # 服务器端文件小于本地 tmp（镜像间内容可能不一致）：
                # 删除临时文件，从头下载
                log_warn(f"镜像 {mirror.split('/')[2]} 返回 416，从头下载")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                r.close()
                resume_pos = 0
                r = http_get(mirror, timeout=600, stream=True, headers=None)

            if r.status_code == 206:
                # 服务器支持 Range：追加写
                mode = "ab"
            elif r.status_code == 200 and resume_pos > 0:
                # 服务器忽略 Range 返回全量：从头写
                log_warn(f"镜像 {mirror.split('/')[2]} 不支持断点续传，重新从 0 开始下载")
                resume_pos = 0
                r.raw.decode_content = False
                mode = "wb"
            else:
                mode = "ab" if resume_pos > 0 and r.status_code == 206 else "wb"

            # 关键：禁止 urllib3 自动解压（即使服务器错误地返回了 gzip 编码，
            # 我们仍以原始字节写入，保证 JSON 内容正确）
            if hasattr(r, "raw"):
                r.raw.decode_content = False

            bytes_written = 0
            # 用底层 read(amt) 循环读取原始字节（兼容所有 urllib3 版本）
            with open(tmp_path, mode) as f:
                while True:
                    chunk = r.raw.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)

            if bytes_written == 0:
                raise RuntimeError("下载内容为空")

            # 校验：下载后尝试解析 JSON，失败则删除临时文件重试
            try:
                json.load(open(tmp_path, "r", encoding="utf-8"))
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise RuntimeError(f"{filename} 下载内容损坏，已清除临时文件，请重试")

            # 原子替换：避免中断产生损坏缓存
            os.replace(tmp_path, cache_path)
            size_mb = os.path.getsize(cache_path) / 1024 / 1024
            log_info(f"下载 {filename} 完成 ({size_mb:.2f} MB)")
            return load_json(cache_path)

        except Exception as e:
            last_err = str(e)
            log_warn(f"从 {mirror.split('/')[2]} 下载 {filename} 失败: {e}")
            log_info("尝试下一个镜像...")
            continue
        finally:
            if r is not None:
                r.close()

    # 所有镜像均失败
    raise RuntimeError(
        f"下载 {filename} 失败（已尝试 {len(RAW_MIRRORS)} 个镜像源）: {last_err}"
    )


def download_textmap(force: bool = False) -> dict:
    """下载中文文本映射（TextMap/TextMapCHS.json，约 48MB）"""
    return download_raw_file(TEXTMAP_FILENAME, force=force, subdir="TextMap")


# ==================== 数据归一化 ====================

def build_hash_key_map(textmap: dict) -> dict:
    """构建 hash -> 中文文本 映射"""
    return {str(k): v for k, v in textmap.items()}


# 内置中文名映射（用于 TextMap 缺失时的兜底）
EN_TO_CN = {
    "Kate": "凯特", "Ayaka": "神里绫华", "Qin": "琴", "PlayerBoy": "空",
    "Lisa": "丽莎", "PlayerGirl": "荧", "Barbara": "芭芭拉", "Kaeya": "凯亚",
    "Diluc": "迪卢克", "Razor": "雷泽", "Ambor": "安柏", "Venti": "温迪",
    "Xiangling": "香菱", "Beidou": "北斗", "Xingqiu": "行秋", "Xiao": "魈",
    "Ningguang": "凝光", "Klee": "可莉", "Zhongli": "钟离", "Fischl": "菲谢尔",
    "Bennett": "班尼特", "Tartaglia": "达达利亚", "Noel": "诺艾尔", "Qiqi": "七七",
    "Chongyun": "重云", "Ganyu": "甘雨", "Albedo": "阿贝多", "Diona": "迪奥娜",
    "Mona": "莫娜", "Keqing": "刻晴", "Sucrose": "砂糖", "Xinyan": "辛焱",
    "Rosaria": "罗莎莉亚", "Hutao": "胡桃", "Kazuha": "枫原万叶", "Feiyan": "烟绯",
    "Yoimiya": "宵宫", "Tohma": "托马", "Eula": "优菈", "Shougun": "雷电将军",
    "Sayu": "早柚", "Kokomi": "珊瑚宫心海", "Gorou": "五郎", "Sara": "九条裟罗",
    "Itto": "荒泷一斗", "Yae": "八重神子", "Heizo": "鹿野院平藏", "Yelan": "夜兰",
    "Momoka": "绮良良", "Aloy": "亚萝伊", "Shenhe": "申鹤", "Yunjin": "云堇",
    "Shinobu": "久岐忍", "Ayato": "神里绫人", "Collei": "柯莱", "Dori": "多莉",
    "Tighnari": "提纳里", "Nilou": "妮露", "Cyno": "赛诺", "Candace": "坎蒂丝",
    "Nahida": "纳西妲", "Layla": "莱依拉", "Wanderer": "流浪者", "Faruzan": "珐露珊",
    "Yaoyao": "瑶瑶", "Alhatham": "艾尔海森", "Dehya": "迪希雅", "Mika": "米卡",
    "Kaveh": "卡维", "Baizhuer": "白术", "Linette": "琳妮特", "Liney": "林尼",
    "Freminet": "菲米尼", "Wriothesley": "莱欧斯利", "Neuvillette": "那维莱特",
    "Charlotte": "夏洛蒂", "Furina": "芙宁娜", "Chevreuse": "夏沃蕾", "Navia": "娜维娅",
    "Gaming": "嘉明", "Liuyun": "闲云", "Chiori": "千织", "Sigewinne": "希格雯",
    "Arlecchino": "阿蕾奇诺", "Sethos": "赛索斯", "Clorinde": "克洛琳德",
    "Emilie": "艾梅莉埃", "Kachina": "卡齐娜", "Kinich": "基尼奇", "Mualani": "玛拉妮",
    "Xilonen": "希诺宁", "Chasca": "恰斯卡", "Olorun": "欧洛伦", "Mavuika": "玛薇卡",
    "Citlali": "茜特菈莉", "Lanyan": "蓝砚", "Mizuki": "梦见月瑞希", "Iansan": "伊安珊",
    "Varesa": "瓦蕾莎", "Escoffier": "爱可菲", "Ifa": "伊法", "SkirkNew": "丝柯克",
    "Dahlia": "达希亚", "Ineffa": "伊涅法", "MannequinBoy": "模特（男）",
    "MannequinGirl": "模特（女）", "Aino": "艾诺", "Nefer": "妮菲尔",
    "Durin": "杜林", "Jahoda": "贾霍达", "Columbina": "哥伦比娜",
    "Varka": "瓦卡", "Lohen": "洛亨", "Linnea": "林内娅",
    "Nicole": "尼科尔", "Prune": "普吕纳",
    "Odette": "奥黛塔", "Alyosha": "阿罗夏",
    "Side_Ambor": "安柏（试用）", "Side_Kate": "凯特（试用）",
}

# 内置补充角色（数据源尚未收录、但已确认为正式可玩的 7.0 角色）。
# 数值为基础占位（待官方 ExcelBinOutput 收录后自动被源数据覆盖），
# 字段结构与 AvatarExcelConfigData 保持一致，走完全相同的解析管线。
SUPPLEMENT_AVATARS = [
    {
        # 奥黛塔 (Odette) - 7.0 五星
        "id": 10000133,
        "useType": "AVATAR_FORMAL",
        "qualityType": "QUALITY_ORANGE",
        "iconName": "UI_AvatarIcon_Odette",
        "weaponType": "WEAPON_SWORD_ONE_HAND",
        "_element": "水",
        "hpBase": 1210.0, "attackBase": 28.0, "defenseBase": 62.0,
        "critical": 0.05, "criticalHurt": 0.5, "chargeEfficiency": 1.0,
    },
    {
        # 阿罗夏 (Alyosha) - 7.0 四星
        "id": 10000134,
        "useType": "AVATAR_FORMAL",
        "qualityType": "QUALITY_PURPLE",
        "iconName": "UI_AvatarIcon_Alyosha",
        "weaponType": "WEAPON_BOW",
        "_element": "冰",
        "hpBase": 870.0, "attackBase": 21.0, "defenseBase": 52.0,
        "critical": 0.05, "criticalHurt": 0.5, "chargeEfficiency": 1.0,
    },
]


def resolve_avatar_name(av: dict, hashes: dict) -> str:
    """
    获取角色名：优先中文 TextMap，其次内置中文映射，回退到英文代号。
    未实装角色在 TextMap 中无中文名，将保留英文代号（或标注 '未实装' 由下游决定）。
    """
    nm = hashes.get(str(av.get("nameTextMapHash", "")), "")
    if nm:
        return nm
    icon = av.get("iconName", "") or av.get("imageName", "") or ""
    if icon:
        for prefix in ("UI_AvatarIcon_", "AvatarImage_Forward_"):
            if prefix in icon:
                code = icon.split(prefix, 1)[1]
                return EN_TO_CN.get(code, code)
    return f"Char_{av.get('id', 0)}"


def normalize_characters(
    avatars: list,
    avatar_curves: list,
    skill_depots: list,
    textmap: dict,
    char_name_map: dict,
    avatar_promotes: list = None,
) -> list:
    """
    角色基础面板数据
    - 90级基础 HP / 攻击 / 防御（经成长曲线计算）
    - 突破加成、暴击、暴伤
    - 技能仓库关联
    - name_cn 字段：优先 TextMap 中文名，缺失时回退英文代号
    - element: 从技能仓库的爆发技能 costElemType 推断
    - ascension_bonus: 从 AvatarPromote 解析突破属性加成
    """
    hashes = build_hash_key_map(textmap)
    if avatar_promotes is None:
        avatar_promotes = []

    # 元素类型映射（costElemType -> 中文元素）
    ELEM_MAP = {
        "Fire": "火", "Water": "水", "Grass": "草", "Electric": "雷",
        "Ice": "冰", "Wind": "风", "Rock": "岩", "None": "物理",
    }

    # 建立 skill_id -> costElemType 映射（从 AvatarSkill 数据）
    skill_elem_map = {}
    for sk in (char_name_map.get("_avatar_skills", []) if isinstance(char_name_map, dict) else []):
        cet = sk.get("costElemType", "")
        if cet:
            skill_elem_map[sk.get("id")] = cet

    # 建立 promote_id -> 突破属性加成映射
    promote_map = {}
    for p in avatar_promotes:
        pid = p.get("avatarPromoteId", 0)
        if pid not in promote_map:
            promote_map[pid] = []
        # 提取突破加成属性
        bonus = {}
        for prop in p.get("addProps", []):
            ptype = prop.get("propType", "")
            val = prop.get("value", 0)
            if ptype and ptype != "FIGHT_PROP_NONE" and val:
                bonus[ptype] = val
        if bonus:
            promote_map[pid].append({
                "level": p.get("promoteLevel", 0),
                "bonus": bonus,
            })

    # 成长曲线表: curve_name -> {level: value}
    curves = {}
    for item in avatar_curves:
        for c in item["curveInfos"]:
            ctype = c["type"]
            if ctype not in curves:
                curves[ctype] = {}
            curves[ctype][item["level"]] = c["value"]

    def curve_value(curve_type: str, level: int) -> float:
        vals = curves.get(curve_type, {})
        if not vals:
            return 1.0
        if level in vals:
            return vals[level]
        levels = sorted(vals.keys())
        if level <= levels[0]:
            return vals[levels[0]]
        if level >= levels[-1]:
            return vals[levels[-1]]
        for i in range(len(levels) - 1):
            if levels[i] <= level <= levels[i + 1]:
                t = (level - levels[i]) / (levels[i + 1] - levels[i])
                return vals[levels[i]] + t * (vals[levels[i + 1]] - vals[levels[i]])
        return vals[levels[-1]]

    results = []
    # 合并内置补充角色（若源数据已收录同 id，则自动跳过补充项）
    seen_ids = {a.get("id") for a in avatars}
    merged_avatars = [a for a in SUPPLEMENT_AVATARS if a.get("id") not in seen_ids] + list(avatars)

    for av in merged_avatars:
        avatar_id = av["id"]

        # ---------- 过滤规则：仅保留正式可玩角色 ----------
        # 1. 必须有 id
        if not avatar_id:
            continue

        # 2. 排除非正式 useType
        #    实际数据中 avatarType 字段多为空，使用 useType 区分角色性质：
        #    AVATAR_FORMAL=正式可玩角色；AVATAR_TEST/AVATAR_ABANDON/
        #    AVATAR_SYNC_TEST 均为测试/废弃/同步测试角色，需排除。
        use_type = av.get("useType", "")
        if use_type and use_type not in ("AVATAR_FORMAL",):
            continue

        # 3. 解析名称（优先 TextMap，其次内置映射/英文代号）
        name_cn = hashes.get(str(av.get("nameTextMapHash", "")), "") or ""
        if not name_cn:
            name_cn = resolve_avatar_name(av, hashes)

        # 4. 排除明显非正式角色（名称关键词）
        exclude_keywords = ["试用", "测试", "Side_", "NPC", "未实装", "模特"]
        if any(kw in name_cn for kw in exclude_keywords):
            continue

        # 5. 排除 id >= 10000900 的重复/测试副本
        #    （旅行者本体为 10000005/10000007，重复副本如 10000901~10000999 需排除）
        if avatar_id >= 10000900:
            continue

        # 6. 完全无名称（未实装）的角色排除
        if name_cn == f"Char_{avatar_id}":
            continue

        depot_id = av.get("skillDepotId", 0)

        # 找到技能仓库
        depot = next((d for d in skill_depots if d.get("id") == depot_id), {})
        talent_ids = depot.get("talents", [])
        talent_ids = [t for t in talent_ids if t and t > 0]

        # 元素类型：从技能仓库的爆发技能（energySkill）的 costElemType 推断
        element = ""
        energy_skill_id = depot.get("energySkill", 0)
        if energy_skill_id and energy_skill_id in skill_elem_map:
            element = ELEM_MAP.get(skill_elem_map[energy_skill_id], "")
        # 若爆发技能无元素（如物理角色），尝试从普通技能推断
        if not element:
            for sid in [s for s in depot.get("skills", []) if s] + [s for s in depot.get("subSkills", []) if s]:
                if sid in skill_elem_map:
                    element = ELEM_MAP.get(skill_elem_map[sid], "")
                    if element and element != "物理":
                        break
        # 补充角色：源数据无技能仓库，使用内置元素标注
        if not element and av.get("_element"):
            element = av["_element"]

        # 突破加成：从 AvatarPromote 按 avatarPromoteId 匹配
        promote_id = av.get("avatarPromoteId", 0)
        ascension_bonus = {}
        for p in promote_map.get(promote_id, []):
            for ptype, val in p.get("bonus", {}).items():
                ascension_bonus[ptype] = ascension_bonus.get(ptype, 0) + val

        # 90级属性（基础值 × 成长曲线）
        hp_base = av.get("hpBase", 0)
        atk_base = av.get("attackBase", 0)
        def_base = av.get("defenseBase", 0)

        hp_curve = "GROW_CURVE_HP_S4"
        atk_curve = "GROW_CURVE_ATTACK_S4"
        def_curve = "GROW_CURVE_HP_S4"
        for gc in av.get("propGrowCurves", []):
            t = gc.get("type", "")
            g = gc.get("growCurve", "")
            if t == "FIGHT_PROP_BASE_HP":
                hp_curve = g
            elif t == "FIGHT_PROP_BASE_ATTACK":
                atk_curve = g
            elif t == "FIGHT_PROP_BASE_DEFENSE":
                def_curve = g

        hp_90 = hp_base * curve_value(hp_curve, 90)
        atk_90 = atk_base * curve_value(atk_curve, 90)
        def_90 = def_base * curve_value(def_curve, 90)

        results.append({
            "id": avatar_id,
            "name": name_cn,
            "name_cn": name_cn,
            "quality": av.get("qualityType", ""),
            "weapon_type": av.get("weaponType", ""),
            "body_type": av.get("bodyType", ""),
            "element": element,
            "base_stats": {
                "hp": hp_base,
                "atk": atk_base,
                "def": def_base,
            },
            "stats_90": {
                "hp": round(hp_90, 2),
                "atk": round(atk_90, 2),
                "def": round(def_90, 2),
            },
            "base_crit_rate": av.get("critical", 0.0),
            "base_crit_dmg": av.get("criticalHurt", 0.5),
            "charge_efficiency": av.get("chargeEfficiency", 1.0),
            "ascension_bonus": ascension_bonus,
            "skill_depot_id": depot_id,
            "talent_ids": talent_ids,
            "grow_curves": {
                "hp": hp_curve,
                "atk": atk_curve,
                "def": def_curve,
            },
        })
    return results


def normalize_skills(
    proud_skills: list,
    avatar_skills: list,
    skill_depots: list,
    textmap: dict,
) -> list:
    """
    技能倍率表
    - ProudSkill: 天赋升级的倍率参数（paramList）
    - AvatarSkill: 技能基础定义
    - 关联角色技能仓库
    """
    hashes = build_hash_key_map(textmap)

    # 建立 avatar_skill_id -> skill 信息
    skill_info = {}
    for sk in avatar_skills:
        skill_info[sk.get("id")] = {
            "id": sk.get("id"),
            "name": hashes.get(str(sk.get("nameTextMapHash", "")), "") or f"Skill_{sk.get('id')}",
            "name_cn": hashes.get(str(sk.get("nameTextMapHash", "")), "") or f"Skill_{sk.get('id')}",
            "desc": hashes.get(str(sk.get("descTextMapHash", "")), "") or "",
            "max_level": sk.get("maxLevel", 10),
            "skill_type": sk.get("skillType", ""),
            "cost_elemental_energy": sk.get("costElemVal", 0),
            "proud_skill_group_id": sk.get("proudSkillGroupId", 0),
        }

    # 构建 角色 -> 技能列表
    depot_map = {}
    for d in skill_depots:
        depot_map[d.get("id")] = {
            "skills": d.get("skills", []),
            "sub_skills": d.get("subSkills", []),
            "energy_skill": d.get("energySkill", 0),
            "talents": d.get("talents", []),
        }

    # ProudSkill 按 proudSkillGroupId 分组
    proud_groups = {}
    for ps in proud_skills:
        gid = ps.get("proudSkillGroupId", 0)
        if gid not in proud_groups:
            proud_groups[gid] = []
        proud_groups[gid].append(ps)

    results = []
    seen_depot = set()
    for depot_id, depot in depot_map.items():
        if depot_id in seen_depot:
            continue
        seen_depot.add(depot_id)

        # 推断技能类型：skills[0]=普攻, skills[1]=战技, energySkill=爆发
        # subSkills 通常为被动/特殊技能，标记为 'passive'
        skill_type_map = {}
        skills_list = [s for s in depot["skills"] if s]
        for idx, sid in enumerate(skills_list):
            if idx == 0:
                skill_type_map[sid] = "normal_attack"
            elif idx == 1:
                skill_type_map[sid] = "elemental_skill"
            else:
                skill_type_map[sid] = "other"
        for sid in [s for s in depot["sub_skills"] if s]:
            skill_type_map[sid] = "passive"
        if depot["energy_skill"]:
            skill_type_map[depot["energy_skill"]] = "elemental_burst"

        char_skills = []
        all_skill_ids = (
            skills_list
            + [s for s in depot["sub_skills"] if s]
        )
        if depot["energy_skill"]:
            all_skill_ids.append(depot["energy_skill"])

        for skill_id in all_skill_ids:
            info = skill_info.get(skill_id)
            if not info:
                continue

            skill_entry = {
                "skill_id": skill_id,
                "name": info["name"],
                "name_cn": info["name_cn"],
                "desc": info["desc"],
                "max_level": info["max_level"],
                "skill_type": skill_type_map.get(skill_id, info["skill_type"] or "unknown"),
                "cost_energy": info["cost_elemental_energy"],
                "proud_skill_group_id": info.get("proud_skill_group_id", 0),
                "proud_skills": [],
            }
            char_skills.append(skill_entry)

        if char_skills:
            results.append({
                "depot_id": depot_id,
                "skills": char_skills,
            })

    # 汇总所有 ProudSkill 组数据（用于倍率表）
    proud_list = []
    for gid in sorted(proud_groups.keys()):
        group = sorted(proud_groups[gid], key=lambda x: x.get("level", 0))
        entry = {
            "group_id": gid,
            "proud_skill_type": group[0].get("proudSkillType", 0) if group else 0,
            "name": hashes.get(str(group[0].get("nameTextMapHash", "")) if group else "", ""),
            "name_cn": hashes.get(str(group[0].get("nameTextMapHash", "")) if group else "", ""),
            "desc": hashes.get(str(group[0].get("descTextMapHash", "")) if group else "", ""),
            "levels": [
                {
                    "level": p.get("level", 0),
                    "param_list": p.get("paramList", []),
                    "add_props": p.get("addProps", []),
                }
                for p in group
            ],
        }
        proud_list.append(entry)

    return {
        "skill_depots": results,
        "proud_skill_groups": proud_list,
    }


def normalize_weapons(
    weapons: list,
    weapon_curves: list,
    equip_affixes: list,
    textmap: dict,
) -> list:
    """
    武器数据
    - 基础攻击力（90级）
    - 副属性（暴击/暴伤/充能等）
    - 精炼效果（EquipAffix）
    """
    hashes = build_hash_key_map(textmap)

    # 武器成长曲线
    wcurves = {}
    for item in weapon_curves:
        for c in item.get("curveInfos", []):
            ctype = c["type"]
            if ctype not in wcurves:
                wcurves[ctype] = {}
            wcurves[ctype][item["level"]] = c["value"]

    def wcurve_value(curve_type: str, level: int) -> float:
        vals = wcurves.get(curve_type, {})
        if not vals:
            return 1.0
        if level in vals:
            return vals[level]
        levels = sorted(vals.keys())
        if level <= levels[0]:
            return vals[levels[0]]
        if level >= levels[-1]:
            return vals[levels[-1]]
        for i in range(len(levels) - 1):
            if levels[i] <= level <= levels[i + 1]:
                t = (level - levels[i]) / (levels[i + 1] - levels[i])
                return vals[levels[i]] + t * (vals[levels[i + 1]] - vals[levels[i]])
        return vals[levels[-1]]

    # 精炼效果
    # 注意：武器 skillAffix 引用的是 EquipAffix 的 id 字段（如 111401），
    # 而 affixId 是每级唯一值（如 1114010）。故此处以 id 为键建立映射。
    affix_map = {}
    for af in equip_affixes:
        aid = af.get("id", 0)
        if aid not in affix_map:
            affix_map[aid] = []
        affix_map[aid].append({
            "level": af.get("level", 1),
            "name": hashes.get(str(af.get("nameTextMapHash", "")), ""),
            "name_cn": hashes.get(str(af.get("nameTextMapHash", "")), ""),
            "desc": hashes.get(str(af.get("descTextMapHash", "")), ""),
            "param_list": af.get("paramList", []),
            "open_config": af.get("openConfig", ""),
        })

    results = []
    for w in weapons:
        wid = w.get("id", 0)
        name = hashes.get(str(w.get("nameTextMapHash", "")), "") or f"Weapon_{wid}"
        rank = w.get("rankLevel", 1)
        weapon_type = w.get("weaponType", "")

        # 基础攻击力与副属性
        base_atk = 0.0
        sub_stat = {}
        for prop in w.get("weaponProp", []):
            ptype = prop.get("propType", "")
            init_value = prop.get("initValue", 0)
            curve = prop.get("type", "")
            if ptype == "FIGHT_PROP_BASE_ATTACK" and curve:
                base_atk = init_value * wcurve_value(curve, 90)
            elif ptype != "FIGHT_PROP_BASE_ATTACK":
                sub_stat[ptype] = init_value

        # 精炼效果
        affixes = []
        for afid in w.get("skillAffix", []):
            if afid in affix_map:
                affixes.extend(affix_map[afid])

        results.append({
            "id": wid,
            "name": name,
            "name_cn": name,
            "rank": rank,
            "weapon_type": weapon_type,
            "base_atk_90": round(base_atk, 2),
            "sub_stat": sub_stat,
            "desc": hashes.get(str(w.get("descTextMapHash", "")), ""),
            "refinements": affixes,
        })
    return results


# 圣遗物套装效果属性中文名（TextMap 缺失时的兜底）
_ARTIFACT_PROP_CN = {
    "FIGHT_PROP_ATTACK_PERCENT": "攻击力",
    "FIGHT_PROP_DEFENSE_PERCENT": "防御力",
    "FIGHT_PROP_CRITICAL": "暴击率",
    "FIGHT_PROP_CRITICAL_HURT": "暴击伤害",
    "FIGHT_PROP_ELEMENT_MASTERY": "元素精通",
    "FIGHT_PROP_CHARGE_EFFICIENCY": "元素充能效率",
    "FIGHT_PROP_HP": "生命值",
    "FIGHT_PROP_HP_PERCENT": "生命值",
    "FIGHT_PROP_DEFENSE": "防御力",
    "FIGHT_PROP_HEALED_ADD": "受治疗加成",
    "FIGHT_PROP_HEAL_ADD": "治疗加成",
    "FIGHT_PROP_SHIELD_COST_MINUS_RATIO": "护盾强效",
    "FIGHT_PROP_ICE_ADD_HURT": "冰元素伤害",
    "FIGHT_PROP_ELEC_ADD_HURT": "雷元素伤害",
    "FIGHT_PROP_FIRE_ADD_HURT": "火元素伤害",
    "FIGHT_PROP_WIND_ADD_HURT": "风元素伤害",
    "FIGHT_PROP_WATER_ADD_HURT": "水元素伤害",
    "FIGHT_PROP_ROCK_ADD_HURT": "岩元素伤害",
    "FIGHT_PROP_GRASS_ADD_HURT": "草元素伤害",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "物理伤害",
    "FIGHT_PROP_ELEC_SUB_HURT": "雷元素抗性",
    "FIGHT_PROP_FIRE_SUB_HURT": "火元素抗性",
}

# 圣遗物套装 openConfig 中文描述（TextMap 缺失时的兜底）
_ARTIFACT_OPENCONFIG_CN = {
    "Relic_ExtraAtkCritUp": "2件套：攻击力提高18%；4件套：超载、蒸发、融化、雷元素扩散、火元素扩散、水元素扩散反应造成的伤害提升50%。施放元素爆发后，2件套的效果提升50%，持续10秒。",
    "Relic_GiantKiller": "2件套：生命值低于50%时，造成的伤害增加。",
    "Relic_AbsorbTeamElemResist": "2件套：元素精通提高80点；4件套：队伍中附近的角色获得对应元素抗性穿透。",
    "Relic_AllElemResistUp": "2件套：元素抗性提高；4件套：全元素抗性提升。",
    "Relic_ElemDmgEnhanceElemResist": "2件套：对应元素伤害提高；4件套：元素抗性提升。",
    "Relic_LowHPGainExtraCritRate": "2件套：生命值低于50%时，暴击率提升。",
    "Relic_AtkAndExtraAtkUp": "2件套：攻击力提高；4件套：攻击力进一步提升。",
    "Relic_SkillEnhanceNormalAtkAndExtraAtk": "2件套：普通攻击与重击伤害提升；4件套：元素战技伤害提升。",
    "Relic_ReactionGainExtraElemMasteryForTeam": "2件套：元素精通提高；4件套：触发元素反应后全队元素精通提升。",
    "Relic_SkillDamageUp": "2件套：元素战技伤害提高。",
    "Relic_KillingRefreshSkill": "2件套：击败敌人后刷新元素战技冷却。",
    "Relic_UltGainEnergyForTeam": "2件套：施放元素爆发后全队获得能量。",
    "Relic_ChestHealSelf": "2件套：开启宝箱后治疗自身。",
    "Relic_CoinHealSelf": "2件套：拾取摩拉后治疗自身。",
    "Relic_RestoreEnergyGainExtraEnergyForTeam": "2件套：恢复能量后全队获得额外能量。",
    "Relic_UltHealSelf": "2件套：施放元素爆发后治疗自身。",
    "Relic_CriticUpAgainstIceAndFrozen": "2件套：对冰元素影响下的敌人暴击率提升。",
    "Relic_DamageUpAgainstElectric": "2件套：对雷元素附着的敌人伤害提升。",
    "Relic_DamageUpAgainstFireAndBurning": "2件套：对火元素附着的敌人伤害提升。",
    "Relic_SkillEnhanceCured": "2件套：受到治疗后元素战技伤害提升。",
    "Relic_MeleeAttackUp": "2件套：近战攻击伤害提升。",
    "Relic_ReactionWindEnhance": "2件套：风元素扩散反应伤害提升。",
    "Relic_ReactionIceEnhance": "2件套：冰元素反应伤害提升。",
    "Relic_ReactionElectricEnhance": "2件套：雷元素反应伤害提升。",
    "Relic_ReactionFireEnhance": "2件套：火元素反应伤害提升。",
    "Relic_ElementalBurstUp": "2件套：元素爆发伤害提升。",
    "Relic_TeamAtkupAfterElementalBurst": "2件套：施放元素爆发后全队攻击力提升。",
    "Relic_KillEnhanceExtraAtk": "2件套：击败敌人后攻击力提升。",
    "Relci_RangerAttackUp": "2件套：远程角色攻击力提升。",
}


def _artifact_desc_fallback(affix: dict) -> str:
    """当 TextMap 缺失套装效果描述时，基于 addProps/openConfig 生成中文描述"""
    oc = affix.get("openConfig", "")
    if oc and oc in _ARTIFACT_OPENCONFIG_CN:
        return _ARTIFACT_OPENCONFIG_CN[oc]
    # 基于 addProps 生成（如 攻击力 18%）
    parts = []
    for p in affix.get("addProps", []):
        pt = p.get("propType", "")
        val = p.get("value", 0)
        if pt == "FIGHT_PROP_NONE" or not pt:
            continue
        cn = _ARTIFACT_PROP_CN.get(pt, pt)
        if val and abs(val) < 1:
            parts.append(f"{cn}提高{val*100:.0f}%")
        elif val:
            parts.append(f"{cn}提高{val:.0f}")
    if parts:
        return "、".join(parts)
    return ""


def normalize_artifacts(
    reliquary_sets: list,
    reliquaries: list,
    equip_affixes: list,
    textmap: dict,
) -> list:
    """
    圣遗物数据
    - 圣遗物套装（2件/4件效果）
    - 主副词条
    """
    hashes = build_hash_key_map(textmap)

    # 套装效果
    # 注意：ReliquarySet.equipAffixId 引用的是 EquipAffix 的 id 字段（如 210001），
    # 而 affixId 是每级唯一值（如 2100010/2100011）。故以 id 为键建立映射。
    # 套装效果 level: 0 = 2件套, 1 = 4件套（需全部保留）
    affix_map = {}
    for af in equip_affixes:
        aid = af.get("id", 0)
        if aid not in affix_map:
            affix_map[aid] = []
        affix_map[aid].append(af)

    set_effects = {}
    for rs in reliquary_sets:
        sid = rs.get("setId", 0)
        affix_id = rs.get("equipAffixId", 0)
        name = hashes.get(str(rs.get("textList", [0])[0]), "")
        effects = []
        for af in affix_map.get(affix_id, []):
            lv = af.get("level", 0)
            # level 0 -> 2件套, level 1 -> 4件套
            pieces = 2 if lv == 0 else (4 if lv == 1 else (lv + 1) * 2)
            desc = hashes.get(str(af.get("descTextMapHash", "")), "")
            if not desc:
                desc = _artifact_desc_fallback(af)
            effects.append({
                "pieces": pieces,
                "desc": desc,
                "param_list": af.get("paramList", []),
                "open_config": af.get("openConfig", ""),
            })
        set_effects[sid] = {
            "set_id": sid,
            "name": name,
            "name_cn": name,
            "contains": rs.get("containsList", []),
            "need_num": rs.get("setNeedNum", []),
            "effects": effects,
        }

    # 单件圣遗物基础信息（花/羽毛/沙/杯/头）
    piece_stats = {}
    for rel in reliquaries:
        rid = rel.get("id", 0)
        if rid in piece_stats:
            continue
        piece_stats[rid] = {
            "id": rid,
            "set_id": rel.get("setId", 0),
            "slot": rel.get("equipType", ""),
            "rank": rel.get("rankLevel", 1),
            "main_prop": rel.get("mainPropDepotId", 0),
            "append_prop": rel.get("appendPropDepotId", 0),
        }

    # 输出只保留套装定义（保持 v2 结构）
    return list(set_effects.values())


def normalize_constellations(
    talents: list,
    skill_depots: list,
    textmap: dict,
    avatars: list,
) -> list:
    """
    角色命座效果
    - 通过 skillDepot.talents 关联到角色
    """
    hashes = build_hash_key_map(textmap)

    # 角色名映射
    char_names = {}
    for av in avatars:
        char_names[av.get("skillDepotId", 0)] = resolve_avatar_name(av, hashes)

    talent_map = {}
    for t in talents:
        talent_map[t.get("talentId", 0)] = t

    results = []
    for d in skill_depots:
        depot_id = d.get("id", 0)
        char_id = next(
            (av.get("id") for av in avatars if av.get("skillDepotId") == depot_id),
            None,
        )
        char_name = char_names.get(depot_id, "")
        talents_list = [t for t in d.get("talents", []) if t and t > 0]

        consts = []
        for tid in talents_list:
            t = talent_map.get(tid)
            if not t:
                continue
            # 从 openConfig 提取层数: Ayaka_Constellation_1 -> 1
            m = re.search(r"_(\d+)$", t.get("openConfig", "") or "")
            const_level = int(m.group(1)) if m else (tid % 100)
            cname = hashes.get(str(t.get("nameTextMapHash", "")), "") or f"Constellation_{const_level}"
            consts.append({
                "talent_id": tid,
                "constellation_level": const_level,
                "name": cname,
                "name_cn": cname,
                "desc": hashes.get(str(t.get("descTextMapHash", "")), "") or "",
                "param_list": t.get("paramList", []),
                "open_config": t.get("openConfig", ""),
            })

        if char_name and consts:
            results.append({
                "character_id": char_id,
                "character_name": char_name,
                "character_name_cn": char_name,
                "depot_id": depot_id,
                "constellations": consts,
            })
    return results


def _apply_meropide_panel_override(characters: list) -> int:
    """若存在 data/meropide/characters_meropide.json（meropide.cn 采集数据），
    用其权威 Lv90 面板覆盖本地曲线计算值。

    背景：AnimeGameData 仓库的 AvatarCurveExcelConfigData 数值失真
    （如 GROW_CURVE_HP_S5@90 = 8.739，实际游戏值 ≈ 13.225），
    导致全角色 stats_90 系统性偏低约 32%。meropide 面板与游戏内实测一致。
    """
    mp_path = os.path.join(DATA_DIR, "meropide", "characters_meropide.json")
    if not os.path.exists(mp_path):
        return 0
    try:
        with open(mp_path, "r", encoding="utf-8") as f:
            mp = json.load(f)
    except Exception as e:
        print(f"  [WARN] meropide 数据加载失败，跳过面板覆盖: {e}")
        return 0
    by_name = {c.get("name"): c for c in mp.get("items", [])}
    n = 0
    for ch in characters:
        m = by_name.get(ch.get("name_cn"))
        if not m:
            continue
        s90 = (m.get("stats_by_level") or {}).get("90") or {}
        if all(isinstance(s90.get(k), (int, float)) and s90[k] > 0
               for k in ("hp", "atk", "def")):
            ch["stats_90"] = {"hp": s90["hp"], "atk": s90["atk"], "def": s90["def"]}
            ch["stats_source"] = f"meropide ({m.get('fetch_date', '')})"
            n += 1
    return n


# ==================== 主流程 ====================

def main():
    global VERBOSE

    parser = argparse.ArgumentParser(
        description="原神数据获取脚本 v3.0（数据源: DimbreathBot/AnimeGameData）"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新下载全部数据，忽略版本检测",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细日志",
    )
    args = parser.parse_args()
    VERBOSE = args.verbose

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    print("=" * 56)
    print("  原神数据获取脚本 v3.0")
    print(f"  数据源: https://github.com/{REPO}")
    print(f"  输出目录: {DATA_DIR}")
    print("=" * 56)

    # ---------- [1/6] 版本检测 ----------
    print("\n[1/6] 版本检测")
    local_ver = load_local_version()
    remote_ver = None
    try:
        remote_ver = get_remote_version()
    except Exception as e:
        log_warn(f"无法获取远程版本信息: {e}")
        log_warn("将检查缓存完整性；若缓存完整则继续使用缓存数据")

    if local_ver:
        log_info(f"检查本地版本: {format_version(local_ver)} (commit: {local_ver.get('short_sha', '?')})")
    else:
        log_info("检查本地版本: 无（首次运行）")

    if remote_ver:
        log_info(f"远程最新版本: {format_version(remote_ver)} (commit: {remote_ver['short_sha']})")
        log_debug(f"最近提交: {remote_ver['message']}  ({remote_ver['date']})")

    # 缓存完整性检查
    cache_complete = (
        all(os.path.exists(os.path.join(RAW_DIR, fn)) for fn in SOURCE_FILES)
        and os.path.exists(os.path.join(RAW_DIR, TEXTMAP_FILENAME))
    )

    # 确定更新策略
    if args.force:
        strategy = "force"
        log_info("检测到 --force，强制全量重新下载...")
    elif remote_ver and local_ver and local_ver.get("sha") and local_ver.get("sha") == remote_ver.get("sha"):
        if cache_complete:
            strategy = "cache"
            log_info("版本一致且缓存完整，无需下载，直接使用缓存数据")
        else:
            strategy = "full"
            log_warn("版本一致但缓存不完整，重新下载缺失文件")
    elif remote_ver and not local_ver:
        strategy = "full"
        log_info("首次运行，开始全量下载...")
    elif remote_ver:
        strategy = "full"
        log_info("发现新版本，开始下载...")
    else:
        # 远程版本不可用
        if cache_complete:
            strategy = "cache"
            log_warn("远程版本不可用，但缓存完整，使用缓存数据")
        else:
            strategy = "full"
            log_warn("远程版本不可用且缓存不完整，尝试重新下载")

    # ---------- [2/6] 下载源数据 ----------
    print("\n[2/6] 下载源数据")

    if strategy == "cache":
        log_info("读取缓存数据...")
        data = {}
        for fn in SOURCE_FILES:
            data[fn] = load_json(os.path.join(RAW_DIR, fn))
        textmap = load_json(os.path.join(RAW_DIR, TEXTMAP_FILENAME))
        log_info("缓存读取完成")
    else:
        data = {}
        for fn in SOURCE_FILES:
            data[fn] = download_raw_file(fn, force=(strategy == "force"))
        textmap = download_textmap(force=(strategy == "force"))
        if not textmap:
            # TextMap 为空或下载失败 → 必须报错退出，避免生成缺少中文名的数据
            raise RuntimeError("TextMapCHS.json 下载失败，无法生成包含中文名的数据，已中止。")

    # ---------- [3/6] 生成数据文件 ----------
    print("\n[3/6] 生成 characters.json ...")
    characters = normalize_characters(
        data["AvatarExcelConfigData.json"],
        data["AvatarCurveExcelConfigData.json"],
        data["AvatarSkillDepotExcelConfigData.json"],
        textmap,
        {"_avatar_skills": data["AvatarSkillExcelConfigData.json"]},
        data["AvatarPromoteExcelConfigData.json"],
    )
    n_mp = _apply_meropide_panel_override(characters)
    if n_mp:
        print(f"  已用 meropide.cn 权威面板覆盖 {n_mp} 名角色的 stats_90")
    print(f"  角色数: {len(characters)}")
    out_path = os.path.join(DATA_DIR, "characters.json")
    save_json(out_path, characters)
    print(f"  -> 已保存 {out_path}")

    print("\n[4/6] 生成 skills.json ...")
    skills = normalize_skills(
        data["ProudSkillExcelConfigData.json"],
        data["AvatarSkillExcelConfigData.json"],
        data["AvatarSkillDepotExcelConfigData.json"],
        textmap,
    )
    print(f"  技能仓库: {len(skills['skill_depots'])} 个")
    print(f"  天赋倍率组: {len(skills['proud_skill_groups'])} 组")
    out_path = os.path.join(DATA_DIR, "skills.json")
    save_json(out_path, skills)
    print(f"  -> 已保存 {out_path}")

    print("\n[5/6] 生成 weapons.json / artifacts.json / constellations.json ...")
    weapons = normalize_weapons(
        data["WeaponExcelConfigData.json"],
        data["WeaponCurveExcelConfigData.json"],
        data["EquipAffixExcelConfigData.json"],
        textmap,
    )
    print(f"  武器数: {len(weapons)}")
    out_path = os.path.join(DATA_DIR, "weapons.json")
    save_json(out_path, weapons)
    print(f"  -> 已保存 {out_path}")

    artifacts = normalize_artifacts(
        data["ReliquarySetExcelConfigData.json"],
        data["ReliquaryExcelConfigData.json"],
        data["EquipAffixExcelConfigData.json"],
        textmap,
    )
    print(f"  圣遗物套装数: {len(artifacts)}")
    out_path = os.path.join(DATA_DIR, "artifacts.json")
    save_json(out_path, artifacts)
    print(f"  -> 已保存 {out_path}")

    constellations = normalize_constellations(
        data["AvatarTalentExcelConfigData.json"],
        data["AvatarSkillDepotExcelConfigData.json"],
        textmap,
        data["AvatarExcelConfigData.json"],
    )
    print(f"  命座角色数: {len(constellations)}")
    out_path = os.path.join(DATA_DIR, "constellations.json")
    save_json(out_path, constellations)
    print(f"  -> 已保存 {out_path}")

    log_info("数据解析完成，生成 5 个 JSON 文件")

    # ---------- [6/6] 更新版本文件 ----------
    print("\n[6/6] 更新本地版本文件")
    if remote_ver:
        save_local_version(remote_ver)
        log_info(f"更新本地版本文件: {format_version(remote_ver)} (commit: {remote_ver['short_sha']})")
    else:
        log_warn("未获取到远程版本信息，跳过版本文件更新（下次运行将重新检测）")

    print("\n=== 数据获取完成！===")
    print(f"5 个 JSON 文件已生成到 {DATA_DIR}/")
    print(f"原始数据缓存: {RAW_DIR}/")
    if args.force:
        print("（本次为强制刷新）")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断，已取消。")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)