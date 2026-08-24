"""
队伍类 - 管理 4 个角色，实现月反应间接伤害的排序加权算法
"""
from . import constants

class Team:
    def __init__(self, members: list):
        """
        members: 长度为 4 的 Character 列表（不足4个可补 None）
        """
        self.members = members[:4]
        while len(self.members) < 4:
            self.members.append(None)

    def calculate_lunar_indirect_damage(self, trigger_element: str, enemy_res: float = 0.1) -> float:
        """
        计算月反应间接伤害（排序加权求和）
        - 遍历 4 个成员，计算每个人的"个人月反应伤害"
        - 从高到低排序
        - 加权求和：最高×1 + 第二×1/2 + 第三×1/12 + 第四×1/12

        trigger_element: 月反应类型 ("lunar_charged", "lunar_crystallize", "lunar_bloom")
        """
        if trigger_element not in constants.LUNAR_REACTION_COEFF:
            raise ValueError(f"未知的月反应类型: {trigger_element}")

        coeff = constants.LUNAR_REACTION_COEFF[trigger_element]["indirect"]
        res_factor = constants.resistance_factor(enemy_res)

        personal_damages = []
        for char in self.members:
            if char is None:
                continue
            panel = char.get_effective_panel()
            # 个人伤害 = 反应系数 × 等级系数 × (1 + 月反应基础伤害加成) × (1 + 精通增益 + 反应伤害加成) × 抗性区 × 暴击区
            em_bonus = constants.em_bonus_lunar(panel["elemental_mastery"])
            lunar_bonus = panel["lunar_dmg_bonus"]
            reaction_bonus = panel["reaction_dmg_bonus"]
            crit_dmg = panel["crit_dmg"]

            personal = (
                coeff
                * constants.LEVEL_COEFFICIENT
                * (1 + lunar_bonus)
                * (1 + em_bonus + reaction_bonus)
                * res_factor
                * (1 + crit_dmg)
            )
            personal_damages.append(personal)

        # 从高到低排序
        personal_damages.sort(reverse=True)

        # 加权求和（只取前四高）
        total = 0.0
        for i, dmg in enumerate(personal_damages[:4]):
            weight = constants.LUNAR_INDIRECT_WEIGHTS[i]
            total += dmg * weight

        return total

    def get_active_modifiers(self) -> list:
        """获取队伍中所有激活的常驻效果（如元素共鸣、武器特效等）"""
        modifiers = []
        elements = set()
        for char in self.members:
            if char is not None:
                elements.add(char.element)
        # 元素共鸣（简化示例）
        if len(elements) == 1:
            modifiers.append({"type": "elemental_resonance", "element": list(elements)[0]})
        return modifiers

    def calculate_lunar_state(self) -> dict:
        """计算队伍当前的月兆状态
        - 初辉：队伍中月兆角色数量 >= 1
        - 满辉：队伍中月兆角色数量 >= 2
        当前阶段仅作状态标记，不产生数值加成。
        """
        lunar_count = sum(
            1 for m in self.members
            if m is not None and "月兆" in getattr(m, "states", [])
        )
        return {
            "lunar_count": lunar_count,
            "chuhui": lunar_count >= 1,   # 初辉
            "manhui": lunar_count >= 2,   # 满辉
        }