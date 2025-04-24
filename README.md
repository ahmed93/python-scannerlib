# Code Scanner Library

A Python library for detecting and processing QR codes and Data Matrix codes using a Raspberry Pi camera.

## Overview

This library provides a simple and robust interface for real-time code detection on Raspberry Pi systems equipped with a camera. It supports multiple detection modes, thread-safe operation, and comprehensive error handling.

## Features

-   **QR Code detection** using the pyzbar library
-   **Data Matrix detection** using the pylibdmtx library
-   **Multiple detection modes**:
    -   Single: Detect one code, then wait for it to be removed
    -   Continuous: Detect codes continuously
    -   Triggered: Only detect when explicitly triggered
-   **Adaptive image processing** for better detection in various lighting conditions
-   **Thread-safe operation** with proper resource management
-   **Comprehensive logging** for debugging and monitoring
-   **Simple callback mechanism** for detection events
-   **Terminal application** for testing and demonstration

## Requirements

-   Raspberry Pi with camera module
-   Python 3.6+
-   libcamera and picamera2 (Raspberry Pi camera interface)
-   OpenCV for image processing
-   pyzbar for QR code detection
-   pylibdmtx for Data Matrix code detection

## Installation

1. Install system dependencies:

```bash
# For Raspberry Pi OS
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv libzbar0 libdmtx0a
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Example

```python
from code_scanner import CodeScanner, DetectionMode
import time

# Define callback function
def on_code_detected(code_info):
    if code_info is None:
        print("Code removed")
    else:
        print(f"Detected {code_info.type} code: {code_info.data}")
        print(f"Position: {code_info.rect}")

# Create scanner
scanner = CodeScanner()

# Start scanner in single mode
scanner.set_mode(DetectionMode.SINGLE)
scanner.start(on_code_detected)

try:
    # Application logic
    print("Waiting for codes...")
    time.sleep(60)  # Run for 60 seconds
finally:
    # Clean up resources
    scanner.stop()
```

### Different Detection Modes

```python
# Single mode: Detect one code, wait for removal, then detect next
scanner.set_mode(DetectionMode.SINGLE)

# Continuous mode: Continuously detect all codes
scanner.set_mode(DetectionMode.CONTINUOUS)

# Triggered mode: Only scan when explicitly triggered
scanner.set_mode(DetectionMode.TRIGGERED)
scanner.trigger_scan()  # Manually trigger a scan
```

### Terminal Application

The library includes a simple terminal application (`scanner_app.py`) for testing and demonstration:

```bash
# Run the terminal application
python scanner_app.py
```

## API Reference

### CodeScanner Class

The main class for code detection.

#### Methods

-   `__init__(logger=None)`: Initialize the scanner with optional custom logger
-   `start(code_callback=None)`: Start code scanning with optional callback
-   `stop()`: Stop scanning and release resources
-   `set_mode(mode)`: Set the detection mode
-   `trigger_scan()`: Manually trigger a scan (for TRIGGERED mode)

#### Detection Modes

-   `DetectionMode.SINGLE`: Detect one code, then wait for removal
-   `DetectionMode.CONTINUOUS`: Continuously detect all codes
-   `DetectionMode.TRIGGERED`: Only scan when manually triggered

### CodeInfo Class

Contains information about a detected code.

#### Properties

-   `data`: The decoded content of the code
-   `type`: Type of code ('qr' or 'datamatrix')
-   `rect`: Rectangle coordinates (x, y, width, height)
-   `points`: Polygon points (corners) of the code if available
-   `timestamp`: Time when the code was detected

## Troubleshooting

### Common Issues

1. **Camera not available**

    - Ensure the Raspberry Pi camera is enabled in raspi-config
    - Check camera cable connection
    - Verify picamera2 is installed properly

2. **Poor detection quality**

    - Improve lighting conditions
    - Ensure code is within camera view and not blurry
    - Try adjusting camera position or distance

3. **Missing dependencies**
    - Ensure all required libraries are installed
    - Check if libzbar0 and libdmtx0a system packages are installed

### Debug Logging

To enable detailed logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("code_scanner_app")
scanner = CodeScanner(logger=logger)
```

## Performance Optimization

For better detection performance:

1. Position the camera 10-20 cm from the codes for optimal resolution
2. Ensure good, even lighting (avoid glare and shadows)
3. Use higher contrast codes when possible (black on white)
4. Adjust camera resolution for better performance:
    ```python
    # Modify in code_scanner.py
    CAMERA_RESOLUTION = (640, 480)  # Higher resolution for better detection
    ```

## License

[MIT License](LICENSE)

## Contributions

Contributions are welcome! Please feel free to submit a Pull Request.
