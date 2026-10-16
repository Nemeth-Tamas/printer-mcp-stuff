"""Render Unicode to ESC/POS bitmap, then send as a RAW Windows print job."""
import os
from threading import Lock
from PIL import Image, ImageDraw, ImageFont

LOCK = Lock()
WIDTH = int(os.getenv("PRINT_WIDTH_DOTS", "576"))
MAX_HEIGHT = 12000

def _font():
    for path in (os.getenv("PRINT_FONT", ""), r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if path:
            try:
                return ImageFont.truetype(path, 26)
            except OSError:
                pass
    return ImageFont.load_default()

def render_text(text: str):
    if len(text) > 12000:
        raise ValueError("Text too long")
    font = _font()
    img = Image.new("L", (WIDTH, MAX_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    margin, y = 12, 12
    for paragraph in text.split("\n"):
        line = ""
        words = paragraph.split(" ")
        lines = []
        for word in words:
            candidate = (line + " " + word).strip()
            if draw.textbbox((0, 0), candidate or " ", font=font)[2] <= WIDTH - 2 * margin:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
        for item in lines:
            if draw.textbbox((0, 0), item or " ", font=font)[2] > WIDTH - 2 * margin:
                raise ValueError("Word exceeds print width")
            height = max(30, draw.textbbox((0, 0), item or " ", font=font)[3] + 12)
            if y + height + margin > MAX_HEIGHT:
                raise ValueError("Receipt too long")
            draw.text((margin, y), item, font=font, fill=0)
            y += height
    return img.crop((0, 0, WIDTH, max(64, y + 22)))

def raster_bytes(image):
    image = image.convert("1")
    width, height = image.size
    byte_width = (width + 7) // 8
    data = bytearray()
    pix = image.load()
    for y in range(height):
        for xbyte in range(byte_width):
            value = 0
            for bit in range(8):
                x = xbyte * 8 + bit
                if x < width and pix[x, y] == 0:
                    value |= 128 >> bit
            data.append(value)
    return b"\x1d\x76\x30\x00" + bytes((byte_width & 255, byte_width >> 8, height & 255, height >> 8)) + data

def list_printers():
    import win32print
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]

def print_text(text, cut=True, beep=False):
    import win32print
    name = os.getenv("PRINTER_NAME")
    if not name:
        raise ValueError("PRINTER_NAME not configured")
    content = b"\x1b\x40" + raster_bytes(render_text(text)) + b"\n\n\n"
    if beep:
        content += b"\x1b\x42\x02\x02"
    if cut:
        content += b"\x1d\x56\x00"
    with LOCK:
        h = win32print.OpenPrinter(name)
        try:
            job = win32print.StartDocPrinter(h, 1, ("Echo Birch receipt", None, "RAW"))
            try:
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, content)
                win32print.EndPagePrinter(h)
            finally:
                win32print.EndDocPrinter(h)
            return job
        finally:
            win32print.ClosePrinter(h)
