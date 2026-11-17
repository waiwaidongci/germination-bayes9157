import {useEffect,useState} from 'react';
import {ShieldCheck,Copy,Check} from 'lucide-react';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {StudySelector} from '../components/StudySelector';
import {DataTable} from '../components/common/DataTable';
import {Notice} from '../components/common/Notice';
import {getBudgets,getReleases,publishRelease} from '../api/privacy';
import {DPBudgetRow,DPRelease} from '../types/domain';
import {number,percent,time} from '../utils/format';

export function Privacy(){
    const s=useResearchData(),{user}=useAuth(),a=useAction();
    const [studyId,setStudyId]=useState(0),[releaseId,setReleaseId]=useState(''),[epsilon,setEpsilon]=useState(.1),[releases,setReleases]=useState<DPRelease[]>([]),[budgets,setBudgets]=useState<DPBudgetRow[]>([]),[copied,setCopied]=useState('');
    const study=s.studies.find(x=>x.id===studyId)||s.studies[0];
    const load=async()=>{if(study){setReleases(await getReleases(study.id))}setBudgets(await getBudgets())};
    useEffect(()=>{if(study)load()},[study?.id]);
    const current=budgets.find(b=>b.source===study?.source);
    function submit(e:React.FormEvent){e.preventDefault();if(!study)return;a.execute(async()=>{const r=await publishRelease(study.id,{release_id:releaseId,epsilon});setReleaseId('');await load();copy(r.shared_path)})}
    function copy(path:string){const url=window.location.origin+path;navigator.clipboard?.writeText(url).catch(()=>{});setCopied(path);setTimeout(()=>setCopied(''),2500)}
    return <div className="page">
        <div className="page-title"><div><p className="eyebrow">DIFFERENTIAL PRIVACY RELEASE / 06</p><h1>批级差分隐私发布<span>增删一个完整批次为邻接；只发布批率等权均值，批次数保密。</span></h1></div></div>
        <Notice message={s.error||a.error} onRetry={s.refresh}/>
        <StudySelector studies={s.studies} value={study?.id||0} onChange={setStudyId}/>
        {study&&<div className="source-note"><b>{study.code} · {study.name}</b><p>来源 <code>{study.source}</code>；同一来源所有研究共用一个隐私账本，累计上限1，换快照不重置。</p>
            <small>剩余预算 {current?number(current.remaining,6):'1.000000'} / 已发布 {current?.releases||0} 次 · 敏感度 Δ=1/9（两侧均至少8批）</small></div>}
        <div className="privacy-grid">
            <section>
                <h2>发布新的噪声均值</h2>
                {user?.role!=='viewer'?<form onSubmit={submit}>
                    <label>发布号<input aria-label="发布号" value={releaseId} onChange={e=>setReleaseId(e.target.value)} required maxLength={64} placeholder="例如 DP-2026-11-16-01 / 同号重试返回原结果"/></label>
                    <label>本次隐私预算 ε（0 &lt; ε ≤ 1）<input aria-label="隐私预算" type="number" min="0.000001" max="1" step="0.000001" value={epsilon} onChange={e=>setEpsilon(Number(e.target.value))} required/></label>
                    <p className="caption">每次自选正预算；从同一来源账本扣除。预算耗尽后拒绝新发布。同一发布号重试返回原噪声结果、不再扣费；同号异内容返回409。</p>
                    <button className="primary" disabled={a.busy||!study||!releaseId}>发布差分隐私摘要 <ShieldCheck size={15}/></button>
                </form>:<p className="role-note">阅读者可查看已发布摘要与预算，发布需分析员或负责人权限。</p>}
                <div className="dp-protocol">
                    <h3>保证与边界</h3>
                    <ol>
                        <li><b>邻接与敏感度</b><p>相邻数据集为增删一个完整批次。两侧都须≥8批，故较大侧m≥9；等权均值变化至多1/m≤1/9，取 Δ=1/9。</p></li>
                        <li><b>次数保密</b><p>均值使用数据相关分母，发布物不含批次数、逐批n/k、批号、原始计数或先验αβ。</p></li>
                        <li><b>预算与故障</b><p>扣费与结果写入同一事务，同成同败；并发扣费使用条件更新，不会超额。</p></li>
                        <li><b>顺序组合</b><p>同一来源多次发布按ε累加，上限1。单次发布不能外推为多次独立保证。</p></li>
                    </ol>
                </div>
            </section>
            <aside className="dp-side">
                <h2>来源隐私账本</h2>
                {budgets.length?<ul className="budget-list">{budgets.map(b=><li key={b.source}><b>{b.source}</b><span>已用 {number(b.spent,6)} / {number(b.total,2)} · 剩余 {number(b.remaining,6)} · {b.releases}次</span><i><em style={{width:Math.min(100,(b.spent/b.total)*100)+'%'}}/></i></li>)}</ul>:<p className="empty">尚无发布记录；首次发布后建立来源账本。</p>}
            </aside>
        </div>
        <div className="section-heading"><h2>已发布摘要</h2><span>共享链接匿名可读；内部页面保留审计字段</span></div>
        {releases.length?<div className="compact-table"><DataTable head={['发布号','ε','Δ','噪声尺度','发布均值','已用/剩余','时间','共享链接']}>{releases.map(r=><tr key={r.release_id}><td>{r.release_id}</td><td>{number(r.epsilon,6)}</td><td>{number(r.sensitivity,6)}</td><td>{number(r.noise_scale,6)}</td><td>{percent(r.noisy_mean)}</td><td>{number(r.budget.spent,6)} / {number(r.budget.remaining,6)}</td><td>{time(r.created_at)}</td><td><button className="text-link" onClick={()=>copy(r.shared_path)}>{copied===r.shared_path?<Check size={13}/>:<Copy size={13}/>}{copied===r.shared_path?'已复制':'复制链接'}</button></td></tr>)}</DataTable></div>:<p className="empty">该研究尚未发布差分隐私摘要。</p>}
    </div>;
}
