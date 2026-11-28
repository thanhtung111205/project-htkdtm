import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertCircle, AlertTriangle, ArrowDownRight, LoaderCircle, RefreshCw } from "lucide-react"
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { PageHeading, Panel, SelectControl } from "@/components/shared/common"
import {
  fetchPlatforms,
  fetchForecast,
  fetchAnomaly,
  type PlatformItem,
  type ForecastResponse,
  type AnomalyResponse,
} from "@/services/api"
import { maeCompare } from "@/services/mock-data"

type Metric = "sentiment" | "negative"

interface TrendChartPoint {
  month: string
  actual?: number
  forecast?: number
  lower?: number
  band?: number
}

const GRID = "hsl(var(--border))"
const TICK = { fontSize: 10, fill: "hsl(var(--muted-foreground))" }

function TrendTooltip({
  active,
  payload,
  label,
  metric,
}: {
  active?: boolean
  payload?: { dataKey?: string | number; name?: string; value?: number; color?: string }[]
  label?: string
  metric: Metric
}) {
  if (!active || !payload?.length) return null
  const visible = payload.filter(
    (item) => ["actual", "forecast"].includes(String(item.dataKey)) && typeof item.value === "number"
  )
  if (!visible.length) return null
  return (
    <div className="rounded-xl border border-border bg-card p-3 text-xs shadow-lg">
      <div className="mb-2 font-semibold text-foreground">{label}</div>
      {visible.map((item) => (
        <div key={String(item.dataKey)} className="mt-1 flex items-center justify-between gap-5">
          <span className="text-muted-foreground">{item.name}</span>
          <b style={{ color: item.color }}>
            {metric === "sentiment" ? (item.value as number).toFixed(2) : `${item.value}%`}
          </b>
        </div>
      ))}
    </div>
  )
}

