import { Fragment, useEffect, useRef, useState, type ReactNode } from "react"
import { AlertCircle, ArrowUp, BookOpen, Sparkles } from "lucide-react"

import { PageHeading } from "@/components/shared/common"
import { askChat } from "@/services/chat"

interface ChatMessage {
  from: "user" | "ai"
  text: string
  period?: string | null
  error?: boolean
}

const STARTER_SUGGESTIONS = [
  "Tình hình ELSA Speak tháng trước thế nào?",
  "Nền tảng nào có Sentiment Index cao nhất?",
  "Xu hướng của DUOLINGO 6 tháng gần đây",
  "Dự báo tháng tới của ELSA Speak",
  "So sánh nền tảng trong nước và quốc tế",
  "Sentiment Index được tính như thế nào?",
]

/** Hiện câu trả lời: giữ xuống dòng, **chữ đậm** kiểu Markdown. Không dùng innerHTML. */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, lineIndex) => {
        const parts: ReactNode[] = line.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
          part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
        )
        return (
          <Fragment key={lineIndex}>
            {lineIndex > 0 && <br />}
            {parts}
          </Fragment>
        )
      })}
    </>
  )
}

export default function TroLyPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      from: "ai",
      text:
        "Xin chào! Tôi là trợ lý phân tích EduVision. Tôi trả lời bằng số liệu thật trong kho: tình hình từng nền tảng, " +
        "xếp hạng, xu hướng theo tháng, dự báo, cảnh báo, sự kiện, báo chí và cách tính các chỉ số.",
    },
  ])
  const [suggestions, setSuggestions] = useState<string[]>(STARTER_SUGGESTIONS)
  const [input, setInput] = useState("")
  const [typing, setTyping] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  // Lưu ý: hàm trong useEffect không được trả về giá trị nào khác ngoài hàm dọn dẹp.
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" })
  }, [messages, typing])

  const ask = async (raw: string) => {
    const text = raw.trim()
    if (!text || typing) return
    setMessages((current) => [...current, { from: "user", text }])
    setInput("")
    setTyping(true)
    try {
      const result = await askChat(text)
      setMessages((current) => [...current, { from: "ai", text: result.answer, period: result.period }])
      if (result.suggestions.length) setSuggestions(result.suggestions)
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không gọi được trợ lý."
      setMessages((current) => [...current, { from: "ai", text: message, error: true }])
    } finally {
      setTyping(false)
    }
  }

  return (
    <>
      <PageHeading eyebrow="PHÂN TÍCH ĐỐI THOẠI" title="Trợ lý AI" description="Đặt câu hỏi bằng tiếng Việt về dữ liệu học viên." />

      <div className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white"><Sparkles size={17} /></div>
            <div>
              <div className="text-xs font-semibold text-foreground">EduVision AI</div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <span className="size-1.5 rounded-full bg-emerald-500" />Trả lời từ kho dữ liệu (truy vấn có tham số)
              </div>
            </div>
          </div>
          <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-600">Dữ liệu thật</span>
        </div>

        <div className="flex max-h-[460px] min-h-[390px] flex-col gap-5 overflow-y-auto bg-muted/40 p-5">
          {messages.map((message, index) => (
            <div key={index} className={`flex gap-3 ${message.from === "user" ? "justify-end" : ""}`}>
              {message.from === "ai" && (
                <div className={`grid size-8 shrink-0 place-items-center rounded-lg text-white ${message.error ? "bg-rose-500" : "bg-indigo-600"}`}>
                  {message.error ? <AlertCircle size={14} /> : <Sparkles size={14} />}
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                  message.from === "user" ? "rounded-tr-md bg-indigo-600 text-white" : "rounded-tl-md border border-border bg-card text-foreground"
                }`}
              >
                <RichText text={message.text} />
                {message.from === "ai" && index > 0 && !message.error && (
                  <div className="mt-3 flex items-center gap-1.5 border-t border-border pt-2 text-[10px] text-muted-foreground">
                    <BookOpen size={11} />Nguồn: kho dữ liệu EduVision{message.period ? ` · ${message.period}` : ""}
                  </div>
                )}
              </div>
            </div>
          ))}
          {typing && (
            <div className="flex gap-3">
              <div className="grid size-8 place-items-center rounded-lg bg-indigo-600 text-white"><Sparkles size={14} /></div>
              <div className="flex items-center gap-1 rounded-2xl border border-border bg-card px-4">
                <i className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
                <i className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <i className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>

        <div className="border-t border-border p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {suggestions.map((question) => (
              <button
                key={question}
                onClick={() => ask(question)}
                disabled={typing}
                className="rounded-full border border-border px-3 py-1.5 text-[10px] text-muted-foreground transition hover:border-indigo-300 hover:bg-indigo-500/10 hover:text-indigo-600 disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              ask(input)
            }}
            className="flex items-center gap-2 rounded-xl border border-border bg-background p-1.5 focus-within:border-indigo-300"
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              maxLength={2000}
              placeholder="Ví dụ: Nền tảng nào có tỷ lệ tiêu cực cao nhất năm 2025?"
              className="min-w-0 flex-1 bg-transparent px-3 py-2 text-xs text-foreground outline-none placeholder:text-muted-foreground"
            />
            <button
              type="submit"
              disabled={!input.trim() || typing}
              aria-label="Gửi câu hỏi"
              className="grid size-9 place-items-center rounded-lg bg-indigo-600 text-white transition hover:bg-indigo-700 disabled:opacity-40"
            >
              <ArrowUp size={17} />
            </button>
          </form>
          <div className="mt-2 text-center text-[9px] text-muted-foreground">
            Số liệu lấy trực tiếp từ kho; nền tảng dưới 30 đánh giá trong kỳ không được xếp hạng.
          </div>
        </div>
      </div>
    </>
  )
}
