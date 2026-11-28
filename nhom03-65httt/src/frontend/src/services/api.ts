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
// DTOs & API KPI/BHI/So sánh (Phần C: chuẩn bị cho kpi.py của Hưng)
// ============================================================================

export interface KpiItem {
  platform: string
  period_start: string
  value: number
  sample_size?: number
  is_partial?: boolean
}

export interface KpiSeriesResponse {
  kpi: string
  name: string
  unit: string
  granularity: string
  items: KpiItem[]
}

export interface KpiSummaryMetric {
  current_value: number
  previous_value?: number
  change_rate?: number
  unit?: string
}

export interface KpiSummaryResponse {
  platform: string
  period: string
  new_reviews: KpiSummaryMetric
  sentiment_index: KpiSummaryMetric
  negative_rate: KpiSummaryMetric
  bhi: KpiSummaryMetric
}

export interface BhiPoint {
  period_start: string
  value: number
}

export interface BhiResponse {
  platform: string
  items: BhiPoint[]
}

export interface PlatformCompareItem {
  platform: string
  sample_size: number
  value: number
}

export interface CompareResponse {
  kpi: string
  common_period: {
    start: string
    end: string
  }
  items: PlatformCompareItem[]
}

/**
 * Lấy chuỗi dữ liệu KPI: GET /api/v1/kpi?kpi=&platform=
 */
export async function fetchKpi(kpi: string, platform?: string): Promise<KpiSeriesResponse> {
  const query = new URLSearchParams({ kpi })
  if (platform) query.set("platform", platform)
  return fetchApi<KpiSeriesResponse>(`/kpi?${query.toString()}`)
}

/**
 * Thẻ số tóm tắt kỳ gần nhất: GET /api/v1/kpi/summary?platform=
 */
export async function fetchKpiSummary(platform: string): Promise<KpiSummaryResponse> {
  return fetchApi<KpiSummaryResponse>(`/kpi/summary?platform=${encodeURIComponent(platform)}`)
}

/**
 * Biểu đồ chỉ số sức khỏe thương hiệu BHI: GET /api/v1/bhi?platform=&from=&to=
 */
export async function fetchBhi(platform: string, from?: string, to?: string): Promise<BhiResponse> {
  const query = new URLSearchParams({ platform })
  if (from) query.set("from", from)
  if (to) query.set("to", to)
  return fetchApi<BhiResponse>(`/bhi?${query.toString()}`)
}

/**
 * So sánh giữa các nền tảng: GET /api/v1/compare?platforms=A,B&kpi=
 */
export async function fetchCompare(platforms: string[], kpi: string): Promise<CompareResponse> {
  const query = new URLSearchParams({
    platforms: platforms.join(","),
    kpi,
  })
  return fetchApi<CompareResponse>(`/compare?${query.toString()}`)
}
