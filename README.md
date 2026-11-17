# 铎岑种子萌发批次概率册

以独立批次的萌发数k/试种数n拟合有界Beta-Binomial经验贝叶斯先验，读取条件收缩、区间、阈值概率和同批下一轮计数预测。

铎岑种质试验室有14位批次分析员。上游 `duocen-germination-lots-202611.csv` 是各批独立试种汇总；过去直接比较小批0/1比例、忽略批间差异、把拟合先验当成已知真相。本系统替代跨批率估计与补种研究归档，下游由种质负责人批准独立补种计划，阅读者下载获批汇总/预测PMF。全部是合成研究，不执行真实补种、种子合格判定或自动发货。

## 启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

可在含中文和空格的路径运行。前端 http://localhost:18236 ，API文档 http://localhost:19236/docs ，PostgreSQL localhost:17736。恰好frontend/backend/worker/db/redis五服务，均有健康检查；后端与worker等待数据库/Redis、前端等待后端。Nginx `/api/` 去前缀代理。数据库、Redis队列与backend/worker共享完整结果JSON分别使用命名卷。

| 角色 | 账号 | 密码 | 页面与权限 |
|---|---|---|---|
| admin 种质负责人 | admin@duocen.demo | Duocen2026! | 七页；批注、创建研究、提交、批准/退回、DP发布 |
| analyst 批次分析员 | analyst@duocen.demo | Duocen2026! | 七页；核对n/k、创建研究、计数批注、补种说明、DP发布 |
| viewer 抽样阅读者 | viewer@duocen.demo | Duocen2026! | 七页只读；获批后下载汇总及完整预测PMF CSV；共享页匿名可读 |

JWT角色后端真实执行，viewer写入403、analyst审批403、未批准导出403，已审阅建议不可重复审批。登录/计数批注/排队/worker完成/建议和审批写审计；登录IP每分钟最多30次。另有全局异常中间件，422校验handler只返回loc/msg文本，不回显NaN/Inf input，避免错误响应序列化成500。部署前修改JWT_SECRET及Compose内数据库口令。

## 一天的研究剧本

1. 09:00 许禾登录，打开 `DC-01`“异质批次 · 萌发观察”，核对28个独立批次，每批一条n/k，n20–180。
2. 09:05 选 `DC-01-L01`，看到58/68，原始率85.3%；给计数保留下一轮独立试种批注。
3. 09:10 查看 `DC-03` 全零边界，系统拒绝估计先验；全一或少于8批也拒绝。
4. 09:15 新建“异质批次条件EB”，研究阈值.7、同批下一轮20粒。形状界[.01,5000]与10个起点固定，阈值和未来m不参与先验拟合。
5. 09:16 worker实际多起点优化边际似然。真实主运行得到α≈8.510929815、β≈3.425220221，10/10起点通过检查，投影梯度范数约6.55e−10；这是测试起点中的最佳合格结果，不是全局最优证明。
6. 09:20 L01条件后验均值约83.2%，95%等尾区间约.7433–.9051、数据权重约85.1%；同批未来20粒条件均值约16.641、方差约3.451。
7. 09:25 切换 `DC-02` 同观测率夹具：所有批70/100，α真实触及5000上界，界面标弱识别；不把窄条件区间当成稳定已知先验。
8. 10:00 陆岑批准独立补种研究，温桥下载 `germination-N-summary.csv` 和 `germination-N-predictive.csv`，按相同n/k口径另做独立试种。

## 七页、五实体与seed

批次总览、计数来源、先验与情景、条件后验、补种审阅、研究留痕、隐私发布（另有免登录的 `/shared/releases/{token}` 匿名共享页）。`GerminationStudy / SeedLot / LotCount / BayesRun / SamplingNote` 均贯穿表/model/schema/service/route/前端API/store/页面或业务组件，另有User/Audit。批次身份与n/k只读核对，计数批注可写，运行冻结快照后不回写。

三研究×28=84批次、84计数：DC-01潜在率Beta(8,4)再Binomial抽样（固定种子320）；DC-02全部70/100为人工构造的同观测率上界夹具，不冒充随机抽样；DC-03固定种子322生成n、k全部0，全一另外有独立算法拒绝验证。每批n20–180。自然键email、study code、(study,lot code)、lot_id唯一计数、基线run name；重复seed只补缺失，不覆盖用户批注、计数或已批准建议。`SEED_DEMO=true`启动执行，失败记日志；可独立重复执行seed。

