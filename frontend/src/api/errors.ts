/** The server answered with an error status. `detail` is FastAPI's message, when there is one. */
export class ApiError extends Error {
  readonly status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
  }
}

/** The request never got an answer: offline, DNS, CORS failure, server down. */
export class NetworkError extends Error {
  constructor() {
    super('Network request failed')
    this.name = 'NetworkError'
  }
}

/** 401: the token is missing/expired (any call), or the email/password is wrong (login). */
export class AuthError extends ApiError {
  constructor(detail: string) {
    super(401, detail)
    this.name = 'AuthError'
  }
}

/** 403: on register, a wrong or missing invitation code. */
export class ForbiddenError extends ApiError {
  constructor(detail: string) {
    super(403, detail)
    this.name = 'ForbiddenError'
  }
}

/** 409: the email is already registered. */
export class ConflictError extends ApiError {
  constructor(detail: string) {
    super(409, detail)
    this.name = 'ConflictError'
  }
}

/** 429: too many requests (auth attempts, or the LLM budget). `retryAfter` is the server's Retry-After, in seconds. */
export class RateLimitError extends ApiError {
  readonly retryAfter: number | null
  constructor(detail: string, retryAfter: number | null = null) {
    super(429, detail)
    this.name = 'RateLimitError'
    this.retryAfter = retryAfter
  }
}

/** One problem from FastAPI's 422 list (`loc` and `msg` are all we use; `input` is never sent back). */
export interface FieldProblem {
  loc: (string | number)[]
  msg: string
  type: string
}

/** 422: the server rejected the input (too long, blank, ...). `problems` is FastAPI's list. */
export class ValidationError extends ApiError {
  readonly problems: FieldProblem[]
  constructor(detail: string, problems: FieldProblem[]) {
    super(422, detail)
    this.name = 'ValidationError'
    this.problems = problems
  }
}

/** The answer stream ended without a `done` or `error` event: the connection dropped mid-answer. */
export class StreamInterruptedError extends Error {
  constructor() {
    super('The answer stream ended unexpectedly')
    this.name = 'StreamInterruptedError'
  }
}

/** 404: no such resource, or someone else's (the server answers both the same way). */
export class NotFoundError extends ApiError {
  constructor(detail: string) {
    super(404, detail)
    this.name = 'NotFoundError'
  }
}

/** `Retry-After` is whole seconds (or an HTTP date, which our server never sends): a number or null. */
export function parseRetryAfter(value: string | null | undefined): number | null {
  if (!value || !/^\d+$/.test(value.trim())) return null
  const seconds = Number(value)
  return seconds > 0 && seconds <= 3600 ? seconds : null
}

/** Pick the typed error for a status. */
export function errorForStatus(status: number, detail: string, extra: { retryAfter?: number | null; problems?: FieldProblem[] } = {}): ApiError {
  switch (status) {
    case 401:
      return new AuthError(detail)
    case 403:
      return new ForbiddenError(detail)
    case 404:
      return new NotFoundError(detail)
    case 409:
      return new ConflictError(detail)
    case 429:
      return new RateLimitError(detail, extra.retryAfter ?? null)
    case 422:
      // A plain-string detail ("The file has no text") is already a readable sentence: keep it as is.
      return extra.problems?.length ? new ValidationError(detail, extra.problems) : new ApiError(422, detail)
    default:
      return new ApiError(status, detail)
  }
}

export const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
