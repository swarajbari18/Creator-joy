from datetime import date, datetime
from typing import Optional, Any


def parse_upload_date(upload_date: Optional[str]) -> Optional[date]:
    """Parse yt-dlp's YYYYMMDD string into a date object."""
    if upload_date is None:
        return None
    try:
        # yt-dlp format is YYYYMMDD
        return datetime.strptime(upload_date, "%Y%m%d").date()
    except ValueError:
        return None


def days_since_upload(upload_date: Optional[str]) -> Optional[int]:
    """Number of days between upload and today."""
    d = parse_upload_date(upload_date)
    if d is None:
        return None
    return max(0, (date.today() - d).days)


def er_views(
    like_count: Optional[int],
    comment_count: Optional[int],
    view_count: Optional[int],
) -> Optional[float]:
    """
    Primary engagement rate: (likes + comments) / views * 100
    """
    if not view_count or view_count == 0:
        return None
    
    likes = like_count or 0
    comments = comment_count or 0
    
    return ((likes + comments) / view_count) * 100


def er_followers(
    like_count: Optional[int],
    comment_count: Optional[int],
    follower_count: Optional[int],
) -> Optional[float]:
    """
    Secondary engagement rate: (likes + comments) / followers * 100
    """
    if not follower_count or follower_count == 0:
        return None
    
    likes = like_count or 0
    comments = comment_count or 0
    
    return ((likes + comments) / follower_count) * 100


def like_rate(like_count: Optional[int], view_count: Optional[int]) -> Optional[float]:
    if not view_count or view_count == 0 or like_count is None:
        return None
    return (like_count / view_count) * 100


def comment_rate(comment_count: Optional[int], view_count: Optional[int]) -> Optional[float]:
    if not view_count or view_count == 0 or comment_count is None:
        return None
    return (comment_count / view_count) * 100


def like_to_comment_ratio(like_count: Optional[int], comment_count: Optional[int]) -> Optional[float]:
    if not comment_count or comment_count == 0 or like_count is None:
        return None
    return like_count / comment_count


def er_per_minute(er_v: Optional[float], duration_seconds: Optional[int]) -> Optional[float]:
    if er_v is None or not duration_seconds or duration_seconds == 0:
        return None
    return er_v / (duration_seconds / 60)


def views_per_minute(view_count: Optional[int], duration_seconds: Optional[int]) -> Optional[float]:
    if not view_count or not duration_seconds or duration_seconds == 0:
        return None
    return view_count / (duration_seconds / 60)


def engagement_velocity(
    like_count: Optional[int],
    comment_count: Optional[int],
    video_age_days: Optional[int],
) -> Optional[float]:
    if video_age_days is None or video_age_days == 0:
        return None
    
    likes = like_count or 0
    comments = comment_count or 0
    
    return (likes + comments) / video_age_days


def compute_heatmap_metrics(heatmap: Optional[list[dict]]) -> tuple[Optional[float], Optional[float]]:
    if not heatmap:
        return None, None
    
    values = [h.get("value", 0) for h in heatmap if "value" in h]
    if not values:
        return None, None
    
    max_val = max(values)
    avg_val = sum(values) / len(values)
    return float(max_val), float(avg_val)


def compute_all_engagement_metrics(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Computes all engagement metrics from yt-dlp metadata.
    Exact keys required by the implementation plan.
    """
    view_count = metadata.get("view_count")
    like_count = metadata.get("like_count")
    comment_count = metadata.get("comment_count")
    follower_count = metadata.get("channel_follower_count") or metadata.get("subscriber_count")
    duration = metadata.get("duration")
    upload_date_str = metadata.get("upload_date")
    heatmap = metadata.get("heatmap")
    
    age_days = days_since_upload(upload_date_str)
    er_v = er_views(like_count, comment_count, view_count)
    hp_peak, hp_avg = compute_heatmap_metrics(heatmap)
    
    return {
        "er_views": er_v,
        "er_followers": er_followers(like_count, comment_count, follower_count),
        "like_rate": like_rate(like_count, view_count),
        "comment_rate": comment_rate(comment_count, view_count),
        "like_to_comment_ratio": like_to_comment_ratio(like_count, comment_count),
        "er_per_minute": er_per_minute(er_v, duration),
        "views_per_minute": views_per_minute(view_count, duration),
        "engagement_velocity": engagement_velocity(like_count, comment_count, age_days),
        "heatmap_peak_intensity": hp_peak,
        "heatmap_avg_intensity": hp_avg,
        # Raw pass-throughs
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "channel_follower_count": follower_count,
        "duration_seconds": duration,
        "video_age_days": age_days,
    }
