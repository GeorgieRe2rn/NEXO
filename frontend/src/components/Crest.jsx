import { useEffect, useState } from "react";

export default function Crest({ src, name, size = 56, color = "#FF783E" }) {
  const [ok, setOk] = useState(true);
  useEffect(() => setOk(true), [src]);
  const dim = typeof size === "number" ? `${size}px` : size;
  if (!ok || !src) {
    return (
      <div
        className="rounded-full shrink-0 grid place-items-center font-display text-sm ring-1 ring-ink-950/15 bg-ink-950/5"
        style={{ width: dim, height: dim }}
      >
        {(name || "?").slice(0, 3).toUpperCase()}
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={name}
      width={size}
      height={size}
      referrerPolicy="no-referrer"
      onError={() => setOk(false)}
      className="object-contain shrink-0"
      style={{ width: dim, height: dim }}
    />
  );
}
