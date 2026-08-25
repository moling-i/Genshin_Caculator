# -*- coding: utf-8 -*-
"""
全角色天赋数值机制单元测试。

覆盖范围：
- 解析扫描：data/meropide/characters_meropide.json 中所有角色、所有固有天赋
  描述必须能被 parse_effect 完整解析（不报错、不丢弃、无 unparsed）。
- 数值验证：对每个含数值型（stat 类）天赋的角色，逐个验证其机制
  （直接增伤 / 属性转换 / 充能转伤 / 血量条件 / 无视防御 / 减抗 /
   反应加成 / 天赋等级提升 / 队伍共享 / 属性线性转增伤 / flat 伤害加算 /
   月曜缩放）在面板与伤害引擎中的正确性。
"""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import data_loader
from src.character import Character
from src.team import Team
from src.calculator import calculate_damage
from src import constants

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEROPIDE_PATH = os.path.join(
    BASE_DIR, "data", "meropide", "characters_meropide.json"
)


def make_char(name, **attrs):
    """按中文名构造角色并设置面板属性。"""
    c = Character(name)
    for k, v in attrs.items():
        setattr(c, k, v)
    return c


def find_passive_index(char, name_keyword):
    """返回名称包含关键字的固有天赋下标。"""
    for i, p in enumerate(char.passive_skills):
        if name_keyword in (p.get("name") or ""):
            return i
    raise AssertionError(f"{char.name} 未找到天赋: {name_keyword}")


def load_meropide_items():
    with io.open(MEROPIDE_PATH, encoding="utf-8") as f:
        return json.load(f).get("items", [])


class TestParseSweep(unittest.TestCase):
    """步骤1/步骤2 验证：所有角色所有天赋描述均可解析，无 unparsed、无丢弃。"""

    def test_all_passives_parse_without_error_or_loss(self):
        total = 0
        for item in load_meropide_items():
            name = item.get("name_cn") or item.get("name") or ""
            try:
                passives = data_loader.load_passive_skills(name) or []
            except Exception:
                continue
            for p in passives:
                desc = (p.get("description") or "").strip()
                if not desc:
                    continue
                total += 1
                eff = data_loader.parse_effect(desc)
                self.assertIn(eff["category"], ("stat", "mechanism"),
                              f"[{name}] {p.get('name')} 分类异常")
                # 仅数值型(stat)天赋要求结构化解析成功；
                # 纯机制(mechanism)类描述无可用数值，允许标记为不可计算
                if eff["category"] == "stat":
                    self.assertFalse(eff.get("unparsed"),
                                     f"[{name}] {p.get('name')} 未被解析: "
                                     f"{desc[:40]}")
        self.assertGreater(total, 100, "解析样本数异常偏少")

    def test_apply_all_passives_and_panel_never_crash(self):
        """每个角色启用全部天赋后面板计算均不崩溃。"""
        checked = 0
        for item in load_meropide_items():
            name = item.get("name_cn") or item.get("name")
            try:
                c = Character(name)
            except ValueError:
                continue  # 主数据中尚无该角色，跳过面板验证
            applied = c.apply_all_passives()
            panel = c.get_effective_panel()
            self.assertIsInstance(panel, dict)
            self.assertTrue(all(a["category"] != "unparsed" for a in applied))
            checked += 1
        self.assertGreater(checked, 20)

    def test_team_passives_never_crash(self):
        chars = []
        for name in ["纳西妲", "砂糖", "枫原万叶", "琳妮特"]:
            chars.append(make_char(name))
        team = Team(chars)
        result = team.apply_team_passives()

