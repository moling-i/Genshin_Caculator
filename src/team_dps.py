"""
队伍 DPS 评估模块

设计目标：在「用户编排的轮换」下，计算整支队伍在一段时间内的总伤害与平均 DPS，
并以此作为优化目标，联合搜索 4 名成员的词条分配（见 optimizer.py 的 TeamDPSOptimizer）。

轮换（Rotation）由若干「步骤（RotationStep）」组成，每步指定：
  - character_index : 出手的成员下标（0~3）
  - skill_type      : normal / skill / burst / charged
  - hit_count       : 该技能取前几段倍率求和（多段技能用；默认 1）
  - field_seconds   : 该步占用的相对时间（秒）；缺省按技能类型给保守默认
  - reaction_type   : 该步触发的反应（vaporize / melt / aggravate / lunar_* 等），可空
  - is_crit         : 是否强制暴击（默认 False → 按暴击期望计入）

说明：本仓库数据（meropide / gensri）包含技能倍率、冷却与能量消耗，但**不包含**
每次动作的动画时长，因此时间轴由用户显式给出（或取默认估值），不做帧级模拟。
"""
import json
import logging
import os
from .character import Character
from .effects import EffectManager
from .calculator import calculate_damage
from .team import Team
from . import constants, data_loader

logger = logging.getLogger(__name__)

# 动作帧数据（来自 gcsim，单位秒）；由 fetch_gcsim_frames.py 在联网机器上生成
ACTION_FRAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "action_frames.json",
)


def load_action_frames(path=None):
    """加载动作帧数据 {character_id: {skill_type: seconds}}；缺失或损坏时返回空字典。"""
    p = path or ACTION_FRAMES_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _step_seconds(step, char, action_frames):
    """步骤占用秒数：优先用显式 field_seconds，其次用 gcsim 帧数据，最后退回启发式默认。"""
    if step.field_seconds is not None:
        return step.field_seconds
    if action_frames and char is not None:
        af = action_frames.get(getattr(char, "id", None))
        if isinstance(af, dict) and step.skill_type in af:
            return af[step.skill_type]
    return DEFAULT_STEP_SECONDS.get(step.skill_type, 1.5)

# 每步默认占用时间（秒）——仅在没有明确给出 field_seconds 时兜底使用
DEFAULT_STEP_SECONDS = {
    "normal": 2.0,
    "skill": 1.5,
    "burst": 1.5,
    "charged": 2.0,
}

# 剧变反应不暴击（暴击区恒为 1.0）
_TRANSFORMATIVE = ("overload", "superconduct", "swirl", "shatter", "electrocharged")


class RotationStep:
    """轮换中的单步动作"""

    __slots__ = (
        "character_index", "skill_type", "hit_count",
        "field_seconds", "reaction_type", "is_crit", "label",
    )

    def __init__(self, character_index, skill_type, hit_count=1,
                 field_seconds=None, reaction_type=None, is_crit=False, label=""):
        self.character_index = int(character_index)
        self.skill_type = skill_type
        self.hit_count = int(hit_count)
        self.field_seconds = field_seconds
        self.reaction_type = reaction_type
        self.is_crit = bool(is_crit)
        self.label = label or f"成员{self.character_index + 1}·{self.skill_type}"

    def to_dict(self):
        return {
            "character_index": self.character_index,
            "skill_type": self.skill_type,
            "hit_count": self.hit_count,
            "field_seconds": self.field_seconds,
            "reaction_type": self.reaction_type,
            "is_crit": self.is_crit,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            character_index=d["character_index"],
            skill_type=d["skill_type"],
            hit_count=d.get("hit_count", 1),
            field_seconds=d.get("field_seconds"),
            reaction_type=d.get("reaction_type"),
            is_crit=d.get("is_crit", False),
            label=d.get("label", ""),
        )


class Rotation:
    """一支队伍的轮换（步骤序列）"""

    def __init__(self, steps, name="", source=""):
        # 兼容传入 RotationStep 对象或 dict（app.py 编排界面产出 dict）
        self.steps = [
            s if isinstance(s, RotationStep) else RotationStep.from_dict(s)
            for s in steps
        ]
        self.name = name
        self.source = source

    def total_time(self):
        t = 0.0
        for s in self.steps:
            t += s.field_seconds if s.field_seconds is not None \
                else DEFAULT_STEP_SECONDS.get(s.skill_type, 1.5)
        return t

    def to_dict(self):
        return {
            "name": self.name,
            "source": self.source,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            [RotationStep.from_dict(s) for s in d.get("steps", [])],
            name=d.get("name", ""),
            source=d.get("source", ""),
        )


