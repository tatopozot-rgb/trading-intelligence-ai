"""Pure model acceptance for the existing local sync; no git/vault/daemon writes.

Run: python test_sync_review.py <directory-containing-sync_agent_city.py>
"""
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv.pop(1)).resolve()))
sync = importlib.import_module('sync_agent_city')


def source(agenda='', checkpoint=''):
    return dict(fetch_ok=True, errores=[], ramas=[], md_agenda=agenda,
                md_check=checkpoint, shadow=False,
                cfg='MODO = "PAPER"\nUSAR_DINERO_REAL = False\nCAPITAL_USD = 100.0\nDRAWDOWN_HALT_PCT = 15.0\n')


class SyncAcceptance(unittest.TestCase):
    def setUp(self):
        # Even accidental transport or filesystem paths fail instead of running.
        for name in ('git', 'escribir', 'guardar_eventos', 'escribir_vault', 'ejecutar_tests'):
            p = patch.object(sync, name, side_effect=AssertionError('Review must remain pure'))
            p.start()
            self.addCleanup(p.stop)

    def test_completed_table_without_status_column_is_done(self):
        agenda = '## Completed Tasks\n| Task | Agent | Date | PR |\n|---|---|---|---|\n| Fixture done | Trading Codex | 2026-10-06 | #1 |\n'
        model = sync.construir(source(agenda), None)
        self.assertEqual(model['tasks'][0]['status'], 'DONE')

    def test_markdown_emphasis_does_not_hide_explicit_done(self):
        self.assertEqual(sync.estado_tarea('**DONE** — commit abc'), 'DONE')

    def test_old_test_count_is_not_presented_as_current_evidence(self):
        checkpoint = '### 1. Historical\n92/92 tests passing\n### 23. Current\n262/262 tests passing\n'
        model = sync.construir(source(checkpoint=checkpoint), None)
        result = next(a for a in model['agents'] if a['key'] == 'codex')['last_result']
        self.assertNotIn('92/92', result['text'])

    def test_unknown_activity_stays_not_synced_not_working(self):
        model = sync.construir(source(), None)
        self.assertTrue(all(a['state'] == 'NOT_SYNCED' for a in model['agents']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
