import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperienceParameters:
    progression_weight: float
    penalty_step: float
    penalty_cap: float
    partial_recovery: int


def round_half_up_1(value: float) -> float:
    return math.floor(float(value) * 10 + 0.5) / 10


def calculate_effective_experience(points, parameters):
    debts = {}
    output = []
    for point in points:
        experience = point["experience"]
        context = experience["repetition_context"]
        family_id = context["loop_family_id"]
        if context["variation"] == "full_break":
            debts.clear()
        elif context["variation"] == "partial_break":
            debts = {
                key: max(0, value - parameters.partial_recovery)
                for key, value in debts.items()
            }
        if family_id:
            debts[family_id] = debts.get(family_id, 0) + 1
        repeat_count = debts.get(family_id, 0) if family_id else 0
        progression_bonus = round_half_up_1(
            parameters.progression_weight
            * float(experience["progression_pull"]["score"])
            / 5
        )
        penalty = 0.0
        if float(point["start"]) > 1200 and repeat_count > 5:
            penalty = round_half_up_1(min(
                parameters.penalty_cap,
                parameters.penalty_step * (repeat_count - 5),
            ))
        effective = round_half_up_1(min(
            5.0,
            max(0.0, float(experience["score"]) + progression_bonus - penalty),
        ))
        output.append({
            "progression_bonus": progression_bonus,
            "repetition_penalty": penalty,
            "effective_repeat_count": repeat_count,
            "effective_score": effective,
        })
    return output


def expected_experience_fields(points, parameters):
    return calculate_effective_experience(points, parameters)


def load_locked_parameters():
    config_path = Path(__file__).resolve().parents[1] / "config" / "experience-model.json"
    with config_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    params = data["parameters"]
    return ExperienceParameters(
        progression_weight=params["progression_weight"],
        penalty_step=params["penalty_step"],
        penalty_cap=params["penalty_cap"],
        partial_recovery=params["partial_recovery"],
    )
