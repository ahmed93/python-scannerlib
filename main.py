#!/usr/bin/env python3
"""
Code Scanner Library
-------------------------
A comprehensive library for detecting and processing QR codes and Data Matrix codes
using a Raspberry Pi camera. This library provides a simple interface for real-time
code detection with multiple detection modes and robust error handling.

Dependencies:
- picamera2: For camera access on Raspberry Pi
- pyzbar: For QR code detection
- pylibdmtx: For Data Matrix code detection
- opencv-python: For image processing

Usage:
    from code_scanner import CodeScanner, DetectionMode, CodeInfo
    
    # Create scanner
    scanner = CodeScanner()
    
    # Define callback for code detection
    def on_code_detected(code_info):
        if code_info is None:
            print("Code removed")
        else:
            print(f"Detected {code_info.type} code: {code_info.data}")
    
    # Start scanner in single detection mode
    scanner.set_mode(DetectionMode.SINGLE)
    scanner.start(on_code_detected)
    
    # ... application logic ...
    
    # Stop scanner when done
    scanner.stop()
"""

import time
import os
import sys
import cv2
import threading
import traceback
from threading import Thread, Lock, Event
import enum
import logging
from typing import Dict, List, Optional, Callable, Tuple, Any

# Set up paths for libcamera
if os.path.exists("/usr/lib/python3/dist-packages/libcamera"):
    sys.path.append("/usr/lib/python3/dist-packages")

# Import picamera2 module
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
    print("✓ Imported Picamera2 module")
except ImportError as e:
    PICAMERA2_AVAILABLE = False
    print(f"✗ Picamera2 import error: {e}")

# Import pyzbar module for QR codes
try:
    from pyzbar import pyzbar
    from pyzbar.pyzbar import ZBarSymbol
    PYZBAR_AVAILABLE = True
    print("✓ Imported pyzbar module for QR code detection")
except ImportError as e:
    PYZBAR_AVAILABLE = False
    print(f"✗ Pyzbar import error: {e}")

# Import pylibdmtx module for Data Matrix codes
try:
    import pylibdmtx.pylibdmtx as dmtx
    DMTX_AVAILABLE = True
    print("✓ Imported pylibdmtx module for Data Matrix detection")
except ImportError:
    DMTX_AVAILABLE = False
    print("✗ pylibdmtx not available. Data Matrix detection will be disabled.")
    print("   To install: pip install pylibdmtx")

# Configuration defaults 
DETECTION_INTERVAL = 0.05  # seconds between code detections
CAMERA_RESOLUTION = (320, 240)
CAMERA_FRAMERATE = 10


class DetectionMode(enum.Enum):
    """
    Enumeration of detection modes for the code scanner.
    
    Modes:
        CONTINUOUS: Continuously scan for codes without waiting.
        SINGLE: Detect one code, then wait for it to be removed before detecting another.
        TRIGGERED: Only scan when explicitly triggered via trigger_scan().
    """
    CONTINUOUS = "continuous"  # Continuously scan for codes
    SINGLE = "single"          # Detect one code, then wait for removal
    TRIGGERED = "triggered"    # Only scan when triggered manually


class CodeInfo:
    """
    Contains information about a detected code.
    
    Attributes:
        data (str): The decoded data content of the code.
        type (str): Type of code ('qr' or 'datamatrix').
        rect (Tuple): Rectangle coordinates (x, y, width, height) of the code.
        points (List): Polygon points for the corners of the code (if available).
        timestamp (float): Time when the code was detected.
    """
    
    def __init__(self, data: str, type: str, rect: Tuple, points: List = None):
        """
        Initialize a CodeInfo object.
        
        Args:
            data (str): The decoded data content of the code.
            type (str): Type of code ('qr' or 'datamatrix').
            rect (Tuple): Rectangle coordinates (x, y, width, height) of the code.
            points (List, optional): Polygon points for the corners of the code.
        """
        self.data = data
        self.type = type  # 'qr' or 'datamatrix'
        self.rect = rect
        self.points = points or []  # Not all detectors provide polygon points
        self.timestamp = time.time()


