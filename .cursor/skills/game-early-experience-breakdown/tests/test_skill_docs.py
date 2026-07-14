import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
REFERENCE = ROOT / "reference.md"
OPENAI = ROOT / "agents" / "openai.yaml"

DIMENSIONS = (
    "阶段目标",
    "任务链",
    "核心循环",
    "渐进体验",
    "地图体验",
    "经济体验",
    "剧情轴",
)
SCRIPTS = (
    "video_timeline.py",
    "extract_frames.py",
    "analysis_model.py",
    "build_viewer.py",
    "write_feishu_sheet.py",
)


class SkillDocumentStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.reference = REFERENCE.read_text(encoding="utf-8")
        cls.openai = OPENAI.read_text(encoding="utf-8")

    def test_frontmatter_is_discoverable_and_concise(self):
        self.assertLess(len(self.skill.splitlines()), 500)
        match = re.match(r"\A---\n(.*?)\n---\n", self.skill, flags=re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: game-early-experience-breakdown", frontmatter)
        description = re.search(r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE)
        self.assertIsNotNone(description)
        self.assertTrue(description.group(1).startswith("Use when"))
        self.assertNotIn("disable-model-invocation", frontmatter)

    def test_trigger_keywords_and_required_prerequisites_are_present(self):
        for keyword in (
            "游戏录屏",
            "前期体验",
            "FTE",
            "新手体验拆解",
            "切片",
            "参考游戏拆解",
            "飞书页签",
        ):
            self.assertIn(keyword, self.skill)
        for prerequisite in (
            "rules/rules.md",
            "mistakes/",
            "spec/feishu-document-writing-special-flow-spec.md",
            "lark-shared",
            "lark-sheets",
        ):
            self.assertIn(prerequisite, self.skill)

    def test_workflow_references_scripts_in_required_order(self):
        positions = [self.skill.index(script) for script in SCRIPTS]
        self.assertEqual(sorted(positions), positions)
        self.assertLess(self.skill.index("--preflight"), self.skill.index("--dry-run"))
        self.assertIn("sheets +info", self.skill)
        self.assertIn("--dry-run", self.skill)
        self.assertIn("回读", self.skill)
        self.assertIn("导出", self.skill)

    def test_new_tab_conflict_policy_is_unambiguous(self):
        combined = self.skill + self.reference
        self.assertIn("只新建页签", combined)
        self.assertIn("新的唯一页签名或取消", combined)
        self.assertNotIn("复用、替换", combined)
        self.assertNotIn("复用、替换、改名或取消", combined)

    def test_skill_contains_fixed_rules_and_completion_guards(self):
        for phrase in (
            "0-30m",
            "每 1m",
            "30-60m",
            "每 5m",
            "1h+",
            "每 10m",
            "中点",
            "1-3",
            "同名",
            "未观察到",
            "事实",
            "推断",
            "置信度",
            "待确认",
            "viewer/index.html",
            "data/<game-slug>.json",
            "screenshots",
            "?dataset=<game-slug>",
            "analysis.json",
            "不能只 OCR",
            "跨片聚合",
            "API success",
            "不提交录屏",
            "全部主截图",
            "必要原视频片段",
            "无需线性观看无信息片段",
        ):
            self.assertIn(phrase, self.skill)
        for dimension in DIMENSIONS:
            self.assertIn(dimension, self.skill)

    def test_reference_defines_contract_layout_errors_and_validation(self):
        for term in (
            '"video"',
            '"slices"',
            '"main_frame"',
            '"evidence_frames"',
            '"dimensions"',
            '"stage_range"',
            '"narrative_climax"',
            '"flow"',
            '"confidence"',
            '"evidence"',
            '"open_questions"',
            "高潮",
            "低谷",
            "心流高点",
            "HTML",
            "飞书",
            "ffmpeg",
            "ffprobe",
            "xlsx",
            "时间片展示",
            "跨片聚合索引",
            "同一证据",
            "不得矛盾",
            "openpyxl",
            "缺失",
            "验证失败",
            '"fact"',
            '"inference"',
            '"stage_id"',
            "none",
            "climax",
            "low",
            "flow_peak",
            "file://",
            "文件选择器",
        ):
            self.assertIn(term, self.reference)
        for dimension in DIMENSIONS:
            self.assertIn(dimension, self.reference)

    def test_reference_defines_concise_feishu_semantics(self):
        combined = self.skill + self.reference
        for phrase in (
            "主要任务",
            "系统对玩家的教学",
            "解锁了什么系统",
            "解锁了哪些地图",
            "玩家等级/战力值/主城等级",
            "剧情在讲什么",
            "叙事目的",
            "允许空置",
            "渐进体验预期 (New Content)",
            "地图体验预期 (Map Progress)",
            "经济体验预期 (Eco Progress)",
        ):
            self.assertIn(phrase, combined)
        self.assertIn("X玩法低镜头锁定区域", self.reference)
        self.assertIn("X玩法全局区域", self.reference)
        self.assertIn("主城全区域", self.reference)
        self.assertIn("SLG大地图", self.reference)
        self.assertIn("不展示“事实：”“推断：”", self.reference)
        self.assertIn("不显示“高潮/低谷：无”", self.reference)

    def test_map_layers_and_key_story_beats_require_functional_evidence(self):
        combined = self.skill + self.reference
        for phrase in (
            "不能仅凭镜头远近",
            "功能建筑集合",
            "造兵",
            "坐标、行军",
            "关键过场",
            "连续字幕",
            "死亡",
            "继承目标",
        ):
            self.assertIn(phrase, combined)

    def test_economic_progress_can_record_verified_core_building_levels(self):
        combined = self.skill + self.reference
        for phrase in (
            "核心建筑等级",
            "大熔炉",
            "只记录可辨识的实际等级",
            "升级条件不等于当前等级",
        ):
            self.assertIn(phrase, combined)

    def test_html_contract_is_compact_overview_with_dimension_tabs(self):
        combined = self.skill + self.reference
        for phrase in (
            "单一总览时间轴",
            "七维选项卡",
            "空维度置灰",
            "不展示推断、证据路径",
            "待确认项为空时隐藏",
        ):
            self.assertIn(phrase, combined)

    def test_uninformative_midpoint_uses_nearby_effective_frame(self):
        combined = self.skill + self.reference
        for phrase in (
            "中点无信息",
            "纯黑",
            "白屏/迷雾过场",
            "临近有效帧",
            "midpoint_uninformative",
        ):
            self.assertIn(phrase, combined)

    def test_manual_dual_curve_contract_and_trend_are_documented(self):
        combined = self.skill + self.reference
        for phrase in (
            "global_curves",
            "情绪强度",
            "体验强度",
            "0～5",
            "positive",
            "negative",
            "mixed",
            "neutral",
            "gameplay_concentration",
            "feedback_density",
            "goal_challenge",
            "interruption",
            "线性回归",
            "真实时间中点",
            "响应式图框",
            "上升",
            "持平",
            "下降",
            "与现有时间片一一对应",
            "SVG",
            "不代表剧情质量差",
        ):
            self.assertIn(phrase, combined)
        self.assertNotIn("综合情绪值 = Σ", combined)
        self.assertNotIn("阶段目标：`0.10`", combined)
        self.assertNotIn("3节点移动平均", combined)
        self.assertNotIn("trend_window", combined)

    def test_emotion_pressure_formula_and_full_height_hit_bands_are_documented(self):
        combined = self.skill + self.reference
        for phrase in (
            "剧情为主体",
            "narrative_score",
            "supporting_score",
            "drivers",
            "environment_pressure",
            "0.7",
            "0.3",
            "max",
            "环境压力",
            "暴风雪倒计时",
            "全高",
            "命中带",
            "480～600px",
        ):
            self.assertIn(phrase, combined)
        self.assertNotIn("人工剧情情绪强度", combined)

    def test_openai_agent_metadata_enables_implicit_discovery(self):
        self.assertIn("interface:", self.openai)
        self.assertIn("display_name:", self.openai)
        self.assertIn("short_description:", self.openai)
        self.assertIn("default_prompt:", self.openai)
        self.assertIn("allow_implicit_invocation: true", self.openai)


if __name__ == "__main__":
    unittest.main()
