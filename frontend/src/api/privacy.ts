import {request} from './client';
import {DPBudgetRow,DPRelease} from '../types/domain';
export const getReleases=(studyId:number)=>request<DPRelease[]>(`/studies/${studyId}/dp-releases`);
export const publishRelease=(studyId:number,data:{release_id:string;epsilon:number})=>request<DPRelease>(`/studies/${studyId}/dp-releases`,{method:'POST',body:JSON.stringify(data)});
export const getBudgets=()=>request<DPBudgetRow[]>('/dp-budgets');
export const getSharedRelease=(token:string)=>request<DPRelease>(`/shared/releases/${token}`);
