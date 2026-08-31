import { create } from 'zustand'
import { persist } from 'zustand/middleware'
export type User = { id: string; username: string; name: string; email?: string; system_role: string; is_active?: boolean }
export type Project = { id: string; name: string; description: string; role: string }
type State = { user?: User; projects: Project[]; projectId?: string; setSession:(token:string,user:User)=>void; setProjects:(items:Project[])=>void; selectProject:(id?:string)=>void; logout:()=>void }
export const useSession=create<State>()(persist((set)=>({projects:[],setSession:(token,user)=>{localStorage.setItem('access_token',token);set({user})},setProjects:(projects)=>set((s)=>({projects,projectId:projects.some(p=>p.id===s.projectId)?s.projectId:projects[0]?.id})),selectProject:(projectId)=>set({projectId}),logout:()=>{localStorage.removeItem('access_token');set({user:undefined,projects:[],projectId:undefined})}}),{name:'ai-test-session',partialize:(s)=>({user:s.user,projectId:s.projectId})}))
