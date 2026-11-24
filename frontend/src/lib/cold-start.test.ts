import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  SLOW_AFTER_MS,
  getWakingSince,
  pendingCount,
  resetColdStart,
  subscribeCold,
  trackRequest,
} from './cold-start'

describe('cold start detection', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetColdStart()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('stays quiet when the API answers in time', () => {
    const done = trackRequest('/sessions')
    vi.advanceTimersByTime(SLOW_AFTER_MS - 1)
    done()
    vi.advanceTimersByTime(10_000)
    expect(getWakingSince()).toBeNull()
  })

  it('flags a request still pending after 4 s, and clears the flag on the answer', () => {
    const listener = vi.fn()
    subscribeCold(listener)
    const done = trackRequest('/auth/me')
    vi.advanceTimersByTime(SLOW_AFTER_MS)
    expect(getWakingSince()).not.toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)

    done()
    expect(getWakingSince()).toBeNull()
    expect(listener).toHaveBeenCalledTimes(2)
    expect(pendingCount()).toBe(0)
  })

  it('an answer to any request clears the banner, and finishing twice is harmless', () => {
    const slow = trackRequest('/auth/me')
    const other = trackRequest('/sessions')
    vi.advanceTimersByTime(SLOW_AFTER_MS)
    expect(getWakingSince()).not.toBeNull()
    other()
    expect(getWakingSince()).toBeNull()
    slow()
    slow()
    expect(pendingCount()).toBe(0)
  })

  it('does not treat a long LLM answer or an upload as a sleeping server', () => {
    const chat = trackRequest('/chat', 'POST')
    const cards = trackRequest('/flashcards', 'POST')
    const upload = trackRequest('/documents', 'POST')
    vi.advanceTimersByTime(60_000)
    expect(getWakingSince()).toBeNull()
    chat()
    cards()
    upload()
  })

  it('but a plain GET /documents still counts', () => {
    trackRequest('/documents', 'GET')
    vi.advanceTimersByTime(SLOW_AFTER_MS)
    expect(getWakingSince()).not.toBeNull()
  })
})