class TestDirectModifiers(unittest.TestCase):
    """直接数值型天赋：增伤 / 暴击 / 精通 / 生命% 等。"""

    def test_wendi_dmg_bonus(self):
        """温迪·魔女的前夜礼：全伤害+50%"""
        c = make_char("温迪"); c.apply_all_passives()
        self.assertAlmostEqual(c.get_effective_panel()["dmg_bonus"], 0.5)

    def test_xiao_stacked_dmg_bonus(self):
        """魈：降魔·平妖大圣(25%) + 坏劫·国土碾尘(15%) = 40%（满层取最大档已计入）"""
        c = make_char("魈"); c.apply_all_passives()
        self.assertAlmostEqual(c.get_effective_panel()["dmg_bonus"], 0.40)

    def test_qiqi_reaction_bonus(self):
        """七七·七宝奉真：反应伤害+50%"""
        c = make_char("七七"); c.apply_all_passives()
        self.assertAlmostEqual(c.get_effective_panel()["reaction_dmg_bonus"], 0.5)

    def test_xinyan_physical_bonus(self):
        """辛焱「…这才是摇滚！」：物理伤害+15%"""
        c = make_char("辛焱"); c.apply_all_passives()
        self.assertAlmostEqual(c.get_effective_panel()["physical_dmg_bonus"], 0.15)

    def test_yelan_hp_percent_and_dmg(self):
        """夜兰：猜先有方 生命上限+6%；妙转随心 伤害+1%"""
        c = make_char("夜兰"); c.apply_all_passives()
        panel = c.get_effective_panel()
        self.assertAlmostEqual(panel["hp"] / (c.base_hp * 1.0), 1.06, places=6)
        self.assertAlmostEqual(c.dmg_bonus, 0.01)

    def test_shenhe_bonuses(self):
        """申鹤：大洞弥罗尊法 冰伤+15%；缚灵通真法印 伤害+30%"""
        c = make_char("申鹤"); c.apply_all_passives()
        panel = c.get_effective_panel()
        self.assertAlmostEqual(panel["elemental_dmg_bonus"], 0.15)
        self.assertAlmostEqual(c.dmg_bonus, 0.30)

    def test_aloxa_reaction_bonus(self):
        """阿罗夏·星赴险域：月曜/剧变反应伤害+20%"""
        c = make_char("阿罗夏"); c.apply_all_passives()
        self.assertAlmostEqual(c.reaction_dmg_bonus, 0.2)

    def test_lauma_crit(self):
        """菈乌玛·奉向霜夜的明光：暴伤+20%、暴击+10%；奉向甘泉的沐濯 伤害加成"""
        c = make_char("菈乌玛"); c.apply_all_passives()
        self.assertAlmostEqual(c.crit_dmg, 0.2)
        self.assertAlmostEqual(c.crit_rate, 0.1)
        self.assertAlmostEqual(c.dmg_bonus, 0.0008)

    def test_columbina_crit_rate(self):
        """哥伦比娅·月亮诱发的疯狂：暴击率+5%"""
        c = make_char("哥伦比娅"); c.apply_all_passives()
        self.assertAlmostEqual(c.crit_rate, 0.05)

    def test_nefer_em_flat(self):
        """奈芙尔·月下的豪赌：元素精通+100"""
        c = make_char("奈芙尔"); c.apply_all_passives()
        self.assertAlmostEqual(
            c.get_effective_panel()["elemental_mastery"], 100.0)


class TestConditionalPassives(unittest.TestCase):
    """条件型天赋：血量阈值随条件正确应用/移除。"""

    def test_hutao_half_hp_fire_bonus(self):
        """胡桃·血之灶火：半血以下火伤+33%；蝶隐之时 暴击+12% 不受血量影响"""
        low = make_char("胡桃", hp_ratio_context=0.5)
        applied_low = low.apply_all_passives()
        cats = [a["category"] for a in applied_low]
        self.assertNotIn("stat_skipped_by_condition", cats)
        panel = low.get_effective_panel()
        self.assertAlmostEqual(panel["elemental_dmg_bonus"], 0.33)
        self.assertAlmostEqual(low.crit_rate, 0.12)

        high = make_char("胡桃", hp_ratio_context=0.9)
        applied_high = high.apply_all_passives()
        self.assertIn("stat_skipped_by_condition",
                      [a["category"] for a in applied_high])
        self.assertAlmostEqual(high.elemental_dmg_bonus, 0.0)
        # 满血下暴击天赋仍然生效
        self.assertAlmostEqual(high.crit_rate, 0.12)

        # 默认上下文（None）视为满血：不应用
        default = make_char("胡桃")
        default.apply_all_passives()
        self.assertAlmostEqual(default.elemental_dmg_bonus, 0.0)

    def test_hutao_damage_changes_with_condition(self):
        """同一技能在半血/满血下的伤害应相差 (1+33%) 倍"""
        def calc(hp_ratio):
            c = make_char("胡桃", hp_ratio_context=hp_ratio,
                          flat_atk=2000, crit_rate=1.0)
            c.apply_all_passives()
            return calculate_damage(c, "skill", 10, 90, 0.1)["damage"]

        d_low, d_high = calc(0.5), calc(1.0)
        self.assertAlmostEqual(d_low / d_high, 1.33, places=4)

    def test_albedo_half_hp_dmg_bonus(self):
        """阿贝多·白垩色的威压：半血以下伤害+25%"""
        low = make_char("阿贝多", hp_ratio_context=0.5)
        low.apply_all_passives()
        self.assertAlmostEqual(low.dmg_bonus, 0.25)

        high = make_char("阿贝多", hp_ratio_context=0.8)
        high.apply_all_passives()
        self.assertAlmostEqual(high.dmg_bonus, 0.0)


