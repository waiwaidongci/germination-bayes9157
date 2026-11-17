import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

_tmp=tempfile.mkdtemp(prefix="dp-tests-")
os.environ["DATABASE_URL"]=f"sqlite+pysqlite:///{_tmp}/test.db?timeout=30"
os.environ["SEED_DEMO"]="false"
os.environ["JWT_SECRET"]="test-secret"

import pytest
from fastapi.testclient import TestClient

from src.config.database import Base,SessionLocal,engine
from src.main import app
from src.models import User
from src.utils.security import hash_password
from src.services import dp_service


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with SessionLocal() as db:
        for role in ("admin","analyst","viewer"):
            db.add(User(email=f"{role}@test.demo",name={"admin":"陆岑","analyst":"许禾","viewer":"温桥"}[role],role=role,password_hash=hash_password("Duocen2026!")))
        db.commit()
    with TestClient(app) as c:
        yield c


def login(client,role="analyst"):
    r=client.post("/auth/login",json={"email":f"{role}@test.demo","password":"Duocen2026!"})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}


def make_study(code="DC-01",source="duocen-germination-lots-202611.csv",batches=12,rates=None):
    if rates is None:rates=[(i+1)/(batches+2) for i in range(batches)]
    with SessionLocal() as db:
        from src.models import GerminationStudy,SeedLot,LotCount
        study=GerminationStudy(code=code,name=code,description="测试",source=source)
        db.add(study);db.flush()
        for i,rate in enumerate(rates):
            n=100;k=int(round(rate*n))
            lot=SeedLot(study_id=study.id,code=f"{code}-L{i+1:02}",name=f"批次{i+1}",origin="测试")
            db.add(lot);db.flush();db.add(LotCount(lot_id=lot.id,n=n,k=k,note="测试计数"))
        db.commit()
        return study.id


def budget(db,source):
    return dp_service.budget_summary(db,source)
