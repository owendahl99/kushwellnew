import os
import qrcode

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = os.path.join(UPLOAD_FOLDER, "qr_codes")
os.makedirs(QR_FOLDER, exist_ok=True)


def generate_qr_code(product_id):
    qr_data = f"https://yourdomain.com/products/{product_id}"
    filename = f"{product_id}.png"
    file_path = os.path.join(QR_FOLDER, filename)
    img = qrcode.make(qr_data)
    img.save(file_path)

    return f"/{QR_FOLDER}/{filename}"


