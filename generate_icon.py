"""
Generates the modern high-resolution icon for Driver Finder.
"""
import os
import struct

def generate_icon(dest_path):
    width = 48
    height = 48
    
    # 48x48 32-bit RGBA icon
    pixels = bytearray()
    
    for y in range(height):
        for x in range(width):
            dx = x - 23.5
            dy = (height - 1 - y) - 23.5
            dist = (dx * dx + dy * dy) ** 0.5
            
            # Outer circular badge
            if dist <= 22.0:
                if 19.5 <= dist <= 22.0:
                    # Royal Blue Accent Border (#1D4ED8)
                    b, g, r, a = 216, 78, 29, 255
                elif dist > 18.0:
                    # Cyan Ring (#0284C7)
                    b, g, r, a = 199, 132, 2, 255
                elif abs(dx) <= 12 and abs(dy) <= 12:
                    # Central processor chip (#0F172A dark slate)
                    if abs(dx) == 12 or abs(dy) == 12:
                        # Chip border (#38BDF8)
                        b, g, r, a = 248, 189, 56, 255
                    elif abs(dx) <= 2 or abs(dy) <= 2:
                        # Circuit bus center cross (#38BDF8)
                        b, g, r, a = 248, 189, 56, 255
                    elif (abs(dx) % 4 == 0) and (abs(dy) % 4 == 0):
                        # Chip pins (#60A5FA)
                        b, g, r, a = 250, 165, 96, 255
                    else:
                        # Chip body (#1E293B)
                        b, g, r, a = 59, 41, 30, 255
                else:
                    # Inner circle gradient / radar glow (#0369A1)
                    b, g, r, a = 161, 105, 3, 255
            else:
                # Transparent outside
                b, g, r, a = 0, 0, 0, 0
                
            pixels.extend([b, g, r, a])
            
    # AND mask (1 bit per pixel, 48*48 / 8 = 288 bytes)
    and_mask = bytearray(288)
    
    # BMP Info Header (40 bytes)
    bih = struct.pack(
        '<IIIHHIIIIII',
        40,          # biSize
        width,       # biWidth
        height * 2,  # biHeight (double for ICO format)
        1,           # biPlanes
        32,          # biBitCount
        0,           # biCompression (BI_RGB)
        len(pixels) + len(and_mask),
        0, 0, 0, 0
    )
    
    image_data = bih + pixels + and_mask
    icondir = struct.pack('<HHH', 0, 1, 1)
    direntry = struct.pack(
        '<BBBBHHII',
        width,
        height,
        0,
        0,
        1,
        32,
        len(image_data),
        6 + 16
    )
    
    with open(dest_path, 'wb') as f:
        f.write(icondir + direntry + image_data)

if __name__ == '__main__':
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_icon.ico')
    generate_icon(target)
    print("Generated:", target)
