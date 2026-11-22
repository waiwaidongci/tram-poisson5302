"""配对信号方案试验的领域逻辑测试，只用标准库：python -I -m unittest -v。"""

import sys
import unittest
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.experiment import (  # noqa: E402
    parse_draw, parse_recon, reconcile, run_experiment, permutation_test, _statistic,
)


def draw_pair(pair_id, group, order_a="旧-新", order_b="新-旧", day=7):
    base = f"2026-11-{day:02d}"
    common = {"pair_id": pair_id, "group_name": group,
              "window_start": f"{base} 08:00:00", "window_end": f"{base} 10:00:00",
              "switch_at": f"{base} 09:00:00"}
    return [{**common, "shift_id": f"{pair_id}-甲", "scheme_order": order_a},
            {**common, "shift_id": f"{pair_id}-乙", "scheme_order": order_b}]


def segment_records(pair_id, shift_id, old_exp, old_block, warm_exp, warm_block,
                    new_exp, new_block, base="2026-11-07"):
    """旧段 08:00-09:00、热身 09:00-09:30、新段 09:30-10:00 各一条跨系统记录。

    信号系统记录只含过车车次，值班系统记录只含阻断次数。
    """
    rows = []
    spans = [("08:00:00", "09:00:00", old_exp, old_block),
             ("09:00:00", "09:30:00", warm_exp, warm_block),
             ("09:30:00", "10:00:00", new_exp, new_block)]
    for start, end, exposure, blockage in spans:
        rows.append({"pair_id": pair_id, "shift_id": shift_id, "source_system": "signal",
                     "record_start": f"{base} {start}", "record_end": f"{base} {end}",
                     "exposure": exposure})
        rows.append({"pair_id": pair_id, "shift_id": shift_id, "source_system": "duty",
                     "record_start": f"{base} {start}", "record_end": f"{base} {end}",
                     "blockage": blockage})
    return rows