class CodeScanner:
    """
    Main class for code detection using a Raspberry Pi camera.
    
    Provides methods for detecting QR codes and Data Matrix codes
    with different detection modes, callbacks for detection events,
    and thread-safe operation.
    """
    
    def __init__(self, logger=None):
        """
        Initialize the code scanner.
        
        Args:
            logger (logging.Logger, optional): Custom logger instance. If None,
                                              a default logger will be created.
        
        Raises:
            RuntimeError: If required dependencies are not available.
        """
        # Set up default logger if none provided
        self.logger = logger
        if self.logger is None:
            # Create a basic default logger
            self.logger = logging.getLogger("CodeScanner")
            self.logger.setLevel(logging.INFO)
            
            # Add console handler if no handlers exist
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s | [%(name)s] | %(levelname)s : %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)

        # Verification before starting
        if not PICAMERA2_AVAILABLE:
            self.logger.error("Picamera2 is required but not available")
            raise RuntimeError("Picamera2 is required but not available")
        if not PYZBAR_AVAILABLE and not DMTX_AVAILABLE:
            self.logger.error("Neither pyzbar nor pylibdmtx is available")
            raise RuntimeError("Neither pyzbar nor pylibdmtx is available")
            
        # Initialize camera
        self.camera = Picamera2()
        
        # Configure camera with optimized settings for code detection
        config = self.camera.create_preview_configuration(
            main={"size": CAMERA_RESOLUTION},
            controls={"FrameRate": CAMERA_FRAMERATE,
                     "NoiseReductionMode": 1,  # Minimal noise reduction
                     "Sharpness": 10}         # Increased sharpness for better detection
        )
        self.camera.configure(config)
        
        # Initialization
        self.is_running = False
        self.code_callback = None
        self.detection_mode = DetectionMode.SINGLE
        self.detection_interval = DETECTION_INTERVAL
        
        # Thread management
        self.capture_thread = None
        self.stop_event = Event()
        self.frame_lock = Lock()
        
        # Current frame
        self.current_frame = None
        
        # Code detection state
        self.last_detected_code = None
        self.last_detected_type = None
        self.code_removed = Event()
        self.code_removed.set()  # Initially no code detected
        self.consecutive_frames_without_code = 0
        self.frames_to_consider_removed = 3
        
        # Detection capabilities
        self.can_detect_qr = PYZBAR_AVAILABLE
        self.can_detect_datamatrix = DMTX_AVAILABLE
        
        self.logger.info(f"QR Code detection: {'ENABLED' if self.can_detect_qr else 'DISABLED'}")
        self.logger.info(f"Data Matrix detection: {'ENABLED' if self.can_detect_datamatrix else 'DISABLED'}")
    
    def start(self, code_callback: Callable = None):
        """
        Start code scanning.
        
        Args:
            code_callback (Callable, optional): Function to call when code is detected or removed.
                The callback should accept a CodeInfo object, or None for code removal.
        
        Returns:
            None
        """
        if self.is_running:
            self.logger.info("Scanner is already running")
            return
        
        # Store callback
        self.code_callback = code_callback
        
        # Start camera
        self.logger.info("Starting camera...")
        self.camera.start()
        time.sleep(1)  # Wait for camera to start
        
        # Reset state
        self.stop_event.clear()
        self.is_running = True
        
        # Start capture thread
        self.logger.info("Starting detection thread...")
        self.capture_thread = Thread(
            target=self._capture_loop,
            daemon=True,
            name="CodeScannerThread"
        )
        self.capture_thread.start()
        
        self.logger.info("Code Scanner started")
    
    def stop(self):
        """
        Stop code scanning and release resources.
        
        Returns:
            None
        """
        if not self.is_running:
            return
        
        # Signal thread to stop
        self.logger.info("Stopping code scanner...")
        self.stop_event.set()
        
        # Wait for thread to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
        
        # Stop camera
        self.logger.info("Stopping camera...")
        try:
            self.camera.stop()
        except Exception as e:
            self.logger.error(f"Error stopping camera: {e}")
        
        self.is_running = False
        self.logger.info("Code Scanner stopped")
    
    def set_mode(self, mode: DetectionMode):
        """
        Set the detection mode.
        
        Args:
            mode (DetectionMode): The detection mode to use.
        
        Returns:
            None
        """
        self.logger.info(f"Setting detection mode to {mode.value}")
        self.detection_mode = mode
        
        # Reset detection state when changing mode
        self.last_detected_code = None
        self.last_detected_type = None
        self.code_removed.set()
        self.consecutive_frames_without_code = 0
    
    def trigger_scan(self):
        """
        Manually trigger a code scan (for TRIGGERED mode).
        
        In TRIGGERED mode, this will scan for a code once and stop
        until triggered again, even if no code is found.
        
        Returns:
            None
        """
        if not self.is_running:
            self.logger.warning("Scanner not running")
            return
        
        if self.detection_mode != DetectionMode.TRIGGERED:
            self.logger.warning("Trigger only works in TRIGGERED mode")
            return
        
        # Reset trigger state
        self.code_removed.clear()  # Mark as "busy" until next trigger
        
        # Get latest frame and scan it once
        with self.frame_lock:
            if self.current_frame is not None:
                frame = self.current_frame.copy()
                self.logger.info("Triggered scan started")
                self._scan_frame(frame)
                self.logger.info("Triggered scan completed")
    
    def _capture_loop(self):
        """
        Main capture loop that runs in a separate thread.
        
        This method continuously captures frames from the camera and processes them
        according to the current detection mode.
        
        Returns:
            None
        """
        self.logger.info("Capture loop started")
        last_code_detection = 0
        frame_count = 0
        
        while not self.stop_event.is_set():
            try:
                # Capture a new frame
                frame = self.camera.capture_array()
                frame_count += 1
                
                # Convert to BGR (OpenCV format)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Update current frame with thread safety
                with self.frame_lock:
                    self.current_frame = frame.copy()
                
                # Code detection with interval limiting
                current_time = time.time()
                if current_time - last_code_detection >= self.detection_interval:
                    last_code_detection = current_time
                    
                    if self.detection_mode == DetectionMode.SINGLE and not self.code_removed.is_set():
                        # Check if code has been removed
                        self._check_code_removal(frame)
                    elif self.detection_mode == DetectionMode.CONTINUOUS or (self.code_removed.is_set() and self.detection_mode != DetectionMode.TRIGGERED):
                        # Scan for codes (TRIGGERED mode only scans when explicitly triggered)
                        self._scan_frame(frame)
                
                # Print occasional status
                if frame_count % 100 == 0:
                    self.logger.debug(f"Processed {frame_count} frames")
                                        
                # Sleep to reduce CPU usage
                time.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"Error in capture loop: {e}")
                self.logger.error(traceback.format_exc())
                time.sleep(0.5)
    
    def _scan_frame(self, frame):
        """
        Scan a frame for QR and Data Matrix codes.
        
        Args:
            frame: BGR image to scan
            
        Returns:
            bool: True if a code was found, False otherwise
        """
        code_found = False
        # Process the frame for optimal code detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Enhanced contrast for better detection
        # Make enhancement conditional based on lighting
        average_brightness = cv2.mean(gray)[0]
        if average_brightness < 100 or average_brightness > 200:
            # Only enhance if lighting is poor
            enhanced = cv2.equalizeHist(gray)
        else:
            enhanced = gray
        
        # First try QR codes
        if self.can_detect_qr:
            # Use pyzbar for QR codes
            try:
                qr_codes = pyzbar.decode(gray, symbols=[ZBarSymbol.QRCODE])
                if qr_codes:
                    # Process detected QR codes
                    for qr in qr_codes:
                        data = qr.data.decode('utf-8')
                        rect = qr.rect
                        points = qr.polygon
                        
                        # Convert polygon points to a simple list
                        points_list = [(p.x, p.y) for p in points]
                        rect_tuple = (rect.left, rect.top, rect.width, rect.height)
                        
                        # Create code info
                        code_info = CodeInfo(data, 'qr', rect_tuple, points_list)
                        
                        # Call callback if set
                        if self.code_callback:
                            self.code_callback(code_info)
                        
                        self.logger.info(f"QR Code detected: {data}")
                        
                        # Update detection state for SINGLE/TRIGGERED mode
                        if self.detection_mode in [DetectionMode.SINGLE, DetectionMode.TRIGGERED]:
                            self.last_detected_code = data
                            self.last_detected_type = 'qr'
                            self.code_removed.clear()
                            self.consecutive_frames_without_code = 0
                            code_found = True
                            return True
            except Exception as e:
                self.logger.error(f"Error in QR detection: {e}")
        
        # Then try Data Matrix codes
        if self.can_detect_datamatrix:
            # Use pylibdmtx for Data Matrix codes
            try:
                dm_codes = dmtx.decode(gray, timeout=50, max_count=1, corrections=0)
                
                if dm_codes:
                    # Process detected Data Matrix codes
                    for dm in dm_codes:
                        data = dm.data.decode('utf-8')
                        
                        # pylibdmtx returns a different format of location data
                        rect = (dm.rect.left, dm.rect.top, dm.rect.width, dm.rect.height)
                        
                        # Create code info (pylibdmtx doesn't provide polygon points)
                        code_info = CodeInfo(data, 'datamatrix', rect)
                        
                        # Call callback if set
                        if self.code_callback:
                            self.code_callback(code_info)
                        
                        self.logger.info(f"Data Matrix detected: {data}")
                        
                        # Update detection state for SINGLE/TRIGGERED mode
                        if self.detection_mode in [DetectionMode.SINGLE, DetectionMode.TRIGGERED]:
                            self.last_detected_code = data
                            self.last_detected_type = 'datamatrix'
                            self.code_removed.clear()
                            self.consecutive_frames_without_code = 0
                            code_found = True
                            return True
            except Exception as e:
                self.logger.error(f"Error in Data Matrix detection: {e}")
        
        # If we reached here and did not return earlier, no code was found
        return False
    
    def _check_code_removal(self, frame):
        """
        Check if a previously detected code has been removed.
        
        Args:
            frame: BGR image to check
            
        Returns:
            None
        """
        if not self.last_detected_code or not self.last_detected_type:
            return
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Check if the code is still present
        still_present = False
        
        if self.last_detected_type == 'qr' and self.can_detect_qr:
            # Check for QR code
            try:
                qr_codes = pyzbar.decode(gray, symbols=[ZBarSymbol.QRCODE])
                for qr in qr_codes:
                    if qr.data.decode('utf-8') == self.last_detected_code:
                        still_present = True
                        break
            except Exception:
                pass
        
        elif self.last_detected_type == 'datamatrix' and self.can_detect_datamatrix:
            # Check for Data Matrix
            try:
                dm_codes = dmtx.decode(gray, timeout=100, max_count=1)
                for dm in dm_codes:
                    if dm.data.decode('utf-8') == self.last_detected_code:
                        still_present = True
                        break
            except Exception:
                pass
        
        # If code not found, increment counter
        if not still_present:
            self.consecutive_frames_without_code += 1
            
            # If missing for enough consecutive frames, consider it removed
            if self.consecutive_frames_without_code >= self.frames_to_consider_removed:
                self.logger.info(f"{self.last_detected_type.upper()} Code removed: {self.last_detected_code}")
                
                # Call callback with None to signal removal
                if self.code_callback:
                    self.code_callback(None)
                
                # Reset detection state
                self.last_detected_code = None
                self.last_detected_type = None
                self.code_removed.set()
                self.consecutive_frames_without_code = 0