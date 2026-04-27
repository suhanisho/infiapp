"use client";

import { useState } from "react";

type CallState = "idle" | "loading" | "success" | "error";

export function BackendButton() {
  const [state, setState] = useState<CallState>("idle");
  const [message, setMessage] = useState("");

  async function callBackend() {
    setState("loading");
    setMessage("");
    try {
      const response = await fetch("/api/hello", {
        method: "POST",
        headers: { "content-type": "application/json" },
      });
      const body = (await response.json()) as { message?: string; error?: string };
      if (!response.ok) {
        throw new Error(body.error || "Backend call failed");
      }
      setMessage(body.message || "");
      setState("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Backend call failed");
      setState("error");
    }
  }

  return (
    <div className="backend-panel">
      <button type="button" onClick={callBackend} disabled={state === "loading"}>
        {state === "loading" ? "Calling..." : "Call backend"}
      </button>
      <p className={`result result-${state}`} aria-live="polite">
        {message || "Ready"}
      </p>
    </div>
  );
}

