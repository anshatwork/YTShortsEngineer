"""
Audio API Integration
Smart 4-tier fallback system for background audio selection.
Tier 1: Local cache → Tier 2: Pixabay API → Tier 3: Freesound API → Tier 4: Silent/Generic
"""

import os
import requests
import random
import logging
from pathlib import Path
from typing import Optional
from core.audio_themes import AudioTheme
from core.audio_theme_map import get_search_queries_for_theme

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioFetcher:
    """
    Smart audio fetcher with 4-tier fallback strategy.
    
    Fallback order:
    1. Check local cache (assets/audio_cache/<theme>/)
    2. Query Pixabay API (free, 500 req/hour)
    3. Query Freesound API (free, unlimited with attribution)
    4. Return None for silent/generic fallback
    """
    
    def __init__(self):
        """Initialize audio fetcher with cache directory and API keys."""
        self.cache_dir = Path("assets/audio_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # API keys from environment
        self.pixabay_key = os.getenv("PIXABAY_API_KEY")
        self.freesound_key = os.getenv("FREESOUND_API_KEY")
        
        # Cache size limit (MB)
        self.max_cache_size_mb = int(os.getenv("AUDIO_CACHE_MAX_SIZE_MB", "500"))
    
    def fetch_audio_for_theme(self, theme: AudioTheme) -> Optional[str]:
        """
        Fetch audio file for theme using 4-tier fallback.
        
        Args:
            theme: Audio theme enum
            
        Returns:
            Path to audio file or None if all tiers fail
        """
        logger.info(f"Fetching audio for theme: {theme.value}")
        
        # Tier 1: Check local cache
        cached = self._check_cache(theme)
        if cached:
            logger.info(f"✓ Tier 1 (Cache): Found {cached}")
            return cached
        
        # Tier 2: Try Pixabay
        if self.pixabay_key:
            logger.info("Tier 1 (Cache): Miss → Trying Tier 2 (Pixabay)")
            pixabay_file = self._fetch_from_pixabay(theme)
            if pixabay_file:
                cached_path = self._cache_audio(theme, pixabay_file)
                logger.info(f"✓ Tier 2 (Pixabay): Downloaded and cached {cached_path}")
                return cached_path
        else:
            logger.warning("Pixabay API key not set, skipping Tier 2")
        
        # Tier 3: Try Freesound
        if self.freesound_key:
            logger.info("Tier 2 (Pixabay): Miss → Trying Tier 3 (Freesound)")
            freesound_file = self._fetch_from_freesound(theme)
            if freesound_file:
                cached_path = self._cache_audio(theme, freesound_file)
                logger.info(f"✓ Tier 3 (Freesound): Downloaded and cached {cached_path}")
                return cached_path
        else:
            logger.warning("Freesound API key not set, skipping Tier 3")
        
        # Tier 4: Fallback to None (silent/generic)
        logger.warning(f"✗ All tiers failed for theme '{theme.value}' → Proceeding without background audio")
        return None
    
    def _check_cache(self, theme: AudioTheme) -> Optional[str]:
        """
        Check if theme audio exists in local cache.
        
        Args:
            theme: Audio theme enum
            
        Returns:
            Path to random cached audio file or None
        """
        theme_dir = self.cache_dir / theme.value
        if theme_dir.exists() and theme_dir.is_dir():
            # Find all audio files
            audio_files = list(theme_dir.glob("*.mp3")) + list(theme_dir.glob("*.wav"))
            if audio_files:
                # Return random cached file for variety
                return str(random.choice(audio_files))
        return None
    
    def _fetch_from_pixabay(self, theme: AudioTheme) -> Optional[str]:
        """
        Fetch audio from Pixabay API.
        
        Args:
            theme: Audio theme enum
            
        Returns:
            Path to downloaded file or None
        """
        try:
            # Get search queries for theme
            queries = get_search_queries_for_theme(theme)
            query = queries[0] if queries else "background music"
            
            url = "https://pixabay.com/api/"
            params = {
                "key": self.pixabay_key,
                "q": query,
                "type": "music",
                "per_page": 5,
                "order" : "popular"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("hits") and len(data["hits"]) > 0:
                # Get first result's preview URL
                audio_url = data["hits"][0].get("previewURL")
                if audio_url:
                    return self._download_audio(audio_url, theme)
            
            logger.warning(f"No Pixabay results for query: {query}")
            return None
            
        except Exception as e:
            logger.warning(f"Pixabay fetch failed: {e}")
            return None
    
    def _fetch_from_freesound(self, theme: AudioTheme) -> Optional[str]:
        """
        Fetch audio from Freesound API.
        
        Args:
            theme: Audio theme enum
            
        Returns:
            Path to downloaded file or None
        """
        try:
            # Get search queries for theme
            queries = get_search_queries_for_theme(theme)
            query = queries[0] if queries else "background music"
            
            # Freesound API search endpoint
            search_url = "https://freesound.org/apiv2/search/text/"
            params = {
                "query": query,
                "token": self.freesound_key,
                "fields": "id,name,previews",
                "page_size": 5,
                "filter": "duration:[10.0 TO 60.0]"  # 10-60 second clips
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("results") and len(data["results"]) > 0:
                # Get first result's preview URL (high quality MP3)
                result = data["results"][0]
                preview_url = result.get("previews", {}).get("preview-hq-mp3")
                
                if preview_url:
                    return self._download_audio(preview_url, theme)
            
            logger.warning(f"No Freesound results for query: {query}")
            return None
            
        except Exception as e:
            logger.warning(f"Freesound fetch failed: {e}")
            return None
    
    def _download_audio(self, url: str, theme: AudioTheme) -> Optional[str]:
        """
        Download audio file from URL.
        
        Args:
            url: Audio file URL
            theme: Audio theme (for filename)
            
        Returns:
            Path to downloaded file or None
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Create temp file
            import tempfile
            import hashlib
            
            # Generate unique filename based on URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            extension = ".mp3"  # Default to MP3
            
            # Detect extension from URL or content-type
            if ".wav" in url.lower():
                extension = ".wav"
            
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=extension,
                prefix=f"{theme.value}_{url_hash}_"
            )
            
            temp_file.write(response.content)
            temp_file.close()
            
            logger.info(f"Downloaded audio to {temp_file.name}")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Audio download failed: {e}")
            return None
    
    def _cache_audio(self, theme: AudioTheme, audio_file: str) -> str:
        """
        Move downloaded audio to cache directory.
        
        Args:
            theme: Audio theme
            audio_file: Path to downloaded file
            
        Returns:
            Path to cached file
        """
        theme_dir = self.cache_dir / theme.value
        theme_dir.mkdir(exist_ok=True)
        
        # Move file to cache
        cached_path = theme_dir / Path(audio_file).name
        Path(audio_file).rename(cached_path)
        
        logger.info(f"Cached audio to {cached_path}")
        return str(cached_path)
    
    def cleanup_cache(self):
        """
        Remove oldest cached files if cache exceeds size limit.
        Implements LRU (Least Recently Used) cleanup.
        """
        try:
            # Calculate total cache size
            total_size = 0
            files_with_mtime = []
            
            for audio_file in self.cache_dir.rglob("*.mp3"):
                size = audio_file.stat().st_size
                mtime = audio_file.stat().st_mtime
                total_size += size
                files_with_mtime.append((audio_file, size, mtime))
            
            for audio_file in self.cache_dir.rglob("*.wav"):
                size = audio_file.stat().st_size
                mtime = audio_file.stat().st_mtime
                total_size += size
                files_with_mtime.append((audio_file, size, mtime))
            
            total_size_mb = total_size / (1024 * 1024)
            
            if total_size_mb > self.max_cache_size_mb:
                logger.info(f"Cache size ({total_size_mb:.1f}MB) exceeds limit ({self.max_cache_size_mb}MB), cleaning up...")
                
                # Sort by modification time (oldest first)
                files_with_mtime.sort(key=lambda x: x[2])
                
                # Remove oldest files until under limit
                for audio_file, size, _ in files_with_mtime:
                    if total_size_mb <= self.max_cache_size_mb:
                        break
                    
                    audio_file.unlink()
                    total_size_mb -= size / (1024 * 1024)
                    logger.info(f"Removed {audio_file.name} ({size / (1024 * 1024):.1f}MB)")
                
                logger.info(f"Cache cleanup complete. New size: {total_size_mb:.1f}MB")
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
