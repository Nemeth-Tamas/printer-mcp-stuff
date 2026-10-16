"""Unicode thermal receipt rendering and Windows RAW ESC/POS output."""
import os
from threading import Lock
from PIL import Image, ImageDraw, ImageFont

LOCK = Lock()
MAX_HEIGHT = 12000

def width():
    value = int(os.getenv("PRINT_WIDTH_DOTS", "576"))
    if not 128 <= value <= 1024 or value % 8:
        raise ValueError("PRINT_WIDTH_DOTS must be divisible by 8 and between 128 and 1024")
    return value

def _font():
    for path in (os.getenv("PRINT_FONT", ""), r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if path:
            try:
                return ImageFont.truetype(path, 26)
            except OSError:
                pass
    return ImageFont.load_default()

def render_text(text):
    if not text or len(text) > 12000:
        raise ValueError("Text must contain 1-12000 characters")
    font, w = _font(), width()
    image = Image.new("L", (w, MAX_HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    margin, y = 12, 12
    for paragraph in text.split("\n"):
        line, lines = "", []
        for word in paragraph.split(" "):
            candidate = (line + " " + word).strip()
            if draw.textbbox((0, 0), candidate or " ", font=font)[2] <= w - 2 * margin:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        lines.append(line)
        for item in lines:
            if draw.textbbox((0, 0), item or " ", font=font)[2] > w - 2 * margin:
                raise ValueError("A word exceeds printable width")
            height = max(30, draw.textbbox((0, 0), item or " ", font=font)[3] + 12)
            if y + height + margin > MAX_HEIGHT:
                raise ValueError("Receipt too long")
            draw.text((margin, y), item, font=font, fill=0)
            y += height
    return image.crop((0, 0, w, max(64, y + 22)))

def render_qr(data, size=5):
    import qrcode
    if not data or len(data) > 1500:
        raise ValueError("QR content must contain 1-1500 characters")
    if not 2 <= size <= 8:
        raise ValueError("QR module size must be 2-8")
    qr = qrcode.QRCode(border=4, box_size=size, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("L")
    if image.width > width():
        raise ValueError("QR exceeds printable width; reduce module size or content")
    return image

def stack_images(images):
    w = width()
    gap = 12
    height = sum(img.height for img in images) + gap * max(0, len(images)-1)
    if height > MAX_HEIGHT:
        raise ValueError("Receipt too long")
    result = Image.new("L", (w, height), 255)
    y = 0
    for img in images:
        result.paste(img, ((w - img.width)//2, y))
        y += img.height + gap
    return result

def raster_bytes(image):
    image = image.convert("1")
    w, h = image.size
    byte_width = (w + 7) // 8
    if h > 65535:
        raise ValueError("Image too tall")
    pixels = image.load()
    data = bytearray(byte_width * h)
    for y in range(h):
        for x in range(w):
            if pixels[x, y] == 0:
                data[y * byte_width + x // 8] |= (128 >> (x % 8))
    return b"\x1d\x76\x30\x00" + bytes((byte_width & 255, byte_width >> 8, h & 255, h >> 8)) + data

def list_printers():
    import win32print
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]

def print_image(image, cut=True, beep=False):
    import win32print
    name = os.getenv("PRINTER_NAME")
    if not name:
        raise ValueError("PRINTER_NAME not configured")
    feed = int(os.getenv("PRINT_BOTTOM_FEED_LINES", "4"))
    if not 0 <= feed <= 12:
        raise ValueError("PRINT_BOTTOM_FEED_LINES must be between 0 and 12")
    content = b"\x1b\x40" + raster_bytes(image) + b"\n" * feed
    if beep:
        content += b"\x1b\x42\x02\x02"
    if cut:
        content += b"\x1d\x56\x00"
    with LOCK:
        handle = win32print.OpenPrinter(name)
        try:
            job = win32print.StartDocPrinter(handle, 1, ("Echo Birch receipt", None, "RAW"))
            try:
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, content)
                win32print.EndPagePrinter(handle)
            finally:
                win32print.EndDocPrinter(handle)
            try:
                from .history import record
                record(job, name)
            except Exception:
                pass  # Printing must not fail because the optional history log failed.
            return job
        finally:
            win32print.ClosePrinter(handle)

def print_text(text, cut=True, beep=False, urgent=False):
    if urgent:
        beep = True
        header = render_banner("SÜRGŐS!  FONTOS ÉRTESÍTÉS")
        return print_image(stack_images([header, render_text(text)]), cut, beep)
    return print_image(render_text(text), cut, beep)

def render_banner(title):
    w = width()
    img = Image.new("L", (w, 95), 255)
    d = ImageDraw.Draw(img)
    d.rectangle((3, 3, w - 4, 90), outline=0, width=5)
    font = _font()
    bbox = d.textbbox((0, 0), title, font=font)
    d.text(((w - (bbox[2] - bbox[0])) // 2, 28), title, font=font, fill=0)
    return img

def print_qr(data, caption="", size=5, cut=True, beep=False):
    images = [render_text(caption)] if caption else []
    images.append(render_qr(data, size))
    return print_image(stack_images(images), cut, beep)

def print_appointment(customer, starts_at, service, notes="", reference="", cut=True, beep=True, mode="customer", phone=""):
    if mode not in ("customer", "technician"):
        raise ValueError("mode must be customer or technician")
    lines = ["CELLNET KFT.", "IDŐPONTFOGLALÁS", "--------------------------",
             f"Időpont: {starts_at}", f"Szolgáltatás: {service}"]
    if reference:
        lines.append(f"Azonosító: {reference}")
    if mode == "technician":
        lines.extend([f"Ügyfél: {customer}", f"Telefon: {phone or '-'}"])
        if notes:
            lines.extend(["--------------------------", f"Belső megjegyzés: {notes}"])
        lines.append("TECHNIKUS PÉLDÁNY")
    else:
        lines.extend([f"Ügyfél: {customer}", "--------------------------", "ÜGYFÉL PÉLDÁNY"])
    return print_text("\n".join(lines), cut, beep)

def print_custom(blocks, cut=True, beep=False, urgent=False):
    """Structured, printable Unicode blocks; no caller-supplied ESC/POS bytes."""
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 80:
        raise ValueError("Provide 1-80 blocks")
    images = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Each block must be an object")
        kind = block.get("type", "text")
        if kind == "text":
            text = block.get("text", "")
            if not isinstance(text, str) or not 1 <= len(text) <= 3000:
                raise ValueError("Text blocks require 1-3000 characters")
            images.append(render_text(text))
        elif kind == "divider":
            image = Image.new("L", (width(), 24), 255)
            ImageDraw.Draw(image).line((10, 12, width()-10, 12), fill=0, width=2)
            images.append(image)
        elif kind == "qr":
            images.append(render_qr(block.get("data", ""), int(block.get("size", 5))))
        elif kind == "heading":
            title = block.get("text", "")
            if not isinstance(title, str) or not 1 <= len(title) <= 55:
                raise ValueError("Heading must contain 1-55 characters")
            images.append(render_banner(title))
        else:
            raise ValueError("Unsupported block type")
    if urgent:
        images.insert(0, render_banner("SÜRGŐS"))
    return print_image(stack_images(images), cut, beep or urgent)
