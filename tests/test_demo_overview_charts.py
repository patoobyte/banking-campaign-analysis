"""Offline regression tests for compact, distinct Left/Right demo comparisons."""
import unittest

import matplotlib.pyplot as plt

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

    def test_category_counts_distinguish_same_bank_campaigns(self):
        fig = category_figure([
            {'Selection': 'Left', 'Category': 'High'},
            {'Selection': 'Right', 'Category': 'Low'},
        ], self.selections)
        axis = fig.axes[0]
        self.assertEqual(len(axis.patches), 4)
        self.assertEqual(len(fig.legends[0].get_texts()), 2)
        self.assertLess(fig.get_figwidth(), 9)

    def test_missing_metric_is_not_counted_as_zero(self):
        record = {'deterministic_metrics': {'visible_image_count': 0}}
        self.assertEqual(_numeric_values([record, {}], 'visible_image_count'), [0])
        self.assertEqual(_numeric_values([record, {}], 'text_characters'), [])


if __name__ == '__main__':
    unittest.main()