共享RunSummary在首页/结果/审阅复用，ShrinkageChart在首页/结果复用；另有StudySelector、PosteriorChart、PredictiveChart及通用Notice/DataTable/StatusBadge。useResearch/useAction处理公共状态。全部数值、CDF与PMF在Python计算，SVG只映射真实结果。

## 有界多起点边际拟合

工作模型：各批 `k_j | p_j ~ Binomial(n_j,p_j)`，批率独立 `p_j ~ Beta(α,β)`。只把它作为研究模型，不当已验证种子性能真相。各批一条完整整数计数，1≤n≤100000、0≤k≤n，不接受布尔/小数，拟合8–200批；全部0或全部1拒绝估计先验。

```text
log L = Σ[log C(n,k) + log B(α+k, β+n−k) − log B(α,β)]
x=log α, y=log β，各自界为log(.01)..log(5000)
∂logL/∂x = α Σ[ψ(k+α)−ψ(n+α+β)−ψ(α)+ψ(α+β)]
∂logL/∂y = β Σ[ψ(n−k+β)−ψ(n+α+β)−ψ(β)+ψ(α+β)]
```

Beta-Binomial PMF口径见[SciPy官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html)。代码使用betaln/gammaln与解析log形状梯度，最小化负logL。六个固定起点(1,1)/(2,2)/(8,4)/(.2,.2)/(1,8)/(8,1)，另四个按平滑合并率仅用于初始化、总浓度2/20/200/5000的起点；初始化平滑不加入似然伪数据。

L-BFGS-B设置maxiter2000/maxls50/gtol1e−8/ftol1e−13，全部起点保存初末形状、logL、状态、迭代/评估、原始目标梯度与投影梯度。只有优化器成功、目标/梯度有限且投影∞范数≤1e−4才接受，再选接受点中LL最高。边界的不可行下降方向投影为0，与[L-BFGS-B官方停止定义](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.fmin_l_bfgs_b.html)一致；投影为0不消除贴边弱识别。形状接近边界或更高目标候选未收敛时标弱识别，绝不声称全局最优或稳定已知先验。物理报告形状最后裁到[.01,5000]，避免exp(log5000)的机器舍入超出数个ULP。

当前DC-02真实拟合α=5000、β≈2143.357，5/10起点合格、alpha:upper，弱识别警示可见。原始负LL logshape梯度α方向非零而边界投影为0，诊断同时保留。

## 条件后验与同批预测

条件于点估αβ，单批k/n的后验为 `Beta(a=α+k,b=β+n−k)`，均值a/(a+b)，95%等尾分位[.025,.975]，阈值尾概率用Beta SF计算Pr(p>阈值)。收缩数据权重n/(n+α+β)，先验权重为其余；估计先验均值不是简单合并比例。

同批下一轮m粒（1–200）的计数为Beta-Binomial(m,a,b)：

```text
P(K=j) = C(m,j) B(a+j,b+m−j)/B(a,b), j=0..m
E[K] = m*a/(a+b)
Var[K] = m*a*b*(a+b+m)/((a+b)^2*(a+b+1))
```

用log PMF与logsumexp覆盖全部0..m，保存归一前质量/误差；只有误差≤1e−7才对浮点微差归一。CDF存201个概率点，避免直接密度端点可能无界；它是展示网格，区间与尾概率由分布函数实算。阈值/未来m变化不改变先验拟合，输入hash变化但fit_hash不变。

这些区间、阈值概率和未来计数**都条件于点估超参数**，不包含αβ估计误差，不是完整层级贝叶斯区间、频率覆盖保证、种子合格概率或自动发货依据。估计先验使用这些批次（包含本批），不冒充独立已知先验；未来预测针对同一批次，不是全新未知批。

## 批级差分隐私发布

对外共享萌发统计不再直接暴露单批数据。`POST /studies/{sid}/dp-releases` 以**增删一个完整批次（lot）**为邻接，发布各批原始率 `k_j/n_j` 的**等权均值**；批次数属于保密内容，因此均值用数据相关分母，不发布批次数。

**敏感度。** 相邻数据集分别有 m 与 m−1 批；两侧都必须≥8批才可发布，故 m≥9。设共享 m−1 批的率之和为 S、被增删批次的率为 r∈[0,1]：