class ExperimentDomainTests(unittest.TestCase):
    def setUp(self):
        self.draw = draw_pair("P1", "港湾路-货栈街口") + draw_pair("P2", "港湾路-渡口街口", day=8)
        self.recon = (segment_records("P1", "P1-甲", 100, 8, 40, 9, 100, 4)
                      + segment_records("P1", "P1-乙", 100, 5, 40, 9, 100, 7)
                      + segment_records("P2", "P2-甲", 200, 20, 80, 9, 200, 10, base="2026-11-08")
                      + segment_records("P2", "P2-乙", 200, 12, 80, 9, 200, 18, base="2026-11-08"))
        self.rng = Random(20261122)

    def _pairs(self, warmup=30):
        return reconcile(parse_draw(self.draw), parse_recon(self.recon), warmup)

    def test_parse_draw_requires_two_shifts_per_pair(self):
        bad = self.draw[:-1]
        with self.assertRaisesRegex(ValueError, "须恰好包含两个班次"):
            parse_draw(bad)

    def test_parse_draw_rejects_switch_outside_window(self):
        bad = [dict(row, switch_at="2026-11-07 07:30:00") for row in self.draw[:2]]
        with self.assertRaisesRegex(ValueError, "切换时间须落在班次窗口内"):
            parse_draw(bad)

    def test_reconcile_marks_warmup_and_includes_complete_pairs(self):
        pairs = self._pairs()
        self.assertEqual([row["pair_id"] for row in pairs], ["P1", "P2"])
        self.assertTrue(all(row["included"] for row in pairs))
        p1 = pairs[0]
        # 热身段每班次只有 1 条 duty 记录（9 次），两班次合计 18，且不进任何方案
        self.assertEqual(p1["warmup_blockage"], 9 * 2)
        self.assertEqual(p1["warmup_exposure"], 40 * 2)
        # 两班按抽签顺序归并：甲 旧-新（旧8/新4），乙 新-旧（旧7/新5）
        self.assertEqual(p1["old_blockage"], 8 + 7)
        self.assertEqual(p1["new_blockage"], 4 + 5)
        self.assertEqual(p1["old_exposure"], 200)
        self.assertEqual(p1["new_exposure"], 200)

    def test_missing_source_excludes_whole_pair_only(self):
        # 删掉 P1-甲 的值班系统阻断记录
        trimmed = [row for row in self.recon
                   if not (row["pair_id"] == "P1" and row["shift_id"] == "P1-甲"
                           and row["source_system"] == "duty")]
        pairs = reconcile(parse_draw(self.draw), parse_recon(trimmed), 30)
        by_id = {row["pair_id"]: row for row in pairs}
        self.assertFalse(by_id["P1"]["included"])
        self.assertTrue(any("缺少值班系统阻断记录" in issue for issue in by_id["P1"]["issues"]))
        self.assertTrue(by_id["P2"]["included"])

    def test_record_outside_window_is_flagged(self):
        bad = self.recon + [{"pair_id": "P1", "shift_id": "P1-甲", "source_system": "signal",
                             "record_start": "2026-11-07 10:00:00", "record_end": "2026-11-07 10:30:00",
                             "exposure": 10}]
        pairs = reconcile(parse_draw(self.draw), parse_recon(bad), 30)
        self.assertFalse(pairs[0]["included"])
        self.assertTrue(any("超出抽签班次窗口" in issue for issue in pairs[0]["issues"]))

    def test_zero_warmup_attributes_full_window(self):
        pairs = self._pairs(warmup=0)
        p1 = pairs[0]
        self.assertEqual(p1["warmup_minutes"], 0.0)
        # 无热身时全部阻断归入方案段：两班次各 8+9+4 与 5+9+7
        self.assertEqual(p1["old_blockage"] + p1["new_blockage"],
                         (8 + 9 + 4) + (5 + 9 + 7))

    def test_permutation_only_flips_whole_pair_labels(self):
        pairs = self._pairs()
        result = permutation_test(pairs, 999, self.rng)
        # 两对 → 精确枚举 4 种排列；观测差为跨对汇总的旧率减新率
        self.assertEqual(result["permutation_draws"], 4)
        self.assertIn("精确枚举", result["method"])
        included = pairs
        old_rate = 100 * sum(r["old_blockage"] for r in included) / sum(r["old_exposure"] for r in included)
        new_rate = 100 * sum(r["new_blockage"] for r in included) / sum(r["new_exposure"] for r in included)
        expected = old_rate - new_rate
        self.assertAlmostEqual(result["observed_difference"], expected, places=10)
        # 翻转全部配对时新旧互换，差异取相反数；四种整组交换关于 0 对称
        flipped_all, _, _ = _statistic(included, frozenset(r["pair_id"] for r in included))
        self.assertAlmostEqual(flipped_all, -expected, places=10)

    def test_single_pair_distribution_covers_difference_and_its_negation(self):
        draw = draw_pair("P1", "港湾路-货栈街口", order_a="旧-新", order_b="旧-新")
        recon = segment_records("P1", "P1-甲", 100, 10, 0, 0, 100, 2) \
            + segment_records("P1", "P1-乙", 100, 8, 0, 0, 100, 3)
        pairs = reconcile(parse_draw(draw), parse_recon(recon), 30)
        result = permutation_test(pairs, 999, Random(1))
        self.assertEqual(result["permutation_draws"], 2)
        # 两种整组交换各出现一次，双侧 p 值恒为 1
        self.assertEqual(result["p_value"], 1.0)
        self.assertTrue(result["reduces_blockage"])
        self.assertAlmostEqual(result["old_rate"], 100 * 18 / 200, places=10)
        self.assertAlmostEqual(result["new_rate"], 100 * 5 / 200, places=10)

    def test_all_excluded_raises(self):
        empty_recon = []
        pairs = reconcile(parse_draw(self.draw), parse_recon(empty_recon), 30)
        with self.assertRaisesRegex(ValueError, "没有任何配对通过对账"):
            permutation_test(pairs, 999, self.rng)

    def test_run_experiment_end_to_end_and_rerun_identical(self):
        first = run_experiment(self.draw, self.recon, 30, 999, Random(7))
        second = run_experiment(self.draw, self.recon, 30, 999, Random(7))
        self.assertEqual(first["stats"]["observed_difference"], second["stats"]["observed_difference"])
        self.assertEqual(first["stats"]["p_value"], second["stats"]["p_value"])
        self.assertEqual(first["stats"]["included_pairs"], 2)
        # 旧方案：P1（甲旧8＋乙旧7）、P2（甲旧20＋乙旧18）
        self.assertEqual(first["totals"]["old_blockage"], 8 + 7 + 20 + 18)
        # 新方案：P1（甲新4＋乙新5）、P2（甲新10＋乙新12）
        self.assertEqual(first["totals"]["new_blockage"], 4 + 5 + 10 + 12)
        self.assertIn("整组交换", first["note"])

    def test_monte_carlo_path_above_exact_limit(self):
        draw, recon = [], []
        for index in range(21):
            day = 1 + index % 28
            draw += draw_pair(f"P{index}", f"组{index}", day=day)
            recon += segment_records(f"P{index}", f"P{index}-甲", 100, 6, 0, 0, 100, 3,
                                     base=f"2026-11-{day:02d}")
            recon += segment_records(f"P{index}", f"P{index}-乙", 100, 6, 0, 0, 100, 3,
                                     base=f"2026-11-{day:02d}")
        result = run_experiment(draw, recon, 30, 199, Random(3))["stats"]
        self.assertEqual(result["permutation_draws"], 200)
        self.assertIn("蒙特卡洛", result["method"])
        self.assertEqual(result["included_pairs"], 21)

    def test_warmup_covering_window_end_leaves_no_second_scheme(self):
        # 热身 60 分钟，09:00 切换、10:00 下班，热身恰好占满切换后全部时间
        draw = draw_pair("P1", "港湾路-货栈街口")
        recon = segment_records("P1", "P1-甲", 100, 8, 40, 9, 100, 4) \
            + segment_records("P1", "P1-乙", 100, 5, 40, 9, 100, 7)
        pairs = reconcile(parse_draw(draw), parse_recon(recon), 60)
        self.assertFalse(pairs[0]["included"])
        self.assertTrue(any("没有落入新方案的有效窗" in issue for issue in pairs[0]["issues"]))

    def test_cross_segment_record_is_split_by_overlap_minutes(self):
        # 一条记录横跨 08:45–09:15：旧段 15 分钟、热身 15 分钟，各分摊一半
        draw = draw_pair("P1", "港湾路-货栈街口")
        cross_signal = {"pair_id": "P1", "shift_id": "P1-甲", "source_system": "signal",
                        "record_start": "2026-11-07 08:45:00", "record_end": "2026-11-07 09:15:00",
                        "exposure": 100}
        cross_duty = {**{k: v for k, v in cross_signal.items() if k != "exposure"},
                      "source_system": "duty", "blockage": 10}
        # 其余时段补齐两个来源，保证配对整体可纳入
        fill = [
            {"pair_id": "P1", "shift_id": "P1-甲", "source_system": "signal",
             "record_start": "2026-11-07 08:00:00", "record_end": "2026-11-07 08:45:00",
             "exposure": 50},
            {"pair_id": "P1", "shift_id": "P1-甲", "source_system": "duty",
             "record_start": "2026-11-07 08:00:00", "record_end": "2026-11-07 08:45:00",
             "blockage": 4},
            {"pair_id": "P1", "shift_id": "P1-甲", "source_system": "signal",
             "record_start": "2026-11-07 09:30:00", "record_end": "2026-11-07 10:00:00",
             "exposure": 60},
            {"pair_id": "P1", "shift_id": "P1-甲", "source_system": "duty",
             "record_start": "2026-11-07 09:30:00", "record_end": "2026-11-07 10:00:00",
             "blockage": 2},
        ]
        # 乙班完整覆盖
        fill += segment_records("P1", "P1-乙", 100, 5, 40, 9, 100, 7)
        recon = [cross_signal, cross_duty] + fill
        pairs = reconcile(parse_draw(draw), parse_recon(recon), 30)
        p1 = pairs[0]
        self.assertTrue(p1["included"], p1["issues"])
        # 甲班旧段车次 = 50（补齐）+ 100 跨段的一半
        self.assertEqual(p1["old_exposure"], 50 + 50 + 100)  # 末项 100 为乙班旧段
        self.assertEqual(p1["warmup_blockage"], 9 + 5)  # 乙班热身 9 ＋ 跨段 duty 一半 5


if __name__ == "__main__":
    unittest.main(verbosity=2)
