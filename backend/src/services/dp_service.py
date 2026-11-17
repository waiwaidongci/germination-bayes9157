"""Batch-level differential-privacy release of germination statistics.

Neighbouring datasets are defined by adding or removing one complete batch
(lot), not by editing a single n/k reading.

Released statistic: the equal-weight mean of per-batch raw rates k_j / n_j.
The number of batches is itself part of the secret: the mean is formed with the
data-dependent denominator and no batch count, lot code, raw count or fitted
prior parameter is published.

Sensitivity
-----------
Take two neighbouring studies D and D' with m and m-1 batches.  Both must be
admissible releases, i.e. contain at least MIN_BATCHES = 8 batches, so m >= 9.
Write S for the sum of the m-1 shared rates and r in [0,1] for the added or
removed rate.  Then

    |mean(D) - mean(D')| = |r/m - S/(m(m-1))| <= max(1/m, 1/m) = 1/m <= 1/9.

For addition m >= 9 trivially; for removal the remaining m-1 >= 8 also forces
m >= 9.  Hence the global L1 sensitivity over every admissible neighbouring pair
is Delta = 1/(MIN_BATCHES+1) = 1/9, and it does not depend on how many batches a
particular release has.  That uniform bound is what makes the noisy mean valid
even though the batch count stays secret.  It is attained by 8 all-zero batches
plus one rate-1 batch (mean 1/9) versus the same 8 zero batches (mean 0).

Mechanism: Laplace(scale = Delta / epsilon).  The published value is projected
onto [0,1]; projection is post-processing and therefore does not weaken the
guarantee.

Budget
------
Each data source owns one ledger capped at 1.0.  A release spends the caller's
chosen epsilon, quantized up to whole 1e-6 units so the charge never undershoots
the noise actually drawn, and the ledger is never reset by a new
snapshot or a new study under the same source.  Charge and published value are
written in a single database transaction, so either both survive or neither
does.  A release id is idempotent: retrying it returns the original noise draw
without another charge; reusing it with different content is rejected.
"""
import math
import secrets
from decimal import Decimal,InvalidOperation,ROUND_CEILING
from fractions import Fraction

from fastapi import HTTPException
from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError

from ..models import DPBudget,DPRelease,GerminationStudy
from ..utils.clock import now
from ..utils.fingerprint import fingerprint
from .analysis_service import prepare_snapshot
from .audit_service import log
from .study_service import create_snapshot

VERSION="batch-dp-equal-weight-mean-laplace-v1"
MECHANISM="laplace"
MIN_BATCHES=8
TOTAL_MICRO=1_000_000
SENSITIVITY=float(Fraction(1,MIN_BATCHES+1))
ATTEMPTS=3
MIN_EPSILON=Decimal("0.000001")


def epsilon_micro(value):
    """Quantize a user-chosen epsilon to integer micro-units, rounding up.

    Rounding up never spends less than the requested epsilon, so the stated
    budget always covers the noise actually drawn.  1e-6 is the smallest unit.
    """
    try:decimal=Decimal(str(value))
    except (InvalidOperation,ValueError):raise HTTPException(422,"隐私预算须为有限正数")
    if not decimal.is_finite() or decimal<=0:raise HTTPException(422,"隐私预算须为有限正数")
    if decimal>1:raise HTTPException(422,"单次隐私预算不能超过同一来源总预算1")
    if decimal<MIN_EPSILON:raise HTTPException(422,"隐私预算至少为0.000001")
    return int((decimal*TOTAL_MICRO).to_integral_value(rounding=ROUND_CEILING))


def secure_uniform():
    """Cryptographically strong uniform draw in the open interval (0,1)."""
    return (secrets.randbits(53)+1)/float(1<<53)


