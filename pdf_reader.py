"""In-memory PDF reading for document intake. No disk writes."""
import io
import pymupdf
from PIL import Image


def read_pdf_pages(pdf_bytes, max_pages=5):
    """Return page text and rendered PIL images, capped at max_pages."""
    pages = []
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as pdf:
        if pdf.needs_pass:
            raise ValueError('Password-protected PDFs are not supported.')
        if len(pdf) == 0:
            raise ValueError('The PDF contains no pages.')
        if len(pdf) > max_pages:
            raise ValueError(f'PDF exceeds the {max_pages}-page limit.')
        for page in pdf:
            if page.rect.width * page.rect.height > 2_000_000:
                raise ValueError('PDF page dimensions are too large.')
            text = page.get_text('text').strip()
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            if pix.width * pix.height > 24_000_000:
                raise ValueError('Rendered PDF page is too large.')
            img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            pages.append({'page_number': page.number + 1, 'text': text, 'image': img})
    return pages
