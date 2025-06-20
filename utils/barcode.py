import barcode
import os
from barcode.writer import ImageWriter

def generate_barcode(data, filename=None, folder='static/barcodes'):
    if not os.path.exists(folder):
        os.makedirs(folder)

    # Use Code128 because it supports letters and numbers
    code128 = barcode.get('code128', data, writer=ImageWriter())

    if not filename:
        filename = f"{data}.png"
    filepath = os.path.join(folder, filename)
    
    code128.save(filepath.replace('.png', ''))  # `save()` auto-appends `.png`
    
    return filepath