```text
|mean(D) − mean(D')| = |r/m − S/(m(m−1))| ≤ max(1/m, 1/m) = 1/m ≤ 1/9
```

故全局 L1 敏感度 Δ=1/(8+1)=1/9，与具体批次数无关；这正是批次数保密时噪声均值仍成立的依据。上界在“8个全零批 + 1个全一/全零批”处取到。注意 m=8 时删批会得到 7 批的邻居，不可发布，所以 1/8 不在邻接域内。

**机制。** Laplace(scale=Δ/ε)，噪声由 `secrets` 抽取的均匀数生成；发布值裁剪到[0,1]，裁剪是后处理，不削弱保证。每次调用自选正 ε（量化到 1e-6 整数单位并向上取整，保证扣费不低于实际噪声），单次上限 1。

**预算。** 每个数据来源（`GerminationStudy.source`）一个账本 `dp_budgets`，累计上限 1；同一来源下所有研究共用，**换快照、加批次、换研究都不重置**。扣费使用带条件的原子 UPDATE（`spent+cost≤total`），并发请求不会超额；耗尽后返回 429 并拒绝新发布。扣费、发布行与审计记录在**同一事务**提交，故障或中断时同成同败：要么预算与结果都落库，要么都不落库。

**幂等与冲突。** `release_id` 全局唯一。重试同一发布号且内容指纹（release_id、来源、研究、ε、逐批 n/k）一致时，直接返回**原噪声结果**与同一共享 token，不再扣费、不再重新抽噪；同号异内容返回 409。并发同号由唯一约束裁决：败者回滚后读到胜者结果并重放，不会二次扣费。

**公开面。** `GET /shared/releases/{token}` 无需登录即可读取，只含研究编号、噪声均值、ε、Δ、噪声尺度、机制、账本剩余与说明文字；**不含原始 n/k、批次数、批号、上游来源文件名、点估 α/β 或任何拟合参数**，也不含 study_id、内容指纹等内部字段（这些只在登录后的内部列表可见）。内部研究、条件后验、导出与审批流程完全照常，不受影响。

**测试。** `backend/requirements-dev.txt` 后运行 `cd backend && python -m pytest tests -q`，覆盖邻接敏感度（两方向、多批次穷举与取界构造）、最小批次数拒绝、Laplace 对称性与尺度、公开页字段白名单、重试重放、同号异内容 409、并发扣费恰好不超 1、并发同号只扣一次、扣费前/扣费后/提交时故障回滚、重复读取稳定、耗尽后仍可读取旧发布、少于8批/未知研究/非法发布号拒绝、审计留痕等 27 项。

组合上，同一来源多次发布按 ε 顺序累加（basic composition），因此总预算 1 是端到端的隐私上限；单次发布不能外推为多次独立保证。

## 开发与工程

React18.3/ReactRouter7.18.5/TypeScript5.7/Vite6.4.6；Python3.11/FastAPI0.115/SQLAlchemy2/NumPy2.2/SciPy1.15；PostgreSQL16/Redis7/Nginx1.27。

```sh
# backend，先准备PostgreSQL/Redis并设置DATABASE_URL、REDIS_URL
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest/httpx，仅测试需要
python -m pytest tests -q
uvicorn src.main:app --reload --port 8000
# 另开终端在backend启动worker；需可写/artifacts，推荐Compose
python -m src.worker
# 前端从项目根进入frontend，Vite代理/api到localhost:8000
cd ../frontend
npm ci
npm run dev
```

backend/src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}按来源、边际拟合、后验、运行、审阅拆分；backend/scripts/seed_demo.py；migration为可选索引，metadata首次建表，非独立全量DDL。frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}为React应用。

角色枚举backend/constants/roles与frontend/constants/enums用于鉴权/显示，队列状态backend/constants/status与前端RunStatus用于worker/StatusBadge，审阅Literal在backend/schemas/note与model/service/前端ReviewStatus。环境变量COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET、SEED_DEMO在.env；DATABASE_URL/REDIS_URL由Compose定义。

测试脚本、真实截图、关键JSON/CSV与已知差异在同批test-artifacts/gb-0032/TESTING.md，源码不放日志或截图。当前单worker，无来源上传、崩溃恢复、多worker去重或设备操作。清理仅本题：`docker compose down -v --remove-orphans`。MIT License。
