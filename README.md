# 原神伤害计算器

基于原神（Genshin Impact）伤害计算核心公式实现的伤害计算引擎，支持**普通元素反应**与**月反应（Lunar）**的完整乘区计算。核心功能是在给定总词条数下搜索最优副词条分配，使角色（在队伍语境下）的期望伤害最大化。

## 功能特点

- **通用乘区计算**：基础伤害区、增伤区、防御区、抗性区、暴击区
- **常规元素反应**：增幅（蒸发/融化）、剧变（超载/超导/扩散/碎冰/感电）、激化（蔓激化/超激化）、结晶
- **月反应（Lunar）**：
  - 间接伤害（由元素反应触发），支持多角色面板加权求和（前四高：0.6 / 0.3 / 0.05 / 0.05）
  - 直接伤害（由角色技能造成）
  - 月反应伤害可暴击

- **数据驱动**：角色/武器/圣遗物/命座效果从 `data/` 目录的 JSON 加载
- **效果系统**：武器特效、圣遗物套装、命座效果通过 `open_config` 关键词解析并叠加修饰器
- **属性优化**：`src/optimizer.py` 在给定总词条数下搜索最优副词条分配（攻击%/暴击率/暴击伤害/元素精通），使期望伤害最大化
- **队伍DPS 联合优化**：`src/team_dps.py` + `src/team_optimizer.py` 在用户编排的「轮换」下评估整队 DPS，并联合搜索 4 名成员的副词条分配使整队 DPS 最高（自动计入队友联动：精通共享、双火共鸣、增攻击等）
- **网页界面**：`app.py` 提供 Streamlit 交互式 UI，支持配置角色/武器/圣遗物/反应、编排轮换并一键优化（单体或整队）
- **单元测试**：`tests/test_calculator.py` 与 `tests/test_team_dps.py` 覆盖核心计算与联合优化逻辑

## 安装

```bash
pip install -r requirements.txt      # Python 3.14+
pip install -r requirements_py312.txt # Python 3.8 - 3.12
```

## 快速开始

### 1. 运行单元测试

```bash
python -m unittest tests.test_calculator -v
```

### 2. 命令行计算（CLI）

```bash
python main.py --char 10000016 --skill burst --talent 10 --reaction vaporize --crit
```

### 3. 网页界面（Streamlit）

```bash
pip install -r requirements.txt
streamlit run app.py
```

打开浏览器后，在左侧配置角色、武器、圣遗物、敌人、反应类型与优化参数（总词条数、最小暴击率、主词条），点击「开始优化」即可获得最优副词条分配、最大期望伤害与乘区明细、培养建议与收敛曲线。

**整队 DPS 优化**：展开「⚔️ 队伍DPS 轮换编排」编辑轮换步骤（哪名成员出哪招、打几段、站场几秒、是否触发反应；可一键载入主流配队示例），右侧设置每名成员词条数后点击「🚀 开始队伍DPS优化」，即联合搜索全队 4 名成员的副词条分配使整队 DPS 最高。

