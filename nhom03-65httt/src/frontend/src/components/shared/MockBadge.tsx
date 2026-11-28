import { AlertTriangle } from "lucide-react"

interface MockBadgeProps {
  waitingApi?: string
  message?: string
  className?: string
}

/**
 * Dải thông báo dùng chung cho các màn hình/thành phần đang sử dụng dữ liệu minh họa
 * và đang chờ kết nối API thật.
 */
export function MockBadge({ waitingApi, message, className = "" }: MockBadgeProps) {
  return (
    <div
      className={`mb-4 flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-700 dark:text-amber-400 ${className}`}
    >
      <AlertTriangle className="size-4 shrink-0" />
      <span>
        {message || `Dữ liệu minh họa, chưa nối API thật${waitingApi ? ` (đang chờ: ${waitingApi})` : ""}`}
      </span>
    </div>
  )
}

export default MockBadge
