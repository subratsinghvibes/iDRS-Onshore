"""
Video Processing Module for Netflix-like Streaming

This module provides video processing utilities using FFmpeg for:
1. Fast-start optimization (moov atom at beginning for instant playback)
2. Video compression with quality preservation
3. HLS (HTTP Live Streaming) generation for adaptive bitrate streaming
4. Thumbnail generation

Requirements:
- FFmpeg must be installed on the system
  - macOS: brew install ffmpeg
  - Windows: winget install ffmpeg OR download from ffmpeg.org
  - Linux: apt install ffmpeg
"""

import os
import re
import json
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from decimal import Decimal

logger = logging.getLogger(__name__)


# Default settings - will be overridden by Django settings when accessed
_DEFAULT_SETTINGS = {
    'compression': {
        'crf': 23,
        'preset': 'medium',
        'audio_bitrate': '128k',
    },
    'compression_min_size_mb': 50,
    'hls_min_size_mb': 100,
    'target_height': 720,
    'hls': {
        'segment_duration': 6,
        'playlist_type': 'vod',
        'quality_levels': [
            {'height': 360, 'bitrate': '800k', 'name': '360p'},
            {'height': 480, 'bitrate': '1400k', 'name': '480p'},
            {'height': 720, 'bitrate': '2800k', 'name': '720p'},
            {'height': 1080, 'bitrate': '5000k', 'name': '1080p'},
        ],
    },
}


def get_processing_settings():
    """
    Get video processing settings from Django settings or use defaults.
    This function is called lazily to avoid import-time issues.
    """
    try:
        from django.conf import settings as django_settings
        custom_settings = getattr(django_settings, 'VIDEO_PROCESSING', {})
    except Exception:
        custom_settings = {}
    
    # Merge with defaults
    settings = _DEFAULT_SETTINGS.copy()
    
    if custom_settings:
        settings['compression']['crf'] = custom_settings.get('COMPRESSION_CRF', settings['compression']['crf'])
        settings['compression']['preset'] = custom_settings.get('COMPRESSION_PRESET', settings['compression']['preset'])
        settings['compression']['audio_bitrate'] = custom_settings.get('AUDIO_BITRATE', settings['compression']['audio_bitrate'])
        settings['compression_min_size_mb'] = custom_settings.get('COMPRESSION_MIN_SIZE_MB', settings['compression_min_size_mb'])
        settings['hls_min_size_mb'] = custom_settings.get('HLS_MIN_SIZE_MB', settings['hls_min_size_mb'])
        settings['target_height'] = custom_settings.get('TARGET_HEIGHT', settings['target_height'])
        settings['hls']['segment_duration'] = custom_settings.get('HLS_SEGMENT_DURATION', settings['hls']['segment_duration'])
    
    return settings


# Alias for backward compatibility
VIDEO_PROCESSING_SETTINGS = _DEFAULT_SETTINGS


