"""Tests for batch-level differential privacy releases."""
import json
import math
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from src.models import DPBudget,DPRelease
from src.services import dp_service
from conftest import SessionLocal,budget,login,make_study


# ---------------------------------------------------------------- sensitivity
def test_equal_weight_mean_uses_data_dependent_count():
    study=make_study(rates=[.5,.5,.5,.5,.5,.5,.5,.5,.9])
    with SessionLocal() as db:
        from src.services.study_service import create_snapshot
        from src.models import GerminationStudy
        s=db.get(GerminationStudy,study)
        lots,counts,rates=dp_service.dp_inputs(create_snapshot(db,s))
    assert len(rates)==9
    assert sum(rates)/len(rates)==pytest.approx((8*.5+.9)/9)
    assert dp_service.SENSITIVITY==pytest.approx(1/9)


def test_add_or_remove_one_batch_sensitivity_is_bounded_by_one_ninth():
    """Brute force both directions over every admissible m and adversarial rates.

    Both neighbours must be publishable (>=8 batches), so the larger study has
    m >= 9 batches.  |mean(D)-mean(D')| = |r/m - S/(m(m-1))| <= max(1/m,1/m).
    """
    worst=0.0
    for m in range(9,120):
        restmax=max(abs(r/m-S/(m*(m-1))) for r in (0.0,1.0) for S in (0.0,float(m-1)))
        worst=max(worst,restmax)
    assert worst==pytest.approx(1/9)


def test_sensitivity_bound_is_attained_at_minimum_batches():
    """8 zero batches vs the same 8 plus a rate-1 batch: means 0 vs 1/9."""
    eight=sum([0.0]*8)/8
    nine=sum([0.0]*8+[1.0])/9
    assert abs(nine-eight)==pytest.approx(dp_service.SENSITIVITY)
    assert dp_service.SENSITIVITY==pytest.approx(1/9)
    # a 7-batch neighbour is not publishable, so the tighter 1/8 is out of scope
    assert (1/8)>dp_service.SENSITIVITY


# ------------------------------------------------------------------- neighbor
def test_minimum_batch_count_enforced_for_addition_and_removal():
    make_study(code="DC-07",rates=[.5]*7)
    with SessionLocal() as db:
        from src.models import GerminationStudy
        from src.services.study_service import create_snapshot
        s=db.query(GerminationStudy).filter_by(code="DC-07").first()
        with pytest.raises(ValueError):dp_service.dp_inputs(create_snapshot(db,s))


def test_laplace_noise_is_symmetric_and_scaled():
    mid=dp_service.laplace_noise(lambda:.5,1.0)
    assert mid==pytest.approx(0.0)
    hi=dp_service.laplace_noise(lambda:.75,2.0)
    lo=dp_service.laplace_noise(lambda:.25,2.0)
    assert hi==pytest.approx(-lo)
    assert hi==pytest.approx(2*math.log(2))


# --------------------------------------------------------------- publication
def test_publish_and_anonymous_shared_page_hides_raw_data(client):
    sid=make_study()
    user=login(client)
    r=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-1","epsilon":.2},headers=user)
    assert r.status_code==201,r.text
    body=r.json()
    assert body["epsilon"]==pytest.approx(.2)
    assert body["sensitivity"]==pytest.approx(1/9)
    assert body["mechanism"]=="laplace"
    assert body["noise_scale"]==pytest.approx((1/9)/.2)
    assert 0<=body["noisy_mean"]<=1
    shared=client.get(body["shared_path"])
    assert shared.status_code==200
    payload=shared.json()
    text=json.dumps(payload,ensure_ascii=False)
    for leaked in ("lot","lots","count","counts","n","k","raw_rate","batch_count","alpha","beta","fit","study_id","request_fingerprint","source","snapshot_hash"):
        assert leaked not in payload,leaked
    assert "DC-01-L" not in text
    assert payload["study_code"]=="DC-01"
    assert payload["noisy_mean"]==body["noisy_mean"]
    assert payload["budget"]["spent"]==pytest.approx(.2)


def test_repeated_reads_return_the_same_published_value(client):
    sid=make_study()
    headers=login(client)
    body=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"READ-1","epsilon":.4},headers=headers).json()
    reads=[client.get(body["shared_path"]).json() for _ in range(4)]
    assert {r["noisy_mean"] for r in reads}=={body["noisy_mean"]}
    assert all(r["budget"]==reads[0]["budget"] for r in reads)
    listed=client.get(f"/studies/{sid}/dp-releases",headers=headers).json()
    assert listed[0]["noisy_mean"]==body["noisy_mean"]
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(.4)


