"use client";

import type { FormEvent } from "react";
import { useState } from "react";

type CallState = "idle" | "loading" | "success" | "error";
type MessageItem = {
  messageId: string;
  createdAt: string;
  message: string;
};

export function BackendButton() {
  const [state, setState] = useState<CallState>("idle");
  const [listState, setListState] = useState<CallState>("idle");
  const [input, setInput] = useState("sample message from the web");
  const [statusMessage, setStatusMessage] = useState("");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [nextKey, setNextKey] = useState<Record<string, unknown> | null>(null);

  async function storeMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("loading");
    setStatusMessage("");
    try {
      const response = await fetch("/api/sample/messages", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: input }),
      });
      const body = (await response.json()) as {
        item?: MessageItem;
        message?: string;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(body.error || "Backend call failed");
      }
      setStatusMessage(body.item?.message ? `Stored ${body.item.message}` : body.message || "Stored");
      setState("success");
      await loadMessages(true);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Backend call failed");
      setState("error");
    }
  }

  async function loadMessages(reset = false) {
    setListState("loading");
    try {
      const params = new URLSearchParams({ limit: "5" });
      const cursor = reset ? null : nextKey;
      if (cursor) {
        params.set("nextKey", JSON.stringify(cursor));
      }
      const response = await fetch(`/api/sample/messages?${params.toString()}`);
      const body = (await response.json()) as {
        messages?: MessageItem[];
        nextKey?: Record<string, unknown> | null;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(body.error || "Backend call failed");
      }
      setMessages((current) => (reset ? body.messages || [] : [...current, ...(body.messages || [])]));
      setNextKey(body.nextKey || null);
      setListState("success");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Backend call failed");
      setListState("error");
    }
  }

  return (
    <div className="backend-panel">
      <form className="message-form" onSubmit={storeMessage}>
        <label htmlFor="message-input">Message</label>
        <input
          id="message-input"
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={state === "loading"}
          maxLength={240}
          required
        />
        <button type="submit" disabled={state === "loading"}>
          {state === "loading" ? "Storing..." : "Store message"}
        </button>
      </form>
      <div className="message-actions">
        <button type="button" onClick={() => void loadMessages(true)} disabled={listState === "loading"}>
          {listState === "loading" ? "Loading..." : "List messages"}
        </button>
        <button type="button" onClick={() => void loadMessages(false)} disabled={!nextKey || listState === "loading"}>
          Load more
        </button>
      </div>
      <p className={`result result-${state}`} aria-live="polite">
        {statusMessage || "Ready"}
      </p>
      <ol className="message-list" aria-label="Stored messages">
        {messages.map((item) => (
          <li key={item.messageId}>
            <span>{item.message}</span>
            <time dateTime={item.createdAt}>{new Date(item.createdAt).toLocaleString()}</time>
          </li>
        ))}
      </ol>
    </div>
  );
}