def laplace_noise(uniform,scale):
    if not scale>0 or not math.isfinite(scale):raise ValueError("Laplace尺度须为有限正数")
    u=uniform()
    if not 0<u<1:raise ValueError("均匀抽样须落在(0,1)")
    return scale*(math.log(2*u) if u<.5 else -math.log(2*(1-u)))


def dp_inputs(snapshot):
    """Validate the snapshot and return ordered counts plus raw rates."""
    lots,counts,n,k=prepare_snapshot(snapshot,require_study=False)
    if len(lots)<MIN_BATCHES:raise ValueError(f"差分隐私发布要求至少{MIN_BATCHES}个完整独立批次")
    return lots,counts,[c["k"]/c["n"] for c in counts]


def request_fingerprint(release_id,source,study_id,epsilon_u,counts):
    """Content hash of the exact DP query; it commits to per-batch n/k order."""
    return fingerprint({"version":VERSION,"release_id":release_id,"source":source,"study_id":study_id,"epsilon_micro":epsilon_u,"sensitivity":SENSITIVITY,"mechanism":MECHANISM,"batches":[[c["n"],c["k"]] for c in counts]})


def _ensure_budget(db,source):
    """Create a zero-spend ledger in its own short transaction if absent.

    Committing a fresh ledger with zero spend is harmless even if the release
    that follows fails, and it keeps ledger creation out of the charge
    transaction.  A concurrent creator may win the primary key; whoever loses
    re-reads the row instead of failing.
    """
    if db.get(DPBudget,source) is not None:return
    db.add(DPBudget(source=source,total_micro=TOTAL_MICRO,spent_micro=0,release_count=0,updated_at=now()))
    try:db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(DPBudget,source) is None:raise HTTPException(409,"隐私账本正在并发创建，请重试")


def _charge(db,source,cost):
    """Atomically reserve budget; returns remaining when the charge is refused."""
    charged=db.execute(update(DPBudget).where(DPBudget.source==source,DPBudget.spent_micro+cost<=DPBudget.total_micro).values(spent_micro=DPBudget.spent_micro+cost,release_count=DPBudget.release_count+1,updated_at=now()).returning(DPBudget.spent_micro)).first()
    if charged is not None:return None
    total,spent=db.execute(select(DPBudget.total_micro,DPBudget.spent_micro).where(DPBudget.source==source)).one()
    return max(0,total-spent)


def _commit(db):
    """Single transaction boundary: ledger charge, release row and audit land together."""
    db.commit()


def _replay(db,row,fp):
    if row.request_fingerprint!=fp:raise HTTPException(409,"该发布号已用于不同内容；请使用新的发布号")
    return row


def _draw_noise(uniform,scale):
    """Draw once per (attempt, epsilon).  A rollback never reuses the same draw
    for a second attempt, and a replay never draws at all."""
    return laplace_noise(uniform or secure_uniform,scale)


def budget_summary(db,source):
    row=db.execute(select(DPBudget.total_micro,DPBudget.spent_micro).where(DPBudget.source==source)).first()
    if row is None:return {"total":1.0,"spent":0.0,"remaining":1.0}
    total,spent=row
    return {"total":total/TOTAL_MICRO,"spent":spent/TOTAL_MICRO,"remaining":max(0,total-spent)/TOTAL_MICRO}


def public_payload(db,row):
    """Anonymous view: no raw counts, batch count, lot codes or fitted parameters."""
    study=db.get(GerminationStudy,row.study_id)
    return {"release_id":row.release_id,"share_token":row.token,"shared_path":f"/shared/releases/{row.token}","study_code":study.code if study else "","epsilon":row.epsilon,"sensitivity":row.sensitivity,"mechanism":row.mechanism,"noise_scale":row.noise_scale,"noisy_mean":row.noisy_mean,"created_at":row.created_at,"version":VERSION,"budget":budget_summary(db,row.source),"statistic":"各批原始率k/n的等权均值（加入Laplace噪声后）","neighbor":"增删一个完整批次","bound":"增删一个完整批次对该均值的影响至多1/9（L1敏感度，两侧均至少8批）","note":"加入Laplace噪声的批级均值发布。未公开批次数、原始n/k、批号、点估先验或拟合参数；单个发布号不构成多次独立隐私保证。"}