def test_reading_after_budget_exhaustion_still_serves_old_release(client):
    sid=make_study()
    headers=login(client)
    body=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"KEEP","epsilon":1},headers=headers).json()
    assert client.post(f"/studies/{sid}/dp-releases",json={"release_id":"NOPE","epsilon":.1},headers=headers).status_code==429
    assert client.get(body["shared_path"]).json()["noisy_mean"]==body["noisy_mean"]


def test_shared_page_needs_no_login_and_unknown_token_is_404(client):
    sid=make_study()
    token=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-2","epsilon":.1},headers=login(client)).json()["share_token"]
    assert client.get("/shared/releases/"+token).status_code==200
    assert client.get("/shared/releases/does-not-exist").status_code==404


def test_exact_noise_result_replayed_for_same_release_id(client):
    sid=make_study()
    headers=login(client)
    first=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-3","epsilon":.25},headers=headers).json()
    again=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-3","epsilon":.25},headers=headers)
    assert again.status_code==201
    assert again.json()["noisy_mean"]==first["noisy_mean"]
    assert again.json()["share_token"]==first["share_token"]
    with SessionLocal() as db:
        assert budget(db,first["source"])["spent"]==pytest.approx(.25)
        assert db.query(DPRelease).count()==1


def test_release_id_conflict_on_different_content(client):
    sid=make_study()
    headers=login(client)
    client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-4","epsilon":.25},headers=headers)
    conflict=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-4","epsilon":.3},headers=headers)
    assert conflict.status_code==409
    other_sid=make_study(code="DC-02")
    conflict=client.post(f"/studies/{other_sid}/dp-releases",json={"release_id":"REL-4","epsilon":.25},headers=headers)
    assert conflict.status_code==409
    with SessionLocal() as db:
        assert db.query(DPRelease).count()==1
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(.25)


def test_epsilon_validation_and_micro_floor(client):
    sid=make_study()
    headers=login(client)
    for bad in (0,-.1,1.5,"nan","inf"):
        assert client.post(f"/studies/{sid}/dp-releases",json={"release_id":"X","epsilon":bad},headers=headers).status_code==422
    assert dp_service.epsilon_micro(1e-6)==1
    assert dp_service.epsilon_micro(.0000015)==2
    assert dp_service.epsilon_micro(.1)==100000
    assert dp_service.epsilon_micro(Decimal("0.1"))==100000
    with pytest.raises(HTTPException) as err:dp_service.epsilon_micro(4e-7)
    assert err.value.status_code==422
    with pytest.raises(HTTPException) as err:dp_service.epsilon_micro(1.0000001)
    assert err.value.status_code==422


def test_release_endpoint_rejects_small_study_unknown_study_and_bad_ids(client):
    small=make_study(code="DC-08",rates=[.5]*7)
    headers=login(client)
    assert client.post(f"/studies/{small}/dp-releases",json={"release_id":"SMALL","epsilon":.1},headers=headers).status_code==422
    assert client.post("/studies/9999/dp-releases",json={"release_id":"NOPE","epsilon":.1},headers=headers).status_code==404
    assert client.post(f"/studies/{small}/dp-releases",json={"release_id":"bad id!","epsilon":.1},headers=headers).status_code==422
    assert client.post(f"/studies/{small}/dp-releases",json={"release_id":"OK","epsilon":.1,"extra":1},headers=headers).status_code==422
    assert client.get(f"/studies/{small}/dp-releases").status_code==401
    assert client.get("/dp-budgets").status_code==401


def test_publish_records_audit_entry(client):
    sid=make_study()
    headers=login(client)
    client.post(f"/studies/{sid}/dp-releases",json={"release_id":"AUD-1","epsilon":.2},headers=headers)
    audits=client.get("/audits",headers=headers).json()
    assert any(a["action"]=="dp.release" and a["target"]=="AUD-1" for a in audits)


def test_viewer_cannot_publish(client):
    sid=make_study()
    assert client.post(f"/studies/{sid}/dp-releases",json={"release_id":"REL-V","epsilon":.1},headers=login(client,"viewer")).status_code==403


