import {useEffect,useState} from 'react';
import {useParams} from 'react-router-dom';
import {getSharedRelease} from '../api/privacy';
import {DPRelease} from '../types/domain';
import {number,percent,time} from '../utils/format';

const TOKEN_KEY='germination-token';
const USER_KEY='germination-user';

export function SharedRelease(){
    const {token=''}=useParams();
    const [data,setData]=useState<DPRelease|null>(null);
    const [error,setError]=useState('');
    const [loading,setLoading]=useState(true);
    useEffect(()=>{
        let live=true;
        setLoading(true);
        fetch('/api/shared/releases/'+encodeURIComponent(token))
            .then(async r=>{if(!r.ok)throw new Error('共享发布不存在或链接无效');return r.json()})
            .then(d=>{if(live){setData(d);setError('')}})
            .catch(e=>{if(live){setError((e as Error).message);setData(null)}})
            .finally(()=>live&&setLoading(false));
        return()=>{live=false};
    },[token]);
    return <div className="shared-public">
        <header className="shared-masthead"><div className="brand"><strong>铎岑<small>GERMINATION / PRIVACY RELEASE</small></strong></div><span>匿名共享页 · 无需登录</span></header>
        <main className="shared-main">
            <p className="eyebrow">BATCH-LEVEL DIFFERENTIAL PRIVACY / SHARED</p>
            <h1>批级差分隐私摘要<span>只公开加入噪声后的批率等权均值。</span></h1>
            {error&&<div role="alert" className="notice">{error}</div>}
            {loading&&!data&&!error&&<p className="empty">正在读取共享发布……</p>}
            {data&&<div className="shared-card">
                <div className="shared-head"><span className="eyebrow">{data.study_code} / {data.release_id}</span><h2>共享发布摘要</h2><p>{data.statistic}</p></div>
                <div className="shared-value"><span>批率等权均值（已加Laplace噪声）</span><b>{percent(data.noisy_mean)}</b><small>{number(data.noisy_mean,6)}；已投影到[0,1]，投影属后处理，不削弱隐私保证。</small></div>
                <dl className="shared-grid">
                    <div><dt>邻接定义</dt><dd>{data.neighbor}</dd></div>
                    <div><dt>L1敏感度 Δ</dt><dd>{number(data.sensitivity,6)}</dd></div>
                    <div><dt>本次隐私预算 ε</dt><dd>{number(data.epsilon,6)}</dd></div>
                    <div><dt>噪声尺度 Δ/ε</dt><dd>{number(data.noise_scale,6)}</dd></div>
                    <div><dt>机制</dt><dd>{data.mechanism==='laplace'?'Laplace':'—'}</dd></div>
                    <div><dt>发布时间</dt><dd>{time(data.created_at)}</dd></div>
                </dl>
                <p className="shared-bound">{data.bound}。同一来源累计预算上限1，已用{number(data.budget.spent,6)}、剩余{number(data.budget.remaining,6)}；换快照不重置。</p>
                <p className="shared-note">{data.note}</p>
                <p className="fingerprint">SHARE TOKEN {data.share_token} / {data.version||data.mechanism}</p>
            </div>}
            <footer className="shared-footer"><span>本页匿名可读，不含原始n/k、批次数、批号、点估先验或拟合参数。</span><span>内部研究与拟合照常使用，不受本页影响。</span></footer>
        </main>
    </div>;
}
