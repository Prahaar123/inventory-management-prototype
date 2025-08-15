# barcode_generator.py
import os
from datetime import datetime

# Try to import barcode & ImageWriter; handle absence gracefully
try:
    import barcode
    from barcode.writer import ImageWriter
    HAS_BARCODE_LIB = True
except Exception:
    HAS_BARCODE_LIB = False

def generate_unique_barcode(prefix="INV"):
    """
    Timestamp-based unique barcode string.
    Example: INV250810123045123456
    """
    ts = datetime.now().strftime("%y%m%d%H%M%S%f")
    return f"{prefix}{ts}"

def generate_barcode_image(code_str: str, save_path="barcodes"):
    """
    Generate a Code128 barcode PNG and return the saved file path.
    If python-barcode or pillow not installed, raise an informative error.
    """
    if not HAS_BARCODE_LIB:
        raise RuntimeError("python-barcode and pillow are required to generate barcode images. Install with: pip install python-barcode pillow")

    os.makedirs(save_path, exist_ok=True)
    CODE128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    barcode_obj = CODE128(code_str, writer=writer)
    filename = os.path.join(save_path, code_str)  # .png appended by save()
    file_path = barcode_obj.save(filename)
    return file_path

# quick test when run directly
if __name__ == "__main__":
    code = generate_unique_barcode()
    print("Generated code:", code)
    if HAS_BARCODE_LIB:
        p = generate_barcode_image(code)
        print("Saved at:", p)
    else:
        print("Barcode libs not installed; install python-barcode and pillow to generate images.")