# -------------------------------------------------------------------- budget
def test_budget_cap_per_source_and_snapshot_never_resets(client):
    sid_a=make_study(code="DC-10",source="shared-source.csv")
    sid_b=make_study(code="DC-11",source="shared-source.csv")
    headers=login(client)
    assert client.post(f"/studies/{sid_a}/dp-releases",json={"release_id":"A1","epsilon":.6},headers=headers).status_code==201
    assert client.post(f"/studies/{sid_b}/dp-releases",json={"release_id":"B1","epsilon":.4},headers=headers).status_code==201
    exhausted=client.post(f"/studies/{sid_b}/dp-releases",json={"release_id":"B2","epsilon":.000001},headers=headers)
    assert exhausted.status_code==429
    with SessionLocal() as db:
        assert budget(db,"shared-source.csv")["spent"]==pytest.approx(1.0)
        assert db.query(DPRelease).count()==2
    # a fresh snapshot (adding batches) must not reset the ledger
    with SessionLocal() as db:
        from src.models import SeedLot,LotCount,GerminationStudy
        s=db.get(GerminationStudy,sid_a);lot=SeedLot(study_id=s.id,code="DC-10-L99",name="新批次",origin="测试");db.add(lot);db.flush();db.add(LotCount(lot_id=lot.id,n=100,k=50,note="测试计数"));db.commit()
    still=client.post(f"/studies/{sid_a}/dp-releases",json={"release_id":"A3","epsilon":.01},headers=headers)
    assert still.status_code==429


def test_budget_is_isolated_per_source(client):
    sid_a=make_study(code="DC-20",source="source-a.csv")
    sid_b=make_study(code="DC-21",source="source-b.csv")
    headers=login(client)
    assert client.post(f"/studies/{sid_a}/dp-releases",json={"release_id":"SA","epsilon":1},headers=headers).status_code==201
    assert client.post(f"/studies/{sid_b}/dp-releases",json={"release_id":"SB","epsilon":1},headers=headers).status_code==201
    with SessionLocal() as db:
        assert budget(db,"source-a.csv")["remaining"]==pytest.approx(0)
        assert budget(db,"source-b.csv")["remaining"]==pytest.approx(0)
    assert client.post(f"/studies/{sid_b}/dp-releases",json={"release_id":"SB2","epsilon":.5},headers=headers).status_code==429


def test_failure_before_charge_leaves_budget_untouched(client,monkeypatch):
    sid=make_study()
    headers=login(client)
    def boom(*a,**k):raise RuntimeError("抽样失败")
    monkeypatch.setattr(dp_service,"laplace_noise",boom)
    assert client.post(f"/studies/{sid}/dp-releases",json={"release_id":"F1","epsilon":.5},headers=headers).status_code==500
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(0)
        assert db.query(DPRelease).count()==0


def test_failure_after_charge_rolls_back_both(client,monkeypatch):
    sid=make_study()
    headers=login(client)
    def fail_commit(db):
        raise RuntimeError("提交失败")
    monkeypatch.setattr("src.services.dp_service._commit",fail_commit)
    assert client.post(f"/studies/{sid}/dp-releases",json={"release_id":"F2","epsilon":.5},headers=headers).status_code==500
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(0)
        assert db.query(DPRelease).count()==0


def test_race_with_competing_release_replays_or_conflicts_without_double_charge(client,monkeypatch):
    """A competing writer wins between our charge and insert: never charge twice."""
    import src.services.dp_service as svc
    from src.models import GerminationStudy
    from src.schemas.dp import ReleaseInput
    sid=make_study()
    headers=login(client)
    real_charge=svc._charge
    state={"raced":False}

    def charge_then_race(db,source,cost):
        remaining=real_charge(db,source,cost)
        if remaining is None and not state["raced"]:
            state["raced"]=True
            # a second publisher with the same release id commits first (same fingerprint)
            db.rollback()
            other=SessionLocal()
            dp_service.publish(other,other.get(GerminationStudy,sid),ReleaseInput(release_id="RACE",epsilon=.5),type("U",(),{"email":"other@test.demo"})())
            other.close()
            raise svc.IntegrityError("stmt",{},Exception("race"))
        return remaining
    monkeypatch.setattr(svc,"_charge",charge_then_race)
    r=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"RACE","epsilon":.5},headers=headers)
    assert r.status_code==201,r.text
    with SessionLocal() as db:
        assert db.query(DPRelease).count()==1
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(.5)


