import NexoBrand from "../components/NexoBrand";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "../api/client";

import { useFeed } from "../components/FeedContext";
export default function AdminLogin() {
  const nav = useNavigate();
  const { reloadAccount } = useFeed();
  const [params] = useSearchParams();
  const requested = params.get("volver") || "/admin";
  const target =
    requested.startsWith("/") && !requested.startsWith("//")
      ? requested
      : "/admin";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.csrf().catch(() => {});
    api.me().then((m) => {
      if (m?.authenticated) nav(target, { replace: true });
    });
  }, [nav, target]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.csrf();
      await api.login(username, password);
      reloadAccount();
      nav(target);
    } catch (err) {
      setError("No se pudo entrar. Revisa usuario y contraseña.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <section className="hidden lg:flex flex-col justify-between border-r border-ink-950/10 p-12 xl:p-20 bg-pitch-900">
        <Link to="/" className="text-xl font-bold tracking-widest">
          <NexoBrand />
        </Link>
        <div>
          <p className="eyebrow text-led mb-5">
            Análisis deportivo con evidencia
          </p>
          <h1 className="text-5xl xl:text-6xl font-display leading-tight">
            El juego cambia.
            <br />
            <span className="text-mute">El análisis evoluciona.</span>
          </h1>
          <p className="text-mute text-sm leading-7 mt-7 max-w-sm">
            Supervisa las fuentes, evalúa los pronósticos y entiende la calidad
            del conocimiento extraído.
          </p>
        </div>
        <p className="text-xs text-mute">
          Extracción de Conocimiento en Bases de Datos
        </p>
      </section>
      <div className="min-h-screen flex flex-col items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-6">
            <span className="h-9 w-9 rounded-lg bg-led text-ink-950 grid place-items-center font-bold">
              V
            </span>
            <div>
              <p className="font-display text-2xl leading-none">
                Bienvenido de nuevo
              </p>
              <p className="text-[12px] text-mute mt-1">Acceso interno</p>
            </div>
          </div>
          <label
            htmlFor="username"
            className="block text-[12px] text-mute mb-2"
          >
            Usuario
          </label>
          <input
            id="username"
            required
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full mb-3 rounded-md bg-pitch-800 border border-ink-950/10 px-3 py-2 outline-none focus:border-ink-950/30"
          />
          <label
            htmlFor="password"
            className="block text-[12px] text-mute mb-2"
          >
            Contraseña
          </label>
          <input
            type="password"
            id="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full mb-4 rounded-md bg-pitch-800 border border-ink-950/10 px-3 py-2 outline-none focus:border-ink-950/30"
          />
          {error && <p className="text-rust-400 text-sm mb-3">{error}</p>}
          <button
            disabled={busy}
            className="primary-button w-full mt-2 disabled:opacity-50"
          >
            {busy ? "Entrando…" : "Entrar"}
          </button>
          <Link
            to="/"
            className="mt-4 flex items-center justify-center gap-2 text-sm text-mute hover:text-paper"
          >
            <ArrowLeft size={16} /> Volver a la jornada
          </Link>
        </form>
      </div>
    </div>
  );
}