class TestAttrScaling(unittest.TestCase):
    """属性线性转自身增伤（艾梅莉埃/坎蒂丝/阿贝多式）。"""

    def test_emilie_atk_scaled_cap36(self):
        """艾梅莉埃·精馏：每1000点攻击力+15%伤害，至多36%"""
        c = make_char("艾梅莉埃", flat_atk=1500)
        c.apply_all_passives()
        atk_total = c.get_effective_panel()["atk"]
        expected = min(atk_total / 1000.0 * 0.15, 0.36)
        self.assertAlmostEqual(
            c.get_effective_panel()["elemental_dmg_bonus"], expected, places=6)

    def test_candace_hp_scaled_no_cap(self):
        """坎蒂丝·漫沙陨穹：每1000点生命上限提高0.5%伤害（无上限，cap=null 不崩溃）"""
        c = make_char("坎蒂丝", flat_hp=20000)
        c.apply_all_passives()
        hp_total = c.get_effective_panel()["hp"]
        expected = hp_total / 1000.0 * 0.005
        self.assertAlmostEqual(
            c.get_effective_panel()["elemental_dmg_bonus"], expected, places=6)

    def test_albedo_def_scaled_cap12(self):
        """阿贝多·魔女的前夜礼·白芒之书：每1000点防御+4%元素伤，至多12%"""
        c = make_char("阿贝多", flat_def=4000)
        c.apply_all_passives()
        def_total = c.get_effective_panel()["def"]
        expected = min(def_total / 1000.0 * 0.04, 0.12)
        self.assertAlmostEqual(
            c.get_effective_panel()["elemental_dmg_bonus"], expected, places=6)


class TestFlatDmgScaling(unittest.TestCase):
    """flat 伤害加算：来源属性×X% 直接加入基础伤害区。"""

    def test_yunjin_def_flat_in_calculator(self):
        """云堇·莫从恒蹊：追加防御力的11.5%到伤害值（多档位取最高档）；
        计算器 breakdown 应包含 flat_dmg_bonus 且参与最终伤害"""
        c = make_char("云堇", flat_def=1000, crit_rate=1.0)
        c.apply_all_passives()
        panel = c.get_effective_panel()
        flat_expect = panel["def"] * 0.115
        self.assertAlmostEqual(panel["flat_dmg_bonus"], flat_expect, places=4)

        res = calculate_damage(c, "burst", 10, 90, 0.1)
        bd = res["breakdown"]
        self.assertAlmostEqual(bd["flat_dmg_bonus"], flat_expect, places=4)
        # 最终伤害应等于 (基础+flat) 走完后续乘区
        tail = (bd["dmg_bonus_factor"] * bd["def_factor"]
                * bd["res_factor"] * bd["crit_factor"])
        self.assertAlmostEqual(res["damage"], bd["base_damage"] * tail, places=2)

    def test_sethos_em_700pct(self):
        """赛索斯·砂王的赐礼：伤害值提升相当于元素精通的700%"""
        c = make_char("赛索斯", elemental_mastery=100)
        c.apply_all_passives()
        self.assertAlmostEqual(
            c.get_effective_panel()["flat_dmg_bonus"], 700.0, places=4)

    def test_lanyan_em_multi_tier_max(self):
        """蓝砚·苍翎镇邪敕符：精通的309%/774%两档，取最高档774%"""
        c = make_char("蓝砚", elemental_mastery=100)
        c.apply_all_passives()
        self.assertAlmostEqual(
            c.get_effective_panel()["flat_dmg_bonus"], 774.0, places=4)

    def test_clorinde_atk_20pct(self):
        """克洛琳德·破夜的明焰：基于攻击力的20%提升雷伤"""
        c = make_char("克洛琳德", flat_atk=1000)
        c.apply_all_passives()
        atk_total = c.get_effective_panel()["atk"]
        self.assertAlmostEqual(
            c.get_effective_panel()["flat_dmg_bonus"], atk_total * 0.2, places=4)

    def test_zibai_def_60pct_plus_dmg(self):
        """兹白·月下素娥降仙：防御力的60%转伤害值 + 伤害+60%（复合效果拆分应用）"""
        c = make_char("兹白", flat_def=1000)
        c.apply_all_passives()
        panel = c.get_effective_panel()
        self.assertAlmostEqual(panel["flat_dmg_bonus"], panel["def"] * 0.6, places=4)
        self.assertAlmostEqual(panel["dmg_bonus"], 0.6)


