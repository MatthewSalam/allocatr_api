import qrcode
import json
import hmac
import hashlib
import base64
from io import BytesIO
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

def generate_qr_code(student_id: int, allocation_id: int) -> dict:
    """
    Generate QR code with HMAC signature for security
    Args:
        student_id: ID of the student
        allocation_id: ID of the allocation
    
    Returns:
        dict containing:
        - qr_string: JSON string with data
        - signature: HMAC signature
        - qr_image: Base64 encoded QR image
    """
    # Step 1: Create the data to put in QR code
    qr_data = {
        "student_id": student_id,
        "allocation_id": allocation_id,
        "timestamp": int(datetime.utcnow().timestamp())
    }
    
    logger.info(f"Generating QR code for student {student_id}, allocation {allocation_id}")
    
    # Step 2: Create HMAC signature (security feature)
    data_string = json.dumps(qr_data, sort_keys=True)
    # EXPLANATION: Convert dict to JSON string, sort_keys=True ensures same order always
    
    secret_key = os.getenv("QR_SECRET")
    
    signature = hmac.new(
        secret_key.encode(),  # Convert string to bytes
        data_string.encode(),  # Convert JSON string to bytes
        hashlib.sha256  # Use SHA256 hashing algorithm
    ).hexdigest()
    # EXPLANATION: Creates a unique signature from the data using secret key
    # hexdigest() converts to readable hex string like "a1b2c3d4..."
    
    logger.debug(f"Generated HMAC signature: {signature[:20]}...")
    
    # Step 3: Add signature to the data
    qr_data['signature'] = signature
    qr_string = json.dumps(qr_data)
    # EXPLANATION: Now QR contains: student_id, allocation_id, timestamp, AND signature
    
    # Step 4: Generate the actual QR code image
    qr = qrcode.QRCode(
        version=1,  # Size of QR code (1-40, 1 is smallest)
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # Highest error correction
        box_size=10,  # Size of each box in pixels
        border=4,  # Border size (minimum is 4)
    )
    
    qr.add_data(qr_string)
    # EXPLANATION: Put our JSON string into the QR code
    
    qr.make(fit=True)
    # EXPLANATION: Optimize QR size to fit the data
    
    # Step 5: Create the image
    img = qr.make_image(fill_color="black", back_color="white")
    # EXPLANATION: Black squares on white background (standard QR colors)
    
    # Step 6: Convert image to Base64 string
    buffered = BytesIO()
    # EXPLANATION: Create temporary memory buffer to hold image
    
    img.save(buffered, format="PNG")
    # EXPLANATION: Save image as PNG into the buffer
    
    img_bytes = buffered.getvalue()
    # EXPLANATION: Get the image data as bytes
    
    img_str = base64.b64encode(img_bytes).decode()
    # EXPLANATION: Convert bytes to base64 string (safe for JSON/databases)
    
    qr_image_base64 = f"data:image/png;base64,{img_str}"
    # EXPLANATION: Add data URI prefix so browsers can display it directly
    # Format: data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...
    
    logger.info(f"✓ QR code generated successfully (size: {len(img_str)} chars)")
    
    return {
        "qr_string": qr_string,
        "signature": signature,
        "qr_image": qr_image_base64
    }

def verify_qr_code(qr_data_string: QRPayload) -> dict:
    """
    Verify QR code signature to check if it's authentic

    Args:
        qr_data_string: Parsed QR payload from scanned QR code

    Returns:
        dict containing:
        - valid: True/False
        - student_id: if valid
        - allocation_id: if valid
        - error: if invalid
    """

    try:
        # Step 1: Convert Pydantic model to Python dict
        qr_data = qr_data_string.model_dump()
        # EXPLANATION: Convert QRPayload object to normal Python dict

        # Step 2: Extract the signature
        received_signature = qr_data.pop('signature')
        # EXPLANATION: Remove signature from dict (pop = remove and return)

        # Step 3: Recalculate what signature SHOULD be
        data_string = json.dumps(qr_data, sort_keys=True)
        secret_key = os.getenv("QR_SECRET")

        expected_signature = hmac.new(
            secret_key.encode(),
            data_string.encode(),
            hashlib.sha256
        ).hexdigest()
        # EXPLANATION: Calculate signature using same method as generation

        # Step 4: Compare signatures
        if not hmac.compare_digest(received_signature, expected_signature):
            logger.warning("QR code verification FAILED - Invalid signature")
            return {
                "valid": False,
                "error": "Invalid QR code signature - may be forged"
            }

        # Step 5: Check timestamp (optional - prevent old QR codes)
        timestamp = qr_data.get('timestamp')
        current_time = int(datetime.utcnow().timestamp())
        age_hours = (current_time - timestamp) / 3600

        if age_hours > 24 * 365:  # Older than 1 year
            logger.warning(f"QR code is very old: {age_hours/24:.0f} days")

        logger.info("✓ QR code verified successfully")

        return {
            "valid": True,
            "student_id": qr_data['student_id'],
            "allocation_id": qr_data['allocation_id'],
            "timestamp": qr_data['timestamp']
        }

    except KeyError as e:
        logger.error(f"QR code verification FAILED - Missing field: {e}")
        return {
            "valid": False,
            "error": f"Invalid QR code - missing required field: {e}"
        }
    except Exception as e:
        logger.error(f"QR code verification FAILED - {e}")
        return {
            "valid": False,
            "error": f"QR code verification error: {str(e)}"
        }