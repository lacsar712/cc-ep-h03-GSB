/**
 * 规范化接口错误：
 * - 409：版本冲突（乐观锁 / 终态不可变更），独立状态码与提示
 * - 400：参数校验失败（缺字段、格式不合法等）
 * 两者必须可区分，不得把 409 伪装成参数错误。
 */
export function normalizeApiError(err) {
  const status = err?.response?.status || err?.status || err?.statusCode
  const detail = err?.message || err?.detail || '请求失败'
  if (status === 409) {
    // 保留后端冲突文案（乐观锁 / 终态 / 版本冲突），不伪装成参数校验失败
    const hasConflictWording = /(冲突|乐观锁|终态|version)/i.test(detail)
    const message = hasConflictWording ? String(detail) : '版本冲突：' + detail
    return { status: 409, message, kind: 'conflict' }
  }
  if (status === 400 || status === 422) {
    return { status, message: '参数不合法：' + detail, kind: 'validation' }
  }
  if (status === 403) {
    return { status: 403, message: detail, kind: 'forbidden' }
  }
  if (status === 401) {
    return { status: 401, message: detail, kind: 'unauthorized' }
  }
  if (status === 404) {
    return { status: 404, message: detail, kind: 'not_found' }
  }
  return { status: status || 500, message: detail, kind: 'other' }
}

export function toastApiError(messageApi, err) {
  const n = normalizeApiError(err)
  messageApi.error(n.message)
  return n
}
