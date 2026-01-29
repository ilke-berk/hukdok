import sys
import os
import io
import math
import base64
import tempfile
import uuid
import asyncio
import zipfile
from threading import Lock
# Security: Use defusedxml instead of xml.etree to prevent XML DoS attacks
# (Billion Laughs, Quadratic Blowup, etc.)
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element as XmlElement
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Protocol, Type
from concurrent.futures import ProcessPoolExecutor

# ReportLab Imports
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, TableStyle, Spacer, Image, PageBreak, LongTable, Flowable
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from PIL import Image as PILImage

# Logger Import
try:
    from log_manager import TechnicalLogger
except ImportError:
    class MockLogger:
        @staticmethod
        def log(level, message, data=None):
            import logging
            logging.log(getattr(logging, level, logging.INFO), message)
    TechnicalLogger = MockLogger()

# Constants
if getattr(sys, 'frozen', False):
    BACKEND_DIR = Path(sys.executable).parent
else:
    BACKEND_DIR = Path(__file__).parent
DEFAULT_FONT = 'Times-Roman'
FONT_LOAD_FAILED = False
DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'

# Configuration Constants
DEFAULT_MARGIN_PTS = 42.5
MIN_FONT_SIZE = 8.0
MAX_FONT_SIZE = 72.0
MAX_TEXT_CHUNK_LENGTH = 1000
MAX_INLINE_IMAGE_WIDTH = 450
MAX_INLINE_IMAGE_HEIGHT = 600
DEFAULT_IMAGE_WIDTH = 100
DEFAULT_IMAGE_HEIGHT = 50
MAX_PARAGRAPHS_PER_CELL = 3
MAX_IMAGE_PIXELS = 89478485
MAX_IMAGE_WIDTH = 10000
MAX_IMAGE_HEIGHT = 10000

