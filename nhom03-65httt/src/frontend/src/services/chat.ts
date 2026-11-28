/**
 * Gọi chatbot T6: POST /api/v1/chat (cần đăng nhập). Tách riêng khỏi api.ts để không sửa chung một tệp.
 */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1"

export interface ChatResponse {
  answer: string
  intent: string
  mode: string
  platforms: string[]
  period: string | null
  data: Record<string, unknown>[]
  suggestions: string[]
}

export async function askChat(question: string): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  try {
    const token = localStorage.getItem("eduvision.token")
    if (token) headers["Authorization"] = `Bearer ${token}`
  } catch {
    // Không truy cập được localStorage: gửi không kèm token, API sẽ trả 401
  }
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question }),
  })
  if (!response.ok) {
    let detail = ""
    try {
      detail = (await response.json())?.detail ?? ""
    } catch {
      // thân phản hồi không phải JSON
    }
    if (response.status === 401) throw new Error("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.")
    if (response.status === 503) throw new Error("Chưa kết nối được kho dữ liệu, thử lại sau ít phút.")
    throw new Error(typeof detail === "string" && detail ? detail : `Lỗi ${response.status} khi gọi trợ lý.`)
  }
  return (await response.json()) as ChatResponse
}
