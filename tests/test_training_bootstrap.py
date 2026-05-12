import importlib
import unittest


class TrainingBootstrapTest(unittest.TestCase):
    def test_project_model_exports(self):
        model_mod = importlib.import_module("project.model")
        self.assertTrue(hasattr(model_mod, "DACGModel"))
        self.assertTrue(hasattr(model_mod, "DACGModelConfig"))

    def test_structured_loss_module_importable(self):
        loss_mod = importlib.import_module("modules.structured_loss")
        self.assertTrue(hasattr(loss_mod, "compute_structured_loss"))


if __name__ == "__main__":
    unittest.main()
