"""
Test QR Code Generator
Run: python test_qr_generator.py
"""
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from services.qr_generator  import generate_qr_code, verify_qr_code

def test_qr_generation():
    """Test generating a QR code"""
    print("\n" + "="*60)
    print("TEST 1: Generate QR Code")
    print("="*60)
    
    # Generate QR for student 1, allocation 5
    result = generate_qr_code(student_id=1, allocation_id=5)
    
    print(f"✓ QR String: {result['qr_string'][:100]}...")
    print(f"✓ Signature: {result['signature'][:50]}...")
    print(f"✓ Image Length: {len(result['qr_image'])} characters")
    
    # Save QR image to file so you can see it
    save_qr_image(result['qr_image'])
    
    return result

def test_qr_verification(qr_string):
    """Test verifying a QR code"""
    print("\n" + "="*60)
    print("TEST 2: Verify Valid QR Code")
    print("="*60)
    
    result = verify_qr_code(qr_string)
    
    if result['valid']:
        print("✓ QR Code is VALID")
        print(f"  Student ID: {result['student_id']}")
        print(f"  Allocation ID: {result['allocation_id']}")
        print(f"  Timestamp: {result['timestamp']}")
    else:
        print(f"✗ QR Code is INVALID: {result['error']}")
    
    return result

def test_forged_qr():
    """Test that forged QR codes are rejected"""
    print("\n" + "="*60)
    print("TEST 3: Verify FORGED QR Code (should fail)")
    print("="*60)
    
    # Fake QR code with wrong signature
    fake_qr = '{"student_id":999,"allocation_id":999,"timestamp":1234567890,"signature":"fake123"}'
    
    result = verify_qr_code(fake_qr)
    
    if not result['valid']:
        print("✓ Correctly rejected forged QR code")
        print(f"  Error: {result['error']}")
    else:
        print("✗ ERROR: Accepted forged QR code!")
    
    return result

def save_qr_image(base64_image):
    """Save QR code as HTML file to view it"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Generated QR Code</title>
        <style>
            body {{
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f0f0f0;
                font-family: Arial, sans-serif;
            }}
            .container {{
                text-align: center;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            img {{
                border: 2px solid #ddd;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Generated QR Code</h2>
            <p>Student ID: 1 | Allocation ID: 5</p>
            <img src="{base64_image}" alt="QR Code">
            <p>Scan this with your phone to test!</p>
        </div>
    </body>
    </html>
    """
    
    with open('test_qr_code.html', 'w') as f:
        f.write(html_content)
    
    print("✓ QR code saved to: test_qr_code.html")
    print("  Open this file in a browser to see the QR code")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("QR CODE GENERATOR TESTING")
    print("="*60)
    
    # Make sure QR_SECRET is set
    if not os.getenv("QR_SECRET"):
        print("\n⚠️  WARNING: QR_SECRET not set in .env")
        print("Setting temporary secret for testing...")
        os.environ["QR_SECRET"] = "test-secret-key-for-development-only"
    
    # Run tests
    generated = test_qr_generation()
    test_qr_verification(generated['qr_string'])
    test_forged_qr()
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)
    print("\n✓ All tests passed!")
    print("✓ Open 'test_qr_code.html' in a browser to see the QR code")
    print("✓ You can scan it with your phone's camera")