def internal_payload(db,row):
    out=public_payload(db,row)
    out.update({"source":row.source,"study_id":row.study_id,"created_by":row.created_by,"snapshot_hash":row.snapshot_hash,"request_fingerprint":row.request_fingerprint,"budget":{"total":1.0,"spent":row.epsilon_micro/TOTAL_MICRO,"remaining":budget_summary(db,row.source)["remaining"]} })
    return out


def publish(db,study,data,user,uniform=None):
    epsilon_u=epsilon_micro(data.epsilon)
    source=(study.source or "").strip()
    if not source:raise HTTPException(422,"研究来源为空，无法建立来源级隐私账本")
    _ensure_budget(db,source)
    snapshot=create_snapshot(db,study)
    try:lots,counts,rates=dp_inputs(snapshot)
    except ValueError as e:raise HTTPException(422,str(e))
    fp=request_fingerprint(data.release_id,source,study.id,epsilon_u,counts)
    snapshot_hash=fingerprint({"version":VERSION,"batches":[[c["n"],c["k"]] for c in counts]})
    existing=db.query(DPRelease).filter_by(release_id=data.release_id).first()
    if existing is not None:return internal_payload(db,_replay(db,existing,fp))
    true_mean=sum(rates)/len(rates)
    scale=SENSITIVITY*TOTAL_MICRO/epsilon_u
    token=secrets.token_urlsafe(24)
    for attempt in range(ATTEMPTS):
        try:
            projected=min(1.0,max(0.0,true_mean+_draw_noise(uniform,scale)))
            remaining=_charge(db,source,epsilon_u)
            if remaining is not None:
                raise HTTPException(429,f"同一来源的累计隐私预算不足：剩余{remaining/TOTAL_MICRO:.6f}，本次请求{epsilon_u/TOTAL_MICRO:.6f}")
            row=DPRelease(release_id=data.release_id,source=source,study_id=study.id,snapshot_hash=snapshot_hash,epsilon_micro=epsilon_u,epsilon=epsilon_u/TOTAL_MICRO,sensitivity=SENSITIVITY,mechanism=MECHANISM,noise_scale=scale,noisy_mean=projected,request_fingerprint=fp,created_by=user.email)
            row.token=token;db.add(row);db.flush()
            log(db,user.email,"dp.release",data.release_id)
            _commit(db)
            return internal_payload(db,row)
        except IntegrityError:
            db.rollback()
            existing=db.query(DPRelease).filter_by(release_id=data.release_id).first()
            if existing is not None:
                _replay(db,existing,fp);return internal_payload(db,existing)
            if attempt==ATTEMPTS-1:raise HTTPException(409,"发布号正在并发创建，请重试")
        except HTTPException:
            db.rollback();raise
        except Exception:
            db.rollback();raise


def get_shared(db,token):
    row=db.query(DPRelease).filter_by(token=token).first()
    if row is None:raise HTTPException(404,"共享发布不存在或链接无效")
    return row


def shared_payload(db,token):
    return public_payload(db,get_shared(db,token))


def list_releases(db,study_id):
    return [internal_payload(db,r) for r in db.query(DPRelease).filter_by(study_id=study_id).order_by(DPRelease.id.desc())]


def list_budgets(db):
    out=[]
    for total,spent,count,source in db.execute(select(DPBudget.total_micro,DPBudget.spent_micro,DPBudget.release_count,DPBudget.source).order_by(DPBudget.source)):
        out.append({"source":source,"total":total/TOTAL_MICRO,"spent":spent/TOTAL_MICRO,"remaining":max(0,total-spent)/TOTAL_MICRO,"releases":count})
    return out
