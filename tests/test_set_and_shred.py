# -*- coding: utf-8 -*-
"""
圣遗物套装分支（单四件套 / 2+2）与敌人减抗接入伤害公式的回归测试
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import constants
from src.calculator import calculate_damage
from src.character import Character
from src.data_loader import parse_effect
from src.effects import EffectManager
from src.optimizer import DamageOptimizer, OptimizationInput


def _passive_desc(char: Character, key: str) -> str:
    for p in char.passive_skills:
        if key in p.get("name", ""):
            return p.get("description", "")
    raise AssertionError(f"未找到含「{key}」的固有天赋")


class TestArtifactSetBranching(unittest.TestCase):
    """圣遗物套装：单四件套自动附带2件套；2+2 两套各触发2件套"""

    def test_apply_artifact_pieces_filters(self):
        """apply_artifact_pieces 只激活指定件数的效果条目"""
        em = EffectManager(Character("迪卢克", 0))
        em.apply_artifact_pieces("10006", {2})
        self.assertTrue(em.active_effects)
        self.assertTrue(all(e["pieces"] == 2 for e in em.active_effects))

        em2 = EffectManager(Character("迪卢克", 0))
        em2.apply_artifact_pieces("10006", {2, 4})
        self.assertEqual({e["pieces"] for e in em2.active_effects}, {2, 4})

    def test_legacy_set4_triggers_both_pieces(self):
        """旧接口 set_4_id：四件套装备时 2件套+4件套效果同时生效"""
        em = EffectManager(Character("迪卢克", 0))
        em.apply_artifact_effect(set_4_id="10006")
        em.trigger_event("always")
        self.assertEqual({e["pieces"] for e in em.active_effects}, {2, 4})

    def test_legacy_set2_triggers_only_two(self):
        """旧接口 set_2_id：仅触发 2件套效果（修复旧实现整套无差别激活）"""
        em = EffectManager(Character("迪卢克", 0))
        em.apply_artifact_effect(set_2_id="10008")
        em.trigger_event("always")
        self.assertEqual({e["pieces"] for e in em.active_effects}, {2})

    def test_optimizer_single_four_piece(self):
        """非2+2 模式：只选一个四件套，其 2件套+4件套条目同时激活且数值生效"""
        inp = OptimizationInput(
            character_id="迪卢克",
            artifact_set_4="10004",   # 奇迹：4件套元素伤害加成（ElemDmgEnhanceElemResist）
            is_double_two_piece=False,
        )
        opt = DamageOptimizer(inp)
        em = opt._build_effect_manager(Character("迪卢克", 0))
        em.trigger_event("always")
        mods = em.get_final_modifiers()
        self.assertEqual(
            {(e["set_id"], e["pieces"]) for e in em.active_effects},
            {("10004", 2), ("10004", 4)},
        )
        self.assertGreater(mods["elemental_dmg_bonus"], 0)   # 4件套贡献

    def test_optimizer_double_two_piece(self):
        """2+2 模式：两个套装各只触发其 2件套，数值叠加"""
        inp = OptimizationInput(
            character_id="迪卢克",
            artifact_set_2="10006",   # 武人 2件套：攻击%
            artifact_set_4="10008",   # 赌徒 2件套：技能增伤
            is_double_two_piece=True,
        )
        opt = DamageOptimizer(inp)
        em = opt._build_effect_manager(Character("迪卢克", 0))
        em.trigger_event("always")
        mods = em.get_final_modifiers()
        self.assertEqual(
            {(e["set_id"], e["pieces"]) for e in em.active_effects},
            {("10006", 2), ("10008", 2)},
        )
        self.assertGreater(mods["atk_percent"], 0)
        self.assertGreater(mods["dmg_bonus"], 0)

class TestResShred(unittest.TestCase):
    """天赋减抗：解析 → 角色注册 → 抗性乘区生效"""

    def _chongyun_with_shred(self) -> Character:
        c = Character("重云")
        desc = _passive_desc(c, "追冰剑诀")
        eff = parse_effect(desc)
        c.add_res_shred(eff["res_shred"])
        return c

    def test_matching_element_shred_applied_in_calc(self):
        """重云·追冰剑诀（冰抗-10%）：对冰伤角色的抗性区按减抗后数值计算"""
        c = self._chongyun_with_shred()
        res = calculate_damage(c, "skill", 10, 90, 0.1)
        bd = res["breakdown"]
        self.assertAlmostEqual(bd["res_shred_total"], 0.1, places=9)
        self.assertAlmostEqual(bd["effective_enemy_res"], 0.0, places=9)
        self.assertAlmostEqual(bd["res_factor"],
                               constants.resistance_factor(0.0), places=9)

    def test_mismatched_element_not_applied(self):
        """元素专属减抗不匹配时不生效；匹配时生效"""
        c = self._chongyun_with_shred()
        self.assertAlmostEqual(c.get_applicable_res_shred("火"), 0.0, places=9)
        self.assertAlmostEqual(c.get_applicable_res_shred("冰"), 0.1, places=9)

    def test_all_element_shred_applies_to_any(self):
        """希格雯·急性剂量（全抗-10%）：对任意元素都生效"""
        c = Character("希格雯")
        desc = _passive_desc(c, "急性剂量")
        eff = parse_effect(desc)
        c.add_res_shred(eff["res_shred"])
        for elem in ("火", "水", "雷", "冰", "风", "岩", "草"):
            self.assertAlmostEqual(c.get_applicable_res_shred(elem), 0.1, places=9)

    def test_dual_element_shred_registered(self):
        """夏沃蕾·尖兵协同战法（火雷双减抗）：两元素各自匹配"""
        c = Character("夏沃蕾")
        desc = _passive_desc(c, "尖兵协同战法")
        eff = parse_effect(desc)
        c.add_res_shred(eff["res_shred"])
        self.assertAlmostEqual(c.get_applicable_res_shred("火"), 0.4, places=9)
        self.assertAlmostEqual(c.get_applicable_res_shred("雷"), 0.4, places=9)
        self.assertAlmostEqual(c.get_applicable_res_shred("水"), 0.0, places=9)

    def test_full_effects_route_res_shreds(self):
        """optimizer._apply_full_effects 将 UI 的 res_shreds 注入角色"""
        opt = DamageOptimizer(OptimizationInput(character_id="迪卢克"))
        char = Character("迪卢克")
        opt._apply_full_effects(
            char, {"res_shreds": [{"element": "all", "value": 0.1}]})
        self.assertAlmostEqual(char.get_applicable_res_shred("火"), 0.1, places=9)

    def test_extra_res_shred_param(self):
        """calculate_damage 的 extra_res_shred（队友减抗聚合）提升最终伤害"""
        c = Character("迪卢克", 0)
        base = calculate_damage(c, "skill", 10, 90, 0.5)["damage"]
        shred = calculate_damage(c, "skill", 10, 90, 0.5,
                                 extra_res_shred=0.2)["damage"]
        self.assertGreater(shred, base)
        # 0.5 - 0.2 = 0.3 → 抗性区应精确等于 resistance_factor(0.3)
        bd = calculate_damage(c, "skill", 10, 90, 0.5,
                              extra_res_shred=0.2)["breakdown"]
        self.assertAlmostEqual(bd["res_factor"],
                               constants.resistance_factor(0.3), places=9)


if __name__ == "__main__":
    unittest.main()

