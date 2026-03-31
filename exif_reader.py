# exif_reader.py --- A simple EXIF reader for JPEG images.

from PIL import ExifTags
from datetime import datetime
import re

def get_exif_datetime(image):
    try:
        exif = image._getexif()
        if not exif:
            return None

        exif_data = {
            ExifTags.TAGS.get(tag): value
            for tag, value in exif.items()
            if tag in ExifTags.TAGS
        }

        dt = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
        if dt:
            return datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
    except:
        return None

    return None


def get_datetime_from_filename(filename):
    try:
        match = re.search(r"(\d{4}-\d{2}-\d{2}) at (\d{2})\.(\d{2})\.(\d{2})", filename)
        if match:
            dt_str = f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4)}"
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None

    return None