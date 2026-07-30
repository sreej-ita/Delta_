import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import { useProjectChatContext } from "../lib/ProjectChatContext.jsx";

const ICON_SRC = "/mangrove-chatbot-icon.jpg";
const REFUSAL_TEXT = "irrelevant question";

const COLORS = {
  panelBg: "#ffffff",
  border: "#d7e5dd",
  headerBg: "#ffffff",
  headerText: "#0f3d2e",
  iconAccent: "#0f9d63",
  userBubbleBg: "#0f9d63",
  userBubbleText: "#ffffff",
  botBubbleBg: "#f0f5f2",
  botBubbleText: "#16281f",
  refusalText: "#8a9a91",
  inputBg: "#f5f8f6",
  inputText: "#16281f",
  inputPlaceholder: "#8a9a91",
};

/**
 * Floating support chatbot. Mount this once, conditionally, on every page
 * except the landing page (see App.jsx). Talks directly to /api/chat via
 * fetch rather than lib/api.js, since it must also work on Login/Signup
 * before any auth token exists.
 *
 * Reads the current project's metrics from ProjectChatContext (published by
 * ProjectDetail.jsx) and sends them along with every message, so answers
 * are grounded in what's actually on screen instead of the model guessing.
 */
export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi! I'm the Delta assistant. Ask me anything about this dashboard — the map, carbon analytics, deforestation alerts, or MRV reports.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const projectContext = useProjectChatContext();

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, open]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const nextMessages = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: nextMessages.slice(-8),
          project_context: projectContext,
        }),
      });
      const data = await res.json();
      const reply = data?.reply || REFUSAL_TEXT;
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong reaching the assistant. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      {/* Floating launcher */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close assistant" : "Open assistant"}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full overflow-hidden
                   shadow-lg hover:scale-105 transition-all duration-200"
        style={{
          boxShadow: "0 8px 24px rgba(15,61,46,0.35)",
          border: `2px solid ${COLORS.iconAccent}`,
          background: COLORS.panelBg,
        }}
      >
        {open ? (
          <span
            className="w-full h-full flex items-center justify-center"
            style={{ color: COLORS.iconAccent }}
          >
            <X size={22} />
          </span>
        ) : (
          <img
            src={ICON_SRC}
            alt="Chat with the Delta assistant"
            className="w-full h-full object-cover"
          />
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div
          className="fixed bottom-24 right-6 z-50 w-[360px] max-w-[92vw] h-[520px] max-h-[75vh]
                     rounded-2xl overflow-hidden shadow-2xl flex flex-col"
          style={{
            backgroundColor: COLORS.panelBg,
            border: `1px solid ${COLORS.border}`,
          }}
        >
          {/* Watermark — sits on the opaque white panel, behind the content */}
          <img
            src={ICON_SRC}
            alt=""
            aria-hidden="true"
            className="pointer-events-none select-none absolute inset-0 m-auto w-56 h-56 object-contain"
            style={{ opacity: 0.08, zIndex: 0 }}
          />

          {/* Header */}
          <div
            className="relative flex items-center justify-between px-4 py-3"
            style={{
              zIndex: 1,
              backgroundColor: COLORS.headerBg,
              borderBottom: `1px solid ${COLORS.border}`,
            }}
          >
            <div className="flex items-center gap-2">
              <MessageCircle size={16} style={{ color: COLORS.iconAccent }} />
              <span className="text-sm font-semibold" style={{ color: COLORS.headerText }}>
                Delta Assistant
              </span>
              {projectContext?.project_name && (
                <span
                  className="ml-1 truncate text-[11px] font-normal"
                  style={{ color: COLORS.refusalText, maxWidth: 140 }}
                  title={projectContext.project_name}
                >
                  · {projectContext.project_name}
                </span>
              )}
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close"
              style={{ color: COLORS.iconAccent }}
              className="hover:opacity-70 transition-opacity"
            >
              <X size={18} />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollRef}
            className="relative flex-1 overflow-y-auto px-3 py-3 space-y-2"
            style={{ zIndex: 1 }}
          >
            {messages.map((m, i) => {
              const isUser = m.role === "user";
              const isRefusal =
                !isUser && m.content.trim().toLowerCase() === REFUSAL_TEXT;
              return (
                <div
                  key={i}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className="max-w-[80%] rounded-xl px-3 py-2 text-sm leading-snug"
                    style={{
                      backgroundColor: isUser ? COLORS.userBubbleBg : COLORS.botBubbleBg,
                      color: isUser
                        ? COLORS.userBubbleText
                        : isRefusal
                        ? COLORS.refusalText
                        : COLORS.botBubbleText,
                      fontStyle: isRefusal ? "italic" : "normal",
                      fontWeight: isUser ? 500 : 400,
                    }}
                  >
                    {m.content}
                  </div>
                </div>
              );
            })}
            {loading && (
              <div className="flex justify-start">
                <div
                  className="max-w-[80%] rounded-xl px-3 py-2 text-sm italic"
                  style={{ backgroundColor: COLORS.botBubbleBg, color: COLORS.refusalText }}
                >
                  Thinking…
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div
            className="relative p-2 flex items-center gap-2"
            style={{ zIndex: 1, borderTop: `1px solid ${COLORS.border}`, backgroundColor: COLORS.panelBg }}
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about this dashboard…"
              disabled={loading}
              className="flex-1 text-sm rounded-lg px-3 py-2 outline-none disabled:opacity-60"
              style={{
                backgroundColor: COLORS.inputBg,
                color: COLORS.inputText,
              }}
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              aria-label="Send"
              className="w-9 h-9 flex items-center justify-center rounded-lg transition-colors disabled:opacity-40"
              style={{ backgroundColor: COLORS.userBubbleBg, color: "#ffffff" }}
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
