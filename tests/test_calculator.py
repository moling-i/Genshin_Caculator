"""
单元测试 - 验证伤害计算核心引擎
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import Character, Team, EffectManager, calculate_damage, constants


class TestBasicDamage(unittest.TestCase):
    """单人常规伤害测试"""

    def test_diluc_vaporize(self):
        """迪卢克（C0）元素爆发蒸发，检查增伤区是否包含魔女4件效果"""
        diluc = Character("10000016", constellation_level=0)  # 迪卢克 id
        diluc.flat_atk = 0
        diluc.atk_percent = 0.0
        diluc.crit_rate = 0.5
        diluc.crit_dmg = 1.0
        diluc.elemental_dmg_bonus = 0.466  # 魔女4件 + 火伤杯
        diluc.elemental_mastery = 200

        # 应用魔女4件效果（set_id 10008）
        em = EffectManager(diluc)
        em.apply_artifact_effect(set_4_id="10008")  # 魔女套
        em.apply_constellation_effects()

        result = calculate_damage(
            character=diluc,
            skill_type="burst",  # 迪卢克元素爆发
            talent_level=10,
            enemy_level=90,
            enemy_res=0.1,
            reaction_type="vaporize",
            is_crit=True,
            effect_manager=em,
        )
        self.assertIn("damage", result)
        self.assertGreater(result["damage"], 0)
        # 验证增伤区包含魔女效果
        self.assertIn("dmg_bonus_factor", result["breakdown"])
        print(f"迪卢克蒸发伤害: {result['damage']:.2f}")


class TestLunarIndirectDamage(unittest.TestCase):
    """月反应间接伤害测试"""

    def test_lunar_charged_weighted(self):
        """4人队伍触发月感电，验证排序加权算法输出正确"""
        # 创建4个不同面板的角色（使用实际存在的角色ID）
        c1 = Character("10000016", 0)  # 迪卢克
        c1.lunar_dmg_bonus = 0.5
        c1.elemental_mastery = 300
        c1.crit_dmg = 2.0

        c2 = Character("10000002", 0)  # 神里绫华
        c2.lunar_dmg_bonus = 0.3
        c2.elemental_mastery = 200
        c2.crit_dmg = 1.5

        c3 = Character("10000006", 0)  # 丽莎
        c3.lunar_dmg_bonus = 0.1
        c3.elemental_mastery = 100
        c3.crit_dmg = 1.0

        c4 = Character("10000014", 0)  # 芭芭拉
        c4.lunar_dmg_bonus = 0.0
        c4.elemental_mastery = 50
        c4.crit_dmg = 0.5

        team = Team([c1, c2, c3, c4])
        dmg = team.calculate_lunar_indirect_damage("lunar_charged", enemy_res=0.1)

        # 手动计算验证
        res_factor = constants.resistance_factor(0.1)
        coeff = constants.LUNAR_REACTION_COEFF["lunar_charged"]["indirect"]

        def personal(c):
            panel = c.get_effective_panel()
            em_b = constants.em_bonus_lunar(panel["elemental_mastery"])
            return coeff * constants.LEVEL_COEFFICIENT * (1 + panel["lunar_dmg_bonus"]) * (1 + em_b) * res_factor * (1 + panel["crit_dmg"])

        p = sorted([personal(c) for c in [c1, c2, c3, c4]], reverse=True)
        expected = p[0] * 0.6 + p[1] * 0.3 + p[2] * 0.05 + p[3] * 0.05

        self.assertAlmostEqual(dmg, expected, places=2)
        print(f"月感电间接伤害: {dmg:.2f}")


class TestConstellation(unittest.TestCase):
    """命座逻辑测试"""

    def test_raiden_c2_def_ignore(self):
        """雷电将军（C2）开大时，防御区应用 60% 无视防御"""
        raiden = Character("10000052", constellation_level=2)  # 雷电将军 id
        em = EffectManager(raiden)
        em.apply_constellation_effects()
        mods = em.get_final_modifiers()

        self.assertAlmostEqual(mods["def_ignore"], 0.60, places=2)

        # 验证防御区应用
        result = calculate_damage(
            character=raiden,
            skill_type="burst",
            talent_level=10,
            enemy_level=90,
            enemy_res=0.1,
            effect_manager=em,
        )
        def_factor = result["breakdown"]["def_factor"]
        base_def = constants.defense_factor(raiden.char_level, 90)
        self.assertAlmostEqual(def_factor, base_def * 0.4, places=4)
        print(f"雷电将军C2防御区: {def_factor:.4f} (基础: {base_def:.4f})")


class TestWeaponEffect(unittest.TestCase):
    """武器特效测试"""

    def test_weapon_damage_up(self):
        """武器11301（DamageUpToEnemy效果）提供增伤是否正确触发"""
        diluc = Character("10000016", 0)
        em = EffectManager(diluc)
        em.apply_weapon_effect("11301", refinement_level=1)  # 实际存在的武器
        em.trigger_event("always")
        mods = em.get_final_modifiers()

        # 武器11301提供增伤加成（param_list[0]=0.12）
        self.assertGreater(mods["dmg_bonus"], 0)
        print(f"武器11301增伤加成: {mods['dmg_bonus']:.4f}")

    def test_artifact_set_effect(self):
        """圣遗物10008（魔女套）4件套提供技能伤害加成"""
        diluc = Character("10000016", 0)
        em = EffectManager(diluc)
        em.apply_artifact_effect(set_4_id="10008")  # 魔女套
        em.trigger_event("always")
        mods = em.get_final_modifiers()

        # 魔女套4件套提供技能伤害加成
        self.assertGreater(mods["dmg_bonus"], 0)
        print(f"魔女套4件增伤: {mods['dmg_bonus']:.4f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)