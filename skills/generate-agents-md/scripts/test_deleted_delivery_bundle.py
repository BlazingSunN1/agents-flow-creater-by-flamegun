"""Validator-fixture regression: explicit deletion through the public aggregate."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_validate_delivery_bundle as bundle_support
from validate_context_manifest import _parse_metadata, _paths_fingerprint, _cache_key


class DeletedDeliveryBundleTests(unittest.TestCase):
    def test_explicit_deleted_code_link_passes_public_bundle(self):
        f = bundle_support.DeliveryBundleValidatorTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        self.assertEqual([], f.public_issues())
        changed = ['src/legacy.py', 'src/module.py']
        deleted = {'src/legacy.py'}
        (f.root / 'src/legacy.py').write_text('legacy implementation\n')
        (f.root / 'src/legacy.py').unlink()
        f.trace_fixture.matrix.write_text(f.trace_fixture.matrix.read_text().replace(
            '[MOD-001](src/module.py)', '[MOD-001](src/module.py) [MOD-002](src/legacy.py)'))
        metadata, duplicates = _parse_metadata(f.context.read_text())
        self.assertFalse(duplicates)
        metadata.update({'Changed files': ', '.join(changed), 'Deleted files': ', '.join(deleted),
                         'Module changed files': 'module=' + ','.join(changed),
                         'Reuse decision': 'rerun', 'Reuse record': 'N/A: current candidate'})
        code_hash = _paths_fingerprint(', '.join(changed), f.root.resolve(), [], 'changed-file',
                                       deleted_files=deleted)
        metadata['Code fingerprint'] = code_hash
        metadata['Evidence cache key'] = _cache_key(metadata)
        f.context.write_text('# Context Workset impl-run-1\n\n' + '\n'.join(
            '- ' + key + ': ' + value for key, value in metadata.items()) + '\n')
        f.module_run.write_text(f._module_run_record().replace(
            '- Changed files: src/module.py', '- Changed files: ' + ', '.join(changed)))
        self._rebind_review(f, changed, code_hash)
        swimlane = json.loads(f.swimlane.read_text())
        for diagram in swimlane['diagrams']:
            diagram['code_evidence'] = changed
        f.swimlane.write_text(json.dumps(swimlane))
        f._write_agent_inputs()
        f._write_agent_outputs()
        f.multi_agent.write_text(json.dumps(f._multi_agent_evidence()))
        data = json.loads(f.contract.read_text())
        data['change'].update(changed_files=changed, deleted_files=sorted(deleted))
        data['artifacts']['traceability'] = f._contract_ref(f.trace_fixture.matrix)
        f._bind_contract_gate_plan(data, 'completion')
        f.contract.write_text(json.dumps(data))
        self.assertEqual([], f.public_issues())
        (f.root / 'src/legacy.py').write_text('restored')
        self.assertTrue(f.public_issues())

    def _rebind_review(self, f, changed, code_hash):
        output_path = f.root / 'evidence/automated-review.json'
        output = json.loads(output_path.read_text())
        output.update(changed_files=changed, code_fingerprint=code_hash)
        output_path.write_text(json.dumps(output))
        review = f.review.read_text()
        for key, value in {
            'Code fingerprint': code_hash, 'Changed files': ', '.join(changed),
            'Scope': '; '.join(changed) + '; callers; callees; interfaces; configuration; tests; traceability; swimlanes',
            'Review evidence SHA-256': hashlib.sha256(output_path.read_bytes()).hexdigest(),
        }.items():
            review, count = re.subn(r'(?m)^- ' + re.escape(key) + r': .+$', '- ' + key + ': ' + value, review)
            self.assertEqual(1, count)
        f.review.write_text(review)


if __name__ == '__main__':
    unittest.main()