def is_ffmpeg_available():
    """Check if FFmpeg is installed and available."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_ffmpeg_path():
    """Get the path to FFmpeg executable."""
    # Try common locations
    if shutil.which('ffmpeg'):
        return 'ffmpeg'
    
    # Windows common paths
    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return 'ffmpeg'  # Default, hope it's in PATH


def get_video_info(video_path):
    """
    Get video information using ffprobe.
    
    Returns:
        dict with video info (duration, width, height, bitrate, etc.)
    """
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
            data = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = None
            audio_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            
            format_info = data.get('format', {})
            
            return {
                'duration': float(format_info.get('duration', 0)),
                'duration_minutes': int(float(format_info.get('duration', 0)) / 60),
                'bitrate': int(format_info.get('bit_rate', 0)),
                'size': int(format_info.get('size', 0)),
                'width': video_stream.get('width', 0) if video_stream else 0,
                'height': video_stream.get('height', 0) if video_stream else 0,
                'codec': video_stream.get('codec_name', '') if video_stream else '',
                'fps': eval(video_stream.get('r_frame_rate', '0/1')) if video_stream else 0,
                'has_audio': audio_stream is not None,
            }
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
    
    return None


def optimize_for_streaming(input_path, output_path):
    """
    Optimize video for streaming by moving moov atom to the beginning.
    This enables instant playback without downloading the entire file.
    
    Args:
        input_path: Path to input video
        output_path: Path to output video
        
    Returns:
        bool: True if successful
    """
    try:
        cmd = [
            get_ffmpeg_path(),
            '-i', input_path,
            '-c', 'copy',  # No re-encoding, just remux
            '-movflags', '+faststart',  # Move moov atom to beginning
            '-y',  # Overwrite output
            output_path
        ]
        
        logger.info(f"Optimizing video for streaming: {input_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        
        if result.returncode == 0:
            logger.info(f"Video optimized successfully: {output_path}")
            return True
        else:
            logger.error(f"FFmpeg optimization failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error optimizing video: {e}")
        return False


def compress_video(input_path, output_path, target_height=720, crf=23):
    """
    Compress video while maintaining quality.
    Uses H.264 codec with optimized settings for network streaming.
    
    Args:
        input_path: Path to input video
        output_path: Path to output video
        target_height: Target height (width scales proportionally)
        crf: Constant Rate Factor (18-28 recommended, lower = better quality)
        
    Returns:
        bool: True if successful
    """
    try:
        # Get video info to determine if scaling is needed
        video_info = get_video_info(input_path)
        
        # Build FFmpeg command
        cmd = [
            get_ffmpeg_path(),
            '-i', input_path,
            '-c:v', 'libx264',  # H.264 codec
            '-crf', str(crf),  # Quality setting
            '-preset', 'medium',  # Balance speed vs compression
            '-profile:v', 'high',  # High profile for better compression
            '-level', '4.1',  # Compatibility level
        ]
        
        # Add scaling if video is larger than target
        if video_info and video_info['height'] > target_height:
            cmd.extend(['-vf', f'scale=-2:{target_height}'])
        
        # Audio settings
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ac', '2',  # Stereo
        ])
        
        # Streaming optimization
        cmd.extend([
            '-movflags', '+faststart',  # Enable fast start
            '-y',  # Overwrite output
            output_path
        ])
        
        logger.info(f"Compressing video: {input_path} -> {output_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)  # 2 hour timeout
        
        if result.returncode == 0:
            logger.info(f"Video compressed successfully: {output_path}")
            return True
        else:
            logger.error(f"FFmpeg compression failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error compressing video: {e}")
        return False


def generate_hls_stream(input_path, output_dir, tutorial_id):
    """
    Generate HLS (HTTP Live Streaming) segments for adaptive bitrate streaming.
    Creates multiple quality versions like Netflix.
    
    Args:
        input_path: Path to input video
        output_dir: Base directory for HLS output
        tutorial_id: Tutorial UUID for organizing files
        
    Returns:
        str: Path to master playlist or None if failed
    """
    try:
        # Create output directory
        hls_dir = os.path.join(output_dir, 'tutorials', 'hls', str(tutorial_id))
        os.makedirs(hls_dir, exist_ok=True)
        
        # Get video info
        video_info = get_video_info(input_path)
        if not video_info:
            logger.error("Could not get video info")
            return None
        
        source_height = video_info.get('height', 720)
        
        # Determine which quality levels to create based on source resolution
        quality_levels = []
        for level in VIDEO_PROCESSING_SETTINGS['hls']['quality_levels']:
            if level['height'] <= source_height:
                quality_levels.append(level)
        
        if not quality_levels:
            # Source is smaller than all levels, use source resolution
            quality_levels = [{'height': source_height, 'bitrate': '1500k', 'name': f'{source_height}p'}]
        
        # Generate each quality level
        stream_info = []
        for i, level in enumerate(quality_levels):
            level_dir = os.path.join(hls_dir, level['name'])
            os.makedirs(level_dir, exist_ok=True)
            
            playlist_path = os.path.join(level_dir, 'playlist.m3u8')
            segment_pattern = os.path.join(level_dir, 'segment%03d.ts')
            
            cmd = [
                get_ffmpeg_path(),
                '-i', input_path,
                '-c:v', 'libx264',
                '-crf', '23',
                '-preset', 'fast',  # Faster encoding for HLS
                '-profile:v', 'main',
                '-level', '4.0',
                '-vf', f'scale=-2:{level["height"]}',
                '-b:v', level['bitrate'],
                '-maxrate', level['bitrate'],
                '-bufsize', f'{int(level["bitrate"].replace("k", "")) * 2}k',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ac', '2',
                '-hls_time', str(VIDEO_PROCESSING_SETTINGS['hls']['segment_duration']),
                '-hls_playlist_type', VIDEO_PROCESSING_SETTINGS['hls']['playlist_type'],
                '-hls_segment_filename', segment_pattern,
                '-y',
                playlist_path
            ]
            
            logger.info(f"Generating HLS {level['name']}: {input_path}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            
            if result.returncode != 0:
                logger.error(f"HLS generation failed for {level['name']}: {result.stderr}")
                continue
            
            # Calculate approximate bandwidth
            bitrate_num = int(level['bitrate'].replace('k', '')) * 1000
            stream_info.append({
                'name': level['name'],
                'bandwidth': bitrate_num + 128000,  # Video + audio
                'resolution': f'{int(level["height"] * 16/9)}x{level["height"]}',
                'playlist': f'{level["name"]}/playlist.m3u8'
            })
            
            logger.info(f"HLS {level['name']} generated successfully")
        
        if not stream_info:
            logger.error("No HLS streams were generated successfully")
            return None
        
        # Create master playlist
        master_playlist_path = os.path.join(hls_dir, 'master.m3u8')
        with open(master_playlist_path, 'w') as f:
            f.write('#EXTM3U\n')
            f.write('#EXT-X-VERSION:3\n\n')
            
            for stream in sorted(stream_info, key=lambda x: x['bandwidth']):
                f.write(f'#EXT-X-STREAM-INF:BANDWIDTH={stream["bandwidth"]},RESOLUTION={stream["resolution"]},NAME="{stream["name"]}"\n')
                f.write(f'{stream["playlist"]}\n\n')
        
        logger.info(f"Master playlist created: {master_playlist_path}")
        return master_playlist_path
        
    except Exception as e:
        logger.error(f"Error generating HLS: {e}")
        return None


def generate_thumbnail(video_path, output_path, time_offset='00:00:05'):
    """
    Generate thumbnail from video.
    
    Args:
        video_path: Path to video file
        output_path: Path for output thumbnail
        time_offset: Time offset for thumbnail capture (HH:MM:SS)
        
    Returns:
        bool: True if successful
    """
    try:
        cmd = [
            get_ffmpeg_path(),
            '-i', video_path,
            '-ss', time_offset,
            '-vframes', '1',
            '-vf', 'scale=320:-1',  # 320px width, proportional height
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        return False


def process_video_for_streaming(tutorial):
    """
    Process a VideoTutorial for optimal streaming.
    This is the main function to call after a video is uploaded.
    
    Processing steps:
    1. Get video information
    2. Optimize original for streaming (faststart)
    3. Create compressed version
    4. Generate HLS streams (if video is large enough)
    5. Generate thumbnail if missing
    
    Args:
        tutorial: VideoTutorial model instance
        
    Returns:
        dict: Processing results
    """
    from django.core.files import File
    from django.conf import settings
    
    results = {
        'success': False,
        'optimized': False,
        'compressed': False,
        'hls_generated': False,
        'thumbnail_generated': False,
        'error': None,
        'original_size_mb': 0,
        'compressed_size_mb': 0,
    }
    
    if not tutorial.video_file:
        results['error'] = "No video file found"
        return results
    
    # Check FFmpeg availability
    if not is_ffmpeg_available():
        results['error'] = "FFmpeg is not installed or not in PATH"
        logger.warning("FFmpeg not available - video will not be processed")
        # Don't fail completely, just skip processing
        tutorial.processing_status = 'completed'
        tutorial.processing_error = "FFmpeg not available - using original file"
        tutorial.save(update_fields=['processing_status', 'processing_error'])
        results['success'] = True
        return results
    
    try:
        tutorial.processing_status = 'processing'
        tutorial.save(update_fields=['processing_status'])
        
        input_path = tutorial.video_file.path
        
        # Get video info
        video_info = get_video_info(input_path)
        if video_info:
            tutorial.duration_minutes = video_info.get('duration_minutes', 0) or None
        
        # Record original size
        original_size = os.path.getsize(input_path)
        results['original_size_mb'] = round(original_size / (1024 * 1024), 2)
        tutorial.original_size_mb = Decimal(str(results['original_size_mb']))
        
        # Create temp directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Get current settings
            proc_settings = get_processing_settings()
            
            # Step 1: Optimize for streaming (add faststart)
            optimized_filename = f"optimized_{os.path.basename(input_path)}"
            optimized_temp_path = os.path.join(temp_dir, optimized_filename)
            
            if optimize_for_streaming(input_path, optimized_temp_path):
                results['optimized'] = True
                
                # Save optimized version
                optimized_path = os.path.join('tutorials', 'videos', optimized_filename)
                full_optimized_path = os.path.join(settings.MEDIA_ROOT, optimized_path)
                os.makedirs(os.path.dirname(full_optimized_path), exist_ok=True)
                shutil.copy2(optimized_temp_path, full_optimized_path)
                tutorial.optimized_video.name = optimized_path
                
                optimized_size = os.path.getsize(full_optimized_path)
                tutorial.optimized_size_mb = Decimal(str(round(optimized_size / (1024 * 1024), 2)))
            
            # Step 2: Create compressed version (if file is large enough)
            compression_threshold = proc_settings.get('compression_min_size_mb', 50)
            if results['original_size_mb'] > compression_threshold:
                compressed_filename = f"compressed_{os.path.splitext(os.path.basename(input_path))[0]}.mp4"
                compressed_temp_path = os.path.join(temp_dir, compressed_filename)
                
                # Determine target height based on original and settings
                target_height = proc_settings.get('target_height', 720)
                if video_info and video_info.get('height', 0) <= target_height:
                    target_height = video_info['height']
                
                crf = proc_settings['compression'].get('crf', 23)
                if compress_video(input_path, compressed_temp_path, target_height=target_height, crf=crf):
                    results['compressed'] = True
                    
                    # Save compressed version
                    compressed_path = os.path.join('tutorials', 'videos', compressed_filename)
                    full_compressed_path = os.path.join(settings.MEDIA_ROOT, compressed_path)
                    shutil.copy2(compressed_temp_path, full_compressed_path)
                    tutorial.compressed_video.name = compressed_path
                    
                    compressed_size = os.path.getsize(full_compressed_path)
                    results['compressed_size_mb'] = round(compressed_size / (1024 * 1024), 2)
                    tutorial.compressed_size_mb = Decimal(str(results['compressed_size_mb']))
            
            # Step 3: Generate HLS for very large files (enables Netflix-like streaming)
            hls_threshold = proc_settings.get('hls_min_size_mb', 100)
            if results['original_size_mb'] > hls_threshold:
                source_for_hls = input_path
                if results['optimized']:
                    source_for_hls = os.path.join(settings.MEDIA_ROOT, tutorial.optimized_video.name)
                
                hls_result = generate_hls_stream(source_for_hls, settings.MEDIA_ROOT, str(tutorial.id))
                if hls_result:
                    results['hls_generated'] = True
            
            # Step 4: Generate thumbnail if missing
            if not tutorial.thumbnail:
                thumbnail_filename = f"thumb_{tutorial.id}.jpg"
                thumbnail_temp_path = os.path.join(temp_dir, thumbnail_filename)
                
                if generate_thumbnail(input_path, thumbnail_temp_path):
                    thumbnail_path = os.path.join('tutorials', 'thumbnails', thumbnail_filename)
                    full_thumbnail_path = os.path.join(settings.MEDIA_ROOT, thumbnail_path)
                    os.makedirs(os.path.dirname(full_thumbnail_path), exist_ok=True)
                    shutil.copy2(thumbnail_temp_path, full_thumbnail_path)
                    tutorial.thumbnail.name = thumbnail_path
                    results['thumbnail_generated'] = True
        
        # Mark as completed
        tutorial.processing_status = 'completed'
        tutorial.processing_error = ''
        results['success'] = True
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        tutorial.processing_status = 'failed'
        tutorial.processing_error = str(e)
        results['error'] = str(e)
    
    finally:
        tutorial.save()
    
    return results


def cleanup_hls_files(tutorial_id):
    """
    Clean up HLS files for a tutorial.
    
    Args:
        tutorial_id: Tutorial UUID
    """
    from django.conf import settings
    hls_dir = os.path.join(settings.MEDIA_ROOT, 'tutorials', 'hls', str(tutorial_id))
    if os.path.exists(hls_dir):
        shutil.rmtree(hls_dir)
        logger.info(f"Cleaned up HLS files for tutorial {tutorial_id}")