def test_race_with_different_content_is_conflict(client,monkeypatch):
    import src.services.dp_service as svc
    sid=make_study()
    headers=login(client)
    client.post(f"/studies/{sid}/dp-releases",json={"release_id":"DUP","epsilon":.25},headers=headers)
    with SessionLocal() as db:
        before=budget(db,"duocen-germination-lots-202611.csv")["spent"]
    r=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"DUP","epsilon":.5},headers=headers)
    assert r.status_code==409
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(before)


def test_budget_endpoint_reports_ledger(client):
    sid=make_study()
    headers=login(client)
    client.post(f"/studies/{sid}/dp-releases",json={"release_id":"L1","epsilon":.3},headers=headers)
    body=client.get("/dp-budgets",headers=headers).json()
    assert body==[{"source":"duocen-germination-lots-202611.csv","total":1.0,"spent":pytest.approx(.3),"remaining":pytest.approx(.7),"releases":1}]


# ---------------------------------------------------------------- concurrency
def test_concurrent_charges_never_exceed_cap(client):
    """Eight parallel requests of eps=.2 must admit exactly five."""
    from concurrent.futures import ThreadPoolExecutor
    sid=make_study()
    headers=login(client)
    def fire(i):
        return client.post(f"/studies/{sid}/dp-releases",json={"release_id":f"C{i}","epsilon":.2},headers=headers).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes=list(pool.map(fire,range(8)))
    assert codes.count(201)==5,codes
    assert codes.count(429)==3,codes
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(1.0)
        assert db.query(DPRelease).count()==5


def test_concurrent_same_release_id_charges_once(client):
    from concurrent.futures import ThreadPoolExecutor
    sid=make_study()
    headers=login(client)
    def fire(i):
        return client.post(f"/studies/{sid}/dp-releases",json={"release_id":"SAME","epsilon":.5},headers=headers)
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(fire,range(6)))
    successes=[r for r in responses if r.status_code==201]
    assert successes
    assert len({r.json()["noisy_mean"] for r in successes})==1
    with SessionLocal() as db:
        assert db.query(DPRelease).count()==1
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(.5)


def test_simulated_worker_crash_between_charge_and_commit():
    """Charge then rollback (crash) must leave neither spend nor release."""
    make_study()
    with SessionLocal() as db:
        dp_service._ensure_budget(db,"duocen-germination-lots-202611.csv")
        dp_service._charge(db,"duocen-germination-lots-202611.csv",400000)
        db.rollback()
    with SessionLocal() as db:
        assert budget(db,"duocen-germination-lots-202611.csv")["spent"]==pytest.approx(0)
        assert db.query(DPRelease).count()==0


# ------------------------------------------------------------------ integrity
def test_published_record_contains_no_raw_counts_or_lot_codes(client):
    rates=[.11,.23,.37,.41,.53,.67,.79,.83,.97,.07,.19,.29]
    sid=make_study(rates=rates)
    headers=login(client)
    body=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"SAN-1","epsilon":.5},headers=headers).json()
    published=client.get(body["shared_path"]).json()
    assert set(published)=={"release_id","share_token","shared_path","study_code","epsilon","sensitivity","mechanism","noise_scale","noisy_mean","created_at","version","budget","statistic","neighbor","bound","note"}
    text=json.dumps(published,ensure_ascii=False)
    for lot in range(1,13):
        assert f"DC-01-L{lot:02d}" not in text
    assert "raw_rate" not in text and "post_alpha" not in text and "fit" not in text
    assert published["noisy_mean"]==body["noisy_mean"]
    with SessionLocal() as db:
        assert db.query(DPRelease).count()==1
        row=db.query(DPRelease).one()
        assert not any(hasattr(row,name) for name in ("lots","counts","raw_rate","alpha","beta","batch_count"))


def test_release_persists_epsilon_and_sensitivity(client):
    sid=make_study()
    headers=login(client)
    out=client.post(f"/studies/{sid}/dp-releases",json={"release_id":"P1","epsilon":.125},headers=headers).json()
    with SessionLocal() as db:
        row=db.query(DPRelease).filter_by(release_id="P1").one()
        assert row.epsilon_micro==125000
        assert row.sensitivity==pytest.approx(1/9)
        assert row.noise_scale==pytest.approx((1/9)/.125)
    internal=client.get(f"/studies/{sid}/dp-releases",headers=headers).json()
    assert internal[0]["study_id"]==sid
    shared=client.get(out["shared_path"]).json()
    assert "study_id" not in shared
