"use client";

import { useState } from "react";

const EMAIL = "ansh.work2002@gmail.com";

/**
 * Backend-free contact form. On submit it composes a prefilled `mailto:` from
 * the field values and hands off to the visitor's mail client — no server,
 * no API key, no data leaves the browser until they hit send.
 */
export function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  const ready = name.trim() && message.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    const subject = encodeURIComponent(`Shorts Engineer — note from ${name.trim()}`);
    const body = encodeURIComponent(
      `${message.trim()}\n\n— ${name.trim()}${email.trim() ? ` (${email.trim()})` : ""}`,
    );
    window.location.href = `mailto:${EMAIL}?subject=${subject}&body=${body}`;
    setSent(true);
  };

  return (
    <form onSubmit={handleSubmit} className="border border-ink bg-paper">
      {/* Title bar — terminal chrome */}
      <div className="flex items-center justify-between px-4 h-9 border-b border-ink font-mono text-[10px] tracking-[0.2em] uppercase">
        <span className="text-ink">compose message</span>
        <span className="text-ink-soft">→ {EMAIL}</span>
      </div>

      <div className="p-4 sm:p-5 space-y-4">
        <Field label="name" prompt="❯">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="your name"
            required
            className="w-full bg-transparent outline-none text-ink placeholder:text-ink-soft text-[15px]"
          />
        </Field>

        <Field label="email" prompt="❯">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com  (optional)"
            className="w-full bg-transparent outline-none text-ink placeholder:text-ink-soft text-[15px]"
          />
        </Field>

        <Field label="message" prompt="//" align="start">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="what's on your mind…"
            required
            rows={5}
            className="w-full bg-transparent outline-none resize-y text-ink placeholder:text-ink-soft text-[15px] leading-relaxed"
          />
        </Field>
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-between gap-4 px-4 sm:px-5 py-3 border-t border-ink">
        <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-ink-soft">
          {sent ? "opened in your mail client ✓" : "opens your mail client"}
        </span>
        <button
          type="submit"
          disabled={!ready}
          className="group inline-flex items-center gap-3 h-10 px-5 bg-ink text-paper font-mono text-[11px] tracking-[0.2em] uppercase hover:bg-ink-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Send
          <span aria-hidden className="transition-transform group-hover:translate-x-1">
            →
          </span>
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  prompt,
  align = "center",
  children,
}: {
  label: string;
  prompt: string;
  align?: "center" | "start";
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="block font-mono text-[10px] tracking-[0.18em] uppercase text-ink-soft mb-1.5">
        {label}
      </span>
      <div
        className={`flex gap-2 border-b border-rule-soft pb-2 focus-within:border-ink transition-colors ${
          align === "start" ? "items-start" : "items-center"
        }`}
      >
        <span aria-hidden className="font-mono text-ink-muted text-[14px] leading-none pt-0.5">
          {prompt}
        </span>
        {children}
      </div>
    </label>
  );
}
