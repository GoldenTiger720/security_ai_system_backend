# utils/stream_proxy.py

import os
import threading
import subprocess
import logging
import time
import signal
import tempfile
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

class StreamProxy:
    """
    Class for proxying video streams to web-friendly formats (HLS/DASH)
    using FFmpeg.
    """
    
    def __init__(self, camera):
        """
        Initialize the stream proxy
        
        Args:
            camera: Camera model instance
        """
        self.camera = camera
        self.process = None
        self.is_running = False
        self.output_dir = os.path.join(settings.MEDIA_ROOT, 'streams', str(camera.id))
        self.stop_event = threading.Event()
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
    
    def start(self):
        """
        Start the stream proxy
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            # Stop existing process if running
            self.stop()
            
            # Clear output directory
            for file in os.listdir(self.output_dir):
                file_path = os.path.join(self.output_dir, file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            
            # Prepare input URL based on camera type
            input_url = self._get_input_url()
            
            # Prepare FFmpeg command for HLS streaming
            cmd = [
                'ffmpeg',
                '-i', input_url,                 # Input stream
                '-c:v', 'libx264',               # Video codec
                '-preset', 'veryfast',           # Encoding preset
                '-tune', 'zerolatency',          # Tuning for low latency
                '-sc_threshold', '0',            # Disable scene change detection
                '-g', '30',                      # GOP size (1 second at 30 fps)
                '-hls_time', '2',                # Segment length in seconds
                '-hls_list_size', '5',           # Number of segments in playlist
                '-hls_flags', 'delete_segments', # Delete old segments
                '-hls_segment_type', 'mpegts',   # Segment type
                '-hls_segment_filename', f"{self.output_dir}/segment_%03d.ts", # Segment filename pattern
                '-f', 'hls',                     # Output format (HLS)
                f"{self.output_dir}/index.m3u8"  # Output playlist
            ]
            
            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait a moment to see if process starts successfully
            time.sleep(2)
            
            # Check if process is still running
            if self.process.poll() is None:
                self.is_running = True
                
                # Start background thread to monitor process
                self._start_monitor_thread()
                
                logger.info(f"Stream proxy started for camera {self.camera.id}")
                return True
            else:
                stderr = self.process.stderr.read()
                logger.error(f"Failed to start stream proxy: {stderr}")
                return False
            
        except Exception as e:
            logger.error(f"Error starting stream proxy: {str(e)}")
            self.stop()
            return False
    
    def stop(self):
        """
        Stop the stream proxy
        """
        if self.process:
            try:
                # Signal the monitor thread to stop
                self.stop_event.set()
                
                # Terminate the process
                if self.process.poll() is None:
                    # Try graceful termination first
                    self.process.terminate()
                    
                    # Wait for process to terminate
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if not terminated
                        self.process.kill()
                
                self.is_running = False
                logger.info(f"Stream proxy stopped for camera {self.camera.id}")
                
            except Exception as e:
                logger.error(f"Error stopping stream proxy: {str(e)}")
            
            finally:
                self.process = None
    
    def _get_input_url(self):
        """
        Get the input URL for FFmpeg based on camera type
        
        Returns:
            str: Input URL
        """
        # For RTSP cameras
        if self.camera.camera_type == 'rtsp':
            url = self.camera.url
            
            # Add authentication if needed
            if self.camera.username and self.camera.password:
                # Add authentication to URL if not already included
                if '@' not in url:
                    # Parse URL to extract protocol, host, path
                    url_parts = url.split('://', 1)
                    if len(url_parts) > 1:
                        protocol = url_parts[0]
                        rest = url_parts[1].split('/', 1)
                        host = rest[0]
                        path = rest[1] if len(rest) > 1 else ''
                        
                        # Construct URL with embedded credentials
                        url = f"{protocol}://{self.camera.username}:{self.camera.password}@{host}/{path}"
            
            return url
        
        # For HTTP cameras
        elif self.camera.camera_type == 'http':
            url = self.camera.url
            
            # Add authentication if needed
            if self.camera.username and self.camera.password:
                # Add authentication to URL if not already included
                if '@' not in url:
                    # Parse URL to extract protocol, host, path
                    url_parts = url.split('://', 1)
                    if len(url_parts) > 1:
                        protocol = url_parts[0]
                        rest = url_parts[1].split('/', 1)
                        host = rest[0]
                        path = rest[1] if len(rest) > 1 else ''
                        
                        # Construct URL with embedded credentials
                        url = f"{protocol}://{self.camera.username}:{self.camera.password}@{host}/{path}"
            
            return url
        
        # For local webcams
        elif self.camera.camera_type == 'local':
            # Get device index (usually a number)
            device_index = 0
            if self.camera.url and self.camera.url.isdigit():
                device_index = int(self.camera.url)
            
            # On Linux
            if os.name == 'posix':
                return f"/dev/video{device_index}"
            # On Windows
            else:
                return f"video={device_index}"
        
        # For video files
        elif self.camera.camera_type == 'file':
            file_path = self.camera.url
            
            # Check if the file exists
            if not os.path.isfile(file_path):
                # If not absolute path, check in media directory
                media_path = os.path.join(settings.MEDIA_ROOT, file_path)
                if os.path.isfile(media_path):
                    file_path = media_path
            
            return file_path
        
        else:
            raise ValueError(f"Unsupported camera type: {self.camera.camera_type}")
    
    def _start_monitor_thread(self):
        """
        Start a background thread to monitor the FFmpeg process
        """
        def monitor_process():
            while not self.stop_event.is_set():
                # Check if process is still running
                if self.process.poll() is not None:
                    # Process has exited
                    stderr = self.process.stderr.read()
                    if stderr:
                        logger.error(f"Stream proxy exited: {stderr}")
                    else:
                        logger.info(f"Stream proxy exited for camera {self.camera.id}")
                    
                    self.is_running = False
                    break
                
                # Sleep for a bit
                time.sleep(5)
        
        # Start the monitor thread
        monitor_thread = threading.Thread(target=monitor_process)
        monitor_thread.daemon = True
        monitor_thread.start()