"""
Video streaming utilities for efficient video delivery over network.
Implements HTTP Range Requests (RFC 7233) for progressive video streaming.

Features:
- HTTP Range Requests for instant seeking
- Large chunk sizes (256KB) for smooth streaming
- Aggressive caching for better performance
- HLS playlist support for adaptive bitrate streaming
"""

import os
import re
import json
from django.http import StreamingHttpResponse, HttpResponse, Http404, FileResponse
from django.shortcuts import get_object_or_404
from wsgiref.util import FileWrapper
from django.conf import settings

# Optimal chunk size for network streaming (256KB)
# Larger chunks = fewer requests = smoother playback
STREAM_CHUNK_SIZE = 256 * 1024  # 256KB chunks for smooth streaming


class RangeFileWrapper:
    """
    Wrapper for file-like objects to support range requests.
    Allows streaming specific byte ranges of large files.
    Uses larger chunk sizes (256KB) for efficient network transfer.
    """
    def __init__(self, filelike, blksize=STREAM_CHUNK_SIZE, offset=0, length=None):
        self.filelike = filelike
        self.filelike.seek(offset, os.SEEK_SET)
        self.remaining = length
        self.blksize = blksize

    def close(self):
        if hasattr(self.filelike, 'close'):
            self.filelike.close()

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining is None:
            # Read entire file
            data = self.filelike.read(self.blksize)
            if data:
                return data
            raise StopIteration()
        else:
            if self.remaining <= 0:
                raise StopIteration()
            data = self.filelike.read(min(self.remaining, self.blksize))
            if not data:
                raise StopIteration()
            self.remaining -= len(data)
            return data


def parse_range_header(range_header, file_size):
    """
    Parse HTTP Range header and return start and end byte positions.
    
    Args:
        range_header: String like "bytes=0-1023" or "bytes=1024-"
        file_size: Total size of the file in bytes
        
    Returns:
        Tuple of (start, end, length) or None if invalid
    """
    if not range_header:
        return None
        
    # Match pattern: bytes=start-end or bytes=start-
    match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        return None
    
    start = int(match.group(1))
    end = match.group(2)
    
    if end:
        end = int(end)
    else:
        end = file_size - 1
    
    # Validate range
    if start >= file_size or start < 0:
        return None
    
    if end >= file_size:
        end = file_size - 1
    
    if start > end:
        return None
    
    length = end - start + 1
    return start, end, length


def stream_video(request, video_file_path, content_type='video/mp4'):
    """
    Stream video file with support for HTTP Range Requests.
    Optimized for Netflix-like smooth streaming over network.
    
    Features:
    - Progressive video loading (start playing before full download)
    - Instant seeking/scrubbing anywhere in the video
    - Bandwidth optimization with large chunks
    - Aggressive caching for better performance
    - Better user experience on slow networks
    
    Args:
        request: Django HttpRequest object
        video_file_path: Absolute path to video file
        content_type: MIME type of the video
        
    Returns:
        StreamingHttpResponse with appropriate headers
    """
    # Check if file exists
    if not os.path.exists(video_file_path):
        raise Http404("Video file not found")
    
    # Get file size
    file_size = os.path.getsize(video_file_path)
    
    # Get Range header from request
    range_header = request.META.get('HTTP_RANGE', '').strip()
    
    # Open file in binary mode with buffering
    video_file = open(video_file_path, 'rb', buffering=STREAM_CHUNK_SIZE)
    
    if range_header:
        # Parse range request
        range_data = parse_range_header(range_header, file_size)
        
        if range_data:
            start, end, length = range_data
            
            # Create response with partial content using large chunks
            response = StreamingHttpResponse(
                RangeFileWrapper(video_file, blksize=STREAM_CHUNK_SIZE, offset=start, length=length),
                status=206,  # Partial Content
                content_type=content_type
            )
            
            # Set Content-Range header
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Content-Length'] = str(length)
            response['Accept-Ranges'] = 'bytes'
            
        else:
            # Invalid range, return full file
            response = StreamingHttpResponse(
                RangeFileWrapper(video_file, blksize=STREAM_CHUNK_SIZE),
                content_type=content_type
            )
            response['Content-Length'] = str(file_size)
            response['Accept-Ranges'] = 'bytes'
    else:
        # No range request - still use large chunks for initial load
        response = StreamingHttpResponse(
            RangeFileWrapper(video_file, blksize=STREAM_CHUNK_SIZE),
            content_type=content_type
        )
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
    
    # Aggressive caching headers for better performance
    # Cache for 24 hours, allow proxies to cache
    response['Cache-Control'] = 'public, max-age=86400, immutable'
    
    # Add headers to prevent download and force inline viewing
    response['Content-Disposition'] = 'inline'
    
    # Add ETag for efficient cache validation
    import hashlib
    file_stat = os.stat(video_file_path)
    etag = hashlib.md5(f"{file_stat.st_size}-{file_stat.st_mtime}".encode()).hexdigest()
    response['ETag'] = f'"{etag}"'
    
    return response


