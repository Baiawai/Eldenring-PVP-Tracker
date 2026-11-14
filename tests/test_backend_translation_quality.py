"""Regression checks for translated tracker-generated arena messages."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackendTranslationQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))

    def test_combat_start_describes_a_combat(self):
        self.assertEqual(self.packs['ita']['backend'][9], 'Inizio del combattimento')
        self.assertEqual(self.packs['jap']['backend'][9], '戦闘開始')
        self.assertEqual(self.packs['kor']['backend'][9], '전투 시작')

    def test_combat_start_matches_frontend_marker_in_every_language(self):
        for language, pack in self.packs.items():
            with self.subTest(language=language):
                self.assertEqual(pack['counter'][7], pack['backend'][9])

    def test_arena_mode_settings_are_not_unrelated_terms(self):
        self.assertEqual(self.packs['kor']['backend'][14:19],
                         ['전투원 2명', '금지', '모든 플레이어', '선호 없음', '왕실 콜로세움'])
        self.assertEqual(self.packs['tha']['backend'][18], 'โคลอสเซียมหลวง')
        self.assertEqual(self.packs['zht']['backend'][18], '皇家競技場')
        self.assertEqual(self.packs['ara']['backend'][18], 'الكولوسيوم الملكي')
        for language in ('spaes', 'spaar'):
            self.assertEqual(self.packs[language]['backend'][18], 'Coliseo real')

    def test_matchmaking_cancellation_is_not_about_marriage(self):
        self.assertNotIn('casamenteira', self.packs['por']['backend'][7].lower())
        self.assertNotIn('swatanie', self.packs['pol']['backend'][7].lower())
        self.assertNotIn('сватовство', self.packs['rus']['backend'][7].lower())

    def test_exit_messages_retain_line_breaks_in_all_languages(self):
        for language, pack in self.packs.items():
            for index in (0, 1, 3, 13):
                with self.subTest(language=language, index=index):
                    self.assertEqual(pack['backend'][index].count('<br>'), 1)


if __name__ == '__main__':
    unittest.main()
