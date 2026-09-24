"""Offline regression tests for compact, distinct Left/Right demo comparisons."""
import unittest

import matplotlib.pyplot as plt

from demo_ui import _overview_chart_label
from demo_backend import (
    COMMUNICATION_DIMENSIONS, box_metrics_figure, category_figure,
    metrics_figure, radar_figure, _numeric_values,
)


class OverviewChartTests(unittest.TestCase):
    def setUp(self):
        def record(name, words, images):
            return {
                'bank': 'BNP Paribas Fortis', 'campaign_id': name,
                'deterministic_metrics': {'text_characters': words, 'visible_image_count': images},
                'communication_scores': {
                    dimension: {'score': 3} for dimension in COMMUNICATION_DIMENSIONS
                },
            }
        self.left = record('left', 1200, 3)
        self.right = record('right', 2000, 8)
        self.selections = [('Left', [self.left]), ('Right', [self.right])]

    def tearDown(self):
        plt.close('all')

    def test_compact_radar_has_both_series_even_for_same_bank(self):
        fig = radar_figure(self.selections)
        self.assertEqual(len(fig.axes[0].lines), 2)
        self.assertLess(fig.get_figwidth(), 9)
        self.assertEqual([text.get_text() for text in fig.legends[0].get_texts()], ['Left', 'Right'])

    def test_selected_names_are_used_in_radar_and_metric_charts(self):
        named = [('Left: BNP accounts', [self.left]), ('Right: N26 plans', [self.right])]
        radar = radar_figure(named)
        self.assertEqual([text.get_text() for text in radar.legends[0].get_texts()],
                         [label for label, _ in named])
        numeric = metrics_figure(named, ['text_characters'])
        self.assertEqual([tick.get_text() for tick in numeric.axes[0].get_yticklabels()],
                         [label for label, _ in named])
        distribution = box_metrics_figure(named, ['text_characters'])
        self.assertEqual([tick.get_text() for tick in distribution.axes[0].get_yticklabels()],
                         [f'{label} (n=1)' for label, _ in named])

    def test_numeric_bars_use_separate_axes_and_distinct_colours(self):
        fig = metrics_figure(self.selections, ['text_characters', 'visible_image_count'])
        self.assertEqual(len(fig.axes), 2)
        for axis in fig.axes:
            self.assertEqual(len(axis.patches), 2)
            self.assertNotEqual(axis.patches[0].get_facecolor(), axis.patches[1].get_facecolor())
            self.assertEqual([label.get_text() for label in axis.get_yticklabels()], ['Left', 'Right'])
        self.assertNotEqual(fig.axes[0].get_xlim(), fig.axes[1].get_xlim())

    def test_single_page_box_displays_two_distinct_diamonds(self):
        fig = box_metrics_figure(self.selections, ['text_characters'])
        axis = fig.axes[0]
        self.assertEqual(len(axis.collections), 2)
        self.assertEqual([label.get_text() for label in axis.get_yticklabels()], ['Left (n=1)', 'Right (n=1)'])
        self.assertEqual(len(axis.artists), 0)  # no invented box distribution for one page

    def test_box_with_two_pages_per_selection_displays_both_distributions(self):
        left = [self.left, {**self.left, 'deterministic_metrics': {'text_characters': 1900}}]
        right = [self.right, {**self.right, 'deterministic_metrics': {'text_characters': 2500}}]
        fig = box_metrics_figure([('Left', left), ('Right', right)], ['text_characters'])
        axis = fig.axes[0]
        self.assertEqual(len(axis.patches), 2)
        self.assertNotEqual(axis.patches[0].get_facecolor(), axis.patches[1].get_facecolor())

    def test_individual_categories_are_presence_not_numeric_scores(self):
        named = [('Left: BNP account', [self.left]), ('Right: N26 plans', [self.right])]
        fig = category_figure([
            {'Selection': named[0][0], 'Category': 'High'},
            {'Selection': named[1][0], 'Category': 'Low'},
        ], named)
        axis = fig.axes[0]
        self.assertEqual(len(axis.collections), 4)  # two campaigns x two labels
        self.assertEqual(len(axis.patches), 0)  # no misleading 0-1 bars
        self.assertEqual([text.get_text() for text in fig.legends[0].get_texts()],
                         [label for label, _ in named])
        self.assertEqual([text.get_text() for text in axis.get_xticklabels()], ['Left', 'Right'])
        self.assertLess(fig.get_figwidth(), 9)

    def test_bank_categories_show_prevalence_not_raw_counts(self):
        left = [self.left, dict(self.left, campaign_id='second')]
        right = [self.right, dict(self.right, campaign_id='fourth')]
        named = [('Left: BNP Paribas Fortis', left), ('Right: N26', right)]
        fig = category_figure([
            {'Selection': named[0][0], 'Category': 'High'},
            {'Selection': named[1][0], 'Category': 'High'},
            {'Selection': named[1][0], 'Category': 'High'},
        ], named, mode='Whole banks', eligible={named[0][0]: 2, named[1][0]: 2})
        axis = fig.axes[0]
        self.assertEqual(sorted(round(bar.get_width()) for bar in axis.patches), [50, 100])
        self.assertEqual([text.get_text() for text in fig.legends[0].get_texts()],
                         [label for label, _ in named])
        self.assertEqual(axis.get_xlim()[0], 0)
        self.assertIn('100%', [text.get_text() for text in axis.get_xticklabels()])

    def test_chart_labels_identify_selections_and_truncate_long_campaigns(self):
        label = _overview_chart_label('Left', 'Compare your accounts', 'BNP Paribas Fortis')
        self.assertIn('BNP:', label)
        self.assertIn('Compare your accounts', label)
        self.assertEqual(_overview_chart_label('Right', 'N26'), 'Right: N26')
        self.assertLessEqual(len(_overview_chart_label('Left', 'A' * 100)), 43)

    def test_missing_metric_is_not_counted_as_zero(self):
        record = {'deterministic_metrics': {'visible_image_count': 0}}
        self.assertEqual(_numeric_values([record, {}], 'visible_image_count'), [0])
        self.assertEqual(_numeric_values([record, {}], 'text_characters'), [])


if __name__ == '__main__':
    unittest.main()
