import { useState } from "react";
import { ExternalLink, Radio, RefreshCw } from "lucide-react";
import { useDarkMode } from "./ThemeToggle";

// Official auto-follow preset. Its match is selected by SportScore, not Nexo.
const SRC = "https://sportscore.com/embed/tracker/football/live/?theme=light";

export default function SportScoreTracker({ source, matchLabel = null }) {
  const dark = useDarkMode();
  const themedSource = source.replace(/theme=light/, `theme=${dark ? "dark" : "light"}`);
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  return <section className="panel rounded-xl overflow-hidden" aria-label="Cancha en directo de SportScore">
    <header className="px-4 md:px-5 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-ink-950/10">
      <div>
        <h2 className="font-display text-lg flex items-center gap-2"><Radio size={17} className="text-led"/>Cancha en directo</h2>
        <p className="text-[11px] text-mute mt-1">{matchLabel || "Partido elegido por SportScore · Independiente de los filtros de Nexo"}</p>
      </div>
      <button type="button" className="inline-flex items-center gap-2 text-xs text-mute min-h-11 px-2 hover:text-paper" onClick={() => { setFailed(false); setAttempt(n => n + 1); }} aria-label="Recargar cancha de SportScore"><RefreshCw size={14}/>Recargar</button>
    </header>
    {failed ? <div role="status" className="p-6 text-sm text-mute">No se pudo cargar la cancha. Puedes reintentar o abrirla en SportScore.</div> : <iframe
      key={attempt}
      src={themedSource}
      title={matchLabel ? `SportScore: ${matchLabel}` : "SportScore: cancha 3D de un partido seleccionado automáticamente"}
      loading="lazy"
      referrerPolicy="no-referrer-when-downgrade"
      className="block w-full h-[420px] md:h-[480px] border-0"
      onError={() => setFailed(true)}
    />}
    <footer className="px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-mute border-t border-ink-950/10">
      <a href="https://sportscore.com/football/" target="_blank" rel="noopener" className="text-led hover:underline">Football live match tracker by SportScore</a>
      <a href={themedSource} target="_blank" rel="noopener" className="inline-flex gap-1 items-center min-h-8">Abrir cancha <ExternalLink size={12}/></a>
    </footer>
  </section>;
}

