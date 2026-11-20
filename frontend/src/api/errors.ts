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

/** 401/403: the access code is missing or wrong. The client has already cleared it. */
export class AuthError extends ApiError {
  constructor(status: number, detail: string) {
    super(status, detail)
    this.name = 'AuthError'
  }
}

export const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
