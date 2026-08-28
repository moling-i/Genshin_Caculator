"""
原神伤害计算器核心引擎
"""
from .character import Character
from .team import Team
from .effects import EffectManager
from .calculator import calculate_damage
from .optimizer import DamageOptimizer, OptimizationInput, OptimizationResult
from .team_dps import Rotation, RotationStep, evaluate_team_dps, PRESET_ROTATIONS
from .team_optimizer import (
    TeamDPSOptimizer, TeamDPSOptimizationInput, TeamDPSOptimizationResult,
)
from . import constants
from . import data_loader
from .data_loader import (
    get_character_states,
    detect_required_states,
    load_passive_skills,
    parse_effect,
)

__all__ = [
    "Character",
    "Team",
    "EffectManager",
    "calculate_damage",
    "DamageOptimizer",
    "OptimizationInput",
    "OptimizationResult",
    "Rotation",
    "RotationStep",
    "evaluate_team_dps",
    "PRESET_ROTATIONS",
    "TeamDPSOptimizer",
    "TeamDPSOptimizationInput",
    "TeamDPSOptimizationResult",
    "constants",
    "data_loader",
    "get_character_states",
    "detect_required_states",
    "load_passive_skills",
    "parse_effect",
]
