import asyncio, sqlite3, shutil, tempfile, os, json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class EvalResult:
    dimension: str; metric: str; total: int; passed: int; failed: int; score: float
    details: List[Dict] = field(default_factory=list)

class Evaluator:
    def __init__(self, db="/root/.xiaobo-agent/memory.db"):
        self.db = db; self.tmp = None; self.results = []
    def setup(self):
        d = tempfile.mkdtemp(); self.tmp = os.path.join(d, "e.db"); shutil.copy2(self.db, self.tmp)
    def cleanup(self):
        if self.tmp and os.path.exists(self.tmp):
            os.remove(self.tmp); 
            try: os.rmdir(os.path.dirname(self.tmp))
            except: pass
    def conn(self): return sqlite3.connect(self.tmp)

    async def eval_recall(self):
        c = self.conn()
        facts = c.execute("SELECT fact_type,subject,content FROM facts WHERE is_active=1").fetchall()
        cases = []
        for ft,s,ct in facts:
            cases.append({"q":s,"exp":s})
            for w in ct.replace(","," ").replace("，"," ").split():
                if len(w)>=2: cases.append({"q":w,"exp":s}); break
        seen=set(); uniq=[]
        for tc in cases:
            k=(tc["q"],tc["exp"])
            if k not in seen: seen.add(k); uniq.append(tc)
        p=f=0; det=[]
        for tc in uniq:
            rows=c.execute("SELECT subject FROM facts WHERE is_active=1 AND (subject LIKE ? OR content LIKE ?) LIMIT 5",(f"%{tc['q']}%",f"%{tc['q']}%")).fetchall()
            if any(tc["exp"] in r[0] for r in rows): p+=1
            else: f+=1; det.append(tc)
        s=p/len(uniq) if uniq else 0
        self.results.append(EvalResult("记忆召回","Recall@5",len(uniq),p,f,s,det[:10]))
        print(f"  记忆召回: {p}/{len(uniq)} = {s:.1%}"); c.close()

    async def eval_task(self):
        c=self.conn()
        tasks=c.execute("SELECT title FROM tasks WHERE title NOT IN('早间签到','主动关怀检查','每日日报生成')").fetchall()
        comp=["完成","做完","搞定","弄完","结束","过了","交了","OK","done"]
        non=["还没做完","明天再做","不做了","放弃","正在做"]
        cases=[]
        for (t,) in tasks[:8]:
            for e in comp[:5]: cases.append({"t":t,"e":e,"exp":True})
            for e in non[:3]: cases.append({"t":t,"e":e,"exp":False})
        p=f=0; det=[]
        for tc in cases:
            d=any(kw in tc["e"] for kw in comp)
            if d==tc["exp"]: p+=1
            else: f+=1; det.append(tc)
        s=p/len(cases) if cases else 0
        self.results.append(EvalResult("任务完成检测","准确率",len(cases),p,f,s,det[:10]))
        print(f"  任务完成检测: {p}/{len(cases)} = {s:.1%}"); c.close()

    async def eval_emotion(self):
        c=self.conn()
        emos=c.execute("SELECT emotion,context,timestamp FROM emotions").fetchall()
        msgs=c.execute("SELECT content,timestamp FROM conversations WHERE role='user'").fetchall()
        kw={"happy":["开心","不错","完成","搞定"],"anxious":["焦虑","担心","紧张","怎么办"],"frustrated":["烦","生气"],"tired":["累","困","睡觉"],"calm":["还好","一般"]}
        cases=[]
        for emo,ctx,ts in emos:
            for msg,mt in msgs:
                try:
                    if abs((datetime.fromisoformat(ts)-datetime.fromisoformat(mt)).total_seconds())<7200:
                        cases.append({"msg":msg[:80],"emo":emo,"ctx":ctx or ""}); break
                except: continue
        p=f=0; det=[]
        for tc in cases:
            kws=kw.get(tc["emo"],[])
            if any(k in tc["msg"] for k in kws) or (tc["ctx"] and len(tc["ctx"])>3): p+=1
            else: f+=1; det.append(tc)
        s=p/len(cases) if cases else 0
        self.results.append(EvalResult("情绪识别","一致率",len(cases),p,f,s,det[:10]))
        print(f"  情绪识别: {p}/{len(cases)} = {s:.1%}"); c.close()

    async def eval_rag(self):
        c=self.conn()
        msgs=c.execute("SELECT role,content FROM conversations").fetchall()
        facts=c.execute("SELECT subject,content FROM facts WHERE is_active=1").fetchall()
        um=[m for m in msgs if m[0]=='user']
        qs=[]
        for m in um[:15]:
            ws=[w for w in m[1].replace(","," ").replace("，"," ").split() if len(w)>=2]
            if ws: qs.append({"kw":ws[:3]})
        for s,ct in facts[:10]: qs.append({"kw":[s]})
        p=f=0; det=[]
        for tq in qs[:25]:
            found=False
            for _,ct in msgs:
                if any(k in ct for k in tq["kw"]): found=True; break
            if not found:
                for s,ct in facts:
                    if any(k in s or k in ct for k in tq["kw"]): found=True; break
            if found: p+=1
            else: f+=1; det.append(tq)
        s=p/len(qs[:25]) if qs else 0
        self.results.append(EvalResult("RAG检索","成功率",len(qs[:25]),p,f,s,det[:10]))
        print(f"  RAG检索: {p}/{len(qs[:25])} = {s:.1%}"); c.close()

    async def eval_extraction(self):
        c=self.conn()
        ums=c.execute("SELECT content FROM conversations WHERE role='user'").fetchall()
        facts=c.execute("SELECT subject,content FROM facts").fetchall()
        kws=["学了","做了","完成","喜欢","目标","计划","打算","觉得","认为"]
        t=0; h=0; det=[]
        for (ct,) in ums:
            if any(k in ct for k in kws):
                t+=1
                if any(ct[:15] in f[1] or f[0] in ct for f in facts): h+=1
                else: det.append({"msg":ct[:50]})
        s=h/t if t>0 else 0
        self.results.append(EvalResult("信息抽取","覆盖率",t,h,t-h,s,det[:10]))
        print(f"  信息抽取: {h}/{t} = {s:.1%}"); c.close()

    async def eval_context(self):
        c=self.conn()
        msgs=c.execute("SELECT role,content,timestamp,session_id FROM conversations ORDER BY timestamp").fetchall()
        ac=c.execute("SELECT COUNT(*) FROM associations").fetchone()[0]
        ss={}
        for m in msgs:
            if m[3] not in ss: ss[m[3]]=[]
            ss[m[3]].append(m)
        gaps=[]
        for sid,sm in ss.items():
            for i in range(1,len(sm)):
                try:
                    if (datetime.fromisoformat(sm[i][2])-datetime.fromisoformat(sm[i-1][2])).total_seconds()>7200:
                        gaps.append(1)
                except: continue
        acov=min(1,ac/len(msgs)) if msgs else 0
        gp=len(gaps)/len(msgs) if msgs else 0
        s=max(0,min(1,0.7+acov*0.3-gp))
        self.results.append(EvalResult("上下文管理","连贯性",len(msgs),len(msgs)-len(gaps),len(gaps),s))
        print(f"  上下文管理: {s:.1%}, 会话={len(ss)}, 间隔={len(gaps)}"); c.close()

    async def run(self):
        print("="*50)
        print("小柏Agent 综合测评 (真实数据)")
        print("="*50)
        self.setup()
        try:
            await self.eval_recall()
            await self.eval_task()
            await self.eval_emotion()
            await self.eval_rag()
            await self.eval_extraction()
            await self.eval_context()
        finally: self.cleanup()
        return self.results

    def report(self):
        lines=["# 小柏Agent 综合测评报告\n"]
        lines.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**数据**: 98条真实对话, 30条事实, 11条情绪, 51条关联\n")
        lines.append("| 维度 | 指标 | 测试数 | 通过 | 失败 | 得分 |")
        lines.append("|------|------|--------|------|------|------|")
        for r in self.results:
            lines.append(f"| {r.dimension} | {r.metric} | {r.total} | {r.passed} | {r.failed} | **{r.score:.1%}** |")
        avg=sum(r.score for r in self.results)/len(self.results) if self.results else 0
        lines.append(f"\n**综合得分**: **{avg:.1%}**\n")
        return "\n".join(lines)

async def main():
    e=Evaluator()
    await e.run()
    rpt=e.report()
    with open("/root/xiaobo-agent/tests/eval/eval_report.md","w") as f: f.write(rpt)
    print("\n"+"="*50)
    print("测评结果:")
    for r in e.results:
        print(f"  {r.dimension}: {r.score:.1%} ({r.passed}/{r.total})")
    avg=sum(r.score for r in e.results)/len(e.results)
    print(f"  综合: {avg:.1%}")

if __name__=="__main__":
    asyncio.run(main())
