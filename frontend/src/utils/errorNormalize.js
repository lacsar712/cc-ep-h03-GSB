/**
 * 归一化接口错误。
 * 409 = 版本冲突（乐观锁/终态不可变更），与 400/422 参数校验失败严格区分，
 * 不再合并显示为“参数错误”。
 */
export function normalizeApiError(err) {
  const status = err?.response?.status || err?.status || err?.statusCode
  const detail = err?.message || err?.detail || '请求失败'
  if (status === 409) {
    return { status: 409, message: '版本冲突：' + detail, kind: 'conflict' }
  }
  if (status === 400 || status === 422) {
    return { status, message: '参数不合法：' + detail, kind: 'validation' }
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
