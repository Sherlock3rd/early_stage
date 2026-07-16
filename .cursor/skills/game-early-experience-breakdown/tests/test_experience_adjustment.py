import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from calibrate_experience_model import (
    CalibrationError,
    CalibrationReference,
    TrendResult,
    choose_parameters,
    main as calibration_main,
    parameter_grid,
)
from experience_adjustment import ExperienceParameters, calculate_effective_experience


def point(start, base=3.0, pull=0, family="combat", variation="reinforcement"):
    return {
        "start": start,
        "experience": {
            "score": base,
            "progression_pull": {"score": pull, "reason": "测试依据"},
            "repetition_context": {
                "loop_family_id": family,
                "variation": variation,
                "reason": "测试依据",
            },
        },
    }


def reference(name, old_delta, new_delta, direction="rising"):
    return CalibrationReference(
        name=name,
        old_delta=old_delta,
        evaluate=lambda _parameters: TrendResult(
            delta=new_delta,
            direction=direction,
        ),
    )


def valid_reference_triplet():
    return [
        reference("frost", old_delta=1.176, new_delta=1.1),
        reference("sanbing", old_delta=1.347, new_delta=1.3),
        reference("dark-war", old_delta=1.464, new_delta=1.4),
    ]


class ExperienceAdjustmentTests(unittest.TestCase):
    def test_repetition_requires_time_and_count_thresholds(self):
        points = [point(start) for start in (0, 240, 480, 720, 960, 1200, 1260)]
        result = calculate_effective_experience(
            points,
            ExperienceParameters(0.6, 0.2, 1.2, 2),
        )
        assert [item["repetition_penalty"] for item in result[:6]] == [0, 0, 0, 0, 0, 0]
        assert result[6]["repetition_penalty"] == 0.4

    def test_full_break_clears_and_partial_break_reduces_debt(self):
        points = [point(1500 + index * 60) for index in range(6)]
        points.append(point(1860, family="hero", variation="partial_break"))
        points.append(point(1920, family="combat"))
        points.append(point(1980, family="map", variation="full_break"))
        result = calculate_effective_experience(
            points,
            ExperienceParameters(0.6, 0.2, 1.2, 2),
        )
        assert result[5]["effective_repeat_count"] == 6
        assert result[7]["effective_repeat_count"] == 5
        assert result[8]["effective_repeat_count"] == 1

    def test_progression_bonus_and_effective_score_use_half_up_rounding(self):
        result = calculate_effective_experience(
            [point(60, base=3.0, pull=4, family="", variation="full_break")],
            ExperienceParameters(0.6, 0.2, 1.2, 2),
        )[0]
        assert result == {
            "progression_bonus": 0.5,
            "repetition_penalty": 0.0,
            "effective_repeat_count": 0,
            "effective_score": 3.5,
        }

    def test_empty_loop_family_keeps_repeat_count_zero(self):
        points = [point(1500 + index * 60) for index in range(6)]
        points.append(point(1860, family="", variation="reinforcement"))
        points.append(point(1920))

        result = calculate_effective_experience(
            points,
            ExperienceParameters(0.6, 0.2, 1.2, 2),
        )

        self.assertEqual(0, result[6]["effective_repeat_count"])
        self.assertEqual(7, result[7]["effective_repeat_count"])

    def test_calibration_grid_is_fixed_by_design(self):
        candidates = parameter_grid()
        self.assertEqual(5 * 7 * 5 * 3, len(candidates))
        self.assertEqual(
            ExperienceParameters(0.4, 0.1, 0.8, 1),
            candidates[0],
        )
        self.assertEqual(
            ExperienceParameters(0.8, 0.4, 1.6, 3),
            candidates[-1],
        )

    def test_calibration_rejects_reference_delta_drift_over_point_two(self):
        with self.assertRaisesRegex(CalibrationError, "frost|0.2"):
            choose_parameters(
                candidates=[ExperienceParameters(0.8, 0.4, 1.6, 1)],
                references=[
                    reference("frost", old_delta=1.176, new_delta=0.7)
                ],
            )

    def test_calibration_regularization_prevents_drift_only_wrong_choice(self):
        conservative = ExperienceParameters(0.6, 0.2, 1.2, 2)
        aggressive = ExperienceParameters(0.7, 0.2, 1.2, 2)
        old_deltas = {
            "frost": 1.176,
            "sanbing": 1.347,
            "dark-war": 1.464,
        }

        def calibrated_reference(name):
            old_delta = old_deltas[name]

            def evaluate(parameters):
                drift = 0.05 if parameters == conservative else 0.0
                return TrendResult(old_delta + drift, "rising")

            return CalibrationReference(name, old_delta, evaluate)

        references = [
            calibrated_reference(name)
            for name in ("frost", "sanbing", "dark-war")
        ]
        drift_only_choice = min(
            (conservative, aggressive),
            key=lambda parameters: sum(
                (
                    item.evaluate(parameters).delta
                    - item.old_delta
                ) ** 2
                for item in references
            ),
        )
        self.assertEqual(aggressive, drift_only_choice)

        selected = choose_parameters(
            candidates=[aggressive, conservative],
            references=references,
        )
        self.assertEqual(conservative, selected.parameters)
        self.assertAlmostEqual(0.0075, selected.loss)

    def test_calibration_never_reads_blind_datasets(self):
        def blind_evaluator(_parameters):
            raise AssertionError("blind dataset must not be evaluated")

        references = [
            *valid_reference_triplet(),
            CalibrationReference("aoo", 0.0, blind_evaluator),
            CalibrationReference("beboo", 0.0, blind_evaluator),
        ]
        selected = choose_parameters(
            candidates=[ExperienceParameters(0.6, 0.2, 1.2, 2)],
            references=references,
        )
        self.assertNotIn("aoo", selected.reference_names)
        self.assertNotIn("beboo", selected.reference_names)

    def test_calibration_cli_ignores_blind_paths_before_file_access(self):
        missing = "Z:/blind-dataset-must-not-exist.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "locked.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = calibration_main([
                    "--reference",
                    f"aoo={missing},{missing},0",
                    "--reference",
                    f"beboo={missing},{missing},0",
                    "--output",
                    str(output),
                ])

        self.assertEqual(2, code)
        error = json.loads(stderr.getvalue())["error"]["message"]
        self.assertIn("missing", error)
        self.assertNotIn("invalid --reference", error)
        self.assertNotIn(missing, error)


if __name__ == "__main__":
    unittest.main()
