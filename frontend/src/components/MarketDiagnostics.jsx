import {useState} from "react";
import {api} from "../api/client";
import {useFeed} from "./FeedContext";
import usePolling from "../hooks/usePolling";
import MatchOdds from "./MatchOdds";
export default function MarketDiagnostics(){
 const {items}=useFeed();const [selected,setSelected]=useState("");const chosen=selected||String(items[0]?.id||"");
 const {data}=usePolling(()=>chosen?api.match(chosen):Promise.resolve(null),`market-diagnostics-${chosen}`,60000);
 return <details className="panel rounded-xl p-5"><summary className="font-semibold cursor-pointer py-2">Aporte del mercado por partido</summary><label className="block text-xs text-mute mt-4">Partido<select className="field mt-2" value={chosen} onChange={e=>setSelected(e.target.value)}>{items.map(m=><option key={m.id} value={m.id}>{m.home.name} vs {m.away.name}</option>)}</select></label>{data&&<div className="mt-4"><MatchOdds id={chosen} snapshot={data.forecasts?.PRE}/></div>}</details>;
}
