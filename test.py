#!/usr/bin/env python3
"""
Simple QR Code and Data Matrix Scanner Application

A streamlined command-line application to detect and display QR codes and 
Data Matrix codes using the CodeScanner library.
"""
import time
import sys
import signal
import os
import select
import termios
import tty
import atexit
from datetime import datetime

# Import the CodeScanner library
try:
    from main import CodeScanner, DetectionMode, PYZBAR_AVAILABLE, DMTX_AVAILABLE
    print("✓ Successfully imported CodeScanner library")
except ImportError as e:
    print(f"✗ Error importing CodeScanner library: {e}")
    print("Make sure code_scanner.py is in the same directory or PYTHONPATH")
    sys.exit(1)

class ScannerApp:
    """
    Simple application for testing code scanning capabilities.
    """
    
    def __init__(self):
        """Initialize the scanner application."""
        # Initialize state
        self.running = True
        self.scanner = None
        self.codes_detected = 0
        
        # Set up terminal for keyboard input
        self.setup_terminal()
        
        # Register signal handlers and cleanup
        signal.signal(signal.SIGINT, self.handle_exit)
        atexit.register(self.cleanup)
        
        # Print header and capabilities
        self.clear_screen()
        print("-" * 50)
        print(" CODE SCANNER APPLICATION ")
        print("-" * 50)
        print("Capabilities:")
        print(f"  QR Codes: {'ENABLED' if PYZBAR_AVAILABLE else 'DISABLED'}")
        print(f"  Data Matrix: {'ENABLED' if DMTX_AVAILABLE else 'DISABLED'}")
        print("-" * 50)
        
        # Initialize scanner
        try:
            self.scanner = CodeScanner()
            print("Scanner initialized successfully")
        except Exception as e:
            print(f"Error initializing scanner: {e}")
            sys.exit(1)
    
    def setup_terminal(self):
        """Configure terminal for non-blocking input."""
        try:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except Exception as e:
            print(f"Warning: Terminal setup failed: {e}")
            print("You may need to use Ctrl+C to exit")
    
    def restore_terminal(self):
        """Restore terminal to original settings."""
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
        except Exception:
            pass
    
    def handle_exit(self, sig, frame):
        """Handle exit signals."""
        print("\nExiting application...")
        self.running = False
    
    def cleanup(self):
        """Perform cleanup operations."""
        self.restore_terminal()
        if self.scanner:
            self.scanner.stop()
            print("Scanner stopped")
    
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def show_menu(self):
        """Display the main menu options."""
        print("\nSelect a detection mode:")
        print("  1: Single mode - Detect one code at a time")
        print("  2: Continuous mode - Detect all codes continuously")
        print("  3: Triggered mode - Scan only when triggered")
        print("  q: Quit")
        print("-" * 50)
    
    def on_code_detected(self, code_info):
        """
        Callback function for code detection events.
        
        Args:
            code_info: Information about the detected code, or None if removed
        """
        if code_info is None:
            # Code has been removed
            print("\n✓ Code removed - Ready for next detection")
            return
        
        # Code detected
        self.codes_detected += 1
        now = datetime.now().strftime("%H:%M:%S")
        
        # Print detection information
        print("\n" + "-" * 50)
        print(f" {code_info.type.upper()} CODE #{self.codes_detected}")
        print("-" * 50)
        print(f"Data: {code_info.data}")
        print(f"Time: {now}")
        print(f"Position: {code_info.rect}")
        
        # Print controls reminder
        if self.scanner.detection_mode == DetectionMode.TRIGGERED:
            print("\nPress 't' to trigger another scan")
        elif self.scanner.detection_mode == DetectionMode.SINGLE:
            print("\nRemove code to detect another")
    
    def start_detection(self, mode):
        """
        Start code detection with the specified mode.
        
        Args:
            mode: The detection mode to use
        """
        print(f"\nStarting detection in {mode.value} mode...")
        
        # Configure scanner
        self.scanner.set_mode(mode)
        self.scanner.start(self.on_code_detected)
        
        # Show controls
        print("\nControls:")
        print("  1,2,3: Change mode")
        print("  t: Trigger scan (in triggered mode)")
        print("  q: Quit")
        print("  h: Show help")
        
        # Main detection loop
        while self.running:
            # Check for keyboard input
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                key = sys.stdin.read(1)
                
                if key == 'q':
                    print("\nExiting...")
                    self.running = False
                
                elif key == '1':
                    print("\nSwitching to SINGLE mode")
                    self.scanner.set_mode(DetectionMode.SINGLE)
                
                elif key == '2':
                    print("\nSwitching to CONTINUOUS mode")
                    self.scanner.set_mode(DetectionMode.CONTINUOUS)
                
                elif key == '3':
                    print("\nSwitching to TRIGGERED mode")
                    self.scanner.set_mode(DetectionMode.TRIGGERED)
                
                elif key == 't':
                    if self.scanner.detection_mode == DetectionMode.TRIGGERED:
                        print("\nTriggering scan...")
                        self.scanner.trigger_scan()
                    else:
                        print("\nTriggering only works in TRIGGERED mode")
                
                elif key == 'h':
                    print("\nControls:")
                    print("  1,2,3: Change mode")
                    print("  t: Trigger scan (in triggered mode)")
                    print("  q: Quit")
                    print("  h: Show help")
            
            # Sleep to reduce CPU usage
            time.sleep(0.1)
        
        # Stop scanner
        self.scanner.stop()
    
    def run(self):
        """Run the main application loop."""
        self.show_menu()
        
        while self.running:
            # Wait for menu selection
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                choice = sys.stdin.read(1)
                
                if choice == '1':
                    self.start_detection(DetectionMode.SINGLE)
                    # Show menu again after returning from detection
                    self.show_menu() if self.running else None
                
                elif choice == '2':
                    self.start_detection(DetectionMode.CONTINUOUS)
                    self.show_menu() if self.running else None
                
                elif choice == '3':
                    self.start_detection(DetectionMode.TRIGGERED)
                    self.show_menu() if self.running else None
                
                elif choice == 'q':
                    print("\nExiting application...")
                    self.running = False
            
            # Sleep to reduce CPU usage
            time.sleep(0.1)


if __name__ == "__main__":
    print("Starting Code Scanner Application...")
    app = ScannerApp()
    try:
        app.run()
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        app.cleanup()