export default function XuHuongPage() {
  const [platformsList, setPlatformsList] = useState<PlatformItem[]>([])
  const [platform, setPlatform] = useState<string>("ELSA Speak")
  const [metric, setMetric] = useState<Metric>("sentiment")
  const [periods, setPeriods] = useState<number>(12)

  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [forecastData, setForecastData] = useState<ForecastResponse | null>(null)
  const [anomalyData, setAnomalyData] = useState<AnomalyResponse | null>(null)

  // 1. Tải danh sách nền tảng từ GET /api/v1/platforms
  useEffect(() => {
    let mounted = true
    fetchPlatforms()
      .then((items) => {
        if (!mounted) return
        setPlatformsList(items)
        if (items.length > 0) {
          // Giữ nền tảng mặc định là ELSA Speak hoặc nền tảng đầu tiên
          const found = items.find((p) => p.name.toLowerCase() === "elsa speak")
          setPlatform(found ? found.name : items[0].name)
        }
      })
      .catch((err) => {
        if (!mounted) return
        console.warn("Không tải được danh sách nền tảng từ API:", err)
      })
    return () => {
      mounted = false
    }
  }, [])

  // 2. Tải dữ liệu dự báo (/forecast) và phát hiện bất thường (/anomaly)
  const loadData = useCallback(async () => {
    if (!platform) return
    setLoading(true)
    setError(null)
    try {
      const [forecastRes, anomalyRes] = await Promise.all([
        fetchForecast(platform, periods),
        fetchAnomaly(platform, Math.max(periods, 12)),
      ])
      setForecastData(forecastRes)
      setAnomalyData(anomalyRes)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Đã có lỗi xảy ra khi gọi API"
      setError(message)
      setForecastData(null)
      setAnomalyData(null)
    } finally {
      setLoading(false)
    }
  }, [platform, periods])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 3. Chuẩn bị dữ liệu hiển thị biểu đồ từ API thật
  const chartData = useMemo<TrendChartPoint[]>(() => {
    if (!forecastData || !forecastData.periods || forecastData.periods.length === 0) {
      return []
    }

    return forecastData.periods.map((p) => {
      const monthKey = p.month.slice(0, 7) // "YYYY-MM"
      const val = metric === "sentiment" ? p.sentiment_index : p.negative_rate

      const actual = val?.actual !== null && val?.actual !== undefined ? Number(val.actual.toFixed(2)) : undefined
      const forecast = val?.forecast !== null && val?.forecast !== undefined ? Number(val.forecast.toFixed(2)) : undefined

      let lower: number | undefined = undefined
      let band: number | undefined = undefined
      if (val?.ci_lower !== null && val?.ci_lower !== undefined && val?.ci_upper !== null && val?.ci_upper !== undefined) {
        lower = Number(val.ci_lower.toFixed(2))
        band = Math.max(0, Number((val.ci_upper - val.ci_lower).toFixed(2)))
      }

      return {
        month: monthKey,
        actual,
        forecast,
        lower,
        band,
      }
    })
  }, [forecastData, metric])

  // 4. Lấy danh sách các kỳ bất thường để đánh dấu lên biểu đồ
  const anomalyMarkers = useMemo(() => {
    if (!anomalyData?.periods) return []
    return anomalyData.periods
      .filter((a) => a.is_anomaly)
      .map((a) => {
        const monthKey = a.period_start.slice(0, 7)
        const eventText =
          a.events && a.events.length > 0 ? a.events.join(", ") : `Tiêu cực vọt lên ${a.negative_rate}%`
        return {
          month: monthKey,
          label: `Bất thường (${a.negative_rate}%)`,
          detail: eventText,
          period: `${a.period_start} → ${a.period_end}`,
          reviews: a.reviews,
          rate: a.negative_rate,
        }
      })
  }, [anomalyData])

  const platformOptions = useMemo(() => {
    if (platformsList.length > 0) {
      return platformsList.map((item) => item.name)
    }
    return [
      "ELSA Speak",
      "VUIHOC",
      "HOCMAI",
      "MONKEY",
      "DUOLINGO",
      "Khan Academy",
      "Quizlet",
      "Memrise",
      "Busuu",
    ]
  }, [platformsList])

  const lastActual = chartData.filter((d) => d.actual !== undefined).at(-1)?.actual ?? 0
  const lastForecast = chartData.filter((d) => d.forecast !== undefined).at(-1)?.forecast ?? lastActual
  const compare = maeCompare[metric]
  const maeRows = [
    { name: "Mô hình nền", value: compare.baseline },
    { name: "LightGBM, không có cảm xúc", value: compare.withoutSentiment },
    { name: "LightGBM, có đặc trưng cảm xúc", value: compare.withSentiment },
  ]
  const accuracy = metric === "sentiment" ? 78.6 : 74.2
  const domain: [number, number] = metric === "sentiment" ? [-1, 1] : [0, 100]
  const fmt = (v: number) => (metric === "sentiment" ? v.toFixed(2) : `${v}%`)

  return (
    <>
      <PageHeading
        eyebrow="TÍN HIỆU THỊ TRƯỜNG"
        title="Xu hướng & dự báo"
        description="Theo dõi diễn biến theo tháng, dự báo tháng kế tiếp theo từng nền tảng và phát hiện bất thường từ mô hình M3."
      />

      <Panel
        title="Xu hướng và dự báo theo tháng"
        subtitle="Mô hình M3 (LightGBM) · kết nối API /forecast & /anomaly"
      >
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <SelectControl
            label="Nền tảng"
            value={platform}
            onChange={setPlatform}
            options={platformOptions}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-medium text-muted-foreground">Chỉ số</span>
            <div className="flex rounded-lg border border-border p-0.5">
              {(
                [
                  ["sentiment", "Sentiment Index"],
                  ["negative", "Tỷ lệ tiêu cực (%)"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setMetric(key)}
                  className={`rounded-md px-3 py-2 text-xs font-medium ${
                    metric === key ? "bg-indigo-600 text-white" : "text-muted-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <SelectControl
            label="Số tháng gần nhất"
            value={`${periods} tháng`}
            onChange={(val) => setPeriods(Number(val.split(" ")[0]))}
            options={["6 tháng", "12 tháng", "24 tháng", "36 tháng"]}
          />
          <button
            onClick={loadData}
            title="Tải lại dữ liệu"
            className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-xs font-medium text-muted-foreground hover:bg-muted"
          >
            <RefreshCw className="size-3.5" />
            Làm mới
          </button>
        </div>

        {/* Trạng thái Đang tải */}
        {loading && (
          <div className="flex h-[320px] flex-col items-center justify-center rounded-xl border border-border bg-card/40 p-6 text-center">
            <LoaderCircle className="mb-2 size-8 animate-spin text-indigo-600" />
            <p className="text-sm font-medium text-foreground">Đang tải dữ liệu từ máy chủ API...</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Gọi /api/v1/forecast và /api/v1/anomaly cho {platform}
            </p>
          </div>
        )}

        {/* Trạng thái Lỗi (Không quay về dữ liệu mẫu) */}
        {error && !loading && (
          <div className="flex h-[320px] flex-col items-center justify-center rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-center">
            <AlertCircle className="mb-2 size-8 text-destructive" />
            <h3 className="text-sm font-semibold text-foreground">Không thể kết nối đến API dự báo</h3>
            <p className="mt-1 max-w-md text-xs text-muted-foreground leading-relaxed">{error}</p>
            <button
              onClick={loadData}
              className="mt-4 flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-sm"
            >
              <RefreshCw className="size-3.5" />
              Thử lại
            </button>
          </div>
        )}

        {/* Trạng thái Không có dữ liệu / Chuỗi quá ngắn */}
        {!loading && !error && chartData.length === 0 && (
          <div className="flex h-[320px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 p-6 text-center">
            <AlertCircle className="mb-2 size-8 text-amber-500" />
            <h3 className="text-sm font-semibold text-foreground">
              Chưa có dữ liệu dự báo cho nền tảng {platform}
            </h3>
            <p className="mt-1 max-w-lg text-xs text-muted-foreground leading-relaxed">
              {forecastData?.message ||
                "Nền tảng này có chuỗi thời gian chưa đủ 30 đánh giá/tháng hoặc chưa chạy mô hình dự báo M3."}
            </p>
          </div>
        )}

        {/* Biểu đồ khi có dữ liệu thật */}
        {!loading && !error && chartData.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-muted-foreground">
              <span>
                <i className="mr-1.5 inline-block h-0.5 w-4 bg-indigo-600 align-middle" />
                Thực tế
              </span>
              <span>
                <i className="mr-1.5 inline-block h-0.5 w-4 border-t-2 border-dashed border-violet-500 align-middle" />
                Dự báo LightGBM (M3)
              </span>
              <span>
                <i className="mr-1.5 inline-block h-3 w-4 rounded-sm bg-violet-400/30 align-middle" />
                Khoảng tin cậy
              </span>
              {anomalyMarkers.length > 0 && (
                <span>
                  <i className="mr-1.5 inline-block h-0.5 w-4 border-t-2 border-dashed border-rose-500 align-middle" />
                  Kỳ bất thường (tỷ lệ tiêu cực vọt cao)
                </span>
              )}
            </div>

            <div className="h-[340px] min-w-0">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ left: 8, right: 12, top: 12, bottom: 6 }}>
                  <CartesianGrid strokeDasharray="3 5" vertical={false} stroke={GRID} />
                  <XAxis
                    dataKey="month"
                    interval="preserveStartEnd"
                    tickLine={false}
                    axisLine={false}
                    tick={TICK}
                    minTickGap={28}
                  />
                  <YAxis
                    domain={domain}
                    tickLine={false}
                    axisLine={false}
                    tick={TICK}
                    tickFormatter={(value) => (metric === "negative" ? `${value}%` : String(value))}
                    label={{
                      value: metric === "sentiment" ? "Sentiment Index" : "Tỷ lệ tiêu cực (%)",
                      angle: -90,
                      position: "insideLeft",
                      style: { fill: "hsl(var(--muted-foreground))", fontSize: 10 },
                    }}
                  />
                  <Tooltip content={<TrendTooltip metric={metric} />} />

                  {/* Dải tin cậy CI */}
                  <Area
                    dataKey="lower"
                    stackId="ci"
                    stroke="none"
                    fill="transparent"
                    isAnimationActive={false}
                    legendType="none"
                  />
                  <Area
                    dataKey="band"
                    stackId="ci"
                    stroke="none"
                    fill="#8b5cf6"
                    fillOpacity={0.22}
                    isAnimationActive={false}
                    legendType="none"
                  />

                  {/* Đánh dấu các kỳ bất thường từ /anomaly */}
                  {anomalyMarkers.map((item, idx) => (
                    <ReferenceLine
                      key={`${item.month}-${idx}`}
                      x={item.month}
                      stroke="#ef4444"
                      strokeDasharray="3 4"
                      label={{
                        value: item.label,
                        position: "insideTopLeft",
                        fill: "#ef4444",
                        fontSize: 9,
                      }}
                    />
                  ))}

                  {/* Đường thực tế */}
                  <Line
                    dataKey="actual"
                    name="Thực tế"
                    stroke="#4f46e5"
                    strokeWidth={2.5}
                    dot={{ r: 2.5, fill: "#4f46e5" }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />

                  {/* Đường dự báo */}
                  <Line
                    dataKey="forecast"
                    name="Dự báo LightGBM"
                    stroke="#8b5cf6"
                    strokeWidth={2.5}
                    strokeDasharray="6 4"
                    dot={{ r: 3, fill: "#8b5cf6" }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* Thông báo thông điệp từ API forecast nếu có */}
            {forecastData?.message && (
              <div className="mt-3 text-[11px] text-muted-foreground italic border-t border-border pt-2">
                * {forecastData.message}
              </div>
            )}

            {/* Danh sách các kỳ bất thường được phát hiện */}
            {anomalyMarkers.length > 0 ? (
              <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-600">
                  <AlertTriangle className="size-4 shrink-0" />
                  <span>Phát hiện {anomalyMarkers.length} kỳ bất thường (đột biến tỷ lệ tiêu cực):</span>
                </div>
                <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {anomalyMarkers.map((item, idx) => (
                    <div
                      key={idx}
                      className="rounded-lg border border-border bg-card p-2.5 text-xs shadow-sm"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-rose-600">Tháng {item.month}</span>
                        <span className="text-[10px] text-muted-foreground">{item.period}</span>
                      </div>
                      <p className="mt-1 text-[11px] text-foreground/90">{item.detail}</p>
                      <div className="mt-1.5 text-[10px] text-muted-foreground">
                        Quy mô: <b>{item.reviews}</b> đánh giá · Tỷ lệ tiêu cực: <b>{item.rate}%</b>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-3 text-[10px] text-muted-foreground border-t border-border pt-2">
                {anomalyData?.status === "khong_du_ky"
                  ? (anomalyData.message || "Chuỗi kỳ hai tuần chưa đủ để phát hiện bất thường.")
                  : "Không ghi nhận kỳ bất thường nào vượt ngưỡng cơ sở."}
              </div>
            )}
          </>
        )}
      </Panel>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="MAE · Sai số tuyệt đối trung bình" subtitle="Đánh giá walk-forward trên các kỳ gần nhất">
          <div className="text-3xl font-semibold tracking-tight text-foreground">
            {String(compare.withSentiment).replace(".", ",")}
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground">{compare.unit} · thấp hơn là tốt hơn</div>
          <div className="mt-4 flex items-center gap-1 text-[11px] font-medium text-emerald-600">
            <ArrowDownRight size={14} />{" "}
            {(compare.baseline - compare.withSentiment)
              .toFixed(metric === "sentiment" ? 3 : 1)
              .replace(".", ",")}{" "}
            so với mô hình nền
          </div>
        </Panel>

        <Panel title="Dự báo đúng chiều" subtitle="Tỷ lệ xu hướng dự báo đúng trong 12 kỳ gần nhất">
          <div className="flex items-end gap-2">
            <div className="text-3xl font-semibold tracking-tight text-foreground">
              {String(accuracy).replace(".", ",")}%
            </div>
            <div className="mb-1 text-xs text-muted-foreground">12 tháng</div>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${accuracy}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
            <span>Hiện tại {fmt(lastActual)}</span>
            <span>Dự báo {fmt(lastForecast)}</span>
          </div>
        </Panel>

        <Panel title="Giá trị của đặc trưng cảm xúc" subtitle={`So sánh MAE (${compare.unit}) · thấp hơn là tốt hơn`}>
          <div className="h-[130px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={maeRows} layout="vertical" margin={{ left: 4, right: 28, top: 4, bottom: 0 }}>
                <XAxis type="number" hide domain={[0, "dataMax"]} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={150}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                />
                <Tooltip formatter={(value) => [String(value).replace(".", ","), "MAE"]} />
                <Bar
                  dataKey="value"
                  radius={[0, 6, 6, 0]}
                  barSize={16}
                  label={{ position: "right", fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                  isAnimationActive={false}
                >
                  {maeRows.map((row, index) => (
                    <Cell key={row.name} fill={index === 2 ? "#6366f1" : index === 1 ? "#a5b4fc" : "#cbd5e1"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </>
  )
}
