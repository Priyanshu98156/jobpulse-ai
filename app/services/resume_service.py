from pathlib import Path
from pypdf import PdfReader
import logging

logger = logging.getLogger(__name__)

class ResumeService:
    @staticmethod
    def extract_text_from_pdf(file_path: Path) -> str:
        """Extract text cleanly from a PDF resume file."""
        try:
            reader = PdfReader(str(file_path))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            extracted = "\n".join(text_parts).strip()
            return extracted
        except Exception as e:
            logger.error(f"Error parsing PDF resume at {file_path}: {e}")
            return ""

resume_service = ResumeService()

