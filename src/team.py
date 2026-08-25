"""
队伍类 - 管理 4 个角色，实现月反应间接伤害的排序加权算法
"""
from . import constants
from . import data_loader

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

    def apply_team_passives(self) -> dict:
        """
        应用队伍型固有天赋（跨角色增益）：
        - em_share：全队精通共享（砂糖触媒置换术/小小的慧风、伊涅芙全相重构协议）
          施加者自身不受益（与游戏一致），其余成员获得加成
        - em_to_elemental_dmg：万叶式"每点精通→0.04%对应元素伤"，
          按施加者触发后的精通计算，注入受益者的 elemental_dmg_bonus

        :return: {"em_gain": {char_name: 总共获得多少点精通},
                  "dmg_from_em": {char_name: 获得的元素伤害加成}}
        """
        em_gain = {}
        dmg_from_em = {}
        for giver in self.members:
            if giver is None:
                continue
            for p in giver.passive_skills:
                desc = (p.get("description") or "").strip()
                if not desc:
                    continue
                eff = data_loader.parse_effect(desc)
                for te in eff.get("team_effects") or []:
                    for receiver in self.members:
                        if receiver is None or receiver is giver:
                            continue
                        if te["type"] == "em_share":
                            if te.get("from") == "em_max":
                                # 纳西妲式：按全队最高精通的 X%，至多 cap 点
                                em_values = [
                                    m._conversion_source_value("em")
                                    for m in self.members if m is not None
                                ]
                                base = max(em_values) if em_values else 0.0
                                gain = base * float(te.get("pct", 0.0))
                                cap = te.get("cap")
                                if cap is not None:
                                    gain = min(gain, float(cap))
                                receiver.team_effects_received["em_flat"] += gain
                                em_gain[receiver.name] = em_gain.get(receiver.name, 0.0) + gain
                            elif "flat" in te:
                                receiver.team_effects_received["em_flat"] += float(te["flat"])
                                em_gain[receiver.name] = em_gain.get(receiver.name, 0.0) + float(te["flat"])
                            elif "pct" in te:
                                frm = te.get("from", "em")
                                if frm == "em":
                                    src_val = giver._conversion_source_value("em")
                                    flat_eq = src_val * float(te["pct"])
                                    receiver.team_effects_received["em_flat"] += flat_eq
                                    em_gain[receiver.name] = em_gain.get(receiver.name, 0.0) + flat_eq
                                else:
                                    recv_map = receiver.team_effects_received.setdefault("em_from", {})
                                    recv_map[frm] = max(recv_map.get(frm, 0.0), float(te["pct"]))
                        elif te["type"] == "atk_share":
                            receiver.team_effects_received["atk_pct"] += float(te.get("pct", 0.0))
                        elif te["type"] == "em_to_elemental_dmg":
                            bonus = giver._conversion_source_value("em") * float(te["ratio"])
                            receiver.team_effects_received["em_to_dmg"] += bonus
                            dmg_from_em[receiver.name] = dmg_from_em.get(receiver.name, 0.0) + bonus
        return {"em_gain": em_gain, "dmg_from_em": dmg_from_em}

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