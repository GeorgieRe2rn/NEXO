import { useEffect, useState } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";
import { Download, WifiOff, X } from "lucide-react";
export default function PwaStatus(){
  const {needRefresh:[needsUpdate],updateServiceWorker}=useRegisterSW({immediate:true});
  const [prompt,setPrompt]=useState(null);
  const [offline,setOffline]=useState(!navigator.onLine);
  const [dismissed,setDismissed]=useState(false);
  useEffect(()=>{
    const install=e=>{e.preventDefault();setPrompt(e);};
    const online=()=>setOffline(!navigator.onLine);
    const installed=()=>setPrompt(null);
    window.addEventListener("beforeinstallprompt",install);
    window.addEventListener("appinstalled",installed);
    window.addEventListener("online",online);window.addEventListener("offline",online);
    return ()=>{window.removeEventListener("beforeinstallprompt",install);window.removeEventListener("appinstalled",installed);window.removeEventListener("online",online);window.removeEventListener("offline",online);};
  },[]);
  if(offline)return <div role="status" className="pwa-banner"><WifiOff size={17}/><span>Sin conexión. Los marcadores y momios no se están actualizando.</span></div>;
  if(needsUpdate)return <div className="pwa-banner"><Download size={17}/><button onClick={()=>updateServiceWorker(true)}>Nueva versión disponible · Actualizar Nexo</button></div>;
  if(!prompt||dismissed)return null;
  return <div className="pwa-banner"><Download size={17}/><button className="flex-1 text-left" onClick={async()=>{await prompt.prompt();await prompt.userChoice;setPrompt(null);}}>Instalar Nexo en este dispositivo</button><button aria-label="Cerrar invitación de instalación" onClick={()=>setDismissed(true)}><X size={16}/></button></div>;
}
