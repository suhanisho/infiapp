"use client";

import type { FormEvent } from "react";
import { useState } from "react";

type CallState = "idle" | "loading" | "success" | "error";

export function BackendButton() {
  const [state, setState] = useState<CallState>("idle");
  const [input, setInput] = useState("hello from the web");
  const [message, setMessage] = useState("");

  async function callBackend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("loading");
    setMessage("");
    try {
      const response = await fetch("/api/hello", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: input }),
      });
      const body = (await response.json()) as {
        lastMessage?: string;
        message?: string;
        error?: string;
      };
      if (!response.ok) {
        throw new Error(body.error || "Backend call failed");
      }
      setMessage(body.lastMessage || body.message || "");
      setState("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Backend call failed");
      setState("error");
    }
  }

  return (
    <form className="backend-panel" onSubmit={callBackend}>
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
        {state === "loading" ? "Calling..." : "Call backend"}
      </button>
      <p className={`result result-${state}`} aria-live="polite">
        {message || "Ready"}
      </p>
    </form>
  );
}
