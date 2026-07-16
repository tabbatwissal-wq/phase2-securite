import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main


class ReportIntegrationTests(unittest.TestCase):
    def test_executer_pipeline_complet_writes_pivot_and_generates_reports(self):
        class FakePivot:
            def __init__(self):
                self.kpis = []

            def model_dump(self, mode="json"):
                return {
                    "project": {"nom_projet": "Demo", "cle_jira": "TEST"},
                    "reporting_period": {"genere_le": "2026-07-13"},
                    "kpis": [],
                    "tasks": [],
                }

            def model_dump_json(self, indent=2):
                return json.dumps(self.model_dump())

        fake_pivot = FakePivot()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "pivot.json")
            with patch.object(main, "_construire_pivot", return_value=fake_pivot), \
                 patch("main.sauvegarder_pivot", return_value="mongo-123") as save_mock, \
                 patch("main.generer_pptx") as pptx_mock, \
                 patch("main.generer_pdf") as pdf_mock:
                result = main.executer_pipeline_complet("TEST", output_path=output_path)

            self.assertEqual(result["mongo_id"], "mongo-123")
            self.assertTrue(save_mock.called)
            self.assertTrue(pptx_mock.called)
            self.assertTrue(pdf_mock.called)
            self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
