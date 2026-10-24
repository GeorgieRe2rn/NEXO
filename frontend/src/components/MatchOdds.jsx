import { api, kickoffLabel, pct } from "../api/client";
import usePolling from "../hooks/usePolling";
const LABELS={result:"Ganador / empate",goals:"Goles totales"};
export default function MatchOdds({id,snapshot}){
 const {data,error}=usePolling(()=>api.matchOdds(id),`odds-${id}`,60000);
 const odds=data?.odds;
 return <section className="panel rounded-xl p-4 space-y-3 text-xs"><div className="flex justify-between items-center gap-3"><h2 className="font-semibold">Mercado integrado al pronóstico</h2><span className="text-led text-[10px]">Automático</span></div>
 {!odds?<p className="text-mute">{error?"No se pudieron consultar los momios.":"Sin cuotas reales vinculadas. Se conserva el modelo deportivo."}</p>:<><div className="grid sm:grid-cols-2 gap-3">{Object.entries(LABELS).map(([market,label])=>{
 const registered=snapshot?.specialists?.[market]?.odds;
 const signal=registered?.selection||odds.market_signals?.[market];
 const weight=registered?.weight||0;
 return <article key={market} className="rounded-lg border border-ink-950/10 p-3 space-y-2"><h3 className="font-semibold">{label}</h3><p className={weight?"text-led":"text-mute"}>{weight?`${Math.round(weight*100)}% mercado + ${100-Math.round(weight*100)}% modelo deportivo`:"Modelo deportivo sin aporte de cuotas"}</p>{signal?.available?<><p className="text-mute">{signal.sources} fuentes · dispersión {(signal.spread*100).toFixed(1)} puntos porcentuales</p><p className="text-mute">{signal.state==="stable_observed"?"Estabilidad observada entre capturas":signal.state==="moving"?"Mercado en movimiento · aporte suspendido":"Concordancia entre casas; estabilidad temporal aún no medida"}</p>{market==="result"&&<p>Mercado: L {pct(signal.probabilities[0])} · E {pct(signal.probabilities[1])} · V {pct(signal.probabilities[2])}</p>}{market==="goals"&&<p>Línea comparada: {signal.line} · tasa implícita estimada {signal.value.toFixed(2)}</p>}<details className="text-mute leading-6"><summary className="cursor-pointer py-1">Ver selección automática</summary><p>Se usa el consenso robusto; {signal.selected_book.name} es la casa más cercana a esa referencia. No se selecciona por el pago más alto.</p><p>Cuotas: {signal.selected_book.prices.join(" / ")}</p><p>Actualización: {kickoffLabel(signal.selected_book.updated_at)}</p><p>{signal.temporal_observations} capturas comparables{signal.movement!=null?` · movimiento ${(signal.movement*100).toFixed(1)} puntos`:""}.</p></details></>:<p className="text-mute">{signal?.reason||"Sin fuentes suficientes para este mercado."}</p>}{weight>0&&registered?.state!=="validated"&&<p className="text-amber text-[10px]">Regla experimental de calidad; mejora de precisión todavía no validada.</p>}</article>;
 })}</div><p className="text-[10px] text-mute">The Odds API · captura {kickoffLabel(odds.captured_at)}{odds.stale?" · Desactualizada":""}. Solo previo; no son cuotas de Draftea. Sin datos suficientes no se añade aporte.</p></>}
 </section>;
}
