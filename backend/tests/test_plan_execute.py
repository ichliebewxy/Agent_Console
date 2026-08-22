import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import plan_execute as plan_execute_module


class PlanExecuteTests(unittest.TestCase):
    def test_simple_turns_are_not_planned(self):
        self.assertFalse(plan_execute_module.is_multi_step_task("你好"))
        self.assertFalse(plan_execute_module.is_multi_step_task("你会什么工具？"))
        self.assertFalse(plan_execute_module.is_multi_step_task("今天天气怎么样呢"))

    def test_multi_step_turns_are_planned(self):
        self.assertTrue(
            plan_execute_module.is_multi_step_task(
                "帮我写一个爬虫脚本采集数据，然后运行测试，最后导出结果文件"
            )
        )
        self.assertTrue(
            plan_execute_module.is_multi_step_task(
                "请分析这份报告并总结要点，然后生成一份 Markdown 文档并导出"
            )
        )
        self.assertTrue(
            plan_execute_module.is_multi_step_task(
                "分步完成：先下载数据，再转换格式，最后写入知识库"
            )
        )

    def test_extract_json_object_strips_markdown_fence(self):
        fence = chr(96) * 3
        raw = fence + "json" + chr(10) + '{"objective": "o", "steps": [{"title": "t"}]}' + chr(10) + fence
        data = plan_execute_module._extract_json_object(raw)
        self.assertEqual(data["objective"], "o")
        self.assertEqual(data["steps"][0]["title"], "t")

    def test_extract_json_object_embedded_in_prose(self):
        raw = (
            '好的，下面是计划：'
            + chr(10)
            + '{"objective": "整理文档", "steps": []}'
            + ' 就这些。'
        )
        data = plan_execute_module._extract_json_object(raw)
        self.assertEqual(data["objective"], "整理文档")

    def test_apply_reflection_adds_modifies_and_removes_pending(self):
        plan = plan_execute_module.Plan(
            objective="任务",
            steps=[
                plan_execute_module.PlanStep(id="s1", title="一", status="done", result="ok"),
                plan_execute_module.PlanStep(id="s2", title="二"),
                plan_execute_module.PlanStep(id="s3", title="三"),
            ],
        )
        reflection = plan_execute_module.Reflection(
            decision="continue",
            adjustments=[
                {"action": "add", "title": "四", "detail": "新步骤"},
                {"action": "modify", "target_index": 2, "title": "二改"},
                {"action": "remove", "target_index": 3},
            ],
        )
        plan_execute_module.apply_reflection(plan, reflection)
        titles = [s.title for s in plan.steps]
        self.assertIn("四", titles)
        self.assertIn("二改", titles)
        self.assertNotIn("三", titles)
        self.assertEqual(plan.steps[0].title, "一")  # completed step untouched

    def test_build_step_instruction_mentions_objective_and_prior(self):
        plan = plan_execute_module.Plan(
            objective="总体目标",
            steps=[
                plan_execute_module.PlanStep(id="s1", title="已完成", status="done", result="先前的产出"),
                plan_execute_module.PlanStep(id="s2", title="当前步"),
            ],
        )
        instruction = plan_execute_module.build_step_instruction(plan, plan.steps[1], 2, 2)
        self.assertIn("总体目标", instruction)
        self.assertIn("当前步", instruction)
        self.assertIn("先前的产出", instruction)


if __name__ == "__main__":
    unittest.main()