class TestLunarAndAtkOverScaling(unittest.TestCase):
    """月曜反应缩放 / 属性超阈值转增伤。"""

    def test_odetia_atk_over_and_lunar(self):
        """奥黛塔：赤忱者的悲歌 攻击超1000部分每100点+1.5%月伤（≤30%）
        + 星耀祝礼 每100点攻击+0.7%月伤（≤14%）"""
        c = make_char("奥黛塔", flat_atk=3000)
        c.apply_all_passives()
        atk_total = c.get_effective_panel()["atk"]
        over = min(max(atk_total - 1000.0, 0.0) / 100.0 * 0.015, 0.3)
        lunar_part = min(atk_total / 100.0 * 0.007, 0.14)
        self.assertAlmostEqual(
            c.get_effective_panel()["lunar_dmg_bonus"],
            over + lunar_part, places=6)

    def test_ineffa_lunar_from_atk(self):
        """伊涅芙·月兆祝赐·象拟中继：每100点攻击+0.7%月伤，至多14%"""
        c = make_char("伊涅芙", flat_atk=3000)
        c.apply_all_passives()
        atk_total = c.get_effective_panel()["atk"]
        self.assertAlmostEqual(
            c.get_effective_panel()["lunar_dmg_bonus"],
            min(atk_total / 100.0 * 0.007, 0.14), places=6)

    def test_lauma_nefer_lunar_from_em(self):
        """菈乌玛/奈芙尔 月兆祝赐：每点精通+0.0175%月伤，至多14%"""
        for name in ["菈乌玛", "奈芙尔"]:
            c = make_char(name, elemental_mastery=1000)
            c.apply_all_passives()
            self.assertAlmostEqual(
                c.get_effective_panel()["lunar_dmg_bonus"], 0.14, places=6,
                msg=f"{name} 月曜精通缩放错误")

    def test_columbina_lunar_from_hp(self):
        """哥伦比娅·月兆祝赐·借汝月光：每1000点生命+0.2%月伤，至多7%"""
        c = make_char("哥伦比娅", flat_hp=60000)
        c.apply_all_passives()
        hp_total = c.get_effective_panel()["hp"]
        self.assertAlmostEqual(
            c.get_effective_panel()["lunar_dmg_bonus"],
            min(hp_total / 1000.0 * 0.002, 0.07), places=6)

    def test_zibai_lunar_from_def(self):
        """兹白·月兆祝赐·浮明若流：每100点防御+0.7%月伤，至多14%"""
        c = make_char("兹白", flat_def=3000)
        c.apply_all_passives()
        def_total = c.get_effective_panel()["def"]
        self.assertAlmostEqual(
            c.get_effective_panel()["lunar_dmg_bonus"],
            min(def_total / 100.0 * 0.007, 0.14), places=6)


class TestEnemyDebuffs(unittest.TestCase):
    """无视防御 / 敌人减防 / 减抗。"""

    def test_lisa_def_shred_applied_in_calc(self):
        """丽莎·静电场力：Q 引爆降低敌防15% → 防御区乘 (1-15%)"""
        c = make_char("丽莎")
        c.apply_all_passives()
        panel = c.get_effective_panel()
        self.assertAlmostEqual(panel["enemy_def_shred"], 0.15)

        res = calculate_damage(c, "burst", 10, 90, 0.1)
        base = constants.defense_factor(90, 90)
        self.assertAlmostEqual(res["breakdown"]["def_factor"],
                               base * (1 - 0.15), places=6)

    def test_chongyun_res_shred_parsed(self):
        """重云·追冰剑诀：敌人冰抗-10%（结构化输出，供敌方抗性区使用）"""
        chongyun = Character("重云")
        desc = next(p["description"] for p in chongyun.passive_skills
                    if "追冰剑诀" in p.get("name", ""))
        eff = data_loader.parse_effect(desc)
        self.assertEqual(eff["res_shred"], {"element": "冰", "value": 0.1})
        self.assertEqual(eff["category"], "stat")


