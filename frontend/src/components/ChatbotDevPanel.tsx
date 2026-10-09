// Throwaway: lets Víctor click the M7a chatbot read tools instead of curling
// them. NOT part of the plan (docs/plans/m7a-chatbot-lesewerkzeuge.md §5 keeps
// a real `/chat` route out until M6) and talks to scripts/chatbot-dev-server.py,
// a dev-only server outside the backend proper. The Chat tab talks to the local
// model through /chat (the server keeps no transcript, so it is sent back each
// turn); the tool tabs are exactly one tool call each, raw JSON shown as-is. Lives only
// on the branch dev/chatbot-playground, which is never merged into main.
import { useState } from 'react';

type ToolName = 'search_collections' | 'get_collection' | 'check_availability';

const TOOLS: { name: ToolName; label: string }[] = [
  { name: 'search_collections', label: 'Search' },
  { name: 'get_collection', label: 'Collection' },
  { name: 'check_availability', label: 'Availability' },
];

type Mode = 'chat' | ToolName;

interface ChatLine {
  role: 'user' | 'assistant' | 'error';
  text: string;
  seconds?: number;
}

interface Turn {
  tool: ToolName;
  request: Record<string, unknown>;
  result: unknown;
  error?: string;
}

// bbox as "west,south,east,north"; empty means "not given".
function parseBbox(text: string): number[] | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  const parts = trimmed.split(',').map((p) => Number(p.trim()));
  return parts.length === 4 && parts.every(Number.isFinite) ? parts : undefined;
}

function ChatView() {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [transcript, setTranscript] = useState<unknown[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setLines((prev) => [...prev, { role: 'user', text }]);
    setBusy(true);
    const started = performance.now();
    try {
      const res = await fetch('/chatbot-dev/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ messages: [...transcript, { role: 'user', content: text }] }),
      });
      const body = await res.json();
      const seconds = Math.round((performance.now() - started) / 1000);
      if (!res.ok || typeof body.text !== 'string') {
        setLines((prev) => [...prev, { role: 'error', text: body.error ?? `HTTP ${res.status}`, seconds }]);
      } else {
        setTranscript(body.messages);
        setLines((prev) => [...prev, { role: 'assistant', text: body.text, seconds }]);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLines((prev) => [...prev, { role: 'error', text: `network error: ${message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ul className="chatbot-dev-chat">
        {lines.map((line, i) => (
          <li key={i} className={`chatbot-dev-msg ${line.role}`}>
            {line.text}
            {line.seconds !== undefined && <span className="chatbot-dev-msg-time">{line.seconds} s</span>}
          </li>
        ))}
        {busy && <li className="chatbot-dev-msg assistant">… thinking (local model, can take a minute)</li>}
      </ul>
      <div className="chatbot-dev-form">
        <input
          type="text"
          placeholder="Ask about the catalogue, e.g. 'Which radar data covers the Alps in 2024?'"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') send();
          }}
        />
        <button type="button" className="zoom-btn" onClick={send} disabled={busy || !input.trim()}>
          {busy ? '…' : 'Send'}
        </button>
        <button
          type="button"
          className="zoom-btn"
          onClick={() => {
            setLines([]);
            setTranscript([]);
          }}
          disabled={busy}
        >
          New chat
        </button>
      </div>
    </>
  );
}

export default function ChatbotDevPanel() {
  const [mode, setMode] = useState<Mode>('chat');
  const tool: ToolName = mode === 'chat' ? 'search_collections' : mode;
  const [query, setQuery] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [bbox, setBbox] = useState('');
  const [datetime, setDatetime] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    let arguments_: Record<string, unknown>;
    if (tool === 'search_collections') {
      arguments_ = { query: query || undefined, bbox: parseBbox(bbox), datetime: datetime || undefined };
    } else if (tool === 'get_collection') {
      arguments_ = { collection_id: collectionId };
    } else {
      arguments_ = { collection_id: collectionId, bbox: parseBbox(bbox), datetime: datetime || undefined };
    }
    setBusy(true);
    try {
      const res = await fetch('/chatbot-dev/call', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ tool, arguments: arguments_ }),
      });
      const result = await res.json();
      setTurns((prev) => [{ tool, request: arguments_, result }, ...prev]);
    } catch (error) {
      setTurns((prev) => [
        { tool, request: arguments_, result: null, error: error instanceof Error ? error.message : String(error) },
        ...prev,
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel chatbot-dev">
      <div className="chatbot-dev-badge">dev only — local model, not part of the plan</div>

      <div className="chatbot-dev-tools">
        <button
          type="button"
          className={`chatbot-dev-tab${mode === 'chat' ? ' active' : ''}`}
          onClick={() => setMode('chat')}
        >
          Chat
        </button>
        {TOOLS.map((t) => (
          <button
            key={t.name}
            type="button"
            className={`chatbot-dev-tab${mode === t.name ? ' active' : ''}`}
            onClick={() => setMode(t.name)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {mode === 'chat' ? (
        <ChatView />
      ) : (
      <>
      <div className="chatbot-dev-form">
        {tool === 'search_collections' && (
          <input
            type="text"
            placeholder="words, e.g. 'sentinel optical'"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        )}
        {(tool === 'get_collection' || tool === 'check_availability') && (
          <input
            type="text"
            placeholder="collection id"
            value={collectionId}
            onChange={(e) => setCollectionId(e.target.value)}
          />
        )}
        {tool !== 'get_collection' && (
          <>
            <input
              type="text"
              placeholder="bbox: west,south,east,north"
              value={bbox}
              onChange={(e) => setBbox(e.target.value)}
            />
            <input
              type="text"
              placeholder="datetime: 2024-06-01/2024-06-30"
              value={datetime}
              onChange={(e) => setDatetime(e.target.value)}
            />
          </>
        )}
        <button
          type="button"
          className="zoom-btn"
          onClick={send}
          disabled={busy || (tool !== 'search_collections' && !collectionId)}
        >
          {busy ? '…' : 'Send'}
        </button>
      </div>

      <ul className="chatbot-dev-log">
        {turns.map((turn, i) => (
          <li key={i}>
            <div className="chatbot-dev-log-tool">
              {turn.tool}({JSON.stringify(turn.request)})
            </div>
            <pre>{turn.error ? `network error: ${turn.error}` : JSON.stringify(turn.result, null, 2)}</pre>
          </li>
        ))}
      </ul>
      </>
      )}
    </div>
  );
}
