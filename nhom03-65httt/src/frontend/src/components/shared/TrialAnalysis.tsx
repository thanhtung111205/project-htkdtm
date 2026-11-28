import { useState } from "react"
import { AlertCircle, CheckCircle2, ChevronRight, LoaderCircle, Sparkles, Tag } from "lucide-react"

import { Panel } from "@/components/shared/common"
import {
  predictAspects,
  predictSentiment,
  type AspectsPredictionResponse,
  type SentimentPredictionResponse,
} from "@/services/api"

const SAMPLE_TEXTS = [
  "Ứng dụng phát âm rất chuẩn và bài giảng hay, nhưng giá gói năm hơi đắt.",
  "Giao diện trực quan dễ dùng, giáo viên giảng bài nhiệt tình và dễ hiểu.",
  "Ứng dụng thường xuyên bị giật lag khi tải bài học và văng ra ngoài.",
  "Học phí quá cao so với chất lượng, hỗ trợ khách hàng phản hồi rất chậm.",
]

export function TrialAnalysis() {
  const [text, setText] = useState<string>(SAMPLE_TEXTS[0])
  const [analyzing, setAnalyzing] = useState<boolean>(false)

  const [aspectResult, setAspectResult] = useState<AspectsPredictionResponse | null>(null)
  const [aspectError, setAspectError] = useState<string | null>(null)

  const [sentimentResult, setSentimentResult] = useState<SentimentPredictionResponse | null>(null)
  const [sentimentError, setSentimentError] = useState<string | null>(null)

  const [hasRun, setHasRun] = useState<boolean>(false)

  const handleAnalyze = async () => {
    const trimmed = text.trim()
    if (!trimmed) return

    setAnalyzing(true)
    setHasRun(true)
    setAspectError(null)
    setSentimentError(null)

    const [aspectSettled, sentimentSettled] = await Promise.allSettled([
      predictAspects(trimmed),
      predictSentiment(trimmed),
    ])

    if (aspectSettled.status === "fulfilled") {
      setAspectResult(aspectSettled.value)
      setAspectError(null)
    } else {
      setAspectResult(null)
      const msg = aspectSettled.reason instanceof Error ? aspectSettled.reason.message : "Lỗi khi gọi API khía cạnh"
      setAspectError(msg)
    }

    if (sentimentSettled.status === "fulfilled") {
      setSentimentResult(sentimentSettled.value)
      setSentimentError(null)
    } else {
      setSentimentResult(null)
      const msg = sentimentSettled.reason instanceof Error ? sentimentSettled.reason.message : "Lỗi khi gọi API cảm xúc"
      setSentimentError(msg)
    }

    setAnalyzing(false)
  }

  const formatSentimentBadge = (label?: string) => {
    if (!label) return null
    const l = label.toLowerCase()
    if (l === "tich_cuc" || l === "positive" || l === "tích cực") {
      return <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-600">Tích cực</span>
    }
    if (l === "tieu_cuc" || l === "negative" || l === "tiêu cực") {
      return <span className="rounded-full bg-rose-500/15 px-2.5 py-0.5 text-xs font-semibold text-rose-600">Tiêu cực</span>
    }
    return <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-600">Trung lập</span>
  }

  const formatModelLabel = (modelName?: string) => {
    if (!modelName) return "Đang xác định"
    if (modelName.toLowerCase().includes("keyword_baseline")) {
      return "baseline từ khóa, chưa phải M2"
    }
    return modelName
  }

  return (
    <Panel
      title="Phân tích thử nghiệm AI một câu đánh giá"
      subtitle="Thử nghiệm trực tiếp mô hình M1 (Cảm xúc PhoBERT) và M2 (Khía cạnh ABSA) trên dữ liệu nhập tức thời"
      className="border-indigo-500/30 bg-gradient-to-b from-indigo-500/5 to-transparent"
    >
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-foreground">
            Nhập câu đánh giá học viên cần phân tích:
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="Nhập nội dung đánh giá của học viên vào đây..."
            className="w-full rounded-xl border border-border bg-background p-3 text-xs leading-relaxed text-foreground shadow-inner focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
          />
        </div>

        {/* Các câu mẫu click nhanh */}
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">Câu mẫu thử nghiệm nhanh:</div>
          <div className="flex flex-wrap gap-1.5">
            {SAMPLE_TEXTS.map((sample, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setText(sample)}
                className="rounded-lg border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-indigo-500 hover:text-foreground"
              >
                {sample.length > 50 ? `${sample.slice(0, 48)}...` : sample}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border pt-3">
          <div className="text-[11px] text-muted-foreground">
            Kết nối API: <code>POST /api/v1/predict/aspects</code> & <code>POST /api/v1/predict/sentiment</code>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={analyzing || !text.trim()}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
          >
            {analyzing ? (
              <>
                <LoaderCircle className="size-4 animate-spin" />
                Đang phân tích AI...
              </>
            ) : (
              <>
                <Sparkles className="size-4" />
                Phân tích câu
              </>
            )}
          </button>
        </div>

        {/* Khối hiển thị kết quả */}
        {hasRun && (
          <div className="mt-4 grid grid-cols-1 gap-4 border-t border-border pt-4 md:grid-cols-2">
            {/* Cột 1: Kết quả Khía cạnh (M2) */}
            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Tag className="size-4 text-indigo-600" />
                  <span>Khía cạnh được nhắc (M2)</span>
                </div>
                {aspectResult && (
                  <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    Mô hình: <b>{formatModelLabel(aspectResult.model)}</b>
                  </span>
                )}
              </div>

              {aspectError && (
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    <div>
                      <p className="font-semibold">Thông báo mô hình M2</p>
                      <p className="mt-0.5 text-[11px]">{aspectError}</p>
                    </div>
                  </div>
                </div>
              )}

              {aspectResult && (
                <div>
                  {aspectResult.aspects.length === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      Không phát hiện khía cạnh nào trong 4 nhóm chính.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {aspectResult.aspects.map((asp, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between rounded-lg border border-border p-2.5 text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <CheckCircle2 className="size-3.5 text-indigo-600" />
                            <span className="font-semibold text-foreground">{asp.aspect_name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {formatSentimentBadge(asp.sentiment_label)}
                            {asp.confidence !== undefined && (
                              <span className="text-[10px] text-muted-foreground">
                                Độ tin cậy: {Math.round(asp.confidence * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Cột 2: Kết quả Cảm xúc (M1) */}
            <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Sparkles className="size-4 text-indigo-600" />
                  <span>Cảm xúc tổng thể (M1)</span>
                </div>
                {sentimentResult?.model && (
                  <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    Mô hình: <b>{sentimentResult.model}</b>
                  </span>
                )}
              </div>

              {sentimentError && (
                <div className="rounded-lg border border-sky-500/20 bg-sky-500/10 p-3 text-xs text-sky-700 dark:text-sky-400">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    <div>
                      <p className="font-semibold">Thông báo mô hình M1 (PhoBERT)</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed">
                        {sentimentError.includes("501") || sentimentError.includes("503") || sentimentError.includes("chưa được tích hợp")
                          ? "Mô hình cảm xúc M1 (PhoBERT) chưa được tích hợp trên nhánh chính (có sau khi PR T2 của Tùng merge)."
                          : sentimentError}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {sentimentResult && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg border border-border p-3">
                    <span className="text-xs font-medium text-muted-foreground">Dự đoán cảm xúc:</span>
                    <div>{formatSentimentBadge(sentimentResult.label_vi || sentimentResult.label || sentimentResult.sentiment || sentimentResult.sentiment_label)}</div>
                  </div>

                  {sentimentResult.confidence !== undefined && (
                    <div className="text-xs">
                      <div className="flex justify-between text-muted-foreground mb-1">
                        <span>Độ tin cậy:</span>
                        <b>{Math.round(sentimentResult.confidence * 100)}%</b>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-indigo-600"
                          style={{ width: `${Math.round(sentimentResult.confidence * 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {(sentimentResult.scores || sentimentResult.probabilities) && (
                    <div className="space-y-1.5 pt-1 text-[11px]">
                      <div className="text-muted-foreground font-medium">Xác suất phân bố 3 lớp:</div>
                      {Object.entries(sentimentResult.scores || sentimentResult.probabilities || {}).map(([k, v]) => {
                        const labelName = k === "tich_cuc" ? "Tích cực" : k === "tieu_cuc" ? "Tiêu cực" : k === "trung_tinh" ? "Trung tính" : k
                        return (
                          <div key={k} className="flex items-center justify-between">
                            <span className="text-muted-foreground">{labelName}:</span>
                            <span className="font-mono font-medium">{typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v)}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}

export default TrialAnalysis