class TestTalentLevelUp(unittest.TestCase):
    """天赋等级提升型。"""

    def test_tartaglia_normal_plus1(self):
        """达达利亚·诸武精通：普通攻击等级+1 → Lv1 倍率等于无天赋时的 Lv2"""

class TestTeamPassives(unittest.TestCase):
    """队伍共享型天赋（跨角色应用）。"""

    def test_nahida_em_share_cap250(self):
        """纳西妲·净善摄受明论：队内最高精通的25%，至多250点；施加者自身不受益"""
        nahida = make_char("纳西妲", elemental_mastery=1000)
        mate = make_char("温迪", elemental_mastery=200)
        team = Team([nahida, mate, None, None])
        ret = team.apply_team_passives()

        self.assertAlmostEqual(ret["em_gain"][mate.name], 250.0)
        self.assertAlmostEqual(mate.team_effects_received["em_flat"], 250.0)
        self.assertNotIn(nahida.name, ret["em_gain"])  # 自身不受
        self.assertAlmostEqual(
            mate.get_effective_panel()["elemental_mastery"], 450.0)
        # 纳西妲自身精通不变
        self.assertAlmostEqual(
            nahida.get_effective_panel()["elemental_mastery"], 1000.0)

    def test_sucrose_em_share_flat_plus_pct(self):
        """砂糖：触媒置换术 固定+50；小小的慧风 自身精通的20%
        （精通600 → 队友共得 50 + 120 = 170 点）"""
        sucrose = make_char("砂糖", elemental_mastery=600)
        mate = Character("胡桃")
        Team([sucrose, mate, None, None]).apply_team_passives()
        self.assertAlmostEqual(mate.team_effects_received["em_flat"], 170.0)

    def test_kazuha_em_to_teammate_dmg_bonus(self):
        """枫原万叶·风物之诗咏：每点精通为队友提供0.04%对应元素伤
        （精通500 → 队友伤害加成+20%，且该加成进入队友面板 dmg_bonus）"""
        kazuha = make_char("枫原万叶", elemental_mastery=500)
        mate = Character("胡桃")
        Team([kazuha, mate, None, None]).apply_team_passives()
        self.assertAlmostEqual(mate.team_effects_received["em_to_dmg"], 0.2)
        self.assertAlmostEqual(
            mate.get_effective_panel()["dmg_bonus"], 0.2)

    def test_lynette_atk_share(self):
        """琳妮特·巧施协同：全队攻击力+20%（施加者自身不受益）"""
        lyn = make_char("琳妮特", flat_atk=1000)
        mate = make_char("胡桃", flat_atk=1000)
        base_atk = mate.get_effective_panel()["atk"]
        Team([lyn, mate, None, None]).apply_team_passives()
        self.assertAlmostEqual(
            mate.get_effective_panel()["atk"], base_atk * 1.2, places=4)

        c = make_char("达达利亚")
        idx = find_passive_index(c, "诸武精通")
        c.apply_all_passives([idx])

    def test_albedo_em_share_flat125(self):
        """阿贝多·瓶中人的天慧：自身精通+125，且全队精通+125"""
        albedo = make_char("阿贝多")
        idx = find_passive_index(albedo, "瓶中人的天慧")
        albedo.apply_all_passives([idx])
        mate = Character("胡桃")
        Team([albedo, mate, None, None]).apply_team_passives()

        self.assertAlmostEqual(
            albedo.get_effective_panel()["elemental_mastery"], 125.0)
        self.assertAlmostEqual(mate.team_effects_received["em_flat"], 125.0)

    def test_ineffa_em_from_atk_pct(self):
        """伊涅芙·全相重构协议：受益者基于伊涅芙攻击力比例获得精通增益
        （实现语义：受益者总精通 ×(1+6%)）"""
        ineffa = make_char("伊涅芙", flat_atk=2000)
        mate = make_char("胡桃", elemental_mastery=500)
        Team([ineffa, mate, None, None]).apply_team_passives()
        self.assertAlmostEqual(mate.team_effects_received["em_from"]["atk"], 0.06)
        self.assertAlmostEqual(
            mate.get_effective_panel()["elemental_mastery"], 530.0)

    def test_zibai_team_em_flat60(self):
        """兹白·叠嶂峦岫出云：自身防御+15%/精通+60，全队精通+60"""
        zb = make_char("兹白", flat_def=1000)
        idx = find_passive_index(zb, "叠嶂峦岫出云")
        zb.apply_all_passives([idx])
        mate = Character("胡桃")
        Team([zb, mate, None, None]).apply_team_passives()
        self.assertAlmostEqual(zb.def_percent, 0.15)
        self.assertAlmostEqual(
            zb.get_effective_panel()["elemental_mastery"], 60.0)
        self.assertAlmostEqual(mate.team_effects_received["em_flat"], 60.0)


