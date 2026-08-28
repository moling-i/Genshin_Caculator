"""
原神伤害计算器 - 命令行入口
用法: python main.py --character 胡桃 --skill normal --level 10
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import Character, Team, EffectManager, calculate_damage

def main():
    parser = argparse.ArgumentParser(description="原神伤害计算器 CLI")
    parser.add_argument("--character", type=str, required=True, help="角色名或ID")
    parser.add_argument("--skill", type=str, default="normal",
                        choices=["normal", "skill", "burst"], help="技能类型")
    parser.add_argument("--level", type=int, default=10, help="天赋等级")
    parser.add_argument("--enemy-level", type=int, default=90, help="敌人等级")
    parser.add_argument("--enemy-res", type=float, default=0.1, help="敌人抗性 (0.1 表示 10%%)")
    parser.add_argument("--constellation", type=int, default=0, help="命座等级")
    parser.add_argument("--reaction", type=str, default=None,
                        help="反应类型: vaporize, melt, lunar_charged, stellar_superconduct, star_swirl, star_swirl_direct")
    parser.add_argument("--crit", action="store_true", help="是否暴击")
    parser.add_argument("--atk", type=float, default=0, help="额外攻击力")
    parser.add_argument("--crit-rate", type=float, default=0, help="暴击率加成")
    parser.add_argument("--crit-dmg", type=float, default=0, help="暴击伤害加成")
    parser.add_argument("--em", type=float, default=0, help="元素精通")
    parser.add_argument("--elem-dmg", type=float, default=0, help="元素伤害加成")
    parser.add_argument("--lunar-bonus", type=float, default=0, help="月反应基础伤害加成")
    parser.add_argument("--stellar-stacks", type=int, default=0,
                        help="星超导附着次数(0/6/12)")
    parser.add_argument("--star-base-boost", type=float, default=0.0,
                        help="星扩散/星超导基础提升(如0.14表示14%%)")
    parser.add_argument("--star-vortex-level", type=int, default=1,
                        help="星扩散风涡等级(1-6)")
    parser.add_argument("--team", type=str, default=None,
                        help="队伍其他成员（逗号分隔，用于月反应）")

    args = parser.parse_args()

    try:
        char = Character(args.character, constellation_level=args.constellation)
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)

    # 设置面板
    char.flat_atk = args.atk
    char.crit_rate = args.crit_rate
    char.crit_dmg = args.crit_dmg
    char.elemental_mastery = args.em
    char.elemental_dmg_bonus = args.elem_dmg
    char.lunar_dmg_bonus = args.lunar_bonus

    # 效果管理器
    em = EffectManager(char)
    em.apply_constellation_effects()

    # 队伍（月反应/星扩散风涡需要）
    team = None
    if args.team and args.reaction and ("lunar" in args.reaction or args.reaction == "star_swirl"):
        members = [char]
        for name in args.team.split(","):
            name = name.strip()
            if name:
                members.append(Character(name))
        while len(members) < 4:
            members.append(None)
        team = Team(members[:4])

    # 计算伤害
    result = calculate_damage(
        character=char,
        skill_type=args.skill,
        talent_level=args.level,
        enemy_level=args.enemy_level,
        enemy_res=args.enemy_res,
        reaction_type=args.reaction,
        is_crit=args.crit,
        team=team,
        effect_manager=em,
        stellar_stacks=args.stellar_stacks,
        star_base_boost=args.star_base_boost,
        star_vortex_level=args.star_vortex_level,
    )

    print(f"\n=== {char.name} 伤害计算结果 ===")
    print(f"技能类型: {args.skill}")
    print(f"天赋等级: {args.level}")
    print(f"反应类型: {args.reaction or '无'}")
    print(f"暴击: {'是' if args.crit else '否'}")
    print(f"\n最终伤害: {result['damage']:.2f}")
    print(f"\n--- 乘区明细 ---")
    for k, v in result["breakdown"].items():
        if isinstance(v, (int, float)):
            print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()