def _skill_hit_ratios(char: Character, skill_type: str, talent_level: int, hit_count: int):
    """取该技能前 hit_count 段的倍率列表；无数据则退化为单一总倍率。"""
    internal = constants.SKILL_TYPE_MAP.get(skill_type, skill_type)
    res = data_loader.get_skill_ratios(char.skill_depot_id, internal, talent_level)
    ratios = []
    if res:
        params = res.get("param_list", [])
        ratios = [p for p in params if isinstance(p, (int, float))]
    if not ratios:
        r = char.get_talent_ratio(skill_type, talent_level)
        return [r] * max(1, hit_count)
    if hit_count and hit_count < len(ratios):
        ratios = ratios[:hit_count]
    return ratios


def evaluate_team_dps(members, rotation, enemy_level=90, enemy_res=0.1,
                      effect_managers=None, talent_levels=None,
                      extra_res_shred=0.0, action_frames=None, star_params=None):
    """
    评估整队 DPS。

    :param members: 长度 4 的 Character 列表（已应用好主词条/副词条/面板起点/固有天赋）。
    :param rotation: Rotation 实例。
    :param effect_managers: 长度 4 的 EffectManager 列表或 None；
                            非 None 时按其 get_final_modifiers 叠加武器/圣遗物/命座效果。
    :param talent_levels: 长度 4 的字典列表，每个为 {skill_type: level}；缺省统一 10 级。
    :return: dict {total_damage, total_time, dps, per_step, per_character}
    """
    members = (list(members) + [None] * 4)[:4]
    ems = (list(effect_managers) + [None] * 4)[:4] if effect_managers else [None] * 4
    tls = (list(talent_levels) + [None] * 4)[:4] if talent_levels else [None] * 4

    # 星反应参数：仅当该步 reaction_type 属于星反应时转发，避免污染普通步骤
    _STAR_TYPES = ("stellar_superconduct", "star_swirl", "star_swirl_direct")
    sp = dict(star_params or {})

    # 队伍型固有天赋（精通共享 / 攻击共享 等）
    team = Team(members)
    team.apply_team_passives()

    per_character = {i: 0.0 for i in range(4)}
    per_step = []
    total_damage = 0.0
    total_time = 0.0

    for step in rotation.steps:
        idx = step.character_index
        char = members[idx]
        if char is None:
            per_step.append({"label": step.label, "damage": 0.0, "time": 0.0, "note": "空位"})
            continue

        em = ems[idx]
        tl_map = tls[idx] or {}
        level = int(tl_map.get(step.skill_type, 10))
        ratios = _skill_hit_ratios(char, step.skill_type, level, step.hit_count)

        # 月反应/星反应间接伤害：整队加权为一次触发，忽略多段拆分
        if step.reaction_type in ("lunar_charged", "lunar_crystallize", "lunar_bloom", "star_swirl"):
            res = calculate_damage(
                character=char, skill_type=step.skill_type, talent_level=level,
                enemy_level=enemy_level, enemy_res=enemy_res,
                reaction_type=step.reaction_type, is_crit=step.is_crit,
                team=team, effect_manager=em, extra_res_shred=extra_res_shred,
                **(sp if step.reaction_type in _STAR_TYPES else {}),
            )
            step_dmg = res["damage"]
        else:
            step_dmg = 0.0
            for r in ratios:
                res = calculate_damage(
                    character=char, skill_type=step.skill_type, talent_level=level,
                    enemy_level=enemy_level, enemy_res=enemy_res,
                    reaction_type=step.reaction_type, is_crit=step.is_crit,
                    team=team, effect_manager=em, extra_res_shred=extra_res_shred,
                    talent_ratio_override=r,
                    **(sp if step.reaction_type in _STAR_TYPES else {}),
                )
                d = res["damage"]
                # 非剧变且未强制暴击 → 按暴击期望计入（与单体优化器口径一致）
                if step.reaction_type not in _TRANSFORMATIVE and not step.is_crit:
                    panel = char.get_effective_panel()
                    mods = em.get_final_modifiers() if em else {}
                    cr = min(panel["crit_rate"] + mods.get("crit_rate", 0.0), 1.0)
                    cd = panel["crit_dmg"] + mods.get("crit_dmg", 0.0)
                    d = d * (1 + cr * cd)
                step_dmg += d

        secs = _step_seconds(step, char, action_frames)
        total_damage += step_dmg
        total_time += secs
        per_character[idx] += step_dmg
        per_step.append({"label": step.label, "damage": step_dmg, "time": secs})

    dps = total_damage / total_time if total_time > 0 else 0.0
    return {
        "total_damage": total_damage,
        "total_time": total_time,
        "dps": dps,
        "per_step": per_step,
        "per_character": per_character,
    }