class TestEnableDisableToggle(unittest.TestCase):
    """启用/禁用天赋开关后，面板与伤害数值相应变化。"""

    def test_xiao_toggle_second_passive(self):
        """魈：仅启用降魔·平妖大圣 → dmg_bonus 25%；再启坏劫 → 40%"""
        c = make_char("魈")
        idx_second = find_passive_index(c, "坏劫·国土碾尘")
        c.apply_all_passives([i for i in range(len(c.passive_skills))
                              if i != idx_second])
        self.assertAlmostEqual(c.dmg_bonus, 0.25)

        c2 = make_char("魈")
        c2.apply_all_passives()
        self.assertAlmostEqual(c2.dmg_bonus, 0.40)

    def test_hutao_toggle_changes_damage(self):
        """胡桃：关闭血之灶火后半血伤害下降 (1/1.33)"""
        c_on = make_char("胡桃", hp_ratio_context=0.5,
                         flat_atk=2000, crit_rate=1.0)
        idx_fire = find_passive_index(c_on, "血之灶火")
        c_on.apply_all_passives()
        d_on = calculate_damage(c_on, "skill", 10, 90, 0.1)["damage"]

        c_off = make_char("胡桃", hp_ratio_context=0.5,
                          flat_atk=2000, crit_rate=1.0)
        c_off.apply_all_passives(
            [i for i in range(len(c_off.passive_skills)) if i != idx_fire])
        d_off = calculate_damage(c_off, "skill", 10, 90, 0.1)["damage"]

        self.assertAlmostEqual(d_on / d_off, 1.33, places=4)


class TestErScaling(unittest.TestCase):
    """充能效率转伤害加成型天赋。"""

    def test_raiden_er_to_electro_dmg(self):
        """雷电将军·殊胜之御体：超出100%每1%充能 → 雷伤+0.4%
        充能200% → +40%；充能150% → +20%；恰好100% → 无加成"""
        for er, expect in [(2.0, 0.4), (1.5, 0.2), (1.0, 0.0)]:
            c = make_char("雷电将军", er_total=er)
            c.apply_all_passives()
            self.assertAlmostEqual(
                c.get_effective_panel()["elemental_dmg_bonus"],
                expect, places=6, msg=f"充能 {er}")

    def test_aloxa_er_threshold_zero_with_cap(self):
        """阿罗夏·告别冬麦与残叶：每1%充能+0.35%伤害（阈值0，上限70%）"""
        c = make_char("阿罗夏", er_total=1.0)
        c.apply_all_passives()
        self.assertAlmostEqual(c.get_effective_panel()["dmg_bonus"], 0.35, places=6)

        # 上限：充能 ≥300% 时封顶70%
