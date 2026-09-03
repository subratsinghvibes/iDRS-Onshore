"""
Advanced video processing for instant playback like YouTube/Netflix.
Implements automatic compression, adaptive bitrate streaming (HLS), and optimization.
"""

import os
import subprocess
import logging
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


def check_ffmpeg_installed():
    """Check if FFmpeg is installed and available."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_video_info(video_path):
    """Get video information using ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
        return None
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return None


def compress_video_fast(input_path, output_path, target_quality='medium'):
    """
    Fast video compression optimized for network streaming.
    Uses hardware acceleration when available.
    
    Quality levels:
    - low: 480p, CRF 28, fast preset (smallest file, fastest encoding)
    - medium: 720p, CRF 23, medium preset (balanced)
    - high: 1080p, CRF 20, slow preset (best quality)
    """
    quality_settings = {
        'low': {
            'scale': '854:480',
            'crf': '28',
            'preset': 'veryfast',
            'maxrate': '1M',
            'bufsize': '2M'
        },
        'medium': {
            'scale': '1280:720',
            'crf': '23',
            'preset': 'fast',
            'maxrate': '2.5M',
            'bufsize': '5M'
        },
        'high': {
            'scale': '1920:1080',
            'crf': '20',
            'preset': 'medium',
            'maxrate': '5M',
            'bufsize': '10M'
        }
    }
    
    settings_dict = quality_settings.get(target_quality, quality_settings['medium'])
    
    # Build FFmpeg command with optimizations
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-c:v', 'libx264',  # H.264 codec
        '-crf', settings_dict['crf'],  # Quality
        '-preset', settings_dict['preset'],  # Encoding speed
        '-vf', f"scale={settings_dict['scale']}:force_original_aspect_ratio=decrease",  # Resolution
        '-maxrate', settings_dict['maxrate'],  # Max bitrate
        '-bufsize', settings_dict['bufsize'],  # Buffer size
        '-c:a', 'aac',  # Audio codec
        '-b:a', '128k',  # Audio bitrate
        '-ac', '2',  # Stereo audio
        '-movflags', '+faststart',  # Enable fast start for web
        '-threads', '0',  # Use all CPU cores
        '-y',  # Overwrite output
        output_path
    ]
    
    try:
        logger.info(f"Starting video compression: {input_path} -> {output_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Video compression successful: {output_path}")
            return True
        else:
            logger.error(f"Video compression failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Video compression timed out")
        return False
    except Exception as e:
        logger.error(f"Error during video compression: {e}")
        return False


def create_hls_stream(input_path, output_dir):
    """
    Create HLS (HTTP Live Streaming) adaptive bitrate stream.
    This is what YouTube/Netflix use for instant playback.
    
    Creates multiple quality levels:
    - 360p for slow connections
    - 480p for medium connections  
    - 720p for fast connections
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # HLS master playlist path
    master_playlist = os.path.join(output_dir, 'master.m3u8')
    
    # Create multiple quality variants
    cmd = [
        'ffmpeg',
        '-i', input_path,
        
        # 360p stream
        '-vf', 'scale=640:360:force_original_aspect_ratio=decrease',
        '-c:v', 'libx264',
        '-crf', '28',
        '-preset', 'veryfast',
        '-maxrate', '800k',
        '-bufsize', '1600k',
        '-c:a', 'aac',
        '-b:a', '96k',
        '-ac', '2',
        '-hls_time', '4',  # 4 second segments
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', os.path.join(output_dir, '360p_%03d.ts'),
        os.path.join(output_dir, '360p.m3u8'),
        
        # 480p stream
        '-vf', 'scale=854:480:force_original_aspect_ratio=decrease',
        '-c:v', 'libx264',
        '-crf', '26',
        '-preset', 'fast',
        '-maxrate', '1.5M',
        '-bufsize', '3M',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-ac', '2',
        '-hls_time', '4',
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', os.path.join(output_dir, '480p_%03d.ts'),
        os.path.join(output_dir, '480p.m3u8'),
        
        # 720p stream
        '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease',
        '-c:v', 'libx264',
        '-crf', '23',
        '-preset', 'fast',
        '-maxrate', '2.5M',
        '-bufsize', '5M',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-ac', '2',
        '-hls_time', '4',
        '-hls_playlist_type', 'vod',
        '-hls_segment_filename', os.path.join(output_dir, '720p_%03d.ts'),
        os.path.join(output_dir, '720p.m3u8'),
        
        '-threads', '0',
        '-y'
    ]
    
    try:
        logger.info(f"Creating HLS stream: {input_path} -> {output_dir}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result.returncode == 0:
            # Create master playlist
            create_master_playlist(output_dir)
            logger.info(f"HLS stream created successfully: {output_dir}")
            return True
        else:
            logger.error(f"HLS creation failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating HLS stream: {e}")
        return False


def create_master_playlist(output_dir):
    """Create HLS master playlist that lists all quality variants."""
    master_content = """#EXTM3U
