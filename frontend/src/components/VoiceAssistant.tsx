import { useEffect, useRef, useState } from "react";
import { api, refreshAll } from "../api";

// Chrome's Web Speech API. TypeScript's DOM lib doesn't include SpeechRecognition yet.
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;

const Ctor: RecognitionCtor | undefined =
  (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;

interface VoiceReply {
  reply: string;
  action: string;
  source: "ai" | "rules";
  awaiting_answer_item_id: number | null;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Chrome blocked the microphone. Click the icon in the address bar to allow it.",
  "service-not-allowed": "Chrome blocked the microphone. Click the icon in the address bar to allow it.",
  "no-speech": "I didn't hear anything. Try again.",
  "audio-capture": "No microphone was found.",
  network: "Chrome's speech service couldn't be reached. Check your connection.",
};

type State = "idle" | "listening" | "thinking" | "speaking";

export function VoiceAssistant() {
  const [state, setState] = useState<State>("idle");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [typed, setTyped] = useState("");
  const rec = useRef<Recognition | null>(null);
  const answering = useRef<number | null>(null);

  useEffect(() => () => {
    rec.current?.stop();
    window.speechSynthesis?.cancel();
  }, []);

  function listen() {
    if (!Ctor) return;
    window.speechSynthesis?.cancel();
    setError("");
    setHeard("");
    const r = new Ctor();
    r.lang = "en-US";
    r.interimResults = true;
    r.continuous = false;
    let final = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) final += res[0].transcript;
        else interim += res[0].transcript;
      }
      setHeard(final + interim);
    };
    r.onerror = (e) => {
      if (e.error !== "aborted") setError(ERRORS[e.error] ?? `Voice error: ${e.error}`);
    };
    r.onend = () => {
      rec.current = null;
      if (final.trim()) send(final.trim());
      else setState("idle");
    };
    rec.current = r;
    setState("listening");
    r.start();
  }

  function stop() {
    rec.current?.stop();
    window.speechSynthesis?.cancel();
    setState("idle");
  }

  async function send(text: string) {
    setHeard(text);
    setState("thinking");
    try {
      const res = await api<VoiceReply>("/voice", {
        method: "POST",
        body: { text, answering_item_id: answering.current },
      });
      answering.current = res.awaiting_answer_item_id;
      setReply(res.reply);
      refreshAll();
      speak(res.reply, res.awaiting_answer_item_id !== null);
    } catch (err) {
      setError((err as Error).message);
      setState("idle");
    }
  }

  function speak(text: string, thenListen: boolean) {
    if (!window.speechSynthesis) return setState("idle");
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 0.95;
    u.onend = () => {
      setState("idle");
      // The assistant just asked a question: listen for the answer.
      if (thenListen && Ctor) listen();
    };
    u.onerror = () => setState("idle");
    setState("speaking");
    window.speechSynthesis.speak(u);
  }

  const busy = state !== "idle";
  const label = { idle: "Talk", listening: "Listening…", thinking: "Thinking…", speaking: "Speaking…" }[state];

  return (
    <section className="card mt-5 space-y-3 p-4" aria-labelledby="voice-title">
      <h2 id="voice-title" className="text-sm font-medium text-muted">Talk to Shopper</h2>
      {Ctor ? (
        <button
          type="button"
          onClick={busy ? stop : listen}
          aria-pressed={state === "listening"}
          className={`w-full ${state === "listening" ? "btn-danger" : "btn-primary"}`}
        >
          <MicIcon />
          {busy ? `${label} (tap to stop)` : label}
        </button>
      ) : (
        <p className="text-sm text-muted">Voice works in Google Chrome. You can still type below.</p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (typed.trim()) send(typed.trim());
          setTyped("");
        }}
      >
        <label htmlFor="voice-text" className="sr-only">Or type a request</label>
        <input
          id="voice-text"
          className="input text-sm"
          placeholder="Or type: add milk and eggs"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          disabled={state === "thinking"}
        />
      </form>
      <div aria-live="polite" className="space-y-1 text-sm">
        {heard && (
          <p>
            <span className="text-muted">You: </span>
            {heard}
          </p>
        )}
        {reply && state !== "listening" && (
          <p>
            <span className="text-muted">Shopper: </span>
            {reply}
          </p>
        )}
        {error && <p role="alert" className="text-red-700">{error}</p>}
      </div>
      {!heard && !reply && (
        <p className="text-xs text-muted">
          Try “Add two bananas and paper towels” or “What’s on my list?” Approvals and payments stay in the app.
        </p>
      )}
    </section>
  );
}

function MicIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}
