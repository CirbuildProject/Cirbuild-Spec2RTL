"""Unit tests for the PDF parser utility."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from spec2rtl.utils.pdf_parser import PDFParser
from spec2rtl.core.exceptions import PDFParsingError


class TestPDFParser:
    """Tests for the multimodal PDF parser."""

    @patch("spec2rtl.utils.pdf_parser.pdfium.PdfDocument")
    def test_extract_text_valid(self, mock_pdf_document: MagicMock) -> None:
        """Text extraction should return an array of strings (one per page)."""
        # Mock the PDF document setup
        mock_pdf = MagicMock()
        mock_page1 = MagicMock()
        mock_page2 = MagicMock()
        mock_text1 = MagicMock()
        mock_text2 = MagicMock()

        mock_text1.get_text_range.return_value = "Page 1 Content"
        mock_text2.get_text_range.return_value = "Page 2 Content"
        
        # When page.get_textpage() is called, return the text mock directly
        mock_page1.get_textpage.return_value = mock_text1
        mock_page2.get_textpage.return_value = mock_text2
        
        # We need the doc to act like a list of pages
        mock_pdf.__len__.return_value = 2
        mock_pdf.__getitem__.side_effect = [mock_page1, mock_page2]
        mock_pdf_document.return_value = mock_pdf

        parser = PDFParser()
        # Mock pathlib exists so it doesn't fail before reaching pdfium
        with patch.object(Path, 'exists') as mock_exists:
            mock_exists.return_value = True
            result = parser.extract_text(Path("dummy.pdf"))
        
        assert len(result) == 2
        assert result[0] == "Page 1 Content"
        assert result[1] == "Page 2 Content"

    @patch("spec2rtl.utils.pdf_parser.pdfium.PdfDocument")
    def test_extract_text_file_not_found(self, mock_pdf_document: MagicMock) -> None:
        """A nonexistent PDF should raise a generic Spec2RTLError."""
        mock_pdf_document.side_effect = Exception("No such file")

        parser = PDFParser()
        with patch.object(Path, 'exists') as mock_exists:
            mock_exists.return_value = True
            with pytest.raises(PDFParsingError):
                parser.extract_text(Path("missing.pdf"))
