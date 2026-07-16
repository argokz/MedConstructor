import type {
  ApiEndpointBody,
  ApiEndpointPath,
  ApiEndpointResponse,
  ApiMethod,
} from '~/types/api'

export type ApiQueryValue = string | number | boolean | null | undefined
export type ApiQuery = Record<string, ApiQueryValue | ApiQueryValue[]>

export interface ApiClientOptions {
  accessToken?: string | null
}

export interface ApiRequestOptions<TBody = unknown> {
  method?: ApiMethod
  body?: TBody
  query?: ApiQuery
  headers?: HeadersInit
  signal?: AbortSignal
  timeout?: number
  retry?: number | false
  accessToken?: string | null
}

type FetchBody = BodyInit | Record<string, unknown> | null | undefined
type BodyOption<TBody> = [TBody] extends [never] ? { body?: never } : { body: TBody }

export type ApiTypedRequestOptions<
  TMethod extends ApiMethod,
  TPath extends ApiEndpointPath<TMethod>,
> = Omit<ApiRequestOptions<ApiEndpointBody<TMethod, TPath>>, 'method' | 'body'> &
  BodyOption<ApiEndpointBody<TMethod, TPath>>

function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, '')
}

export function resolveApiBase(): string {
  const config = useRuntimeConfig()
  const publicBase = trimTrailingSlash(String(config.public.apiBase || '/medical-api'))
  const internalBase = trimTrailingSlash(String(config.public.internalApiBase || 'http://127.0.0.1:8012'))

  if (import.meta.server) {
    return internalBase
  }

  const host = window.location.hostname
  const isLocal = host === 'localhost' || host === '127.0.0.1'

  if (publicBase.startsWith('http://') || publicBase.startsWith('https://')) {
    if (isLocal) {
      return publicBase
    }
    if (publicBase.includes('127.0.0.1') || publicBase.includes('localhost')) {
      return `${window.location.origin}/medical-api`
    }
    return publicBase
  }

  if (isLocal) {
    return internalBase
  }

  return `${window.location.origin}${publicBase.startsWith('/') ? publicBase : `/${publicBase}`}`
}

export function resolveApiV1Url(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${resolveApiBase()}/api/v1${normalizedPath}`
}

function resolveAccessToken(explicitToken: string | null | undefined): string | null {
  if (explicitToken !== undefined) {
    return explicitToken
  }
  return useCookie<string | null>('mc_access').value
}

function buildHeaders(headers: HeadersInit | undefined, accessToken: string | null): Headers {
  const result = new Headers(headers)
  if (accessToken && !result.has('Authorization')) {
    result.set('Authorization', `Bearer ${accessToken}`)
  }
  return result
}

function toFetchBody<TBody>(body: TBody | undefined): FetchBody {
  return body as FetchBody
}

export function createApiClient(options: ApiClientOptions = {}) {
  async function request<TResponse, TBody = unknown>(
    path: string,
    requestOptions: ApiRequestOptions<TBody> = {},
  ): Promise<TResponse> {
    const accessToken = resolveAccessToken(requestOptions.accessToken ?? options.accessToken)

    return await $fetch<TResponse>(resolveApiV1Url(path), {
      body: toFetchBody(requestOptions.body),
      headers: buildHeaders(requestOptions.headers, accessToken),
      method: requestOptions.method,
      query: requestOptions.query,
      retry: requestOptions.retry,
      signal: requestOptions.signal,
      timeout: requestOptions.timeout,
    })
  }

  async function endpoint<
    TMethod extends ApiMethod,
    TPath extends ApiEndpointPath<TMethod>,
  >(
    method: TMethod,
    path: TPath,
    requestOptions: ApiTypedRequestOptions<TMethod, TPath>,
  ): Promise<ApiEndpointResponse<TMethod, TPath>> {
    return await request<ApiEndpointResponse<TMethod, TPath>, ApiEndpointBody<TMethod, TPath>>(
      path,
      {
        ...requestOptions,
        method,
      },
    )
  }

  return {
    endpoint,
    get: <TResponse>(path: string, requestOptions?: Omit<ApiRequestOptions<never>, 'body' | 'method'>) =>
      request<TResponse, never>(path, { ...requestOptions, method: 'GET' }),
    patch: <TResponse, TBody>(path: string, body: TBody, requestOptions?: Omit<ApiRequestOptions<TBody>, 'body' | 'method'>) =>
      request<TResponse, TBody>(path, { ...requestOptions, body, method: 'PATCH' }),
    post: <TResponse, TBody>(path: string, body: TBody, requestOptions?: Omit<ApiRequestOptions<TBody>, 'body' | 'method'>) =>
      request<TResponse, TBody>(path, { ...requestOptions, body, method: 'POST' }),
    put: <TResponse, TBody>(path: string, body: TBody, requestOptions?: Omit<ApiRequestOptions<TBody>, 'body' | 'method'>) =>
      request<TResponse, TBody>(path, { ...requestOptions, body, method: 'PUT' }),
    remove: <TResponse = void>(path: string, requestOptions?: Omit<ApiRequestOptions<never>, 'body' | 'method'>) =>
      request<TResponse, never>(path, { ...requestOptions, method: 'DELETE' }),
    request,
    url: resolveApiV1Url,
  }
}
