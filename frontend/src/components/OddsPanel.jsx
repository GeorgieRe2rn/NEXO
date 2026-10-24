import { useState } from "react";
import { api, kickoffLabel } from "../api/client";
import usePolling from "../hooks/usePolling";
export default function OddsPanel(){
  const {data,error,reload}=usePolling(api.oddsStatus,"odds-status",60000);
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");
  if(!data)return <p className="text-xs text-mute">{error||"Consultando momios…"}</p>;
  const c=data.combiner;
  return <section className="panel rounded-xl p-5 space-y-4">
    <div className="flex items-start justify-between gap-3"><div><p className="eyebrow text-led mb-2">Referencia del mercado</p><h2 className="font-semibold">Momios reales</h2></div><span className="text-xs text-mute">{data.configured?"API configurada":"Falta clave"}</span></div>
    <div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-mute">Capturas guardadas</p><p className="text-2xl text-led mt-1">{data.observations}</p></div><div><p className="text-xs text-mute">Peso aprendido en 1X2</p><p className="text-2xl mt-1">{Math.round(c.weight*100)}%</p></div></div>
    <p className="text-xs text-mute leading-6">{c.weight>0?"El consenso de momios participa en el pronóstico previo con un peso validado.":`Recopilando evidencia: ${c.samples} / ${c.minimum} partidos evaluados. Mientras se evalúa, la regla automática aporta 10% con concordancia entre al menos tres fuentes y hasta 20% si también hay estabilidad temporal observada.`}</p>
    <p className="text-xs text-mute">Goles: peso validado {Math.round((data.goals_combiner?.weight||0)*100)}% · {data.goals_combiner?.samples||0} / 200 evaluados.</p><details className="text-xs text-mute leading-6"><summary className="cursor-pointer text-paper py-2">Cobertura y método</summary><p>The Odds API · cuotas decimales de las casas identificadas. Se elimina el margen y se toma un consenso robusto entre fuentes vigentes, descartando cuotas alejadas. No son momios de Draftea.</p><p className="mt-2">Ganador/empate y goles usan referencias independientes. Dispersión máxima: 8 puntos porcentuales. Movimiento temporal máximo: 4 puntos. Una sola captura no demuestra estabilidad temporal. Los pesos iniciales son experimentales; al reunir evidencia se reemplazan por pesos evaluados temporalmente, incluso cero. Córners y amarillas: sin cobertura confirmada; no se rellenan.</p><p className="mt-2">{data.refresh} La cuota gratuita limita las consultas. Sin coincidencia exacta de equipos y hora, no se vincula un evento.</p>{data.last_sync&&<p className="mt-2">Última consulta: {kickoffLabel(data.last_sync.at)} · {data.last_sync.imported} capturas · {data.last_sync.unmatched} sin vincular · {data.last_sync.errors?.length||0} errores.</p>}</details>
    <button disabled={busy||!data.configured} className="pill" onClick={async()=>{setBusy(true);try{await api.csrf();const r=await api.syncOdds();setMessage(r.message||`Consulta completada: ${r.imported||0} capturas nuevas. Se respeta la caché diaria.`);reload();}catch{setMessage("No se pudieron consultar los momios.");}finally{setBusy(false);}}}>{busy?"Consultando…":"Sincronizar momios"}</button>
    {message&&<p role="status" className="text-xs text-mute">{message}</p>}
  </section>;
}
