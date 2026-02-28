# YouTube Download 403 Error - Solutions

## Issue
YouTube is blocking downloads with "HTTP Error 403: Forbidden" due to bot detection.

## Solutions Applied

### 1. Enhanced yt-dlp Configuration ✅
Updated `tools/youtube/downloader.py` with:
- User-Agent spoofing (mimics Chrome browser)
- Proper HTTP headers (Accept, Referer, etc.)
- Android + Web player clients for better compatibility
- Retry logic (10 retries for both full downloads and fragments)
- Better error handling with specific 403 detection

### 2. Updated yt-dlp Version ✅
Updated `requirements.txt` to use `yt-dlp>=2024.12.23` (latest version with better YouTube support)

## How to Apply the Fix

1. **Update yt-dlp to the latest version:**
   ```bash
   pip install --upgrade yt-dlp
   ```

2. **Verify the version:**
   ```bash
   yt-dlp --version
   ```

3. **Test the download again:**
   ```bash
   python test_modular_nodes.py
   ```

## Additional Solutions (If Still Failing)

### Option A: Use Cookies (Recommended for persistent issues)
If you're still getting 403 errors, you can use your browser's YouTube cookies:

1. **Export cookies from your browser:**
   - Install a browser extension like "Get cookies.txt LOCALLY"
   - Visit YouTube while logged in
   - Export cookies to `cookies.txt` in your project root

2. **Update the downloader to use cookies:**
   Add this to `ydl_opts` in `tools/youtube/downloader.py`:
   ```python
   "cookiefile": "cookies.txt",
   ```

### Option B: Use OAuth Authentication
For production use, consider using YouTube Data API v3 for downloads instead of yt-dlp.

### Option C: Add Delays Between Downloads
If downloading multiple videos, add delays to avoid rate limiting:
```python
import time
time.sleep(2)  # Wait 2 seconds between downloads
```

## Testing
After applying the fix, test with:
```bash
python test_modular_nodes.py
```

## Notes
- YouTube frequently updates their bot detection
- Keep yt-dlp updated regularly: `pip install --upgrade yt-dlp`
- The 403 error may also occur due to:
  - Rate limiting (too many requests)
  - Geographic restrictions
  - Age-restricted or private videos
  - YouTube server issues
