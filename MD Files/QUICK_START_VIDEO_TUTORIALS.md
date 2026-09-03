# Quick Start Guide - Video Tutorials Feature

## For Administrators

### Step 1: Access Admin Panel
```
URL: http://127.0.0.1:8011/admin/
Navigate to: Scheduler > Video Tutorials
```

### Step 2: Add Your First Video
1. Click "Add Video Tutorial" button
2. Fill in the form:
   - **Title**: "Getting Started with iDRS"
   - **Description**: "Learn the basics..."
   - **Category**: Select "Getting Started"
   - **Video File**: Upload your MP4 file (max 1GB)
   - **Thumbnail**: Upload a 16:9 image (optional)
   - **Duration**: Enter duration in minutes
   - **Order**: 1 (appears first in category)
   - **Is Active**: ✓ Check this box
3. Click "Save"

### Step 3: Verify Upload
1. Go to: http://127.0.0.1:8011/tutorials/
2. Your video should appear in the "Getting Started" category
3. Click to play and verify it works

## For Users

### Accessing Tutorials
1. Log in to iDRS
2. Look in the sidebar under "Help & Support"
3. Click "Video Tutorials"
4. Browse by category and click any video to watch

## Quick Commands

### Create Sample Placeholders (Optional)
```bash
.venv/bin/python manage.py create_sample_tutorials
```
This creates placeholder entries to show the structure. You'll still need to upload actual videos.

### Check Media Directory
```bash
ls -la media/tutorials/videos/
ls -la media/tutorials/thumbnails/
```

## Video Preparation Tips

### Convert Video to MP4 (if needed)
Using FFmpeg:
```bash
ffmpeg -i input.mov -c:v libx264 -c:a aac -movflags +faststart output.mp4
```

### Create Thumbnail from Video
```bash
ffmpeg -i video.mp4 -ss 00:00:05 -vframes 1 -vf scale=1280:720 thumbnail.jpg
```

### Compress Large Videos
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output.mp4
```

## Troubleshooting

### "File too large" error
- Check file size: `ls -lh video.mp4`
- Must be under 1GB (1024 MB)
- Compress if needed using FFmpeg

### Video won't play in browser
- Ensure format is MP4 with H.264 codec
- Test in different browser
- Check browser console for errors

### Thumbnail not showing
- Verify Pillow is installed: `.venv/bin/pip list | grep Pillow`
- Check image format (JPG or PNG only)
- Verify aspect ratio is 16:9

### Permission denied
```bash
chmod -R 755 media/tutorials/
```

## Best Practices

1. **Keep videos short**: 5-15 minutes per topic
2. **Use clear titles**: "How to Create a Schedule" not "Tutorial 1"
3. **Add descriptions**: Help users find what they need
4. **Test before activating**: Upload, watch, then activate
5. **Organize logically**: Use order field to sequence tutorials
6. **Update regularly**: Keep content current with app changes

## Categories Guide

- **Getting Started**: First-time user orientation
- **Scheduling**: Schedule creation and management
- **Data Management**: Wells, rigs, norms configuration
- **Reports & Analytics**: Reports and data analysis
- **Admin Features**: User management, system config
- **Other**: Everything else

## URLs Reference

- **Tutorials List**: `/tutorials/`
- **Admin Panel**: `/admin/scheduler/videotutorial/`
- **Media Files**: `/media/tutorials/videos/`
- **Thumbnails**: `/media/tutorials/thumbnails/`

## Support

For issues or questions:
1. Check Django logs: `logs/django.log`
2. Check browser console for JavaScript errors
3. Verify media files are accessible
4. Review settings in `drilling_scheduler/settings.py`

## Next Steps

1. Upload your first video tutorial
2. Test playback on different devices
3. Gather user feedback
4. Add more tutorials based on common questions
5. Consider adding video transcripts for accessibility
