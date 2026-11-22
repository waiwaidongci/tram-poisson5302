"""服务层重算/撤下规则测试，用内存假网关替代数据库，不依赖第三方包。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.constants.enums import ConclusionState, ExperimentStatus  # noqa: E402
from src.services import experiments as service  # noqa: E402
from tests.test_experiment import draw_pair, segment_records  # noqa: E402


class FakeConclusion:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeExperiment:
    def __init__(self, draw_rows, warmup=30, permutations=999):
        self.id = 1
        self.name = "示例试验"
        self.draw_rows = draw_rows
        self.draw_checksum = service.fingerprint(draw_rows)
        self.warmup_minutes = warmup
        self.permutations = permutations
        self.pair_count = len({row["pair_id"] for row in draw_rows})
        self.included_count = 0
        self.status = ExperimentStatus.DRAFT
        self.result = None
        self.error = None
        self.recon_rows = None
        self.recon_checksum = None
        self.computed_at = None
        self.updated_at = None


class FakeGateway:
    """与 ExperimentGateway 同接口的内存实现。"""

    def __init__(self):
        self.experiments = {}
        self.conclusions = []
        self.audit_log = []
        self._seq = 0

    def find_experiment_by_draw_checksum(self, checksum):
        for item in self.experiments.values():
            if item.draw_checksum == checksum:
                return item
        return None

    def create_experiment(self, **kwargs):
        self._seq += 1
        item = FakeExperiment(kwargs["draw_rows"],
                              warmup=kwargs["warmup_minutes"],
                              permutations=kwargs["permutations"])
        item.id = self._seq
        item.name = kwargs["name"]
        item.draw_checksum = kwargs["draw_checksum"]
        item.pair_count = kwargs["pair_count"]
        item.author = kwargs["author"]
        self.experiments[item.id] = item
        return item

    def find_active_conclusion(self, experiment_id):
        for conclusion in self.conclusions:
            if conclusion.experiment_id == experiment_id and \
               conclusion.state == ConclusionState.ACTIVE:
                return conclusion
        return None

    def next_conclusion_version(self, experiment_id):
        versions = [c.version for c in self.conclusions if c.experiment_id == experiment_id]
        return (max(versions) if versions else 0) + 1

    def add_conclusion(self, **kwargs):
        conclusion = FakeConclusion(**kwargs)
        self.conclusions.append(conclusion)
        return conclusion

    def audit(self, actor, event, target, **info):
        self.audit_log.append((actor, event, target, info))


class ExperimentServiceTests(unittest.TestCase):
    def setUp(self):
        self.draw = draw_pair("P1", "港湾路-货栈街口") + draw_pair("P2", "港湾路-渡口街口", day=8)
        self.recon_v1 = (segment_records("P1", "P1-甲", 100, 8, 40, 9, 100, 4)
                         + segment_records("P1", "P1-乙", 100, 5, 40, 9, 100, 7)
                         + segment_records("P2", "P2-甲", 200, 20, 80, 9, 200, 10, base="2026-11-08")
                         + segment_records("P2", "P2-乙", 200, 12, 80, 9, 200, 18, base="2026-11-08"))

    def test_register_parses_and_persists_flat_draw_rows(self):
        gateway = FakeGateway()
        item, created = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        self.assertTrue(created)
        self.assertEqual(item.pair_count, 2)
        self.assertEqual(item.status, ExperimentStatus.DRAFT)
        # 入库的是扁平行，时间为字符串，可直接 JSON 序列化
        self.assertEqual(len(item.draw_rows), 4)
        self.assertIsInstance(item.draw_rows[0]["window_start"], str)
        # 同抽签单同名重复登记不新建
        again, created_again = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        self.assertFalse(created_again)
        self.assertIs(again, item)

    def test_first_compute_creates_active_conclusion_version_one(self):
        gateway = FakeGateway()
        item, _ = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        service.recompute(gateway, item, self.recon_v1, "analyst", reason="manual")
        self.assertEqual(item.status, ExperimentStatus.COMPUTED)
        self.assertIsNone(item.error)
        conclusion = gateway.conclusions[0]
        self.assertEqual(conclusion.version, 1)
        self.assertEqual(conclusion.state, ConclusionState.ACTIVE)
        self.assertEqual(conclusion.result["stats"]["included_pairs"], 2)

    def test_source_update_supersedes_before_recompute(self):
        gateway = FakeGateway()
        item, _ = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        service.recompute(gateway, item, self.recon_v1, "analyst")
        first = gateway.conclusions[0]
        # 源数据更新：删掉 P2-甲 值班系统的全部阻断记录，该班次缺窗 → 整对排除
        recon_v2 = [row for row in self.recon_v1
                    if not (row["pair_id"] == "P2" and row["shift_id"] == "P2-甲"
                            and row["source_system"] == "duty")]
        service.recompute(gateway, item, recon_v2, "analyst", reason="source-refresh")
        # 旧结论必须先被撤下，而不是被覆盖
        self.assertEqual(first.state, ConclusionState.SUPERSEDED)
        self.assertIsNotNone(first.superseded_at)
        self.assertIn("源数据更新", first.reason)
        second = gateway.conclusions[1]
        self.assertEqual(second.version, 2)
        self.assertEqual(second.state, ConclusionState.ACTIVE)
        self.assertEqual(second.result["stats"]["excluded_pairs"], 1)
        self.assertEqual(item.status, ExperimentStatus.COMPUTED)
        self.assertEqual(item.included_count, 1)
        # 审计轨迹包含撤下与重算两个事件
        events = [entry[1] for entry in gateway.audit_log]
        self.assertIn("experiment.conclusion_superseded", events)
        self.assertIn("experiment.recomputed", events)

    def test_failed_recompute_keeps_superseded_conclusion_and_marks_failed(self):
        gateway = FakeGateway()
        item, _ = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        service.recompute(gateway, item, self.recon_v1, "analyst")
        first = gateway.conclusions[0]
        # 更新后的对账数据导致所有配对都缺窗
        service.recompute(gateway, item, [], "analyst", reason="source-refresh")
        self.assertEqual(first.state, ConclusionState.SUPERSEDED)
        self.assertEqual(item.status, ExperimentStatus.FAILED)
        self.assertIn("没有任何配对通过对账", item.error)
        # 失败不产生新的 active 结论，旧结论仍保留为 superseded
        self.assertEqual(len(gateway.conclusions), 1)
        self.assertIsNone(item.result)
        self.assertEqual(item.recon_checksum, service.fingerprint([]))

    def test_risk_report_works_without_any_recon(self):
        gateway = FakeGateway()
        item, _ = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        report = service.reconcile_only(item)
        self.assertIsNone(report["recon_checksum"])
        self.assertEqual(len(report["pairs"]), 2)
        self.assertTrue(all(not row["included"] for row in report["pairs"]))
        self.assertTrue(all("缺窗" in issue for row in report["pairs"] for issue in row["issues"]))

    def test_risk_report_lists_missing_sources_per_shift(self):
        gateway = FakeGateway()
        item, _ = service.register(gateway, "首轮抽签", self.draw, 30, 999, "analyst")
        service.recompute(gateway, item, self.recon_v1, "analyst")
        trimmed = [row for row in self.recon_v1
                   if not (row["pair_id"] == "P1" and row["shift_id"] == "P1-甲")]
        item.recon_rows = trimmed
        item.recon_checksum = service.fingerprint(trimmed)
        report = service.reconcile_only(item)
        p1 = next(row for row in report["pairs"] if row["pair_id"] == "P1")
        self.assertFalse(p1["included"])
        joined = " ".join(p1["issues"])
        self.assertIn("缺少信号系统过车", joined)
        self.assertIn("值班系统阻断记录", joined)
        p2 = next(row for row in report["pairs"] if row["pair_id"] == "P2")
        self.assertTrue(p2["included"])
    def test_reproducible_reruns_with_same_snapshot(self):
        gateway = FakeGateway()
        item_a, _ = service.register(gateway, "A", self.draw, 30, 999, "analyst")
        item_b, _ = service.register(gateway, "B", self.draw, 30, 999, "analyst")
        service.recompute(gateway, item_a, self.recon_v1, "analyst")
        service.recompute(gateway, item_b, self.recon_v1, "analyst")
        self.assertEqual(item_a.result["stats"]["p_value"], item_b.result["stats"]["p_value"])
        self.assertEqual(item_a.result["stats"]["observed_difference"],
                         item_b.result["stats"]["observed_difference"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
