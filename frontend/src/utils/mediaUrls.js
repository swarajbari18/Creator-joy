export function thumbnailUrl(projectId, videoId) {
  return `/downloads/projects/${projectId}/videos/${videoId}/source_video.webp`
}

export function thumbnailFallbackUrl(projectId, videoId) {
  return `/downloads/projects/${projectId}/videos/${videoId}/source_video.jpg`
}

export function videoUrl(projectId, videoId) {
  return `/downloads/projects/${projectId}/videos/${videoId}/source_video.mp4`
}
