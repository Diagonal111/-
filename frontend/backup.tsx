import { useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, ShieldCheck, UploadCloud } from 'lucide-react'
import { api } from './api'

type Preview={token:string;exported_at:string;questions:number;attempts:number;photos:number;legacy:boolean}
export function BackupPanel({onRestored}:{onRestored:()=>Promise<void>}){
  const [preview,setPreview]=useState<Preview|null>(null), [accepted,setAccepted]=useState(false)
  const [busy,setBusy]=useState(''), [error,setError]=useState(''), [notice,setNotice]=useState('')
  const [safety,setSafety]=useState<{name:string;size:number}[]>([])
  const input=useRef<HTMLInputElement>(null)
  const load=()=>api<{name:string;size:number}[]>('/backups/safety').then(setSafety).catch(()=>{})
  useEffect(()=>{load()},[])
  const validate=async(file:File)=>{
    setBusy('validate');setError('');setPreview(null);setAccepted(false);setNotice('')
    try{const form=new FormData();form.append('file',file);setPreview(await api<Preview>('/backups/validate',form))}catch(e){setError((e as Error).message)}finally{setBusy('')}
  }
  const restore=async()=>{
    if(!preview||!accepted)return
    setBusy('restore');setError('')
    try{await api('/backups/restore',{token:preview.token});setPreview(null);setAccepted(false);await onRestored();await load();setNotice('恢复完成。恢复前的数据已保存为下方的安全备份。')}catch(e){setError((e as Error).message)}finally{setBusy('')}
  }
  return <section className="panel settings-card"><div className="section-head"><h2><ShieldCheck size={18}/>恢复学习备份</h2></div><div className="settings-body">
    {error&&<div className="alert error" role="alert">{error}</div>}{notice&&<div className="info-strip" role="status">{notice}</div>}
    <p className="subtle">选择拾知导出的 ZIP。先检查文件与照片完整性，再预览恢复内容。AI 服务配置沿用本机当前设置。</p><input ref={input} type="file" hidden accept=".zip" onChange={e=>{if(e.target.files?.[0])validate(e.target.files[0]);e.target.value=''}}/>
    <button className="btn secondary full" disabled={!!busy} onClick={()=>input.current?.click()}><UploadCloud size={16}/>{busy==='validate'?'正在检查备份…':'选择备份并检查'}</button>
    {preview&&<div className="backup-preview"><h4>备份内容</h4><p>导出时间：{preview.exported_at}</p><div className="data-line"><span>题目 / 作答 / 照片</span><strong>{preview.questions} / {preview.attempts} / {preview.photos}</strong></div>{preview.legacy&&<p className="subtle">旧版备份会自动补齐题目版本信息。</p>}<label className="checkbox-line"><input type="checkbox" checked={accepted} disabled={!!busy} onChange={e=>setAccepted(e.target.checked)}/>我确认用此备份替换当前学习数据。程序会先自动保存当前数据。</label><button className="btn primary full" disabled={!accepted||!!busy} onClick={restore}>{busy==='restore'?'正在恢复…':'确认恢复此备份'}</button><p className="subtle">预览 30 分钟内有效；期间学习数据改变时，需要重新检查。</p></div>}
    {safety.length>0&&<div className="safety-list"><h4>恢复前的安全备份</h4>{safety.map(s=><a href={'/api/backups/safety/'+s.name} download key={s.name}><ArrowDownToLine size={14}/><span>{s.name}</span><small>{Math.ceil(s.size/1024)} KB</small></a>)}</div>}
  </div></section>
}
