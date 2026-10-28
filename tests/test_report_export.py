import unittest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

from services.report_export import _inline_markup, _report_flowables, _report_styles, create_pdf_report


class ReportExportTests(unittest.TestCase):
    def test_markdown_is_rendered_and_input_markup_is_escaped(self):
        markup = _inline_markup('**Bold** and `code` with <unsafe> & a range 100\u2013140')
        self.assertIn('<b>Bold</b>', markup)
        self.assertIn('&lt;unsafe&gt;', markup)
        self.assertIn('&amp;', markup)
        self.assertNotIn('**', markup)
        self.assertIn('100-140', markup)

    def test_sections_and_numbered_lists_are_distinct(self):
        blocks = _report_flowables('## 6. Actions\n\n1. **Verify** the listing.\n\n**Data Quality Notice:**\n\n- Limited coverage.\n\n***', _report_styles())
        paragraphs = [block for block in blocks if isinstance(block, Paragraph)]
        self.assertEqual(paragraphs[1].bulletText, '1.')
        self.assertEqual(paragraphs[1].getPlainText(), 'Verify the listing.')
        self.assertEqual(paragraphs[2].getPlainText(), 'Data Quality Notice:')
        self.assertTrue(paragraphs[0].getKeepWithNext())

    def test_pdf_generation_handles_html_characters_and_markdown(self):
        pdf = create_pdf_report('# Test <Business>\n\n## Evidence\n\n- **Name:** A & B\n\n## Actions\n\n1. Verify records.')
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf), 1000)
