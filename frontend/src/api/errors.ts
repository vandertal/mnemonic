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

/** 429: too many requests (auth attempts, or the LLM budget). */
export class RateLimitError extends ApiError {
  constructor(detail: string) {
    super(429, detail)
    this.name = 'RateLimitError'
  }
}

/** 404: no such resource, or someone else's (the server answers both the same way). */
export class NotFoundError extends ApiError {
  constructor(detail: string) {
    super(404, detail)
    this.name = 'NotFoundError'
  }
}

/** Pick the typed error for a status. */
export function errorForStatus(status: number, detail: string): ApiError {
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
      return new RateLimitError(detail)
    default:
      return new ApiError(status, detail)
  }
}

export const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
