"""
YouTube Video Downloader - Flask Backend
Downloads YouTube videos in highest quality with audio using yt-dlp
"""

from flask import Flask, render_template, request, jsonify, send_file, make_response
from flask_cors import CORS
import yt_dlp
import os
import re
import threading
import uuid
import time
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Store download progress and status
downloads = {}

# Download directory
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


def sanitize_filename(filename):
    """Remove invalid characters and emojis from filename"""
    # Remove Windows invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove emojis and other non-ASCII characters that cause issues
    filename = ''.join(c for c in filename if ord(c) < 65536 and (ord(c) < 0x1F600 or ord(c) > 0x1FAFF))
    # Remove any remaining problematic Unicode characters (emojis in various ranges)
    filename = re.sub(r'[\U00010000-\U0010ffff]', '', filename)
    # Clean up extra spaces
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def progress_hook(d, download_id):
    """Track download progress"""
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            percent = (downloaded / total) * 100
            downloads[download_id]['progress'] = round(percent, 1)
            downloads[download_id]['speed'] = d.get('speed', 0)
            downloads[download_id]['eta'] = d.get('eta', 0)
    elif d['status'] == 'finished':
        downloads[download_id]['progress'] = 100
        downloads[download_id]['status'] = 'processing'


def download_video(url, download_id, quality_height=0):
    """Download video in a separate thread
    
    Args:
        url: YouTube video URL
        download_id: Unique ID for tracking this download
        quality_height: Video height (e.g., 1080, 720, 480). 0 means audio only.
    """
    try:
        downloads[download_id] = {
            'status': 'starting',
            'progress': 0,
            'title': '',
            'filename': '',
            'error': None,
            'speed': 0,
            'eta': 0
        }
        
        # Build format string based on quality
        if quality_height == 0:
            # Audio only - extract as MP3
            format_str = 'bestaudio/best'
            output_template = str(DOWNLOAD_DIR / '%(title)s.%(ext)s')
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        else:
            # Video with specific height
            format_str = f'bestvideo[height<={quality_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality_height}]+bestaudio/best[height<={quality_height}]/best'
            output_template = str(DOWNLOAD_DIR / '%(title)s.%(ext)s')
            postprocessors = []
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': format_str,
            'merge_output_format': 'mp4' if quality_height > 0 else None,
            'outtmpl': output_template,
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'retries': 10,
            'file_access_retries': 10,
            'fragment_retries': 10,
        }

        # Check for cookies file (Render Secret File or local)
        # Render mounts secret files at /etc/secrets/
        cookie_locations = [
            '/etc/secrets/cookies.txt',  # Render production path
            'cookies.txt'                # Local development path
        ]
        
        for cookie_path in cookie_locations:
            if os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path
                print(f"Using cookies from: {cookie_path}")
                break
        
        if postprocessors:
            ydl_opts['postprocessors'] = postprocessors
        
        # Remove None values
        ydl_opts = {k: v for k, v in ydl_opts.items() if v is not None}
        
        # First, get video info
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'video'))
            downloads[download_id]['title'] = title
            downloads[download_id]['thumbnail'] = info.get('thumbnail', '')
            downloads[download_id]['duration'] = info.get('duration', 0)
            downloads[download_id]['status'] = 'downloading'
        
        # Download the video with retry logic for Windows file locking
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    # For audio, the extension changes to mp3
                    if quality_height == 0:
                        filename = filename.rsplit('.', 1)[0] + '.mp3'
                    downloads[download_id]['filename'] = filename
                    downloads[download_id]['status'] = 'completed'
                    downloads[download_id]['progress'] = 100
                    return  # Success, exit the function
            except Exception as e:
                last_error = e
                error_str = str(e)
                # Check if it's a file access error (Windows file locking)
                if 'WinError 32' in error_str or 'being used by another process' in error_str:
                    if attempt < max_retries - 1:
                        # Wait before retry (exponential backoff)
                        time.sleep(2 ** attempt)
                        downloads[download_id]['status'] = 'retrying'
                        continue
                # If not a file lock error or max retries reached, raise
                raise
        
        # If we get here, all retries failed
        raise last_error
            
    except Exception as e:
        downloads[download_id]['status'] = 'error'
        downloads[download_id]['error'] = str(e)


