import { useState, useEffect, useCallback } from 'react'
import { listVideos, ingestUrl, transcribeVideo, indexVideo } from '../api/videos'
import { parseEngagement } from '../utils/parseEngagement'

function parseVideo(v) {
  return { ...v, engagement: parseEngagement(v.engagement_metrics) }
}

export function useVideos(projectId) {
  const [videos, setVideos] = useState([])
  const [pendingIngestions, setPendingIngestions] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      setLoading(true)
      const data = await listVideos(projectId)
      setVideos(data.map(parseVideo))
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  const addVideo = useCallback(async (url, role) => {
    const tempId = crypto.randomUUID()
    setPendingIngestions(p => [...p, { tempId, url, role, stage: 'downloading', error: null, videoId: null }])

    const updateStage = (stage, error = null, videoId = null) =>
      setPendingIngestions(p => p.map(x => x.tempId === tempId ? { ...x, stage, error, videoId: videoId ?? x.videoId } : x))

    try {
      const video = await ingestUrl(projectId, url, role)
      if (!video || video.status === 'failed') {
        updateStage('error', video?.error_message || 'Download failed')
        return
      }
      updateStage('transcribing', null, video.id)

      try {
        await transcribeVideo(projectId, video.id)
      } catch (e) {
        updateStage('error', e.message)
        return
      }
      updateStage('indexing', null, video.id)

      try {
        await indexVideo(projectId, video.id)
      } catch (e) {
        updateStage('error', e.message)
        return
      }

      updateStage('done')
      await load()
      setPendingIngestions(p => p.filter(x => x.tempId !== tempId))
    } catch (e) {
      updateStage('error', e.message)
    }
  }, [projectId, load])

  const retryIngestion = useCallback(async (tempId) => {
    const pending = pendingIngestions.find(p => p.tempId === tempId)
    if (!pending) return

    const updateStage = (stage, error = null, videoId = null) =>
      setPendingIngestions(p => p.map(x => x.tempId === tempId ? { ...x, stage, error, videoId: videoId ?? x.videoId } : x))

    let videoId = pending.videoId

    if (!videoId) {
      updateStage('downloading', null)
      try {
        const video = await ingestUrl(projectId, pending.url, pending.role)
        if (!video || video.status === 'failed') {
          updateStage('error', video?.error_message || 'Download failed')
          return
        }
        videoId = video.id
        updateStage('transcribing', null, videoId)
      } catch (e) {
        updateStage('error', e.message)
        return
      }
    } else {
      updateStage('transcribing', null)
    }

    try {
      await transcribeVideo(projectId, videoId)
    } catch (e) {
      updateStage('error', e.message)
      return
    }
    updateStage('indexing')

    try {
      await indexVideo(projectId, videoId)
    } catch (e) {
      updateStage('error', e.message)
      return
    }

    updateStage('done')
    await load()
    setPendingIngestions(p => p.filter(x => x.tempId !== tempId))
  }, [projectId, pendingIngestions, load])

  return { videos, pendingIngestions, loading, addVideo, retryIngestion, reload: load }
}
