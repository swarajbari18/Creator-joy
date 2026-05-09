# Engagement Rate Research: Computation, Normalization, and Storage for Creator-Joy

**Written:** 2026-05-08  
**Scope:** Engagement rate computation from yt-dlp metadata for YouTube, TikTok, and Instagram video analysis  
**Purpose:** Complete developer reference — no additional research needed to implement

---

## Table of Contents

1. [Available Data Fields](#1-available-data-fields)
2. [Standard Industry Formulas](#2-standard-industry-formulas)
3. [What We Can Compute from Our Exact Fields](#3-what-we-can-compute-from-our-exact-fields)
4. [Normalization for Cross-Video and Cross-Creator Comparison](#4-normalization-for-cross-video-and-cross-creator-comparison)
5. [Industry Benchmarks by Platform and Tier](#5-industry-benchmarks-by-platform-and-tier)
6. [Qdrant Storage Strategy: Store vs. Compute](#6-qdrant-storage-strategy-store-vs-compute)
7. [Missing Data Handling](#7-missing-data-handling)
8. [Recommended Primary Metric and Implementation Summary](#8-recommended-primary-metric-and-implementation-summary)

---

## 1. Available Data Fields

These are the exact fields yt-dlp provides in the metadata JSON. Every formula in this document uses only these fields.

```python
# Raw yt-dlp fields — types as observed in practice
view_count:             int   | None   # e.g. 8007
like_count:             int   | None   # e.g. 230   (may be None on some videos)
comment_count:          int   | None   # e.g. 160
channel_follower_count: int   | None   # e.g. 2090000
duration:               int   | None   # seconds, e.g. 293
average_rating:         None            # YouTube removed this; always None — ignore it
upload_date:            str   | None   # "YYYYMMDD", e.g. "20260507"
channel_is_verified:    bool  | None
heatmap:                list  | None   # YouTube "most replayed" data — sparse
```

**Important caveats identified in research:**

- `like_count` is sometimes `None` on YouTube — YouTube periodically breaks this in yt-dlp (see [yt-dlp issue #8759](https://github.com/yt-dlp/yt-dlp/issues/8759))
- `channel_follower_count` is `None` for some channels lacking a subscriber display
- YouTube Shorts `view_count` from yt-dlp historically underreports by ~50% for newer Shorts (see [yt-dlp issue #13122](https://github.com/yt-dlp/yt-dlp/issues/13122))
- `heatmap` is usually `None` — only populated for videos that have accumulated enough views to trigger YouTube's "Most Replayed" feature
- `average_rating` has been `None` since YouTube removed public ratings in 2021 — do not reference this field anywhere in the system

---

## 2. Standard Industry Formulas

### 2.1 The "Classic" Follower-Based Formula

The most historically common formula in influencer marketing:

```
ER_followers = (likes + comments) / followers × 100
```

**Why it exists:** Follower count was the original proxy for audience size before platforms exposed view counts widely. It answers: "Of everyone who could have seen this, how many engaged?"

**Why it is increasingly disfavored for video:** On YouTube and TikTok, algorithmic distribution means the actual viewers of a given video are mostly *not* the creator's followers. A video from a 2M-follower channel may get 80% of its views from non-subscribers via recommendations or search. Using followers as the denominator produces a rate that reflects the creator's overall audience size, not the video's actual performance.

### 2.2 The View-Based Formula (Recommended for Video)

The dominant formula in YouTube, TikTok, and Shorts analytics:

```
ER_views = (likes + comments) / views × 100
```

**Why it is preferred for video:**
- Views represent actual exposures — people who saw the video and had the opportunity to engage
- Algorithmic distribution on YouTube, TikTok, and Reels means most viewers are *not* followers; views are a far more accurate denominator
- This is the formula used by HypeAuditor, SociaVault (75,000-channel study), Social Status, and all major YouTube analytics tools
- It enables fair comparison between channels of wildly different sizes: a 50K-subscriber channel and a 5M-subscriber channel showing the same ER_views are genuinely performing equivalently per viewer

**Why it has caveats:**
- View counts include repeat views from the same user, which dilutes ER_views compared to reach-based metrics (which we cannot compute from yt-dlp data)
- YouTube Shorts accumulate views at a much faster rate than long-form content, inflating the denominator and suppressing ER_views unless duration-normalized

### 2.3 Platform-Specific Formula Variants

Different platforms publish different signals; the formula adapts accordingly.

**YouTube (what major analytics tools use):**
```
ER = (likes + comments) / views × 100
```
Dislikes are excluded because YouTube removed the dislike count from public APIs in 2021. Shares are not exposed via yt-dlp metadata.

**TikTok (full formula with weighted signals):**
```
ER = (likes + comments + shares + saves) / views × 100

# Weighted variant used by Emplicit and similar tools:
ER_weighted = (likes×1 + comments×5 + shares×7 + saves×10) / views × 100
```
yt-dlp does not expose TikTok saves or shares in the metadata fields we have confirmed. Until those fields are verified available, use the unweighted view-based formula.

**Instagram (view-based for video, follower-based for images):**
```
# For Reels/video content — preferred:
ER = (likes + comments) / views × 100

# For static posts where views are unavailable:
ER = (likes + comments + saves) / followers × 100
```
Since Creator-Joy ingests video URLs, the view-based formula applies for all Instagram content.

**LinkedIn:**
```
ER = (reactions + comments + shares) / impressions × 100
```
LinkedIn is impression-based by convention. yt-dlp does not currently support LinkedIn video extraction in a way that surfaces these fields, so LinkedIn is a future concern.

### 2.4 Which Formula Is Most Fair for Cross-Video, Cross-Creator Comparison

**The unambiguous answer is ER_views (view-based engagement rate).**

Here is why follower-based ER fails for cross-creator comparison:

- Channel A: 100K followers, video gets 500K views (mostly non-followers via recommendation), 10K likes + 500 comments → ER_followers = 10.5%, ER_views = 2.1%
- Channel B: 2M followers, video gets 500K views, 10K likes + 500 comments → ER_followers = 0.525%, ER_views = 2.1%

Both videos performed identically per viewer — the same share of people who watched chose to engage. ER_views correctly reports 2.1% for both. ER_followers makes Channel A look 20x better than Channel B purely because of its smaller subscriber base.

**For cross-platform comparison:** ER_views is still the most consistent denominator, but absolute numbers will differ between platforms due to platform-specific engagement culture. TikTok users like more freely than YouTube users. A 5% ER_views on YouTube is phenomenal; a 5% on TikTok is average. Always compare within-platform.

---

## 3. What We Can Compute from Our Exact Fields

The following defines every meaningful engagement metric derivable from yt-dlp metadata. Python code uses the exact field names from yt-dlp.

```python
from datetime import date, datetime
from typing import Optional

def parse_upload_date(upload_date: Optional[str]) -> Optional[date]:
    """Parse yt-dlp's YYYYMMDD string into a date object."""
    if upload_date is None:
        return None
    try:
        return datetime.strptime(upload_date, "%Y%m%d").date()
    except ValueError:
        return None

def days_since_upload(upload_date: Optional[str]) -> Optional[int]:
    """Number of days between upload and today."""
    d = parse_upload_date(upload_date)
    if d is None:
        return None
    return (date.today() - d).days
```

### Metric 1: View-Based Engagement Rate (Primary)

```python
def er_views(
    like_count: Optional[int],
    comment_count: Optional[int],
    view_count: Optional[int],
) -> Optional[float]:
    """
    Primary engagement rate: what fraction of viewers chose to interact.
    
    Formula: (likes + comments) / views × 100
    
    Returns None if view_count is None or zero (cannot divide).
    Returns partial metric if only one of likes/comments is available.
    """
    if not view_count:
        return None
    total_engagement = (like_count or 0) + (comment_count or 0)
    return round((total_engagement / view_count) * 100, 4)
```

**What it measures:** The fraction of viewers who actively engaged (liked or commented) after watching.  
**What it tells a creator:** How compelling the video is to people who actually saw it, independent of channel size.  
**Caveats:** Repeat views from the same user inflate the denominator; a highly replayed video will show a lower ER_views than its true per-viewer rate. Also, short videos get more views faster, which can suppress this metric relative to long-form content.

---

### Metric 2: Follower-Based Engagement Rate (Secondary / Cross-Channel Context)

```python
def er_followers(
    like_count: Optional[int],
    comment_count: Optional[int],
    channel_follower_count: Optional[int],
) -> Optional[float]:
    """
    Classic influencer-marketing ER: engagement relative to subscriber base.
    
    Formula: (likes + comments) / followers × 100
    
    Use for: understanding how well the video resonated with the existing audience.
    Do NOT use as the primary comparison metric for cross-creator comparison.
    """
    if not channel_follower_count:
        return None
    total_engagement = (like_count or 0) + (comment_count or 0)
    return round((total_engagement / channel_follower_count) * 100, 4)
```

**What it measures:** How well the video activated the existing subscriber/follower base.  
**What it tells a creator:** Whether their own audience cared about this particular video.  
**Caveats:** Highly misleading for cross-creator comparison (see Section 2.4). For a large channel (2M+ followers), even a highly engaging video will show a very small follower-based ER.

---

### Metric 3: Like-to-Comment Ratio

```python
def like_to_comment_ratio(
    like_count: Optional[int],
    comment_count: Optional[int],
) -> Optional[float]:
    """
    Ratio of likes to comments. Indicates depth of engagement vs. passive approval.
    
    Formula: likes / comments
    
    High ratio (>20): Video gets passive approval — people like but don't discuss.
    Low ratio (<5):   Video sparks active discussion — comments are proportionally high.
    """
    if not comment_count or comment_count == 0:
        return None
    if not like_count:
        return None
    return round(like_count / comment_count, 2)
```

**What it measures:** The ratio of passive approval (likes) to active engagement (comments).  
**What it tells a creator:** Controversial or discussion-worthy videos have low ratios; feel-good or visually impressive content has high ratios. Tutorial content typically has lower ratios (viewers ask questions).  
**Caveats:** Comment counts can be inflated by spam or pinned-comment threads. Not directly actionable without context.

---

### Metric 4: Comments-per-View Rate

```python
def comment_rate(
    comment_count: Optional[int],
    view_count: Optional[int],
) -> Optional[float]:
    """
    Comments as a fraction of views. Comments are harder to generate than likes.
    
    Formula: comments / views × 100
    
    Comments signal deep engagement — someone cared enough to type a response.
    YouTube's algorithm weights comments more heavily than likes.
    """
    if not view_count or not comment_count:
        return None
    return round((comment_count / view_count) * 100, 4)
```

**What it measures:** How often viewers convert to active commenters.  
**What it tells a creator:** Comment rate above 0.5% is strong on YouTube. A high comment rate with a low like rate suggests the content is polarizing or asks a question.  
**Caveats:** Comments are suppressed on some videos by creator settings. Disabled comments should be flagged in the UI.

---

### Metric 5: Likes-per-View Rate

```python
def like_rate(
    like_count: Optional[int],
    view_count: Optional[int],
) -> Optional[float]:
    """
    Likes as a fraction of views. Isolated from comments.
    
    Formula: likes / views × 100
    
    Useful when comment_count is None — at minimum we may have likes.
    """
    if not view_count or not like_count:
        return None
    return round((like_count / view_count) * 100, 4)
```

**What it measures:** How often viewers click Like after watching.  
**What it tells a creator:** A direct signal of positive sentiment. YouTube benchmarks: 1-3% is typical; 5%+ is exceptional.  
**Caveats:** Like count is the most frequently missing field from yt-dlp (platform hides it). Treat as a fallback, not a primary.

---

### Metric 6: Engagement Velocity (Engagement Per Day)

```python
def engagement_velocity(
    like_count: Optional[int],
    comment_count: Optional[int],
    upload_date: Optional[str],
) -> Optional[float]:
    """
    Total engagement divided by the number of days the video has been live.
    
    Formula: (likes + comments) / days_since_upload
    
    Normalizes for video age — a 2-year-old video with 10K likes and a
    2-day-old video with 10K likes are very different performers.
    """
    age_days = days_since_upload(upload_date)
    if not age_days or age_days == 0:
        return None  # Uploaded today — divide by 1 day to avoid inflated rate
    total_engagement = (like_count or 0) + (comment_count or 0)
    return round(total_engagement / age_days, 2)
```

```python
def engagement_velocity_per_view_day(
    like_count: Optional[int],
    comment_count: Optional[int],
    view_count: Optional[int],
    upload_date: Optional[str],
) -> Optional[float]:
    """
    ER_views normalized by video age. Best metric for comparing videos of
    different ages on a level playing field.
    
    Formula: ER_views / days_since_upload × 100
    
    Think of it as: "how much engagement per view is this video still generating per day?"
    """
    er = er_views(like_count, comment_count, view_count)
    age_days = days_since_upload(upload_date)
    if er is None or not age_days or age_days == 0:
        return None
    return round(er / age_days, 6)
```

**What it measures:** Rate of engagement accumulation over the video's lifetime.  
**What it tells a creator:** A 3-day-old video and a 3-year-old video cannot be fairly compared on raw ER_views. Velocity reveals whether a video is still "alive" in the algorithm or has gone cold. Older videos with declining velocity are done; newer videos with high velocity are being actively promoted.  
**Caveats:** Engagement velocity is not meaningful for upload_date=today (division by 0 or 1 day produces misleading spikes). Set a minimum age of 3 days before reporting velocity. YouTube videos can also experience "second wind" viral spikes years later — velocity alone doesn't tell you *why* engagement is occurring.

---

### Metric 7: Duration-Normalized View Rate (Views per Minute of Content)

```python
def views_per_minute(
    view_count: Optional[int],
    duration: Optional[int],
) -> Optional[float]:
    """
    Views divided by video length in minutes.
    
    Formula: views / (duration / 60)
    
    A 60-second video with 10K views and a 60-minute video with 10K views
    are in completely different categories. This normalizes for content length.
    """
    if not view_count or not duration or duration == 0:
        return None
    duration_minutes = duration / 60
    return round(view_count / duration_minutes, 2)
```

```python
def er_per_minute(
    like_count: Optional[int],
    comment_count: Optional[int],
    view_count: Optional[int],
    duration: Optional[int],
) -> Optional[float]:
    """
    Engagement rate per minute of content. Normalizes ER_views for video length.
    
    Formula: ER_views / (duration / 60)
    
    This is the fairest way to compare a 60-second Short against a 20-minute
    tutorial — both are normalized to "engagement generated per minute of content."
    """
    er = er_views(like_count, comment_count, view_count)
    if er is None or not duration or duration == 0:
        return None
    duration_minutes = duration / 60
    return round(er / duration_minutes, 4)
```

**What it measures:** How much engagement the video generates relative to its length.  
**What it tells a creator:** Short-form videos inherently accumulate more views faster (less time investment per view), making ER_views comparisons between Shorts and long-form videos unfair. ER_per_minute corrects for this. Research confirms that YouTube Shorts get 1.4× more ER_views than long-form content purely due to duration, not superior content quality.  
**Caveats:** This metric should be used for *format comparison* (Shorts vs. long-form) not absolute benchmarking. Do not present this to creators without explaining what it measures, as it can be counterintuitive.

---

### Metric 8: Heatmap Peak Intensity (When Available)

```python
def heatmap_peak_intensity(heatmap: Optional[list]) -> Optional[float]:
    """
    When the yt-dlp heatmap field is populated, extract the maximum normalized
    "most replayed" value. This indicates the single most engaging moment in the video.
    
    yt-dlp heatmap format (when present):
    [
        {"start_time": 0.0, "end_time": 10.0, "value": 0.32},
        {"start_time": 10.0, "end_time": 20.0, "value": 0.87},
        ...
    ]
    
    value is normalized 0.0–1.0 where 1.0 = the absolute peak replay moment.
    
    Formula: max(segment["value"] for segment in heatmap)
    """
    if not heatmap or not isinstance(heatmap, list):
        return None
    try:
        values = [seg["value"] for seg in heatmap if "value" in seg]
        if not values:
            return None
        return round(max(values), 4)
    except (KeyError, TypeError):
        return None

def heatmap_average_intensity(heatmap: Optional[list]) -> Optional[float]:
    """
    Average normalized replay intensity across all segments.
    Values below 0.3 indicate low retention; above 0.6 indicates strong hold.
    """
    if not heatmap or not isinstance(heatmap, list):
        return None
    try:
        values = [seg["value"] for seg in heatmap if "value" in seg]
        if not values:
            return None
        return round(sum(values) / len(values), 4)
    except (KeyError, TypeError):
        return None
```

**What it measures:** Peak and average viewer retention intensity from YouTube's "Most Replayed" data.  
**What it tells a creator:** A heatmap peak at the 2-minute mark on a 10-minute video tells you exactly which moment is most compelling. Average intensity below 0.3 suggests viewers drop off early and don't return; above 0.6 suggests strong retention throughout.  
**Caveats:** Heatmap data is only populated for videos with significant view counts (rough threshold: ~10K+ views). It is absent on most competitor videos. Do not display heatmap metrics if the field is None — surface a clear "not enough data" message.

---

### Complete Metric Computation Function

```python
from typing import Optional
from datetime import date, datetime

def compute_all_engagement_metrics(metadata: dict) -> dict:
    """
    Given a yt-dlp metadata dict, compute all engagement metrics.
    Returns a dict of metric_name -> value (None if not computable).
    """
    vc = metadata.get("view_count")
    lc = metadata.get("like_count")
    cc = metadata.get("comment_count")
    fc = metadata.get("channel_follower_count")
    dur = metadata.get("duration")
    ud = metadata.get("upload_date")
    hm = metadata.get("heatmap")

    return {
        # Primary
        "er_views":                      er_views(lc, cc, vc),
        # Secondary / context
        "er_followers":                  er_followers(lc, cc, fc),
        # Decomposed signals
        "like_rate":                     like_rate(lc, vc),
        "comment_rate":                  comment_rate(cc, vc),
        "like_to_comment_ratio":         like_to_comment_ratio(lc, cc),
        # Normalization for comparison
        "er_per_minute":                 er_per_minute(lc, cc, vc, dur),
        "views_per_minute":              views_per_minute(vc, dur),
        "engagement_velocity":           engagement_velocity(lc, cc, ud),
        "engagement_velocity_per_view_day": engagement_velocity_per_view_day(lc, cc, vc, ud),
        # Heatmap signals (usually None)
        "heatmap_peak_intensity":        heatmap_peak_intensity(hm),
        "heatmap_avg_intensity":         heatmap_average_intensity(hm),
        # Raw counts (store for reference)
        "view_count":                    vc,
        "like_count":                    lc,
        "comment_count":                 cc,
        "channel_follower_count":        fc,
        "duration_seconds":              dur,
        "video_age_days":                days_since_upload(ud),
    }
```

---

## 4. Normalization for Cross-Video and Cross-Creator Comparison

When a creator compares their video to a competitor's — or their own videos to each other — raw counts are meaningless and even normalized rates can mislead without further adjustment. This section defines what to do.

### 4.1 The Core Problem

| Metric           | Channel A (50K subs) | Channel B (2M subs) | Fair comparison? |
|-----------------|----------------------|---------------------|-----------------|
| Raw likes        | 1,200                | 45,000              | No — A looks terrible |
| ER_followers     | 2.4%                 | 2.25%               | No — B penalized for size |
| ER_views         | 2.4%                 | 2.4%                | Yes — if views are equal |
| ER_per_minute    | 0.8% /min            | 0.8% /min           | Yes — if durations differ |

### 4.2 Per-View Normalization (The Standard Approach)

Always use `er_views` as the baseline for cross-creator comparison. This eliminates channel size bias because it asks: "Given that someone saw this video, what percentage engaged?"

```python
def compare_er_views(videos: list[dict]) -> list[dict]:
    """
    Rank videos by ER_views for fair cross-creator comparison.
    Each item in videos should have pre-computed engagement metrics.
    """
    ranked = [v for v in videos if v.get("er_views") is not None]
    return sorted(ranked, key=lambda v: v["er_views"], reverse=True)
```

**Limitation:** Per-view normalization still does not account for video length. A 30-second Short and a 45-minute documentary competing on ER_views is not apples-to-apples.

### 4.3 Per-Follower Normalization (When to Use It)

Use `er_followers` when the question is specifically: "Is this creator good at activating their existing audience?" This is the right metric for a brand deciding which creator to sponsor — they want a creator whose followers actually engage, not just a creator with massive algorithmic reach.

Do NOT use `er_followers` for:
- Comparing two videos from different channels (size bias)
- Determining which of a creator's own videos performed best (all share the same denominator)
- Any cross-platform comparison

### 4.4 Duration Normalization (For Format Mix Comparison)

When a creator's channel has a mix of Shorts (< 60 seconds) and long-form content (> 5 minutes), ER_views comparisons are unfair. Use `er_per_minute` to normalize.

```python
def compare_across_formats(videos: list[dict]) -> list[dict]:
    """
    For channels with mixed Shorts + long-form content.
    ER_per_minute is the fairest cross-format metric.
    """
    ranked = [v for v in videos if v.get("er_per_minute") is not None]
    return sorted(ranked, key=lambda v: v["er_per_minute"], reverse=True)
```

**Research finding:** YouTube Shorts generate approximately 1.4× more ER_views than long-form videos purely due to shorter duration, not content quality. If a creator asks "why does my 30-second Short have a higher engagement rate than my 20-minute tutorial?", the answer is duration bias — `er_per_minute` will equalize this.

**Practical threshold for format classification:**

```python
def classify_format(duration_seconds: Optional[int]) -> str:
    if duration_seconds is None:
        return "unknown"
    if duration_seconds <= 60:
        return "short"       # YouTube Short / TikTok standard
    elif duration_seconds <= 300:
        return "medium"      # 1–5 minutes
    elif duration_seconds <= 1200:
        return "long"        # 5–20 minutes
    else:
        return "very_long"   # 20+ minutes
```

### 4.5 Engagement Velocity (For Comparing Videos of Different Ages)

A 2-year-old video with 100K total likes has accumulated that engagement over 730 days. A 3-day-old video with 5K likes has done so in 3 days. On a velocity basis:

- Old video: 100,000 / 730 = 137 engagements/day
- New video: 5,000 / 3 = 1,667 engagements/day

The new video is outperforming on velocity by 12x. This is the right metric when the question is "which of my recent videos is the algorithm currently pushing?"

```python
def compare_by_velocity(videos: list[dict], min_age_days: int = 3) -> list[dict]:
    """
    Rank videos by engagement velocity. Only include videos at least min_age_days old
    to avoid division-by-tiny-number distortion on brand-new uploads.
    """
    qualified = [
        v for v in videos
        if v.get("engagement_velocity") is not None
        and (v.get("video_age_days") or 0) >= min_age_days
    ]
    return sorted(qualified, key=lambda v: v["engagement_velocity"], reverse=True)
```

**Important decay context:** Social media engagement is front-loaded. On TikTok and Instagram Reels, most engagement occurs within the first 48 hours. On YouTube, the distribution is flatter — evergreen content can attract engagement for months or years. A YouTube video's "true" velocity should be measured at multiple time windows (7-day, 30-day, lifetime) — but with yt-dlp metadata we only have lifetime totals.

### 4.6 What Not to Do

Do NOT compute a "normalized score" that mixes er_views, er_followers, and velocity into a single composite number to display to creators. These metrics answer fundamentally different questions. A composite score obscures the underlying story. Instead, present each metric separately with a one-line explanation of what it means. The chat interface (RAG) should be able to explain why one metric says one thing and another says something different.

---

## 5. Industry Benchmarks by Platform and Tier

### 5.1 YouTube Benchmarks (2025–2026)

**Primary formula used by industry:** `(likes + comments) / views × 100`

Data source: SociaVault 75,000-channel study; Social Status; Buffer 52M-post analysis.

| Subscriber Tier | Subscribers    | Median ER_views | Below Average | Good Range  | Excellent |
|----------------|---------------|-----------------|---------------|-------------|-----------|
| Nano            | 1K–10K        | 5.23%           | < 3.4%        | 5.2–7.8%   | > 8%      |
| Micro           | 10K–50K       | 3.74%           | < 2.5%        | 3.7–5.4%   | > 6%      |
| Mid             | 50K–100K      | 2.81%           | < 1.9%        | 2.8–4.1%   | > 5%      |
| Macro           | 100K–500K     | 2.12%           | < 1.4%        | 2.1–3.2%   | > 4%      |
| Mega            | 500K+         | 1.41%           | < 0.9%        | 1.4–2.2%   | > 3%      |

**Overall median across all channels:** 3.06%

**Qualitative scale (all channel sizes combined):**
- < 1%: Passive audience — viewers watching but not reacting
- 1–2.5%: Average
- 2.5–5%: Good
- > 5%: Excellent
- > 10%: Rare and exceptional (usually niche or newly viral content)

**YouTube Shorts vs. Long-form (same channel):**
- Shorts median ER_views: 4.71% (up from 3.95% in Jan 2024)
- Long-form median ER_views: ~2–3%
- Shorts generate ~1.4× more ER_views than long-form purely due to duration effect

**Niche benchmarks:**
- Gaming: ~5.1% (highly opinionated, comment-heavy audience)
- Education/Tutorials: ~4.2% (viewers ask questions in comments)
- Entertainment/Vlog: ~2.5–3.5%
- News/Commentary: ~2–3%

**YouTube content longevity:** Unlike TikTok (48-hour engagement peak), YouTube videos remain discoverable via search and recommendations for months or years. Engagement velocity on YouTube cannot be compared to TikTok velocity.

### 5.2 TikTok Benchmarks (2025–2026)

**Primary formula used by industry:** `(likes + comments) / views × 100` (yt-dlp compatible version)
**Full formula (when shares + saves available):** `(likes + comments + shares + saves) / views × 100`

| Follower Tier  | Followers      | Average ER_views | Good Range    | Exceptional |
|---------------|---------------|-----------------|---------------|-------------|
| Nano           | < 10K         | ~7–10%          | 7–12%         | > 15%       |
| Micro          | 10K–100K      | ~6–8%           | 6–10%         | > 12%       |
| Mid            | 100K–500K     | ~5.1%           | 4–7%          | > 10%       |
| Macro          | 500K–1M       | ~4.48%          | 3–6%          | > 8%        |
| Mega           | 1M–5M         | ~3.76%          | 3–5%          | > 7%        |
| Celebrity      | 10M+          | ~2.88%          | 2–4%          | > 6%        |

**Platform average:** 2.5% (views-based) — 5x higher than Instagram's 0.5%

**TikTok-specific note:** TikTok's For You Page distributes content primarily to non-followers, making follower-based ER essentially meaningless for this platform. `er_views` is the only appropriate metric for TikTok. The platform recorded a 45% year-over-year increase in shares per post in 2025, but shares are not exposed in yt-dlp metadata.

**Engagement decay:** TikTok content peaks within 48–72 hours. A TikTok video's engagement velocity measured at 7 days is almost always declining.

### 5.3 Instagram Benchmarks (2025–2026)

**For Reels/Video content** (the case for Creator-Joy):
**Primary formula:** `(likes + comments) / views × 100`

| Follower Tier  | Followers      | Average ER_views | Good Range    |
|---------------|---------------|-----------------|---------------|
| Nano           | 1K–10K        | ~4–6%           | 4–8%          |
| Micro          | 10K–100K      | ~2–4%           | 2–5%          |
| Mid-Tier       | 100K–500K     | ~1.5–3%         | 2–4%          |
| Macro          | 500K–1M       | ~1–2.5%         | 1.5–3%        |
| Mega           | 1M+           | ~0.5–2%         | 1–2%          |

**Platform-wide ER_views average:** ~1.16% (declining ~24% YoY in 2025)

**Instagram content format performance:**
- Reels: 0.50% avg (follower-based; but higher view-based)
- Carousels: 0.55% avg (follower-based)
- Static images: 0.45% avg (follower-based)

**Instagram algorithmic shift:** In 2025, Instagram's algorithm increasingly prioritizes watch time (completion rate) over absolute engagement count. A Reel watched 80% to completion drives more reach than one that receives many likes with low completion. We do not have completion rate from yt-dlp metadata.

### 5.4 Engagement Rate Decay Curve

Research confirms a consistent pattern: engagement is front-loaded, and rates decay over time as views accumulate without proportional engagement growth.

| Platform   | Peak Engagement Window | Typical Decay Shape          |
|-----------|----------------------|------------------------------|
| TikTok    | Hours 1–48           | Sharp cliff after 72 hours   |
| Instagram | Hours 1–48           | Moderate cliff after 72 hours|
| YouTube   | Days 1–7 (initial)   | Long tail — can revive months later |

**Practical implication for Creator-Joy:** When a creator asks "which of my videos has the best engagement rate?", older videos will almost always show lower ER_views than newer ones, not because they were worse content, but because they've had more time to accumulate passive views. The `engagement_velocity_per_view_day` metric partially corrects for this by normalizing ER_views by age.

**YouTube evergreen exception:** YouTube SEO-optimized videos can see engagement rate *increase* months after upload when they begin ranking in search results. The "long tail" of YouTube engagement is fundamentally different from TikTok/Instagram. This is why a YouTube video's ER_views measured at 6 months post-upload is not directly comparable to its ER_views at 1 week post-upload.

### 5.5 Channel Size vs. Engagement Rate (The Inverse Law)

All platforms show an inverse relationship between channel size and engagement rate. This is well-documented and universal:

- Smaller creators have more intimate communities that engage more actively per viewer
- Larger creators attract more passive viewers who watch but do not interact
- Algorithms distribute large creators' content to broader, less targeted audiences

**Implication for Creator-Joy:** When a creator compares their video to a competitor's video, you must contextualise the benchmark comparison within the same follower tier. A 50K-subscriber creator should not be compared to YouTube's overall median of 3.06% — they should be compared to the 3.74% micro-channel median. Always surface the relevant tier benchmark alongside the computed ER_views.

---

## 6. Qdrant Storage Strategy: Store vs. Compute

### 6.1 The Core Principle

The general rule for Qdrant (and vector databases generally): **store anything you need to filter by; store anything that is expensive or complex to recompute; compute at query time only things that are trivial and require no storage overhead.**

For engagement metrics in Creator-Joy, the calculus is straightforward:

- All engagement metrics are cheap to compute (simple arithmetic)
- But Qdrant cannot filter on values that aren't in the payload
- If you want to answer "find all videos where er_views > 3%" with a vector search + filter, er_views must be in the payload at index time

**Recommendation: Pre-compute and store all engagement metrics as Qdrant payload fields.** Recompute them when videos are refreshed (if ever). The computation cost at index time is negligible; the benefit to filtering at query time is significant.

### 6.2 Recommended Qdrant Payload Schema

```python
# Qdrant point payload schema for a video document
VIDEO_PAYLOAD_SCHEMA = {
    # Identity
    "video_id":           str,    # YouTube/TikTok/Instagram video ID
    "url":                str,
    "platform":           str,    # "youtube" | "tiktok" | "instagram"
    "channel_id":         str,
    "channel_name":       str,
    
    # Raw counts (stored for display; not indexed unless needed for range queries)
    "view_count":         int,
    "like_count":         int,     # may be None — use null-safe handling
    "comment_count":      int,
    "channel_follower_count": int,
    "duration_seconds":   int,
    
    # Temporal
    "upload_date":        str,     # "YYYY-MM-DD" (normalized from YYYYMMDD)
    "video_age_days":     int,     # days since upload at index time
    "indexed_at":         str,     # ISO datetime of when we stored this
    
    # Pre-computed engagement metrics (all float, all nullable)
    "er_views":                         float,  # PRIMARY — index this
    "er_followers":                     float,
    "like_rate":                        float,
    "comment_rate":                     float,
    "like_to_comment_ratio":            float,
    "er_per_minute":                    float,  # index this for format comparison
    "views_per_minute":                 float,
    "engagement_velocity":              float,  # index this for velocity queries
    "engagement_velocity_per_view_day": float,
    "heatmap_peak_intensity":           float,  # null for most videos
    "heatmap_avg_intensity":            float,
    
    # Classification
    "format":             str,     # "short" | "medium" | "long" | "very_long"
    "channel_is_verified": bool,
    
    # Content (for text search / RAG retrieval)
    "title":              str,
    "description":        str,
    "tags":               list,    # list[str]
    "transcript_summary": str,     # generated by our transcription pipeline
}
```

### 6.3 Which Fields to Index in Qdrant

Create payload indexes for fields you will filter on in searches. Without an index, Qdrant scans all vectors then applies the filter (slow at scale). With an index, Qdrant can use the index to narrow candidates before or during vector search.

```python
# Fields to create Qdrant payload indexes on (using the Qdrant Python client)
from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

client = QdrantClient(...)

FIELDS_TO_INDEX = [
    ("er_views",               PayloadSchemaType.FLOAT),
    ("er_per_minute",          PayloadSchemaType.FLOAT),
    ("engagement_velocity",    PayloadSchemaType.FLOAT),
    ("view_count",             PayloadSchemaType.INTEGER),
    ("like_count",             PayloadSchemaType.INTEGER),
    ("comment_count",          PayloadSchemaType.INTEGER),
    ("duration_seconds",       PayloadSchemaType.INTEGER),
    ("video_age_days",         PayloadSchemaType.INTEGER),
    ("upload_date",            PayloadSchemaType.KEYWORD),  # for date-range filtering via string sort
    ("platform",               PayloadSchemaType.KEYWORD),
    ("channel_id",             PayloadSchemaType.KEYWORD),
    ("format",                 PayloadSchemaType.KEYWORD),
    ("channel_is_verified",    PayloadSchemaType.BOOL),
]

for field_name, field_type in FIELDS_TO_INDEX:
    client.create_payload_index(
        collection_name="videos",
        field_name=field_name,
        field_schema=field_type,
    )
```

**Do NOT index** fields you will never filter by: `transcript_summary`, `description`, `heatmap_peak_intensity` (too sparse), `like_to_comment_ratio` (rarely queried as a filter).

### 6.4 Example Filtered Queries

```python
from qdrant_client.models import Filter, FieldCondition, Range, MatchValue

# Query: "Find my top-performing videos by engagement rate"
high_er_filter = Filter(
    must=[
        FieldCondition(key="channel_id", match=MatchValue(value="UC_creator_channel_id")),
        FieldCondition(key="er_views", range=Range(gte=3.0)),  # > 3% ER_views
    ]
)

# Query: "Compare engagement across these two specific videos"
two_video_filter = Filter(
    should=[
        FieldCondition(key="video_id", match=MatchValue(value="video_id_1")),
        FieldCondition(key="video_id", match=MatchValue(value="video_id_2")),
    ]
)

# Query: "What's trending now? — videos with high velocity, uploaded in last 7 days"
trending_filter = Filter(
    must=[
        FieldCondition(key="video_age_days", range=Range(lte=7)),
        FieldCondition(key="engagement_velocity", range=Range(gte=100)),  # 100+ engagements/day
    ]
)

# Query: "Best engagement on short-form content across all creators"
shorts_filter = Filter(
    must=[
        FieldCondition(key="format", match=MatchValue(value="short")),
        FieldCondition(key="er_views", range=Range(gte=5.0)),
    ]
)
```

### 6.5 When to Recompute Metrics

Engagement metrics change over time as views, likes, and comments accumulate. The yt-dlp metadata is a point-in-time snapshot. Design around this:

- **On initial ingest:** Compute all metrics, store in payload
- **On video refresh (if implemented):** Re-fetch yt-dlp metadata, recompute all metrics, upsert the payload
- **`video_age_days`:** This becomes stale the moment it's stored. Either recompute at query time from `upload_date`, or store `upload_date` as the canonical field and compute `video_age_days` dynamically in the RAG response layer
- **`engagement_velocity`:** Since this divides by `video_age_days`, it must be recomputed at display time if you want it to reflect the current age, not the age at index time

**Practical recommendation:** Store `er_views`, `er_followers`, `like_rate`, `comment_rate`, `er_per_minute` as static payload (these don't change when age changes). Recompute `engagement_velocity`, `engagement_velocity_per_view_day`, and `video_age_days` at display/query time using the stored `upload_date` and current date.

---

## 7. Missing Data Handling

Field availability by platform is inconsistent. The system must handle None gracefully at every layer.

### 7.1 Field Availability Matrix

| Field                    | YouTube      | TikTok (yt-dlp) | Instagram (yt-dlp) | Action if None          |
|--------------------------|-------------|------------------|--------------------|-------------------------|
| `view_count`             | Usually set | Usually set      | Varies             | Skip all view-based metrics |
| `like_count`             | Often None  | Usually set      | Usually set        | Skip like_rate; partial ER_views |
| `comment_count`          | Usually set | Varies           | Varies             | Skip comment_rate        |
| `channel_follower_count` | Varies      | Varies           | Varies             | Skip er_followers        |
| `duration`               | Always set  | Always set       | Usually set        | Skip er_per_minute       |
| `upload_date`            | Always set  | Usually set      | Usually set        | Skip velocity            |
| `heatmap`                | Usually None| Not available    | Not available      | Skip heatmap metrics     |

### 7.2 Graceful Degradation Strategy (Code)

```python
def safe_metric(value: Optional[float], metric_name: str) -> dict:
    """
    Wraps a metric value with availability metadata for the UI layer.
    """
    return {
        "value": value,
        "available": value is not None,
        "metric": metric_name,
    }

def engagement_summary_for_display(metrics: dict) -> dict:
    """
    Selects the best available metrics for display given what we have.
    Prioritizes: er_views > like_rate > comment_rate > er_followers > None
    """
    primary = metrics.get("er_views")
    if primary is not None:
        primary_label = "Engagement Rate (per view)"
        primary_note = None
    elif metrics.get("like_rate") is not None:
        primary = metrics["like_rate"]
        primary_label = "Like Rate (per view)"
        primary_note = "Comment count unavailable — showing like rate only"
    elif metrics.get("comment_rate") is not None:
        primary = metrics["comment_rate"]
        primary_label = "Comment Rate (per view)"
        primary_note = "Like count unavailable — showing comment rate only"
    elif metrics.get("er_followers") is not None:
        primary = metrics["er_followers"]
        primary_label = "Engagement Rate (per follower)"
        primary_note = "View count unavailable — using follower-based rate (less comparable)"
    else:
        primary = None
        primary_label = None
        primary_note = "Engagement metrics unavailable — platform did not expose like or comment counts"

    return {
        "primary_metric_value": primary,
        "primary_metric_label": primary_label,
        "note": primary_note,
        "all_metrics": {k: v for k, v in metrics.items() if v is not None},
    }
```

### 7.3 UI/Chat Communication of Missing Data

When surfacing results in the Creator-Joy chat interface, be explicit about what is and is not available. Never silently present a partial metric as if it were the full one.

**Good response pattern:**
> "This video has an engagement rate of 2.3% based on views. Note: YouTube did not expose the like count for this video, so this rate is calculated from comments only — the true engagement rate is likely higher."

**Good response pattern (no view count):**
> "I can't compute a view-based engagement rate for this video because the view count wasn't available in the metadata. The follower-based engagement rate is 0.8%, but this is less meaningful for cross-creator comparison."

**Good response pattern (everything missing):**
> "Engagement metrics for this video aren't available — the platform didn't expose like, comment, or view counts in the accessible metadata. This sometimes happens with private or restricted videos, or on platforms that limit public metric access."

### 7.4 Partial Metric Computation Priority Order

When building the metrics dict, always compute what you can — never reject a video entirely because one field is missing:

```python
METRIC_DEPENDENCIES = {
    "er_views":           ["view_count"],            # likes+comments both optional
    "er_followers":       ["channel_follower_count"],
    "like_rate":          ["like_count", "view_count"],
    "comment_rate":       ["comment_count", "view_count"],
    "like_to_comment_ratio": ["like_count", "comment_count"],
    "er_per_minute":      ["view_count", "duration"],
    "views_per_minute":   ["view_count", "duration"],
    "engagement_velocity": ["upload_date"],
    "heatmap_peak_intensity": ["heatmap"],
}

# er_views with only comment_count (like_count is None):
# (0 + 160) / 8007 × 100 = 2.0% — valid, but disclose that likes are excluded
```

### 7.5 YouTube Shorts View Count Correction

Research note: yt-dlp has a documented issue where YouTube Shorts view counts are ~50% underreported for recently uploaded Shorts (< 2 weeks old). This inflates ER_views for recent Shorts.

```python
def apply_shorts_view_correction(
    view_count: Optional[int],
    format_type: str,
    video_age_days: Optional[int],
    correction_factor: float = 2.0,
) -> Optional[int]:
    """
    Apply a correction factor to Shorts view counts for videos under 14 days old.
    This is a heuristic — flag corrected values in the UI.
    
    Only apply if: format == "short" AND age < 14 days.
    """
    if format_type != "short" or not view_count:
        return view_count
    if video_age_days is None or video_age_days >= 14:
        return view_count
    # Apply correction but flag it
    return int(view_count * correction_factor)
```

This correction is optional and should be flagged in the UI if applied ("View count adjusted for YouTube Shorts reporting lag — actual ER may differ").

---

## 8. Recommended Primary Metric and Implementation Summary

### 8.1 The Recommended Primary Metric: `er_views`

**Use `(like_count + comment_count) / view_count × 100` as the single primary engagement rate for Creator-Joy.**

Reasons:
1. It is the formula used by all major YouTube analytics platforms (HypeAuditor, Social Status, SociaVault, etc.)
2. It eliminates channel-size bias — two channels with wildly different follower counts can be fairly compared per video
3. It works equally well for YouTube, TikTok, and Instagram Reels since all expose view counts
4. It degrades gracefully when either like_count or comment_count is None (uses whichever is available)
5. It is the metric creators instinctively understand: "of the people who saw this, how many engaged?"

### 8.2 Secondary Metrics to Always Surface Alongside the Primary

| Use Case                                | Metric to Show              |
|----------------------------------------|-----------------------------|
| Primary: per-video engagement          | `er_views`                  |
| Cross-channel sponsor evaluation       | `er_followers`              |
| Shorts vs. long-form fair comparison   | `er_per_minute`             |
| Is this video still trending?          | `engagement_velocity`       |
| Which moment was most compelling?      | `heatmap_peak_intensity`    |
| Depth of audience discussion           | `comment_rate`, `like_to_comment_ratio` |

### 8.3 Benchmark Lookup Table for the Chat Interface

The RAG system should include this benchmark data in its context so it can automatically classify a video's performance:

```python
BENCHMARKS = {
    "youtube": {
        "nano":   {"min": 1000,    "max": 10000,   "median_er": 5.23, "good": 5.2, "excellent": 8.0},
        "micro":  {"min": 10000,   "max": 50000,   "median_er": 3.74, "good": 3.7, "excellent": 6.0},
        "mid":    {"min": 50000,   "max": 100000,  "median_er": 2.81, "good": 2.8, "excellent": 5.0},
        "macro":  {"min": 100000,  "max": 500000,  "median_er": 2.12, "good": 2.1, "excellent": 4.0},
        "mega":   {"min": 500000,  "max": None,    "median_er": 1.41, "good": 1.4, "excellent": 3.0},
    },
    "tiktok": {
        "nano":   {"min": 1000,    "max": 10000,   "median_er": 8.50, "good": 7.0, "excellent": 15.0},
        "micro":  {"min": 10000,   "max": 100000,  "median_er": 7.12, "good": 6.0, "excellent": 12.0},
        "mid":    {"min": 100000,  "max": 500000,  "median_er": 5.10, "good": 4.0, "excellent": 10.0},
        "macro":  {"min": 500000,  "max": 1000000, "median_er": 4.48, "good": 3.0, "excellent": 8.0},
        "mega":   {"min": 1000000, "max": None,    "median_er": 3.76, "good": 2.5, "excellent": 6.0},
    },
    "instagram": {
        "nano":   {"min": 1000,    "max": 10000,   "median_er": 5.00, "good": 4.0, "excellent": 8.0},
        "micro":  {"min": 10000,   "max": 100000,  "median_er": 3.00, "good": 2.0, "excellent": 6.0},
        "mid":    {"min": 100000,  "max": 500000,  "median_er": 2.25, "good": 1.5, "excellent": 4.0},
        "macro":  {"min": 500000,  "max": 1000000, "median_er": 1.75, "good": 1.0, "excellent": 3.0},
        "mega":   {"min": 1000000, "max": None,    "median_er": 1.25, "good": 0.5, "excellent": 2.0},
    },
}

def get_tier(follower_count: Optional[int], platform: str) -> Optional[str]:
    """Return the creator tier label for the given follower count and platform."""
    if follower_count is None:
        return None
    tiers = BENCHMARKS.get(platform, {})
    for tier_name, bounds in tiers.items():
        lo = bounds["min"]
        hi = bounds["max"]
        if lo <= follower_count and (hi is None or follower_count < hi):
            return tier_name
    return None

def benchmark_comparison(er_views: float, follower_count: Optional[int], platform: str) -> dict:
    """
    Given a video's ER_views, return a benchmark assessment.
    """
    tier = get_tier(follower_count, platform)
    if tier is None or platform not in BENCHMARKS:
        return {"tier": None, "assessment": "unknown", "benchmark_median": None}
    
    benchmarks = BENCHMARKS[platform][tier]
    median = benchmarks["median_er"]
    good = benchmarks["good"]
    excellent = benchmarks["excellent"]
    
    if er_views >= excellent:
        assessment = "excellent"
    elif er_views >= good:
        assessment = "good"
    elif er_views >= median * 0.7:
        assessment = "average"
    else:
        assessment = "below_average"
    
    return {
        "tier": tier,
        "assessment": assessment,
        "er_views": er_views,
        "benchmark_median": median,
        "benchmark_good": good,
        "benchmark_excellent": excellent,
        "vs_median_pct": round(((er_views - median) / median) * 100, 1),
    }
```

### 8.4 Complete Implementation Checklist

- [ ] Implement `compute_all_engagement_metrics(metadata: dict) -> dict` using the functions in Section 3
- [ ] Normalize `upload_date` from `YYYYMMDD` to `YYYY-MM-DD` when storing in Qdrant
- [ ] Store all pre-computed metrics in Qdrant payload
- [ ] Create payload indexes for `er_views`, `er_per_minute`, `engagement_velocity`, `view_count`, `channel_id`, `platform`, `format`, `upload_date` (see Section 6.3)
- [ ] Implement graceful degradation in `engagement_summary_for_display()` (Section 7.2)
- [ ] Implement `benchmark_comparison()` for the chat interface to contextualize results
- [ ] Recompute `video_age_days` and `engagement_velocity` at display time using stored `upload_date`, not cached values from index time
- [ ] Flag YouTube Shorts view count correction when applicable (< 14 days old)
- [ ] Never display `er_followers` as the primary metric for cross-creator comparison — only as secondary context
- [ ] Always surface the data-availability caveat in the UI when any field is None

---

## Sources

Research conducted May 2026 from the following primary sources:

- [SociaVault: What Is a Good Engagement Rate on YouTube in 2026? (75,000 Channels)](https://sociavault.com/blog/good-engagement-rate-youtube)
- [Hootsuite: Engagement Rate Benchmarks and Formulas 2026 Update](https://blog.hootsuite.com/calculate-engagement-rate/)
- [Socialinsider: How to Calculate Engagement Rate for All Social Media Platforms](https://www.socialinsider.io/blog/how-to-calculate-engagement-rate/)
- [Buffer: The State of Social Media Engagement in 2026 — 52M+ Posts Analyzed](https://buffer.com/resources/state-of-social-media-engagement-2026/)
- [Buffer: Engagement in 2025 — Where Social Media Users Are Actually Interacting](https://buffer.com/resources/average-engagement-rate/)
- [Emplicit: TikTok Engagement Rate Benchmarks 2025](https://emplicit.co/tiktok-engagement-rate-benchmarks-2025/)
- [CreatorFlow: Instagram Engagement Rate by Follower Count 2026](https://creatorflow.so/blog/instagram-engagement-rate/)
- [Impulze.ai: Influencer Engagement Rates for YouTube, TikTok, Instagram](https://www.impulze.ai/post/influencer-engagement-rates)
- [InfluenceFlow: Engagement Rate and Reach Metrics Guide 2025](https://influenceflow.io/resources/engagement-rate-and-reach-metrics-the-complete-2025-guide-for-creators-and-brands/)
- [Qdrant Documentation: Vector Search Filtering](https://qdrant.tech/articles/vector-search-filtering/)
- [Qdrant Documentation: Payload Management](https://qdrant.tech/documentation/manage-data/payload/)
- [Rival IQ: 2025 Social Media Industry Benchmark Report](https://www.rivaliq.com/blog/social-media-industry-benchmark-report/)
- [yt-dlp GitHub Issue #8759: YouTube like_count extraction](https://github.com/yt-dlp/yt-dlp/issues/8759)
- [yt-dlp GitHub Issue #13122: YouTube Shorts view count discrepancy](https://github.com/yt-dlp/yt-dlp/issues/13122)
- [yt-dlp GitHub Issue #3888: YouTube heatmap data](https://github.com/yt-dlp/yt-dlp/issues/3888)
- [Autofaceless: Social Media Engagement Statistics 2026](https://autofaceless.ai/blog/social-media-engagement-statistics-2026)
- [Socialinsider: Social Media Data Collection Challenges](https://www.socialinsider.io/blog/social-media-data-collection/)