# ----------------------------------------------------------------------------
# 主流配队「示例」轮换预设（结构合理、时间近似，均可在 UI 中编辑）
# 成员下标固定：0=主力 / 1~3=队友
# ----------------------------------------------------------------------------
PRESET_ROTATIONS = {
    # 玛薇卡火神队（7.0 示例）：0=主C(玛薇卡) 1=减抗辅助(希诺宁式) 2=班尼特 3=挂冰副C(茜特菈莉式)
    # 你在 UI 中把对应角色塞进成员1~4 即可；反应以融化为主。
    "玛薇卡火神队（示例）": Rotation.from_dict({
        "name": "玛薇卡火神队（示例）",
        "source": "7.0 打法骨架示例，时间近似，请按实际手法编辑",
        "steps": [
            {"character_index": 2, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "班尼特·Q 增攻"},
            {"character_index": 1, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "减抗辅助·E"},
            {"character_index": 3, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "挂冰副C·E"},
            {"character_index": 3, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "挂冰副C·Q"},
            {"character_index": 0, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.5, "label": "主C·E 战意"},
            {"character_index": 0, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "reaction_type": "melt", "label": "主C·Q 融化"},
            {"character_index": 0, "skill_type": "charged", "hit_count": 2, "field_seconds": 3.0, "reaction_type": "melt", "label": "主C·重击 融化×2"},
        ],
    }),
    # 月结晶战舰（7.0 示例）：0=主C 1=月反应辅助(爱可菲式) 2=副C 3=副C
    # 反应以月结晶(lunar_crystallize)为主；你将月系角色塞进成员1~4。
    "月结晶战舰（示例）": Rotation.from_dict({
        "name": "月结晶战舰（示例）",
        "source": "7.0 打法骨架示例，时间近似，请按实际手法编辑",
        "steps": [
            {"character_index": 1, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "月辅·E 挂月"},
            {"character_index": 1, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "月辅·Q"},
            {"character_index": 2, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "副C·E"},
            {"character_index": 3, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "副C·Q"},
            {"character_index": 0, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.5, "label": "主C·E"},
            {"character_index": 0, "skill_type": "normal", "hit_count": 3, "field_seconds": 3.0, "reaction_type": "lunar_crystallize", "label": "主C·A×3 月结晶"},
            {"character_index": 0, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "reaction_type": "lunar_crystallize", "label": "主C·Q 月结晶"},
        ],
    }),
    # 星扩散队（7.0 示例）：0=主C 1=风扩散辅助(万叶式) 2=副C 3=副C
    # 引擎已支持「星反应(Stellar)」：星超导(stellar_superconduct) / 星扩散风涡(star_swirl) / 星扩散直伤(star_swirl_direct)
    "星扩散队（示例）": Rotation.from_dict({
        "name": "星扩散队（示例）",
        "source": "7.0 打法骨架示例（扩散），时间近似，请按实际手法编辑",
        "steps": [
            {"character_index": 1, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "风辅·E 扩散"},
            {"character_index": 1, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "风辅·Q 增伤"},
            {"character_index": 2, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.0, "label": "副C·E"},
            {"character_index": 3, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "label": "副C·Q"},
            {"character_index": 0, "skill_type": "skill", "hit_count": 1, "field_seconds": 1.5, "label": "主C·E"},
            {"character_index": 0, "skill_type": "normal", "hit_count": 2, "field_seconds": 2.0, "reaction_type": "swirl", "label": "主C·A×2 扩散"},
            {"character_index": 0, "skill_type": "burst", "hit_count": 1, "field_seconds": 1.5, "reaction_type": "swirl", "label": "主C·Q 扩散"},
        ],
    }),
}
