import axios from 'axios';
export const api = axios.create({ baseURL: '/api/v1' });
export async function fetchData<T>(path:string):Promise<T> {
  const paginated=/^\/(data\/datasets|reconciliation|exceptions|audit)$/.test(path)||/^\/data\/datasets\/[^/]+\/transactions$/.test(path);
  if(!paginated)return (await api.get<T>(path)).data;
  const all:unknown[]=[];
  for(let offset=0;offset<100000;offset+=200) {
    const rows=(await api.get<unknown[]>(path,{params:{offset,limit:200}})).data;
    all.push(...rows);
    if(rows.length<200)return all as T;
  }
  throw new Error('Result set exceeds the workspace limit; refine the query through the paginated API.');
}
api.interceptors.request.use(config => {
  const demoUser=sessionStorage.getItem('reconcile-demo-user');
  if(demoUser)config.headers['X-Local-Demo-User']=demoUser;
  const token = sessionStorage.getItem('reconcile-token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : 'Unable to reach the service. Check that the backend is running.';
  }
  return error instanceof Error ? error.message : 'Operation failed';
}
export async function download(path: string, filename: string) {
  const response = await api.get(path, { responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url);
}
