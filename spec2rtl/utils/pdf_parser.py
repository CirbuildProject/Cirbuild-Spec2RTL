"""PDF parsing utility for extracting text and page images from spec documents.

Uses pypdfium2 for both text extraction and page rendering. This supports
the multimodal approach where the Understanding Agent receives both raw
text and visual screenshots of pages containing figures, tables, or
equations.
"""

import logging
from pathlib import Path
from typing import List

import pypdfium2 as pdfium

from spec2rtl.core.exceptions import PDFParsingError

logger = logging.getLogger("spec2rtl.utils.pdf_parser")


class PDFParser:
    """Extracts text and renders page images from PDF specification documents.

    This parser uses pypdfium2 (a binding to Google's PDFium) for reliable
    extraction without heavy native dependencies.

    Example:
        parser = PDFParser()
        pages = parser.extract_text(Path("spec.pdf"))
        images = parser.extract_page_screenshots(Path("spec.pdf"), Path("out/"))
    """

    @staticmethod
    def extract_text(filepath: Path) -> List[str]:
        """Extract text content from each page of a PDF document.

        Args:
            filepath: Absolute path to the PDF file.

        Returns:
            A list of strings, one per page, containing the extracted text.

        Raises:
            PDFParsingError: If the file cannot be opened or parsed.
        """
        if not filepath.exists():
            raise PDFParsingError(f"PDF file not found: {filepath}")

        try:
            doc = pdfium.PdfDocument(str(filepath))
            pages: List[str] = []

            for page_index in range(len(doc)):
                page = doc[page_index]
                textpage = page.get_textpage()
                text = textpage.get_text_range()
                pages.append(text)
                textpage.close()
                page.close()

            doc.close()
            logger.info(
                "Extracted text from %d pages: %s", len(pages), filepath.name
            )
            return pages

        except Exception as exc:
            raise PDFParsingError(
                f"Failed to extract text from {filepath}: {exc}"
            ) from exc

    @staticmethod
    def extract_page_screenshots(
        filepath: Path,
        output_dir: Path,
        scale: float = 2.0,
    ) -> List[Path]:
        """Render each page of a PDF as a PNG image for multimodal input.

        Args:
            filepath: Absolute path to the PDF file.
            output_dir: Directory where rendered PNG images will be saved.
            scale: Rendering scale factor (2.0 = 144 DPI).

        Returns:
            A list of Paths to the generated PNG files.

        Raises:
            PDFParsingError: If the file cannot be opened or rendered.
        """
        if not filepath.exists():
            raise PDFParsingError(f"PDF file not found: {filepath}")

        output_dir.mkdir(parents=True, exist_ok=True)
        image_paths: List[Path] = []

        try:
            doc = pdfium.PdfDocument(str(filepath))

            for page_index in range(len(doc)):
                page = doc[page_index]
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()

                image_name = f"{filepath.stem}_page_{page_index + 1:03d}.png"
                image_path = output_dir / image_name
                pil_image.save(str(image_path))
                image_paths.append(image_path)

                page.close()

            doc.close()
            logger.info(
                "Rendered %d page screenshots to %s",
                len(image_paths),
                output_dir,
            )
            return image_paths

        except Exception as exc:
            raise PDFParsingError(
                f"Failed to render pages from {filepath}: {exc}"
            ) from exc
