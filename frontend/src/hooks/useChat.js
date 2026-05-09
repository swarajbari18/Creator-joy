import { useState, useEffect, useCallback, useRef } from 'react'
import { getHistory, streamChat } from '../api/chat'
import { v4 as uuid } from 'uuid'

export function useChat(projectId, sessionId) {
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [currentStreamText, setCurrentStreamText] = useState('')
  const [skillLog, setSkillLog] = useState([])

  const streamTextRef = useRef('')
  const skillLogRef = useRef([])

  useEffect(() => {
    if (!sessionId || !projectId) {
      setMessages([])
      return
    }
    getHistory(projectId, sessionId).then(history => {
      setMessages(history.map(h => ({ id: uuid(), role: h.role, content: h.content })))
    })
  }, [projectId, sessionId])

  const sendMessage = useCallback(async (text) => {
    if (!sessionId || !projectId || streaming) return

    setMessages(prev => [...prev, { id: uuid(), role: 'user', content: text }])
    setStreaming(true)
    setCurrentStreamText('')
    setSkillLog([])
    streamTextRef.current = ''
    skillLogRef.current = []

    await streamChat(projectId, sessionId, text, (event) => {
      if (event.type === 'token') {
        streamTextRef.current += event.content
        setCurrentStreamText(streamTextRef.current)
      } else if (event.type === 'skill_start') {
        const entry = { skill: event.skill, status: 'active', message: event.message }
        skillLogRef.current = [...skillLogRef.current, entry]
        setSkillLog([...skillLogRef.current])
      } else if (event.type === 'skill_complete') {
        skillLogRef.current = skillLogRef.current.map(e =>
          e.skill === event.skill ? { ...e, status: 'complete' } : e
        )
        setSkillLog([...skillLogRef.current])
      } else if (event.type === 'skill_error') {
        skillLogRef.current = skillLogRef.current.map(e =>
          e.skill === event.skill ? { ...e, status: 'error', error: event.error } : e
        )
        setSkillLog([...skillLogRef.current])
      } else if (event.type === 'done') {
        const finalText = streamTextRef.current
        const finalLog = [...skillLogRef.current]
        setMessages(prev => [...prev, {
          id: uuid(),
          role: 'assistant',
          content: finalText,
          skillEvents: finalLog,
        }])
        setCurrentStreamText('')
        setSkillLog([])
        streamTextRef.current = ''
        skillLogRef.current = []
        setStreaming(false)
      } else if (event.type === 'error') {
        setStreaming(false)
      }
    })

    setStreaming(false)
  }, [projectId, sessionId, streaming])

  return { messages, streaming, currentStreamText, skillLog, sendMessage }
}
