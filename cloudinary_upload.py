# cloudinary_upload.py --- A simple script to upload images to Cloudinary.

import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_image(file, filename=None):
    try:
        file.seek(0)

        result = cloudinary.uploader.upload(
            file,
            public_id=f"cashcapture/{filename}" if filename else None,
            overwrite=True,
            resource_type="image"
        )

        return result["secure_url"]

    except Exception:
        return None