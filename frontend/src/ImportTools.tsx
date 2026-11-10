import { useState } from 'react';
import { useQuery,useMutation,useQueryClient } from '@tanstack/react-query';
import { api,errorMessage } from './api';

export default function ImportTools({file,mapping,onMapping}:{file:File|null;mapping:string;onMapping:(value:string)=>void}) {
 const cache=useQueryClient();const [name,setName]=useState('');const [preview,setPreview]=useState<unknown>(null);
 const templates=useQuery<{id:string;name:string;mapping:Record<string,string>}[]>({queryKey:['/data/mappings'],queryFn:async()=>(await api.get('/data/mappings')).data});
 const inspect=useMutation({mutationFn:async()=>{if(!file)throw new Error('Choose a file first');const body=new FormData();body.append('file',file);body.append('mapping',mapping);setPreview((await api.post('/data/upload/preview',body)).data);}});
 const save=useMutation({mutationFn:async()=>api.post('/data/mappings',{name,mapping:JSON.parse(mapping)}),onSuccess:()=>{setName('');cache.invalidateQueries({queryKey:['/data/mappings']});}});
 return <div className="import-tools"><label>Saved mapping template<select defaultValue="" onChange={e=>{const selected=templates.data?.find(t=>t.id===e.target.value);if(selected)onMapping(JSON.stringify(selected.mapping,null,2));}}><option value="">Choose a saved mapping</option>{templates.data?.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><div className="form-row"><label>Template name<input value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Monthly bank export"/></label><button className="secondary" disabled={!name||save.isPending} onClick={()=>save.mutate()}>Save mapping</button></div><button className="secondary" disabled={!file||inspect.isPending} onClick={()=>inspect.mutate()}>Preview first 20 records</button>{(inspect.error||save.error)&&<div className="error">{errorMessage(inspect.error||save.error)}</div>}{preview!==null&&<details open><summary>Validation preview · no records imported</summary><pre>{JSON.stringify(preview,null,2)}</pre></details>}</div>;
}
