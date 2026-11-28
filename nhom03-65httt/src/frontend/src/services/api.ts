/**
 * EduVision BI - Dịch vụ API kết nối Backend FastAPI (EduVision BI, Nhóm 03).
 *
 * HA2: Kết nối API thật (FastAPI) cho tìm kiếm, lọc và phân trang đánh giá.
 * URL cấu hình duy nhất từ biến môi trường Vite VITE_API_BASE_URL.
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1"

/**
 * Lấy Bearer token từ localStorage nếu người dùng đã đăng nhập.
 */
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  try {
    const token = localStorage.getItem("eduvision.token")
    if (token) {
      headers["Authorization"] = `Bearer ${token}`
    }
  } catch {
    // Không truy cập được localStorage
  }
  return headers
}

/**
 * Hàm gọi API tổng quát, xử lý lỗi mạng và trả thông báo tiếng Việt thân thiện (HA2.3).
 * Tự động chuyển hướng về trang /login và xóa session khi gặp lỗi 401 Unauthorized (B7).
 */
async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`
  const headers = {
    ...getAuthHeaders(),
    ...(options.headers as Record<string, string> | undefined),
  }

  let response: Response
  try {
    response = await fetch(url, { ...options, headers })
  } catch {
    throw new Error(
      `Không thể kết nối đến máy chủ API (${API_BASE_URL}). Vui lòng kiểm tra lại dịch vụ backend.`
    )
  }

  // B7: Xử lý 401 Unauthorized
  if (response.status === 401) {
    try {
      localStorage.removeItem("eduvision.token")
      localStorage.removeItem("eduvision.session")
    } catch {
      // Bỏ qua lỗi truy cập storage
    }
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login"
    }
    throw new Error("Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.")
  }

  if (!response.ok) {
    let errorDetail = `Lỗi yêu cầu máy chủ: mã trạng thái ${response.status}`
    try {
      const data = await response.json()
      if (data.detail) {
        errorDetail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)
      }
    } catch {
      // Giữ thông báo mã trạng thái mặc định
    }
    throw new Error(errorDetail)
  }

  return response.json() as Promise<T>
}

// ============================================================================
// Các kiểu dữ liệu DTO
// ============================================================================

export interface PlatformItem {
  id: string
  name: string
  code: string
  category: "domestic" | "international"
  groupName: string // "Trong nước" hoặc "Quốc tế"
}

export interface ReviewItem {
  review_key: number
  review_id: string
  platform: string
  source: string
  rating: number | null
  created_at: string | null
  text: string | null
  sentiment: string | null // "Tích cực", "Trung lập", "Tiêu cực", hoặc null nếu chưa có nhãn
  sentiment_score: number | null
  aspect: string | null
  aspects: string[]
  misaligned: boolean
}

export interface ReviewsResponse {
  total: number
  page: number
  page_size: number
  total_pages: number
  items: ReviewItem[]
}

export interface ReviewFilterParams {
  platform?: string
  start_date?: string
  end_date?: string
  sentiment?: string
  aspect?: string
  keyword?: string
  rating?: number
  misaligned_only?: boolean
  source?: string
  page?: number
  page_size?: number
}

// ============================================================================
// Các hàm API thật (HA2)
// ============================================================================

/**
 * Lấy danh sách 9 nền tảng E-learning từ GET /api/v1/platforms (từ tệp cấu hình chuẩn platforms.yml)
 */
export async function fetchPlatforms(): Promise<PlatformItem[]> {
  interface RawPlatform {
    id: string
    group: string
    play_id?: string | null
    ios_id?: string | null
  }

  const raw = await fetchApi<RawPlatform[]>("/platforms")
  return raw.map((item, idx) => {
    const isDomestic = item.group === "trong_nuoc"
    return {
      id: String(idx + 1),
      name: item.id,
      code: item.id,
      category: isDomestic ? "domestic" : "international",
      groupName: isDomestic ? "Trong nước" : "Quốc tế",
    }
  })
}

/**
 * Tìm kiếm và lọc đánh giá từ GET /api/v1/reviews (HA2.4, HA2.5, HA2.6)
 */
export async function fetchReviews(params: ReviewFilterParams = {}): Promise<ReviewsResponse> {
  const query = new URLSearchParams()

  if (params.platform && params.platform !== "Tất cả nền tảng") {
    query.set("platform", params.platform)
  }
  if (params.source && params.source !== "Tất cả nguồn") {
    query.set("source", params.source)
  }
  if (params.sentiment && params.sentiment !== "Tất cả cảm xúc") {
    query.set("sentiment", params.sentiment)
  }
  if (params.aspect && params.aspect !== "Tất cả khía cạnh") {
    query.set("aspect", params.aspect)
  }
  if (params.keyword?.trim()) {
    query.set("keyword", params.keyword.trim())
  }
  if (params.rating) {
    query.set("rating", String(params.rating))
  }
  if (params.misaligned_only) {
    query.set("misaligned_only", "true")
  }
  if (params.start_date) {
    query.set("start_date", params.start_date)
  }
  if (params.end_date) {
    query.set("end_date", params.end_date)
  }
  if (params.page) {
    query.set("page", String(params.page))
  }
  if (params.page_size) {
    query.set("page_size", String(params.page_size))
  }

  const queryString = query.toString()
  const endpoint = `/reviews${queryString ? `?${queryString}` : ""}`
  return fetchApi<ReviewsResponse>(endpoint)
}

/**
 * Lấy chi tiết một đánh giá theo khóa review_key từ GET /api/v1/reviews/{review_key}
 */
export async function fetchReviewByKey(reviewKey: number): Promise<ReviewItem> {
  return fetchApi<ReviewItem>(`/reviews/${reviewKey}`)
}

// ============================================================================
// DTOs & API Dự báo M3 & Bất thường (HA2.7 - Demo P1)
// ============================================================================

export interface ForecastValue {
  forecast: number
  ci_lower: number | null
  ci_upper: number | null
  actual: number | null
}

export interface ForecastPeriod {
  month: string // "YYYY-MM-DD"
  sentiment_index?: ForecastValue | null
  negative_rate?: ForecastValue | null
}

export interface ForecastResponse {
  platform: string
  message: string | null
  periods: ForecastPeriod[]
}

/**
 * Lấy dữ liệu dự báo ngắn hạn M3 (Sentiment Index và Tỷ lệ tiêu cực) theo nền tảng
 * GET /api/v1/forecast?platform={platform}&periods={periods}
 */
export async function fetchForecast(
  platform: string,
  periods: number = 12
): Promise<ForecastResponse> {
  const query = new URLSearchParams({
    platform,
    periods: String(periods),
  })
  return fetchApi<ForecastResponse>(`/forecast?${query.toString()}`)
}

export interface AnomalyPeriod {
  period_start: string
  period_end: string
  reviews: number
  negative_rate: number
  baseline_mean: number | null
  baseline_std: number | null
  threshold: number | null
  is_anomaly: boolean
  events: string[]
}

export interface AnomalyResponse {
  platform: string
  metric: string
  status: "ok" | "khong_du_ky" | string
  message: string | null
  periods: AnomalyPeriod[]
}

/**
 * Phát hiện bất thường tỷ lệ tiêu cực theo kỳ hai tuần
 * GET /api/v1/anomaly?platform={platform}&periods={periods}
 */
export async function fetchAnomaly(
  platform: string,
  periods: number = 24
): Promise<AnomalyResponse> {
  const query = new URLSearchParams({
    platform,
    periods: String(periods),
  })
  return fetchApi<AnomalyResponse>(`/anomaly?${query.toString()}`)
}

// ============================================================================
// DTOs & API AI Predict (M1 Sentiment PhoBERT & M2 Aspects ABSA)
// ============================================================================

export interface AspectItemPrediction {
  aspect_name: "Technical" | "Academic" | "Customer Service" | "Pricing" | "Other" | string
  sentiment_label: "tich_cuc" | "trung_tinh" | "tieu_cuc" | string
  sentiment_score?: number
  confidence?: number
}

export interface AspectsPredictionResponse {
  model: string
  aspects: AspectItemPrediction[]
}

export interface SentimentProbabilities {
  positive?: number
  neutral?: number
  negative?: number
  [key: string]: number | undefined
}

export interface SentimentPredictionResponse {
  model?: string
  sentiment?: string
  sentiment_label?: string
  label?: string
  label_vi?: string
  confidence?: number
  scores?: Record<string, number>
  probabilities?: SentimentProbabilities
  detail?: string
}

/**
 * Dự đoán khía cạnh nhắc tới trong câu đánh giá (M2, ABSA)
 * POST /api/v1/predict/aspects
 */
export async function predictAspects(text: string): Promise<AspectsPredictionResponse> {
  return fetchApi<AspectsPredictionResponse>("/predict/aspects", {
    method: "POST",
    body: JSON.stringify({ text }),
  })
}

/**
 * Dự đoán cảm xúc 3 lớp cho một câu đánh giá (M1, PhoBERT)
 * POST /api/v1/predict/sentiment
 */
export async function predictSentiment(text: string): Promise<SentimentPredictionResponse> {
  return fetchApi<SentimentPredictionResponse>("/predict/sentiment", {
    method: "POST",
    body: JSON.stringify({ text }),
  })
}

// ============================================================================
// DTOs & API KPI/BHI/Aspects (kpi.py) & Cảnh báo (alerts.py)
// ============================================================================

export interface KpiPeriod {
  month: string // "YYYY-MM-DD"
  platform_name: string
  platform_group: string
  new_review_count: number
  positive_rate: number | null
  negative_rate: number | null
  avg_rating: number | null
  sentiment_index: number | null
  bhi: number | null
  review_share_in_group: number | null
}

export interface KpiFilterParams {
  platform_name?: string
  platform?: string
  platform_group?: string
  start_date?: string
  end_date?: string
}

export interface KpiResponse {
  status: "ok" | "khong_co_du_lieu" | string
  message: string | null
  filters: KpiFilterParams
  data: KpiPeriod[]
}

export interface BhiPoint {
  month: string // "YYYY-MM-DD"
  platform_name: string
  platform_group: string
  review_count: number
  sentiment_index: number | null
  avg_rating: number | null
  bhi: number | null
  flags: string[]
}

export interface BhiResponse {
  status: "ok" | "khong_co_du_lieu" | string
  message: string | null
  filters: KpiFilterParams
  data: BhiPoint[]
}

export interface AspectCountItem {
  platform_name: string
  platform_group: string
  aspect_name: string
  sentiment_label: string
  count: number
}

export interface KpiAspectsResponse {
  status: "ok" | "khong_co_du_lieu" | string
  message: string | null
  filters: KpiFilterParams
  data: AspectCountItem[]
}

/**
 * Lấy danh sách KPI theo tháng: GET /api/v1/kpi
 */
export async function fetchKpi(params: KpiFilterParams = {}): Promise<KpiResponse> {
  const query = new URLSearchParams()
  if (params.platform_name) query.set("platform_name", params.platform_name)
  if (params.platform) query.set("platform", params.platform)
  if (params.platform_group) query.set("platform_group", params.platform_group)
  if (params.start_date) query.set("start_date", params.start_date)
  if (params.end_date) query.set("end_date", params.end_date)
  const qs = query.toString()
  return fetchApi<KpiResponse>(`/kpi${qs ? `?${qs}` : ""}`)
}

/**
 * Lấy Brand Health Index (BHI) theo tháng: GET /api/v1/bhi
 */
export async function fetchBhi(params: KpiFilterParams = {}): Promise<BhiResponse> {
  const query = new URLSearchParams()
  if (params.platform_name) query.set("platform_name", params.platform_name)
  if (params.platform) query.set("platform", params.platform)
  if (params.platform_group) query.set("platform_group", params.platform_group)
  if (params.start_date) query.set("start_date", params.start_date)
  if (params.end_date) query.set("end_date", params.end_date)
  const qs = query.toString()
  return fetchApi<BhiResponse>(`/bhi${qs ? `?${qs}` : ""}`)
}

/**
 * Lấy phân bố cảm xúc theo khía cạnh ABSA: GET /api/v1/kpi/aspects
 */
export async function fetchKpiAspects(params: KpiFilterParams = {}): Promise<KpiAspectsResponse> {
  const query = new URLSearchParams()
  if (params.platform_name) query.set("platform_name", params.platform_name)
  if (params.platform_group) query.set("platform_group", params.platform_group)
  if (params.start_date) query.set("start_date", params.start_date)
  if (params.end_date) query.set("end_date", params.end_date)
  const qs = query.toString()
  return fetchApi<KpiAspectsResponse>(`/kpi/aspects${qs ? `?${qs}` : ""}`)
}

// Ghi chú: Backend hiện chưa có endpoint /kpi/summary và /compare (dự kiến tính toán trực tiếp từ /kpi)

// ============================================================================
// DTOs & API Cảnh báo (alerts.py)
// ============================================================================

export interface AlertItem {
  alert_key: number
  detected_at: string
  detected_date: string
  platform_name: string
  aspect_name: string | null
  metric_name: string
  metric_value: number
  threshold: number
  severity: "cao" | "trung_binh" | "thap"
  status: "moi" | "dang_xu_ly" | "da_xu_ly"
  recommended_action: string | null
  responsible_department: string | null
  notified: boolean
}

export interface AlertListResponse {
  total: number
  limit: number
  offset: number
  items: AlertItem[]
}

export interface AlertFilterParams {
  platform?: string
  status?: "moi" | "dang_xu_ly" | "da_xu_ly"
  department?: string
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

/**
 * Lấy danh sách cảnh báo: GET /api/v1/alerts
 */
export async function fetchAlerts(params: AlertFilterParams = {}): Promise<AlertListResponse> {
  const query = new URLSearchParams()
  if (params.platform) query.set("platform", params.platform)
  if (params.status) query.set("status", params.status)
  if (params.department) query.set("department", params.department)
  if (params.start_date) query.set("start_date", params.start_date)
  if (params.end_date) query.set("end_date", params.end_date)
  if (params.limit !== undefined) query.set("limit", String(params.limit))
  if (params.offset !== undefined) query.set("offset", String(params.offset))
  const qs = query.toString()
  return fetchApi<AlertListResponse>(`/alerts${qs ? `?${qs}` : ""}`)
}
