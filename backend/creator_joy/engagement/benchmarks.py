from typing import Optional

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
    # Normalize platform name
    platform = platform.lower()
    if "youtube" in platform:
        platform = "youtube"
    elif "tiktok" in platform:
        platform = "tiktok"
    elif "instagram" in platform:
        platform = "instagram"
    else:
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
    
    # Normalize platform name for benchmark lookup
    platform_key = platform.lower()
    if "youtube" in platform_key:
        platform_key = "youtube"
    elif "tiktok" in platform_key:
        platform_key = "tiktok"
    elif "instagram" in platform_key:
        platform_key = "instagram"

    if tier is None or platform_key not in BENCHMARKS:
        return {"tier": None, "assessment": "unknown", "benchmark_median": None}
    
    benchmarks = BENCHMARKS[platform_key][tier]
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
        "vs_median_pct": round(((er_views - median) / median) * 100, 1) if median else 0,
    }
