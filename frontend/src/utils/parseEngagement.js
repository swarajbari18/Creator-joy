import { formatCount, formatDuration } from './formatDate'

export function parseEngagement(raw) {
  if (!raw) return {}
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return {}
  }
}

export function formatEngagementForDisplay(raw) {
  const m = parseEngagement(raw)
  const fmt = v => (v != null ? v : null)
  const pct = v => (v != null ? `${v.toFixed(2)}%` : '—')

  return {
    views: formatCount(m.view_count),
    likes: formatCount(m.like_count),
    comments: formatCount(m.comment_count),
    followers: formatCount(m.channel_follower_count),
    erViews: pct(fmt(m.er_views)),
    likeRate: pct(fmt(m.like_rate)),
    commentRate: pct(fmt(m.comment_rate)),
    erPerMinute: pct(fmt(m.er_per_minute)),
    duration: formatDuration(m.duration_seconds),
    age: m.video_age_days != null ? `${m.video_age_days}d ago` : '—',
    tier: m.tier ?? '—',
    heatmapPeak: m.heatmap_peak_intensity != null ? m.heatmap_peak_intensity.toFixed(2) : '—',
  }
}