> 动画时长（每步占用秒数）meropide / gensri 数据未提供；联网机器运行 `python fetch_gcsim_frames.py` 会从 [gcsim](https://github.com/genshinsim/gcsim) 抓取动作帧数据写入 `data/action_frames.json`，旋转步骤秒数留 0 时自动按 gcsim 帧数估算（gcsim 采用 GPL-3.0，请保留来源署名）。

### 4. 在代码中使用

```python
from src import Character, Team, EffectManager, calculate_damage, constants

# 创建角色
diluc = Character("10000016", constellation_level=0)
diluc.crit_rate = 0.5
diluc.crit_dmg = 1.0
diluc.elemental_dmg_bonus = 0.466
diluc.elemental_mastery = 200

# 应用圣遗物/武器/命座效果
em = EffectManager(diluc)
em.apply_artifact_effect(set_4_id="10008")  # 魔女套
em.apply_weapon_effect("11301", refinement_level=1)
em.apply_constellation_effects()
em.trigger_event("always")

# 计算伤害
result = calculate_damage(
    character=diluc,
    skill_type="burst",
    talent_level=10,
    enemy_level=90,
    enemy_res=0.1,
    reaction_type="vaporize",
    is_crit=True,
    effect_manager=em,
)
print(result["damage"])

# 月反应（多角色加权）
team = Team([c1, c2, c3, c4])
lunar_dmg = team.calculate_lunar_indirect_damage("lunar_charged", enemy_res=0.1)
```

## 伤害计算公式

### 通用乘区

```
最终伤害 = 基础伤害区 × 增伤区 × 防御区 × 抗性区 × 暴击区 × 反应区
```

| 乘区 | 公式 |
|------|------|
| 基础伤害区 | `ATK × talent_ratio + flat_bonus` |
| 增伤区 | `1 + elemental_dmg_bonus + other_dmg_bonus` |
| 防御区 | `(char_level+100) / (char_level+100 + enemy_level+100)` |
| 抗性区 | `1 - RES`（0≤RES≤0.75）；`1 - RES/2`（RES<0）；`1/(4*RES+1)`（RES>0.75） |
| 暴击区 | `1 + crit_dmg`（暴击）；期望 `1 + crit_rate × crit_dmg` |

### 常规反应

- **增幅**（蒸发/融化）：`反应系数 × (1 + 2.78×EM/(EM+1400))`
- **剧变**（超载/超导/扩散/碎冰/感电）：`等级系数 × (1 + 16×EM/(EM+2000)) × 抗性区`（不暴击）
- **激化**（蔓激化/超激化）：为基础伤害区提供 `flat_bonus = 等级系数 × 1.15 × (1 + 5×EM/(EM+1200))`

### 月反应

- **间接伤害**（加权求和）：
  ```
  个人伤害_i = 反应系数 × 等级系数 × (1 + lunar_dmg_bonus_i) × (1 + EM_bonus_i + reaction_dmg_bonus_i) × 抗性区_i × 暴击区_i
  最终 = 最高×0.6 + 第二高×0.3 + 第三高×0.05 + 第四高×0.05
  ```
  - 权重与系数已按 gensri.wiki《游戏机制》权威值校准（月感电/月结晶反应系数分别为 3.0 / 1.6）
- **直接伤害**：
  ```
  (反应系数 × 属性 × 倍率 × (1 + lunar_dmg_bonus) × (1 + EM_bonus + reaction_dmg_bonus) + flat_bonus) × 抗性区 × 暴击区
  ```
  - 月感电直接系数 3.0，月结晶直接系数 1.6，月绽放直接系数 1.0

## 项目结构

```
原神伤害计算器/
├── src/
│   ├── __init__.py        # 导出公共 API
│   ├── constants.py       # 公式常量与系数函数
│   ├── data_loader.py     # 加载 data/ 下的 JSON 数据
│   ├── character.py       # Character 类（角色面板/技能倍率）
│   ├── team.py            # Team 类（月反应间接伤害加权）
│   ├── effects.py         # EffectManager（武器/圣遗物/命座效果）
│   ├── calculator.py      # calculate_damage 核心函数
│   ├── optimizer.py        # DamageOptimizer（单体属性配平/最优词条分配）
│   ├── team_dps.py         # Rotation 轮换模型 + 队伍DPS评估器 + 主流配队示例
│   └── team_optimizer.py   # TeamDPSOptimizer（全队4人词条联合优化）
├── data/                  # 角色/武器/圣遗物/技能/命座 JSON
│   └── action_frames.json  # 动作帧数据（由 fetch_gcsim_frames.py 生成，单位秒）
├── tests/
│   ├── test_calculator.py  # 核心计算单元测试
│   └── test_team_dps.py    # 队伍DPS评估 + 联合优化测试
├── main.py                # CLI 入口
├── app.py                 # Streamlit 网页界面（推荐）：单体/整队词条优化
├── fetch_data.py          # 数据抓取脚本（官方 API）
├── fetch_gensri.py        # gensri.wiki 数据采集脚本
├── fetch_gcsim_frames.py  # gcsim 动作帧抓取脚本（联网运行 → 生成 data/action_frames.json）
├── validate_formulas_with_gensri.py # 公式校验脚本（对比 gensri 权威值）
├── legacy/                # 已归档：早期独立的 Streamlit/FastAPI 伤害计算器（与主线优化器思路分歧，已停用）
└── README.md
```

## 数据来源

`data/` 目录下的 JSON 由 `fetch_data.py` 从原神官方 API 抓取，包含角色基础属性、技能倍率（`proud_skill_groups`）、武器特效、圣遗物套装效果与命座效果。

### gensri.wiki（强度研究院）

`data/gensri/` 目录由 `fetch_gensri.py` 从 [gensri.wiki](https://www.gensri.wiki/) 采集：

| 文件 | 内容 |
|------|------|
| `game_mechanics.json` | 伤害公式体系、增幅/激化/剧变/月曜系数、等级系数表（1~100） |
| `calculations.json` | 计算分析文章列表及内容预览 |
| `abyss.json` | 深境螺旋期次信息 |
| `validation_report.md` | 公式校验差异报告 |

运行方式：

```bash
python fetch_gensri.py                    # 全量抓取
python validate_formulas_with_gensri.py   # 与项目公式逐项比对，生成报告
```

> 校验说明：gensri.wiki 明确标注「前玉衡杯提供的反应系数以及贡献权重有误，以此处为准」，
> 本项目的月曜贡献权重（0.6/0.3/0.05/0.05）、月感电/月结晶反应系数、剧变反应系数、
> 超激化/蔓激化分型系数均已按其权威值实现。