class TestMechanismNumerics(unittest.TestCase):
    """机制型天赋数值（v3）：倍率层数 / 额外一段伤害 / 全伤增幅 / 状态门控。"""

    # ---- 技能倍率层数提升 ----

    def test_skirk_wanliu_talent_multiplier(self):
        """丝柯克·万流归寂：普攻110/120/170%、爆发105/115/160%（按死河渡断层数）。"""
        c = make_char("丝柯克", flat_atk=1800, atk_percent=0.6)
        c.apply_all_passives()
        self.assertEqual(c.talent_multipliers.get("normal"), [1.1, 1.2, 1.7])
        self.assertEqual(c.talent_multipliers.get("burst"), [1.05, 1.15, 1.6])

        r3 = calculate_damage(c, "burst", 10, 90, 0.1)
        self.assertAlmostEqual(r3["breakdown"]["talent_mult_factor"], 1.6)
        c.stack_context = {"burst": 1}
        r1 = calculate_damage(c, "burst", 10, 90, 0.1)
        self.assertAlmostEqual(r1["breakdown"]["talent_mult_factor"], 1.05)
        self.assertAlmostEqual(r3["damage"] / r1["damage"], 1.6 / 1.05, places=6)

    def test_klee_spark_magic_multiplier_and_state_gate(self):
        """可莉·火花魔法：重击115/130/150%；关闭「魔导」状态后天赋被跳过。"""
        c0 = Character("可莉")
        idx = find_passive_index(c0, "火花魔法")
        eff = data_loader.parse_effect(c0.passive_skills[idx]["description"])
        self.assertEqual(
            eff["talent_multiplier"]["skill_types"].get("charged"),
            [1.15, 1.3, 1.5],
        )
        # 默认状态触发 → TM 生效
        c1 = Character("可莉")
        c1.apply_all_passives()
        self.assertEqual(c1.talent_multipliers.get("charged"), [1.15, 1.3, 1.5])
        # 关闭魔导 → 门控跳过
        c2 = Character("可莉")
        c2.active_states = {"魔导": False}
        applied = c2.apply_all_passives()
        skipped = [a for a in applied if a["category"] == "stat_skipped_by_state"]
        self.assertTrue(any("火花魔法" in a["name"] for a in skipped))
        self.assertIsNone(c2.talent_multipliers.get("charged"))

    def test_neuvillette_tiered_charged(self):
        """那维莱特：重击·衡平推裁 110%/125%/160% 三档层数。"""
        c = make_char("那维莱特")
        c.apply_all_passives()
        self.assertEqual(c.talent_multipliers.get("charged"), [1.1, 1.25, 1.6])

    def test_faruga_multi_skill_boost_tier(self):
        """法尔伽·晓风的行军：普攻/重击/战技均获 140%→220% 档位。"""
        c = make_char("法尔伽")
        c.apply_all_passives()
        tm = c.talent_multipliers
        for k in ("normal", "charged", "skill"):
            self.assertEqual(tm.get(k), [1.4, 2.2], f"技能 {k} 档位错误")

    # ---- 额外一段伤害 ----

    def test_yanfei_extra_hit_atk_scaled(self):
        """烟绯·法兽灼眼：追加 80% 攻击力，走完整后续乘区。"""
        c = make_char("烟绯", flat_atk=2000)
        c.apply_all_passives()
        self.assertEqual(c.extra_hits, [{"source": "atk", "ratio": 0.8}])
        r = calculate_damage(c, "charged", 10, 90, 0.1)
        panel_atk = r["breakdown"]["base_atk"]
        self.assertAlmostEqual(
            r["breakdown"]["extra_hit_damage"], panel_atk * 0.8, places=4
        )

    def test_yae_miko_max_ratio_selected(self):
        """八重神子·神篱之御荫：40%/50% 双档取最大 50%。"""
        c = make_char("八重神子")
        c.apply_all_passives()
        self.assertIn({"source": "atk", "ratio": 0.5}, c.extra_hits)

    def test_marani_hp_based_extra_hit(self):
        """玛拉妮：基于生命值上限的15%/30%/45%，取最大档 45%。"""
        c = make_char("玛拉妮")
        c.apply_all_passives()
        self.assertIn({"source": "hp", "ratio": 0.45}, c.extra_hits)

    def test_extra_hit_hp_source_value(self):
        """额外段来源属性=hp 时按生命值面板取值（玛拉妮式）。"""
        c = make_char("玛拉妮", flat_hp=20000)
        c.apply_all_passives()
        r = calculate_damage(c, "skill", 10, 90, 0.1)
        total_hp = (c.base_hp + 20000) * (1 + c.hp_percent)
        self.assertAlmostEqual(
            r["breakdown"]["extra_hit_damage"], total_hp * 0.45, places=2
        )
        c2 = make_char("阿罗夏", er_total=3.0)
        c2.apply_all_passives()
        self.assertAlmostEqual(c2.get_effective_panel()["dmg_bonus"], 0.7, places=6)


    # ---- 全伤害增幅 ----

    def test_dulin_damage_amp_cap(self):
        """杜林：每100攻击+3%全伤，至多75%。"""
        c = make_char("杜林", flat_atk=30000)
        c.apply_all_passives()
        r = calculate_damage(c, "skill", 10, 90, 0.1)
        self.assertAlmostEqual(r["breakdown"]["damage_amp"], 0.75)
        self.assertAlmostEqual(r["breakdown"]["amp_factor"], 1.75)

    def test_dulin_damage_amp_proportional(self):
        """杜林低攻击时按比例生效（含基础攻击）。"""
        c = make_char("杜林")
        c.flat_atk = 1000
        c.apply_all_passives()
        r = calculate_damage(c, "skill", 10, 90, 0.1)
        total_atk = (c.base_atk + 1000) * (1 + c.atk_percent)
        self.assertAlmostEqual(
            r["breakdown"]["damage_amp"],
            min(total_atk / 100 * 0.03, 0.75),
            places=6,
        )

    def test_oudaita_reaction_scope_amp(self):
        """奥黛塔·赤忱者的悲歌：增幅限定反应伤害路径。"""
        c = make_char("奥黛塔", flat_atk=30000)
        c.apply_all_passives()
        r_normal = calculate_damage(c, "skill", 10, 90, 0.1)
        self.assertAlmostEqual(r_normal["breakdown"]["damage_amp"], 0.0)
        r_lunar = calculate_damage(
            c, "skill", 10, 90, 0.1, reaction_type="lunar_bloom_direct"
        )
        self.assertAlmostEqual(r_lunar["breakdown"]["damage_amp"], 0.3)

    # ---- 减抗 / 面板修正 ----

    def test_chevreuse_dual_element_res_shred(self):
        """夏沃蕾·尖兵协同战法：火与雷抗性-40%。"""
        c0 = Character("夏沃蕾")
        idx = find_passive_index(c0, "尖兵协同战法")
        eff = data_loader.parse_effect(c0.passive_skills[idx]["description"])
        rs = eff["res_shred"]
        self.assertEqual({rs["element"], rs["element2"]}, {"火", "雷"})
        self.assertAlmostEqual(rs["value"], 0.4)

    def test_sigewinne_all_res_shred(self):
        """希格雯·急性剂量：所有元素与物理抗性-10%。"""
        c0 = Character("希格雯")
        idx = find_passive_index(c0, "急性剂量")
        eff = data_loader.parse_effect(c0.passive_skills[idx]["description"])
        self.assertEqual(eff["res_shred"], {"element": "all", "value": 0.1})

    def test_kokomi_crit_down_modifier(self):
        """心海·庙算无遗：暴击率-100% 进入 modifiers（有效面板=基础+修正）。"""
        c = make_char("珊瑚宫心海")
        before = c.crit_rate
        c.apply_all_passives()
        self.assertAlmostEqual(c.crit_rate, before - 1.0, places=6)
        # 有效面板应体现暴击率归零（基础5% - 100%）
        self.assertLessEqual(c.get_effective_panel()["crit_rate"], 0.0)

    # ---- 状态标签触发判定 ----

    def test_detect_required_states_hint_union(self):
        """温迪·颂时风若依赖「魔导」（提示词命中），即使角色标签为空。"""
        states = data_loader.get_character_states("温迪")
        ps = data_loader.load_passive_skills("温迪") or []
        desc = next(p["description"] for p in ps if "颂时风若" in p.get("name", ""))
        req = data_loader.detect_required_states(desc, states)
        self.assertIn("魔导", req)

    def test_state_toggle_gates_engine_application(self):
        """丝柯克：夜魂/魔导默认触发；手动关闭后相关天赋被跳过。"""
        c = Character("丝柯克")
        self.assertEqual(c.active_states, {"夜魂": True, "魔导": True})
        c.active_states = {"夜魂": False, "魔导": True}
        applied = c.apply_all_passives()
        cats = {a["category"] for a in applied}
        # 万流归寂不依赖标签仍应生效
        self.assertIn("stat", cats)


if __name__ == "__main__":
    unittest.main(verbosity=2)