#EXT-X-VERSION:3

#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
360p.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=854x480
480p.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p.m3u8
"""
    
    master_path = os.path.join(output_dir, 'master.m3u8')
    with open(master_path, 'w') as f:
        f.write(master_content)


def optimize_video_for_streaming(input_path, output_path):
    """
    Ultra-fast optimization for immediate playback.
    Moves moov atom to beginning of file without re-encoding.
    This is the fastest way to enable streaming.
    """
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-c', 'copy',  # Copy streams without re-encoding
        '-movflags', '+faststart',  # Move metadata to beginning
        '-y',
        output_path
    ]
    
    try:
        logger.info(f"Optimizing video for streaming: {input_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )
        
        if result.returncode == 0:
            logger.info(f"Video optimized successfully: {output_path}")
            return True
        else:
            logger.error(f"Video optimization failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error optimizing video: {e}")
        return False


def process_uploaded_video(video_file, tutorial_id):
    """
    Process uploaded video for optimal streaming.
    
    Steps:
    1. Save original file
    2. Quick optimize for immediate availability
    3. Compress in background for smaller file
    4. Optionally create HLS stream for adaptive bitrate
    
    Returns:
        dict with paths to processed files
    """
    # Create processing directory
    media_root = Path(settings.MEDIA_ROOT)
    video_dir = media_root / 'tutorials' / 'videos'
    processed_dir = video_dir / 'processed' / str(tutorial_id)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Save original
    original_path = video_dir / f"{tutorial_id}_original{Path(video_file.name).suffix}"
    
    # Optimized version (fast, for immediate use)
    optimized_path = video_dir / f"{tutorial_id}_optimized.mp4"
    
    # Compressed version (smaller, for long-term use)
    compressed_path = video_dir / f"{tutorial_id}_compressed.mp4"
    
    # HLS directory
    hls_dir = processed_dir / 'hls'
    
    results = {
        'original': str(original_path),
        'optimized': None,
        'compressed': None,
        'hls': None,
        'success': False
    }
    
    try:
        # Save original file
        with open(original_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        
        logger.info(f"Original video saved: {original_path}")
        
        # Check if FFmpeg is available
        if not check_ffmpeg_installed():
            error_msg = (
                "FFmpeg is not installed! Video processing requires FFmpeg. "
                "Please install FFmpeg using 'install_ffmpeg.bat' (Windows) "
                "or follow the installation guide. "
                "Videos will be served in original format without compression."
            )
            logger.error(error_msg)
            results['optimized'] = str(original_path)
            results['success'] = True
            results['error'] = error_msg
            return results
        
        # Step 1: Quick optimize (no re-encoding, very fast)
        if optimize_video_for_streaming(str(original_path), str(optimized_path)):
            results['optimized'] = str(optimized_path)
            results['success'] = True
            logger.info("Quick optimization completed")
        else:
            # If optimization fails, use original
            results['optimized'] = str(original_path)
            results['success'] = True
        
        # Step 2: Compress for smaller file (can be done in background)
        # This takes longer but produces much smaller files
        if compress_video_fast(str(original_path), str(compressed_path), 'medium'):
            results['compressed'] = str(compressed_path)
            logger.info("Compression completed")
        
        # Step 3: Create HLS stream (optional, for adaptive bitrate)
        # Uncomment if you want YouTube-style adaptive streaming
        # if create_hls_stream(str(original_path), str(hls_dir)):
        #     results['hls'] = str(hls_dir / 'master.m3u8')
        #     logger.info("HLS stream created")
        
        return results
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        results['success'] = False
        return results


def get_file_size_mb(file_path):
    """Get file size in megabytes."""
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / (1024 * 1024), 2)
    except:
        return 0
