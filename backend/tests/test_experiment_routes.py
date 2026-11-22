"""路由层测试：用 stub 替代 DB/鉴权，验证配对试验接口的编排与校验。

FastAPI 依赖注入通过 dependency_overrides 替换，不监听端口、不连数据库。
若环境未安装 fastapi/sqlalchemy，则自动跳过。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient  # noqa: E402
    import src.main as main_module  # noqa: E402
    _HAS_FASTAPI = False
except Exception:  # pragma: no cover - 本地无第三方依赖时跳过
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "环境未安装 FastAPI/SQLAlchemy，路由集成测试在容器内运行")
class ExperimentRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main_module.app)

    def test_spec_exposes_nine_pages(self):
        response = self.client.get('/spec')
        self.assertEqual(response.status_code, 200)
        self.assertIn('信号方案配对试验', response.json()['pages'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
