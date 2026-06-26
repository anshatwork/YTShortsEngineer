"use client";

import { useEffect, useState } from "react";

/**
 * Extracts a randomly-selected frame from a video URL using a hidden
 * <video> + <canvas> pipeline. Returns a JPEG data URL once ready, or
 * null while loading / on error (e.g. CORS, decode failure).
 *
 * clipDuration: the length of the clip in seconds, used to pick a random
 * seek time. The actual video.duration is preferred once metadata loads.
 */
export function useThumbnail(
  videoUrl: string | null,
  clipDuration: number,
): string | null {
  const [thumbnail, setThumbnail] = useState<string | null>(null);

  useEffect(() => {
    if (!videoUrl) return;

    let cancelled = false;
    const video = document.createElement("video");
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    video.crossOrigin = "anonymous";
    video.preload = "metadata";
    video.muted = true;

    const onMetadata = () => {
      if (cancelled) return;
      const duration = video.duration > 0 ? video.duration : clipDuration;
      video.currentTime = Math.random() * duration;
    };

    const onSeeked = () => {
      if (cancelled || !ctx) return;
      try {
        canvas.width = video.videoWidth || 1080;
        canvas.height = video.videoHeight || 1920;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        setThumbnail(canvas.toDataURL("image/jpeg", 0.8));
      } catch {
        // tainted canvas or decode failure — leave thumbnail null
      }
    };

    video.addEventListener("loadedmetadata", onMetadata);
    video.addEventListener("seeked", onSeeked);
    video.src = videoUrl;

    return () => {
      cancelled = true;
      video.removeEventListener("loadedmetadata", onMetadata);
      video.removeEventListener("seeked", onSeeked);
      video.src = "";
    };
  }, [videoUrl, clipDuration]);

  return thumbnail;
}
