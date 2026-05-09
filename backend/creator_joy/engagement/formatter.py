from typing import Any
from .benchmarks import benchmark_comparison


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "not available"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def format_metrics_for_system_prompt(videos: list[dict[str, Any]]) -> str:
    """
    Formats a list of video metrics into a readable block for the LLM system prompt.
    Expected keys in each video dict: 
    - title, role, view_count, like_count, comment_count, duration_seconds,
    - er_views, channel_follower_count, platform, video_age_days,
    - heatmap_peak_intensity
    """
    lines = ["## Video Analytics", ""]
    
    for i, video in enumerate(videos):
        label = chr(ord('A') + i)
        title = video.get("title", "Unknown Title")
        role = (video.get("role") or "UNKNOWN ROLE").upper()
        
        views = video.get("view_count")
        likes = video.get("like_count")
        comments = video.get("comment_count")
        duration = format_duration(video.get("duration_seconds"))
        
        er_v = video.get("er_views")
        followers = video.get("channel_follower_count")
        platform = video.get("platform", "youtube")
        age = video.get("video_age_days")
        
        heatmap_peak = video.get("heatmap_peak_intensity")
        
        # Benchmarking
        comparison = {}
        if er_v is not None:
            comparison = benchmark_comparison(er_v, followers, platform)
        
        tier = comparison.get("tier", "unknown")
        assessment = comparison.get("assessment", "unknown")
        median = comparison.get("benchmark_median", "?")
        
        views_str = f"{views:,}" if views is not None else "not available"
        likes_str = f"{likes:,}" if likes is not None else "not available"
        comments_str = f"{comments:,}" if comments is not None else "not available"

        lines.append(f'VIDEO {label} — "{title}" ({role})')
        lines.append(f"  Views: {views_str} | "
                     f"Likes: {likes_str} | "
                     f"Comments: {comments_str} | "
                     f"Duration: {duration}")

        
        er_str = f"{er_v:.2f}%" if er_v is not None else "not available"
        lines.append(f"  ER (views): {er_str} | Tier: {tier} | Assessment: {assessment} (median {median}%)")
        
        f_str = f"{followers:,}" if followers is not None else "not available"
        age_str = f"{age} days ago" if age is not None else "date not available"
        lines.append(f"  Follower base: {f_str} | Uploaded: {age_str}")
        
        hp_str = f"{heatmap_peak:.2f}" if heatmap_peak is not None else "not available"
        lines.append(f"  Heatmap peak: {hp_str}")
        lines.append("")
        
    return "\n".join(lines)