@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Get video information without downloading"""
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        # Check for cookies file (Render Secret File or local)
        cookie_locations = [
            '/etc/secrets/cookies.txt',  # Render production path
            'cookies.txt'                # Local development path
        ]
        
        for cookie_path in cookie_locations:
            if os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path
                break
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get available quality options
            quality_options = []
            seen_heights = set()
            
            if info.get('formats'):
                # Sort formats by height (resolution) in descending order
                video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('height')]
                video_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
                
                for f in video_formats:
                    height = f.get('height', 0)
                    if height and height not in seen_heights:
                        seen_heights.add(height)
                        
                        # Create quality label
                        if height >= 2160:
                            label = f"4K ({height}p)"
                        elif height >= 1440:
                            label = f"2K ({height}p)"
                        else:
                            label = f"{height}p"
                        
                        # Estimate file size if available
                        filesize = f.get('filesize') or f.get('filesize_approx') or 0
                        
                        quality_options.append({
                            'height': height,
                            'label': label,
                            'filesize': filesize,
                            'format_note': f.get('format_note', '')
                        })
            
            # Add audio-only option
            quality_options.append({
                'height': 0,
                'label': 'Audio Only (MP3)',
                'filesize': 0,
                'format_note': 'audio'
            })
            
            return jsonify({
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('channel', info.get('uploader', 'Unknown')),
                'views': info.get('view_count', 0),
                'description': info.get('description', '')[:500],
                'qualities': quality_options
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a video download"""
    data = request.json
    url = data.get('url', '')
    quality_height = data.get('quality')  # None if not specified
    
    # Handle quality parameter
    # quality = 0 means audio only (MP3)
    # quality = None or not specified means best quality (highest resolution)
    # quality > 0 means specific video resolution
    if quality_height is None:
        quality_height = 4320  # Best quality - max out at 8K
    elif quality_height > 4320:
        quality_height = 4320  # Cap at 8K
    # Note: quality_height = 0 is valid and means audio-only
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    download_id = str(uuid.uuid4())
    
    # Start download in background thread
    thread = threading.Thread(target=download_video, args=(url, download_id, quality_height))
    thread.daemon = True
    thread.start()
    
    return jsonify({'download_id': download_id})


@app.route('/api/progress/<download_id>')
def get_progress(download_id):
    """Get download progress"""
    if download_id not in downloads:
        return jsonify({'error': 'Download not found'}), 404
    
    return jsonify(downloads[download_id])


@app.route('/api/file/<download_id>')
def get_file(download_id):
    """Download the completed file"""
    if download_id not in downloads:
        return jsonify({'error': 'Download not found'}), 404
    
    download = downloads[download_id]
    
    if download['status'] != 'completed':
        return jsonify({'error': 'Download not completed'}), 400
    
    if not os.path.exists(download['filename']):
        return jsonify({'error': 'File not found'}), 404
    
    filename = os.path.basename(download['filename'])
    
    # Determine file type and set appropriate MIME type
    if filename.lower().endswith('.mp3'):
        mimetype = 'audio/mpeg'
    else:
        mimetype = 'video/mp4'
        # Ensure video files have .mp4 extension
        if not filename.lower().endswith('.mp4'):
            filename = filename + '.mp4'
    
    # Create ASCII-safe version for basic filename parameter
    ascii_filename = ''.join(c if ord(c) < 128 else '_' for c in filename)
    
    # Use urllib to properly encode the filename for UTF-8 version
    from urllib.parse import quote
    encoded_filename = quote(filename)
    
    response = make_response(send_file(download['filename'], mimetype=mimetype))
    # Include both ASCII filename and UTF-8 encoded filename* for maximum compatibility
    response.headers['Content-Disposition'] = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
    response.headers['Content-Type'] = mimetype
    return response


@app.route('/api/downloads')
def list_downloads():
    """List all downloads in the downloads folder"""
    files = []
    for f in DOWNLOAD_DIR.glob('*.mp4'):
        files.append({
            'name': f.name,
            'size': f.stat().st_size,
            'modified': f.stat().st_mtime
        })
    return jsonify(files)


if __name__ == '__main__':
    print("\n" + "="*60)
    print(" YouTube Video Downloader")
    print("="*60)
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n Open your browser and go to: http://localhost:{port}")
    print("\n Press Ctrl+C to stop the server\n")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host=host, port=port, threaded=True)