# Font Registration Logic
try:
    pdfmetrics.registerFont(TTFont('DejaVuSerif', str(BACKEND_DIR / 'fonts' / 'DejaVuSerif.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuSerif-Bold', str(BACKEND_DIR / 'fonts' / 'DejaVuSerif-Bold.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuSerif-Italic', str(BACKEND_DIR / 'fonts' / 'DejaVuSerif-Italic.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVuSerif-BoldItalic', str(BACKEND_DIR / 'fonts' / 'DejaVuSerif-BoldItalic.ttf')))
    
    pdfmetrics.registerFontFamily(
        'DejaVuSerif',
        normal='DejaVuSerif',
        bold='DejaVuSerif-Bold',
        italic='DejaVuSerif-Italic',
        boldItalic='DejaVuSerif-BoldItalic'
    )
    DEFAULT_FONT = 'DejaVuSerif'
    TechnicalLogger.log("INFO", "DejaVu fonts registered successfully")
except Exception as e:
    FONT_LOAD_FAILED = True
    error_msg = f"DejaVu fonts not found: {e}. Font path: {BACKEND_DIR / 'fonts'}"
    if DEV_MODE:
        TechnicalLogger.log("CRITICAL", error_msg)
        raise RuntimeError(f"CRITICAL: DejaVu fonts missing in DEV_MODE. {e}") from e
    else:
        TechnicalLogger.log("ERROR", f"{error_msg}. Falling back to Times-Roman.")
        DEFAULT_FONT = 'Times-Roman'

# --- Helper Functions ---

def validate_image_safety(image_bytes: bytes) -> Optional[PILImage.Image]:
    """Validate image against decompression bombs and excessive dimensions."""
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        width, height = img.size
        total_pixels = width * height
        
        if total_pixels > MAX_IMAGE_PIXELS:
            TechnicalLogger.log("WARNING", f"Blocked decompression bomb: {total_pixels:,} pixels")
            return None
        if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
            TechnicalLogger.log("WARNING", f"Blocked oversized image: {width}x{height}")
            return None
        return img
    except Exception as e:
        TechnicalLogger.log("WARNING", f"Image validation failed: {e}")
        return None

def format_text_styles(text: str, bold: bool, italic: bool, underline: bool) -> str:
    """Apply HTML formatting based on style flags."""
    if bold and italic and underline: return f"<u><b><i>{text}</i></b></u>"
    elif bold and italic: return f"<b><i>{text}</i></b>"
    elif bold and underline: return f"<u><b>{text}</b></u>"
    elif italic and underline: return f"<u><i>{text}</i></u>"
    elif bold: return f"<b>{text}</b>"
    elif italic: return f"<i>{text}</i>"
    elif underline: return f"<u>{text}</u>"
    else: return text

def convert_color(color_value: Optional[str]) -> Optional[colors.Color]:
    """Convert UDF BGR integer color to ReportLab Color."""
    if color_value is None: return None
    try:
        color_int = int(color_value)
        if color_int < 0: color_int = 0xFFFFFFFF + color_int + 1
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        return colors.Color(r/255, g/255, b/255)
    except (ValueError, TypeError): return None

def get_alignment_style(alignment_value: str) -> int:
    """Convert UDF alignment code to ReportLab constant."""
    if alignment_value == "1": return TA_CENTER
    elif alignment_value == "3": return TA_JUSTIFY
    elif alignment_value == "2": return TA_RIGHT
    else: return TA_LEFT

# --- Plugin Architecture ---

class ElementHandler(Protocol):
    """Protocol for UDF element handlers."""
    def handle(self, converter: 'UDFConverter', element: XmlElement) -> List[Flowable]:
        ...

class PluginRegistry:
    """Registry for UDF element handlers (thread-safe)."""
    _handlers: Dict[str, Type[ElementHandler]] = {}
    _handler_instances: Dict[str, ElementHandler] = {}
    _lock = Lock()

    @classmethod
    def register(cls, tag: str, handler: Type[ElementHandler]):
        with cls._lock:
            cls._handlers[tag] = handler

    @classmethod
    def get_handler_instance(cls, tag: str) -> Optional[ElementHandler]:
        """Get singleton handler instance (thread-safe)."""
        if tag not in cls._handler_instances:
            with cls._lock:
                # Double-check locking pattern
                if tag not in cls._handler_instances:
                    handler_cls = cls._handlers.get(tag)
                    if handler_cls:
                        cls._handler_instances[tag] = handler_cls()
        return cls._handler_instances.get(tag)

class ParagraphHandler:
    """Handler for <paragraph> elements."""
    
    def handle(self, converter: 'UDFConverter', para_elem: XmlElement) -> List[Flowable]:
        # Alignment
        align = get_alignment_style(para_elem.get('Alignment', '0'))
        
        # Spacing / Indent
        line_spacing = float(para_elem.get('LineSpacing', '1.2'))
        if line_spacing < 0.1: line_spacing = 1.0 # Fix weird values
        
        size = float(para_elem.get('size', '12'))
        size = max(MIN_FONT_SIZE, min(size, MAX_FONT_SIZE))
        
        style = ParagraphStyle(
            f'Style_{uuid.uuid4().hex[:8]}',
            parent=converter.base_style,
            alignment=align,
            leftIndent=float(para_elem.get('LeftIndent', '0')),
            rightIndent=float(para_elem.get('RightIndent', '0')),
            firstLineIndent=float(para_elem.get('FirstLineIndent', '0')),
            fontSize=size,
            leading=size * max(1.0, line_spacing)
        )
        
        paragraphs = []
        images = []
        current_text = ""
        
        for child in para_elem:
            chunk = ""
            if child.tag == 'content':
                chunk = self._process_text_node(converter, child, style)
            elif child.tag == 'field':
                chunk = self._process_field_node(converter, child)
            elif child.tag == 'space':
                chunk = ' '
            elif child.tag == 'image':
                img = self._process_inline_image(child)
                if img:
                    if current_text:
                        paragraphs.append(Paragraph(current_text, style))
                        current_text = ""
                    images.append(img)
                else:
                    chunk = "[GÖRSEL]"
            
            if len(current_text) + len(chunk) > MAX_TEXT_CHUNK_LENGTH:
                paragraphs.append(Paragraph(current_text, style))
                current_text = chunk
            else:
                current_text += chunk
        
        if current_text:
            paragraphs.append(Paragraph(current_text, style))
            
        return paragraphs + images

    def _process_text_node(self, converter: 'UDFConverter', node: XmlElement, current_style: ParagraphStyle) -> str:
        """Process content text node with styling (immutable)."""
        start = int(node.get('startOffset', '0'))
        length = int(node.get('length', '0'))
        text = converter.content_text[start:start+length]
        
        # Note: We don't mutate current_style here
        # Color changes should be handled via inline HTML if needed
        
        return format_text_styles(
            text,
            node.get('bold') == 'true',
            node.get('italic') == 'true',
            node.get('underline') == 'true'
        )

    def _process_field_node(self, converter: 'UDFConverter', node: XmlElement) -> str:
        """Process field node."""
        text = node.get('fieldName', '')
        if node.get('startOffset'):
            start = int(node.get('startOffset'))
            length = int(node.get('length'))
            text = converter.content_text[start:start+length]
            
        return format_text_styles(
            text,
            node.get('bold') == 'true',
            node.get('italic') == 'true',
            node.get('underline') == 'true'
        )

    def _process_inline_image(self, node: XmlElement) -> Optional[Image]:
        """Process inline image with proper error handling."""
        data = node.get('imageData')
        if not data: return None
        
        try:
            raw = base64.b64decode(data)
            pil = validate_image_safety(raw)
            if not pil: return None
            
            img = Image(io.BytesIO(raw))
            
            # Resize logic
            w = getattr(img, 'drawWidth', DEFAULT_IMAGE_WIDTH)
            h = getattr(img, 'drawHeight', DEFAULT_IMAGE_HEIGHT)
            
            if w > MAX_INLINE_IMAGE_WIDTH or h > MAX_INLINE_IMAGE_HEIGHT:
                ratio = min(MAX_INLINE_IMAGE_WIDTH/w, MAX_INLINE_IMAGE_HEIGHT/h)
                img.drawWidth = w * ratio
                img.drawHeight = h * ratio
            
            return img
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Inline image processing failed: {e}")
            return None

class TableHandler:
    """Handler for <table> elements."""
    
    def handle(self, converter: 'UDFConverter', table_elem: XmlElement) -> List[Flowable]:
        rows = table_elem.findall('row')
        table_data = []
        
        # We need to process paragraph elements inside cells
        # Since logic is in ParagraphHandler, we can instantiate it or call converter method if we kept it
        # But better to use the handler directly or via registry if we treat internal paragraphs as elements
        # For simplicity in this refactor, we instantiate ParagraphHandler directly here as a helper
        para_handler = ParagraphHandler()

        for row in rows:
            row_items = []
            cells = row.findall('cell')
            for cell in cells:
                cell_content = []
                for p in cell.findall('paragraph'):
                    cell_content.extend(para_handler.handle(converter, p))
                row_items.append(cell_content if cell_content else [Paragraph("", converter.base_style)])
            
            # Optimization: Check if split needed
            needs_split = False
            max_len = 0
            for cell in row_items:
                if len(cell) > MAX_PARAGRAPHS_PER_CELL:
                    needs_split = True
                    max_len = max(max_len, len(cell))
                elif len(cell) > max_len:
                    max_len = len(cell)
            
            if needs_split:
                splits = math.ceil(max_len / MAX_PARAGRAPHS_PER_CELL)
                for i in range(splits):
                    new_row = []
                    start = i * MAX_PARAGRAPHS_PER_CELL
                    end = start + MAX_PARAGRAPHS_PER_CELL
                    for cell in row_items:
                        if start < len(cell):
                            new_row.append(cell[start:end] or [Paragraph("", converter.base_style)])
                        else:
                            new_row.append([Paragraph("", converter.base_style)])
                    table_data.append(new_row)
            else:
                table_data.append(row_items)

        # Style Logic
        col_count = int(table_elem.get('columnCount', '1'))
        col_spans = table_elem.get('columnSpans', '').split(',')
        col_widths = None
        if len(col_spans) == col_count:
             try: 
                 col_widths = [float(x) for x in col_spans]
             except (ValueError, TypeError) as e:
                 TechnicalLogger.log("WARNING", f"Invalid column widths: {e}")

        t_style = [
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3)
        ]
        
        border = table_elem.get('border', 'borderCell')
        if border in ['borderCell', 'border']:
            t_style.append(('GRID', (0,0), (-1,-1), 1, colors.black))
        elif border == 'borderOuter':
            t_style.append(('BOX', (0,0), (-1,-1), 1, colors.black))

        t = LongTable(table_data, colWidths=col_widths, splitByRow=1)
        t.setStyle(TableStyle(t_style))
        return [t]

class PageBreakHandler:
    """Handler for <page-break> elements."""
    def handle(self, converter: 'UDFConverter', elem: XmlElement) -> List[Flowable]:
        return [PageBreak()]

# Register Default Plugins
PluginRegistry.register('paragraph', ParagraphHandler)
PluginRegistry.register('table', TableHandler)
PluginRegistry.register('page-break', PageBreakHandler)

# --- Main Converter Class ---

# Module-level executor for proper async support
_process_executor = None

def get_process_executor():
    """Lazy initialization of ProcessPoolExecutor."""
    global _process_executor
    if _process_executor is None:
        from concurrent.futures import ProcessPoolExecutor
        _process_executor = ProcessPoolExecutor(max_workers=2)
    return _process_executor

class UDFConverter:
    def __init__(self, udf_path: str, output_path: str):
        self.udf_path = udf_path
        self.output_path = output_path
        self.root = None
        self.content_text = ""
        self.pdf_elements = []
        self.header_paragraphs = []
        self.footer_paragraphs = []
        self.bg_image = None
        self.margins = {
            'left': DEFAULT_MARGIN_PTS,
            'right': DEFAULT_MARGIN_PTS,
            'top': DEFAULT_MARGIN_PTS,
            'bottom': DEFAULT_MARGIN_PTS
        }
        self.base_style = None

    def convert(self) -> str:
        """Main execution flow (Synchronous)."""
        self._check_fonts()
        self._parse_xml()
        self._extract_global_content()
        self._setup_page_properties()
        self._setup_styles()
        self._process_elements()
        self._build_pdf()
        self._cleanup()
        return self.output_path

    async def convert_async(self) -> str:
        """Asynchronous execution flow using ProcessPoolExecutor.
        
        Note: CPU-bound PDF generation requires ProcessPool, not ThreadPool.
        ProcessPoolExecutor bypasses GIL for true parallelism.
        """
        loop = asyncio.get_running_loop()
        # Use ProcessPoolExecutor for CPU-bound work
        executor = get_process_executor()
        return await loop.run_in_executor(executor, self.convert)

    def _check_fonts(self):
        """Fail fast in DEV_MODE if fonts are broken."""
        if FONT_LOAD_FAILED and DEFAULT_FONT == 'Times-Roman':
            msg = "WARNING: Degraded font support. Turkish chars will likely break."
            TechnicalLogger.log("WARNING", msg)
            if DEV_MODE:
                raise RuntimeError("CRITICAL: Broken fonts in DEV_MODE.")

    def _parse_xml(self):
        """Parse UDF file (ZIP or XML)."""
        if not os.path.exists(self.udf_path):
            raise FileNotFoundError(f"UDF file not found: {self.udf_path}")
            
        try:
            with open(self.udf_path, 'rb') as f:
                magic = f.read(4)
                f.seek(0)
                if magic[:2] == b'PK': # ZIP
                    with zipfile.ZipFile(f, 'r') as z:
                        with z.open('content.xml') as content_file:
                            tree = ET.parse(content_file, parser=ET.XMLParser(encoding='utf-8'))
                            self.root = tree.getroot()
                else: # XML
                    tree = ET.parse(f, parser=ET.XMLParser(encoding='utf-8'))
                    self.root = tree.getroot()
        except Exception as e:
            raise ValueError(f"Failed to parse UDF file: {e}")

        if self.root is None:
            raise ValueError("Parsed XML root is None.")

    def _extract_global_content(self):
        """Extract global text content for indexing."""
        content_elem = self.root.find('content')
        if content_elem is None:
            raise ValueError("'content' element not found in XML.")
        
        text = content_elem.text or ""
        if text.startswith('<![CDATA[') and text.endswith(']]>'):
            text = text[9:-3]
        self.content_text = text

    def _setup_page_properties(self):
        """Extract margins and background image."""
        props = self.root.find('properties')
        if props:
            fmt = props.find('pageFormat')
            if fmt:
                for key in ['leftMargin', 'rightMargin', 'topMargin', 'bottomMargin']:
                    key_map = key.replace('Margin', '')
                    self.margins[key_map] = float(fmt.get(key, str(DEFAULT_MARGIN_PTS)))
            
            # Background Image
            bg = props.find('bgImage')
            if bg is not None:
                self._process_background_image(bg.get('bgImageData'), bg.get('bgImageSource'))

    def _process_background_image(self, data, source):
        """Process background image with security checks."""
        # Note: Same logic as previous global function, moved here
        if data:
            try:
                raw = base64.b64decode(data)
                pil = validate_image_safety(raw)
                if pil:
                    self.bg_image = Image(io.BytesIO(raw))
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Bg image error: {e}")
        elif source:
            try:
                out_dir = os.path.dirname(os.path.abspath(self.output_path))
                clean_path = os.path.normpath(source.replace('/resources/', '').replace('\\resources\\', ''))
                full_path = os.path.abspath(os.path.join(out_dir, clean_path))
                
                # Path Traversal Check
                if os.path.commonpath([out_dir, full_path]) == out_dir and os.path.exists(full_path):
                     self.bg_image = Image(full_path)
                else:
                    TechnicalLogger.log("WARNING", f"Blocked path traversal: {source}")
            except Exception as e:
                TechnicalLogger.log("WARNING", f"Bg source error: {e}")

    def _setup_styles(self):
        """Initialize ReportLab styles."""
        styles = getSampleStyleSheet()
        self.base_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=DEFAULT_FONT,
            encoding='utf-8'
        )

    def _process_elements(self):
        """Iterate over document elements using Plugin System."""
        elements_elem = self.root.find('elements')
        if elements_elem is None: raise ValueError("No 'elements' found.")
        
        # Get singleton handler instances for better performance
        para_handler = PluginRegistry.get_handler_instance('paragraph')

        # Header/Footer - filter out non-Paragraph flowables
        header = elements_elem.find('header')
        if header and para_handler:
            for p in header.findall('paragraph'):
                flowables = para_handler.handle(self, p)
                # Only add Paragraph objects to avoid wrap() issues
                for f in flowables:
                    if isinstance(f, Paragraph):
                        self.header_paragraphs.append(f)
        
        footer = elements_elem.find('footer')
        if footer and para_handler:
            for p in footer.findall('paragraph'):
                flowables = para_handler.handle(self, p)
                # Only add Paragraph objects to avoid wrap() issues
                for f in flowables:
                    if isinstance(f, Paragraph):
                        self.footer_paragraphs.append(f)

        # Body
        body = elements_elem.find('body')
        target = body if body is not None else elements_elem
        
        for elem in target:
            # Use singleton instances for better performance
            handler = PluginRegistry.get_handler_instance(elem.tag)
            
            if handler:
                try:
                    flowables = handler.handle(self, elem)
                    self.pdf_elements.extend(flowables)
                    # Add spacer after paragraphs/tables for better flow
                    if elem.tag in ['paragraph', 'table']:
                         self.pdf_elements.append(Spacer(1, 5))
                except Exception as e:
                    TechnicalLogger.log("ERROR", f"Handler for {elem.tag} failed: {e}")
            else:
                self._handle_unknown_element(elem)

    def _handle_unknown_element(self, elem: XmlElement):
        """Graceful degradation for unknown tags."""
        tag = elem.tag
        TechnicalLogger.log("WARNING", f"Unknown UDF element: <{tag}>")
        try:
            text = ''.join(elem.itertext()).strip()
            if text:
                s = ParagraphStyle('Unknown', parent=self.base_style, textColor=colors.gray, leftIndent=20)
                self.pdf_elements.append(Paragraph(f"[UNKNOWN: {tag}] {text}", s))
                self.pdf_elements.append(Spacer(1, 5))
        except Exception as e:
            TechnicalLogger.log("WARNING", f"Failed to process unknown element <{tag}>: {e}")

    def _build_pdf(self):
        """Generate final PDF."""
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=A4,
            leftMargin=self.margins['left'],
            rightMargin=self.margins['right'],
            topMargin=self.margins['top'],
            bottomMargin=self.margins['bottom']
        )
        
        def on_page(canvas, doc):
            canvas.saveState()
            # Header
            for i, p in enumerate(self.header_paragraphs):
                # Simple header positioning
                w, h = p.wrap(doc.width, doc.topMargin)
                p.drawOn(canvas, doc.leftMargin, doc.height + doc.topMargin - 15 - i*h)
            # Footer
            for i, p in enumerate(self.footer_paragraphs):
                # Simple footer positioning
                w, h = p.wrap(doc.width, doc.bottomMargin)
                p.drawOn(canvas, doc.leftMargin, doc.bottomMargin - 15 - i*h)
            # Bg
            if self.bg_image:
                canvas.saveState()
                canvas.setFillAlpha(0.1)
                # Note: simplified bg logic
                if hasattr(self.bg_image, 'drawOn'):
                     self.bg_image.drawOn(canvas, 0, 0)
                canvas.restoreState()
            canvas.restoreState()

        doc.build(self.pdf_elements, onFirstPage=on_page, onLaterPages=on_page)
        TechnicalLogger.log("INFO", f"PDF created: {self.output_path}")

    def _cleanup(self):
        """Clear large data structures to aid garbage collection."""
        self.pdf_elements = None
        self.content_text = None
        self.root = None

def convert_udf_to_pdf(udf_path: str, output_path: Optional[str] = None) -> str:
    """Wrapper function for synchronous conversion."""
    if output_path is None:
        temp = tempfile.gettempdir()
        output_path = os.path.join(temp, f"udf_{uuid.uuid4().hex[:8]}.pdf")
        
    converter = UDFConverter(udf_path, output_path)
    return converter.convert()

async def convert_udf_to_pdf_async(udf_path: str, output_path: Optional[str] = None) -> str:
    """Wrapper function for asynchronous conversion."""
    if output_path is None:
        temp = tempfile.gettempdir()
        output_path = os.path.join(temp, f"udf_{uuid.uuid4().hex[:8]}.pdf")
    
    converter = UDFConverter(udf_path, output_path)
    return await converter.convert_async()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("UDFConverterCLI")
        try:
            # Sync mode CLI
            res = convert_udf_to_pdf(sys.argv[1], sys.argv[1].replace('.udf','.pdf'))
            logger.info(f"Success: {res}")
        except Exception as e:
            logger.error(f"Error: {e}")
