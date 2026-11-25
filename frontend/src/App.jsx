import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  RefreshCw,
  Cpu,
  Zap,
  Clock,
  Coins,
  AlertTriangle,
  Server,
  Layers,
  ChevronDown,
  ChevronUp,
  Sliders
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function generateSessionId() {
  const rand = Math.random().toString(36).substring(2, 10);
  const time = Date.now().toString(36).substring(4);
  return `s-${rand}-${time}`;
}

export default function App() {
  // A new session starts on each page load
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful and concise AI assistant.');
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [inputMessage, setInputMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  
  // Health & simulation state
  const [healthInfo, setHealthInfo] = useState(null);
  const [simulateFailureHeader, setSimulateFailureHeader] = useState('');
  const [customSimHeader, setCustomSimHeader] = useState('');

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Fetch health on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
          const data = await res.json();
          setHealthInfo(data);
        } else {
          setHealthInfo({ status: 'error', detail: `HTTP ${res.status}` });
        }
      } catch (err) {
        setHealthInfo({ status: 'error', detail: 'Backend unreachable' });
      }
    };
    checkHealth();
  }, []);

  const startNewSession = () => {
    setSessionId(generateSessionId());
    setMessages([]);
    setInputMessage('');
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || isLoading) return;

    // Immediately clear input as required by contract
    setInputMessage('');

    // Add user message to UI
    const userMsg = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    const activeSimHeader = simulateFailureHeader === 'custom' ? customSimHeader : simulateFailureHeader;

    const headers = {
      'Content-Type': 'application/json',
    };
    if (activeSimHeader) {
      headers['X-Simulate-Failure'] = activeSimHeader;
    }

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: sessionId,
          message: trimmed,
          system_prompt: systemPrompt || undefined,
        }),
      });

      if (!response.ok) {
        let errorDetail = `Request failed with status ${response.status}`;
        try {
          const errData = await response.json();
          if (typeof errData.detail === 'string') {
            errorDetail = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errorDetail = errData.detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
          } else if (errData.detail) {
            errorDetail = JSON.stringify(errData.detail);
          }
        } catch {
          // ignore parsing error
        }

        // Show readable error message in chat, never a blank screen
        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error (${response.status}): ${errorDetail}`,
          },
        ]);
        return;
      }

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'error',
          content: `Network or Connection Error: ${err.message || 'Unable to connect to backend'}`,
        },
      ]);
    } finally {
      setIsLoading(false);
      // Refocus input
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="chat-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand">
          <div className="brand-logo">L</div>
          <div className="brand-text">
            <h1>Lyftr AI Chatbot</h1>
            <p>Resilient Gateway with Key Failover & Caching</p>
          </div>
        </div>

        <div className="header-badges">
          {healthInfo && (
            <span
              className={`badge ${
                healthInfo.status === 'ok' ? 'badge-health-ok' : 'badge-health-err'
              }`}
              title={`Keys: ${healthInfo.keys_configured}, Cache: ${healthInfo.cache_enabled}`}
            >
              <Server size={12} />
              {healthInfo.status === 'ok'
                ? `Online (${healthInfo.keys_configured} Keys)`
                : `Offline: ${healthInfo.detail || 'Error'}`}
            </span>
          )}

          <span className="badge badge-session" title={sessionId}>
            <Layers size={12} />
            {sessionId.slice(0, 16)}...
          </span>

          <button
            className="btn-secondary"
            onClick={startNewSession}
            title="Start fresh conversation"
          >
            <RefreshCw size={13} />
            New Session
          </button>
        </div>
      </header>

      {/* Failover Test Hook Toolbar */}
      <div className="simulation-toolbar">
        <span className="sim-label">
          <AlertTriangle size={14} />
          Failover Test Hook (X-Simulate-Failure):
        </span>
        <div className="sim-btn-group">
          <button
            type="button"
            className={`sim-btn ${simulateFailureHeader === '' ? 'active' : ''}`}
            onClick={() => setSimulateFailureHeader('')}
          >
            Normal (No failure)
          </button>
          <button
            type="button"
            className={`sim-btn ${simulateFailureHeader === 'key_1=429' ? 'active' : ''}`}
            onClick={() => setSimulateFailureHeader('key_1=429')}
          >
            key_1=429 (Failover)
          </button>
          <button
            type="button"
            className={`sim-btn ${simulateFailureHeader === 'key_1=500' ? 'active' : ''}`}
            onClick={() => setSimulateFailureHeader('key_1=500')}
          >
            key_1=500 (Failover)
          </button>
          <button
            type="button"
            className={`sim-btn ${simulateFailureHeader === '*=429' ? 'active' : ''}`}
            onClick={() => setSimulateFailureHeader('*=429')}
          >
            *=429 (503 All Fail)
          </button>
          <button
            type="button"
            className={`sim-btn ${simulateFailureHeader === 'custom' ? 'active' : ''}`}
            onClick={() => setSimulateFailureHeader('custom')}
          >
            Custom Header
          </button>
        </div>

        {simulateFailureHeader === 'custom' && (
          <input
            type="text"
            className="sim-btn"
            style={{ width: '180px', color: '#fff' }}
            placeholder="e.g. key_1=502,key_2=500"
            value={customSimHeader}
            onChange={(e) => setCustomSimHeader(e.target.value)}
          />
        )}
      </div>

      {/* Optional System Prompt Section */}
      <div className="system-prompt-drawer">
        <div
          className="system-prompt-header"
          onClick={() => setShowSystemPrompt(!showSystemPrompt)}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Sliders size={13} />
            System Prompt (Optional session override)
          </span>
          {showSystemPrompt ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
        {showSystemPrompt && (
          <textarea
            data-testid="system-prompt-input"
            className="system-prompt-textarea"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Set a system prompt for this session..."
            rows={2}
          />
        )}
      </div>

      {/* Conversation Area */}
      <div className="messages-area">
        {messages.length === 0 ? (
          <div className="empty-state">
            <Cpu className="empty-icon" />
            <h3>Start a multi-turn conversation</h3>
            <p>
              Send a message to see key failover, response caching, and per-turn token & latency metrics in action.
            </p>
            <div className="empty-hints">
              <button
                className="hint-pill"
                onClick={() => setInputMessage('What is the capital of France?')}
              >
                "What is the capital of France?" (Test cache hit on 2nd session)
              </button>
              <button
                className="hint-pill"
                onClick={() => {
                  setSimulateFailureHeader('key_1=429');
                  setInputMessage('Demonstrate automatic key failover from key_1 to key_2.');
                }}
              >
                "Test key failover with key_1=429"
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg, index) => {
            if (msg.role === 'user') {
              return (
                <div key={index} className="message-row user">
                  <div className="user-bubble">{msg.content}</div>
                </div>
              );
            } else if (msg.role === 'error') {
              return (
                <div key={index} className="message-row assistant">
                  <div className="error-bubble">
                    <AlertTriangle size={16} />
                    <span>{msg.content}</span>
                  </div>
                </div>
              );
            } else {
              // Assistant message container adhering strictly to frontend contract
              const meta = msg.metadata || {};
              const isCache = meta.resolution_source === 'LLM_CACHE';

              return (
                <div key={index} className="message-row assistant">
                  <div
                    data-testid="assistant-message"
                    className="assistant-wrapper"
                  >
                    <div className="assistant-bubble">{msg.content}</div>

                    {/* Metadata elements inside assistant-message */}
                    <div className="assistant-metadata-bar">
                      {/* Resolution Source */}
                      <span
                        data-testid="meta-source"
                        className={`meta-pill ${
                          isCache ? 'meta-source-cache' : 'meta-source-live'
                        }`}
                      >
                        {isCache ? <Zap size={11} /> : <Cpu size={11} />}
                        {meta.resolution_source}
                      </span>

                      {/* Model Used */}
                      <span
                        data-testid="meta-model"
                        className="meta-pill meta-info"
                      >
                        {meta.model}
                      </span>

                      {/* Latency */}
                      <span
                        data-testid="meta-latency"
                        className="meta-pill meta-info"
                      >
                        <Clock size={11} />
                        {meta.latency_ms} ms
                      </span>

                      {/* Input Tokens */}
                      <span
                        data-testid="meta-input-tokens"
                        className="meta-pill meta-info"
                        title="Input prompt tokens"
                      >
                        <Coins size={11} />
                        in: {meta.input_tokens}
                      </span>

                      {/* Output Tokens */}
                      <span
                        data-testid="meta-output-tokens"
                        className="meta-pill meta-info"
                        title="Output completion tokens"
                      >
                        out: {meta.output_tokens}
                      </span>

                      {/* Key & Fallback Indicator */}
                      {meta.key_id && (
                        <span
                          className={`meta-pill ${
                            meta.fallback_attempts > 0 ? 'meta-fallback' : 'meta-info'
                          }`}
                        >
                          {meta.key_id}
                          {meta.fallback_attempts > 0 && ` (${meta.fallback_attempts} fallback)`}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            }
          })
        )}

        {isLoading && (
          <div className="message-row assistant">
            <div className="assistant-bubble">
              <div className="typing-dots">
                <div className="dot"></div>
                <div className="dot"></div>
                <div className="dot"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <footer className="input-container">
        <form onSubmit={handleSendMessage} className="input-box">
          <textarea
            ref={textareaRef}
            data-testid="chat-input"
            className="chat-textarea"
            placeholder="Type a message... (Press Enter to send)"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isLoading}
          />
          <button
            type="submit"
            data-testid="send-button"
            className="send-btn"
            disabled={isLoading || !inputMessage.trim()}
            title="Send message"
          >
            <Send size={16} />
          </button>
        </form>
      </footer>
    </div>
  );
}
