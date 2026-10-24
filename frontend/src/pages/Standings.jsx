import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, dateLabel } from "../api/client";
import { useFeed } from "../components/FeedContext";
import Crest from "../components/Crest";

const primary = [["rank","Pos","Posición"],["points","Pts","Puntos"],["gamesPlayed","PJ","Partidos jugados"],["wins","G","Ganados"],["ties","E","Empatados"],["losses","P","Perdidos"],["pointsFor","GF","Goles a favor"],["pointsAgainst","GC","Goles en contra"],["pointDifferential","DG","Diferencia de goles"]];
const labels = {advanced:"Clasificación (código de la fuente)",deductions:"Deducción de puntos",ppg:"Puntos por partido",rankChange:"Cambio de posición",overall:"Registro G-E-P"};
function Table({code, name}) {
  const [data,setData]=useState(null);
  const [error,setError]=useState(false);
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let active=true;
    const load=()=>api.standings(code).then(d=>{if(active){setData(d);setError(false);}}).catch(()=>{if(active)setError(true);});
    load(); const timer=setInterval(load,300000);
    return ()=>{active=false;clearInterval(timer);};
  },[code,attempt]);
  return <section className="panel rounded-xl overflow-hidden" aria-label={`Tabla de posiciones de ${name}`}>
    <div className="p-5 border-b border-ink-950/10 flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-bold">{name}</h2><Link to={`/plantillas?liga=${code}`} className="text-xs text-led inline-block mt-2">Equipos, jugadores y estadísticas ↗</Link></div>{data && <a href={data.source_url} target="_blank" rel="noreferrer" className="text-xs text-led">Fuente: ESPN ↗</a>}</div>
    {error && <div role="alert" className="p-4 text-sm text-amber">No se pudo actualizar la clasificación. {data ? "Se conserva la última consulta; puede estar desactualizada." : "No hay datos disponibles."} <button className="underline" onClick={()=>setAttempt(n=>n+1)}>Reintentar</button></div>}
    {!data && !error && <p role="status" className="p-6 text-mute">Consultando clasificación…</p>}
    {data && <>{data.stale && <p className="p-4 text-amber text-sm">Datos guardados: la fuente no respondió a la actualización.</p>}{data.groups.map((group,index)=><div key={`${group.name}-${index}`}>
      <div className="px-5 py-4 bg-ink-950/[.02]"><h3 className="font-semibold text-sm">{group.name}</h3><p className="text-xs text-mute mt-1">{group.season} · {group.rows.length} equipos</p></div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={`Clasificación ${group.name}, desplaza para ver todas las columnas`}>
        <table className="w-full text-xs whitespace-nowrap"><caption className="sr-only">Clasificación publicada por ESPN, {group.name}</caption><thead className="text-mute bg-ink-950/[.03]"><tr><th scope="col" className="px-4 py-3 text-left">Pos</th><th scope="col" className="px-4 py-3 text-left sticky left-0 bg-pitch-950">Equipo</th>{primary.slice(1).map(([key,short,full])=><th scope="col" key={key} title={full} className="px-4 py-3 text-right">{short}</th>)}</tr></thead>
        <tbody>{group.rows.map(row=><tr key={row.id} className="border-t border-ink-950/5 hover:bg-ink-950/[.03]"><td className="px-4 py-3 text-mute">{row.stats.rank ?? "—"}</td><th scope="row" className="px-4 py-3 text-left sticky left-0 bg-pitch-950 font-medium"><span className="flex items-center gap-3"><Crest src={row.logo} name={row.name} size={25}/>{row.team_id ? <Link className="hover:text-led" to={`/equipo/${row.team_id}`}>{row.name} ↗</Link> : row.name}</span></th>{primary.slice(1).map(([key])=><td key={key} className={`px-4 py-3 text-right stat-num ${key==="points"?"text-led font-bold":""}`}>{row.stats[key] ?? "—"}</td>)}</tr>)}</tbody></table>
      </div>
      <details className="border-t border-ink-950/10 p-4"><summary className="cursor-pointer text-xs text-led">Todas las estadísticas adicionales publicadas</summary><div className="overflow-x-auto mt-4"><table className="w-full text-xs whitespace-nowrap"><thead><tr><th className="text-left p-3">Equipo</th>{group.columns.filter(c=>!primary.some(([k])=>k===c.key)).map(c=><th key={c.key} title={c.description} className="p-3 text-right">{labels[c.key] || c.label}</th>)}</tr></thead><tbody>{group.rows.map(row=><tr key={row.id} className="border-t border-ink-950/5"><th className="p-3 text-left font-medium">{row.name}</th>{group.columns.filter(c=>!primary.some(([k])=>k===c.key)).map(c=><td key={c.key} className="p-3 text-right">{row.stats[c.key] ?? "—"}</td>)}</tr>)}</tbody></table></div></details>
    </div>)}<p className="p-4 text-[11px] text-mute border-t border-ink-950/10">Última consulta: {dateLabel(data.fetched_at, {year:"numeric",hour:"2-digit",minute:"2-digit"})} · Horario de Hermosillo. Consulta automática cada 5 minutos; la fuente puede tener demora.</p></>}
  </section>;
}
export default function Standings(){
  const {leagues}=useFeed();const [params,setParams]=useSearchParams();const code=params.get("liga")||"ALL";
  return <div className="space-y-6"><div><p className="eyebrow mb-3">Competición / Clasificación</p><h1 className="text-3xl font-bold">Tablas de posiciones.</h1><p className="text-sm text-mute mt-3">Todos los equipos y estadísticas de la clasificación publicada. Cada torneo o conferencia conserva su propia tabla.</p></div>
  <label className="flex items-center gap-3 text-sm">Liga<select aria-label="Liga de la clasificación" className="field max-w-[260px]" value={code} onChange={e=>setParams(e.target.value==="ALL"?{}:{liga:e.target.value})}><option value="ALL">Todas las ligas</option>{leagues.map(l=><option key={l.code} value={l.code}>{l.name}</option>)}</select></label>
  <p className="text-xs text-mute">PJ: jugados · G: ganados · E: empatados · P: perdidos · GF/GC: goles a favor/en contra · DG: diferencia · —: dato no publicado. El orden corresponde al proveedor y sus criterios de desempate. Córners y tarjetas no se incluyen si no están publicados en esta clasificación.</p>
  {leagues.filter(l=>code==="ALL"||l.code===code).map(l=><Table key={l.code} code={l.code} name={l.name}/>)}
  </div>;
}


