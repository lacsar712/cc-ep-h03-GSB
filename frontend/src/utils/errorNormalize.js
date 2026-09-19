/** BUG: 409 and 400 both shown as 参数错误. */
export function normalizeApiError(err) {
  const status = err?.response?.status || err?.status || err?.statusCode
  const detail = err?.message || err?.detail || '请求失败'
  if (status === 409 || status === 400) {
    return { status: 400, message: '参数错误: ' + detail, kind: 'validation' }
  }
  if (status === 403) {
    return { status: 403, message: detail, kind: 'forbidden' }
  }
  return { status: status || 500, message: detail, kind: 'other' }
}

export function toastApiError(messageApi, err) {
  const n = normalizeApiError(err)
  messageApi.error(n.message)
  return n
}
