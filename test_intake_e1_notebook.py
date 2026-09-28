"""intake-e1 Kaggle notebook builder: the generated notebook must carry the frozen
files verbatim and the setup cell must keep the torchvision uninstall that round-2
proved necessary (Version 1 died on the torchvision::nms import chain)."""
import json
import pathlib
import tempfile
import unittest

from local_assistant_finetune.intake_e1 import build_kaggle_notebook as b


class BuildKaggleNotebook(unittest.TestCase):
    def _build(self):
        out = pathlib.Path(tempfile.mktemp(suffix='.ipynb'))
        out.write_text(json.dumps(b.build()))
        return json.loads(out.read_text())

    def test_twelve_cells_in_order(self):
        nb = self._build()
        self.assertEqual(len(nb['cells']), 12)
        joined = [''.join(c['source']) for c in nb['cells']]
        self.assertTrue(joined[0].startswith('# intake-e1'))
        self.assertIn('generate_train_development.py --output', joined[4])
        self.assertIn('validate_no_overlap.py --dataset', joined[6])
        self.assertIn('train_multitask.py --dataset', joined[8])
        self.assertIn('evaluate_dev.py --dataset', joined[10])
        self.assertIn('mosaic.intake-e1.evidence.v1', joined[11])

    def test_setup_cell_uninstalls_torchvision(self):
        nb = self._build()
        setup = ''.join(nb['cells'][2]['source'])
        self.assertIn('--requirement /kaggle/working/e1/requirements-training.lock.txt', setup)
        self.assertIn('&& pip uninstall --yes torchvision', setup)

    def test_frozen_files_embedded_verbatim(self):
        nb = self._build()
        for cell_i, name in ((1, 'requirements-training.lock.txt'), (3, 'generate_train_development.py'),
                             (5, 'validate_no_overlap.py'), (7, 'train_multitask.py'), (9, 'evaluate_dev.py')):
            src = ''.join(nb['cells'][cell_i]['source'])
            self.assertTrue(src.startswith(f'%%writefile /kaggle/working/e1/{name}\n'), name)
            embedded = src.split('\n', 1)[1]
            on_disk = (b.HERE / name).read_text()
            self.assertEqual(embedded, on_disk if on_disk.endswith('\n') else on_disk + '\n', name)

    def test_model_and_revision_pinned(self):
        nb = self._build()
        for i in (8, 10):
            src = ''.join(nb['cells'][i]['source'])
            self.assertIn('--model Qwen/Qwen2.5-1.5B-Instruct', src)
            self.assertIn('--revision 989aa7980e4cf806f80c7fef2b1adb7bc71aa306', src)

    def test_evidence_cell_chains_manifest_and_dev_eval(self):
        nb = self._build()
        src = ''.join(nb['cells'][11]['source'])
        self.assertIn('run/artifact_manifest.json', src)
        self.assertIn('dev-eval.json', src)
        self.assertIn('dataset_sha256', src)


if __name__ == '__main__':
    unittest.main()