def get_video_content_type(file_path):
    """
    Determine video content type from file extension.
    
    Args:
        file_path: Path to video file
        
    Returns:
        MIME type string
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    content_types = {
        '.mp4': 'video/mp4',
        '.webm': 'video/webm',
        '.ogg': 'video/ogg',
        '.ogv': 'video/ogg',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.wmv': 'video/x-ms-wmv',
        '.flv': 'video/x-flv',
        '.mkv': 'video/x-matroska',
    }
    
    return content_types.get(ext, 'video/mp4')


def stream_hls_playlist(request, hls_playlist_path):
    """
    Stream HLS playlist file (.m3u8).
    
    Args:
        request: Django HttpRequest object
        hls_playlist_path: Absolute path to .m3u8 file
        
    Returns:
        HttpResponse with HLS playlist
    """
    if not os.path.exists(hls_playlist_path):
        raise Http404("HLS playlist not found")
    
    with open(hls_playlist_path, 'r') as f:
        content = f.read()
    
    response = HttpResponse(content, content_type='application/vnd.apple.mpegurl')
    response['Cache-Control'] = 'public, max-age=60'  # Cache playlist for 1 minute
    response['Access-Control-Allow-Origin'] = '*'
    
    return response


def stream_hls_segment(request, segment_path):
    """
    Stream HLS segment file (.ts).
    
    Args:
        request: Django HttpRequest object
        segment_path: Absolute path to .ts segment file
        
    Returns:
        StreamingHttpResponse with segment data
    """
    if not os.path.exists(segment_path):
        raise Http404("HLS segment not found")
    
    file_size = os.path.getsize(segment_path)
    video_file = open(segment_path, 'rb', buffering=STREAM_CHUNK_SIZE)
    
    response = StreamingHttpResponse(
        RangeFileWrapper(video_file, blksize=STREAM_CHUNK_SIZE),
        content_type='video/mp2t'
    )
    
    response['Content-Length'] = str(file_size)
    # Cache segments aggressively - they never change
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    response['Access-Control-Allow-Origin'] = '*'
    
    return response


def get_hls_directory(tutorial_id):
    """
    Get the HLS directory path for a tutorial.
    
    Args:
        tutorial_id: UUID of the tutorial
        
    Returns:
        Path to HLS directory
    """
    return os.path.join(settings.MEDIA_ROOT, 'tutorials', 'hls', str(tutorial_id))


def has_hls_stream(tutorial_id):
    """
    Check if HLS stream exists for a tutorial.
    
    Args:
        tutorial_id: UUID of the tutorial
        
    Returns:
        Boolean indicating if HLS stream exists
    """
    hls_dir = get_hls_directory(tutorial_id)
    master_playlist = os.path.join(hls_dir, 'master.m3u8')
    return os.path.exists(master_playlist)


def get_hls_master_playlist_path(tutorial_id):
    """
    Get the path to the HLS master playlist.
    
    Args:
        tutorial_id: UUID of the tutorial
        
    Returns:
        Path to master.m3u8 or None if doesn't exist
    """
    hls_dir = get_hls_directory(tutorial_id)
    master_playlist = os.path.join(hls_dir, 'master.m3u8')
    if os.path.exists(master_playlist):
        return master_playlist
    return None

