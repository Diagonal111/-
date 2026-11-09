"""Deterministic, explainable MVP scheduling. No model calls in state updates."""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from .store import TZ, today, question_dict

INTERVALS = [1, 3, 7, 14, 30, 60]
SUBJECTS = ['数据结构', '计算机组成原理', '操作系统', '计算机网络']
RESULTS = {'correct': 1, 'partial': 0.5, 'incorrect': 0}


def local_day(value):
    return datetime.fromisoformat(value).astimezone(TZ).date()


def derive_state(db, day=None):
    day = day or today()
    knowledge = {r['id']: dict(r) for r in db.execute('SELECT * FROM knowledge')}
    questions = {r['id']: question_dict(r) for r in db.execute('SELECT * FROM questions')}
    for k in knowledge.values():
        k.update(alpha=1.0, beta=1.0, evidence=0.0, attempts=0, due_count=0, question_count=0,
                 last_practiced=None, recent_error=None)
    reviews = {}
    repetitions = defaultdict(int)
    attempts = [dict(r) for r in db.execute("SELECT * FROM attempts WHERE status='confirmed' ORDER BY created_at,id")]
    for a in attempts:
        current = questions.get(a['question_id'])
        q = json.loads(a.get('question_snapshot') or '{}') or current
        if not q or a['grade'] not in RESULTS or not q['verified']:
            continue
        k = knowledge[q['knowledge_id']]
        effective = local_day(a['created_at'])
        key = (q['id'], effective)
        weight = [1.0, 0.2, 0.0][min(2, repetitions[key])] * (0.25 if a['hinted'] else 1.0)
        repetitions[key] += 1
        r = RESULTS[a['grade']]
        k['alpha'] += weight * r
        k['beta'] += weight * (1-r)
        k['evidence'] += weight
        k['attempts'] += 1
        k['last_practiced'] = effective.isoformat()
        if r < 1:
            k['recent_error'] = effective.isoformat()
        # Historical evidence remains attributed to the knowledge point at the time.
        # A revised question starts a fresh review schedule, never a silent regrade.
        if current and q.get('revision',1)!=current.get('revision',1):
            continue
        prev = reviews.get(q['id'])
        stage = prev['stage'] if prev else 0
        # Early repetitions do not increase or postpone the current interval.
        failure = a['grade'] != 'correct' or bool(a['hinted'])
        if failure:
            stage = 0
            next_date = effective + timedelta(days=1)
            last_review = effective
        elif not prev:
            next_date = effective + timedelta(days=1)
            last_review = effective
        elif (effective - date.fromisoformat(prev['last_review'])).days >= 0.8 * INTERVALS[stage]:
            stage = min(stage+1, len(INTERVALS)-1)
            next_date = effective + timedelta(days=INTERVALS[stage])
            last_review = effective
        else:
            next_date = date.fromisoformat(prev['due_date'])
            last_review = date.fromisoformat(prev['last_review'])
        had_error = bool(prev and prev['had_error']) or a['grade'] != 'correct'
        success_days = list(prev['success_days']) if prev else []
        long_success = bool(prev and prev['long_success'])
        if failure:
            success_days = []
            long_success = False
        else:
            if effective.isoformat() not in success_days:
                success_days.append(effective.isoformat())
            if prev and INTERVALS[prev['stage']] >= 7 and last_review == effective:
                long_success = True
        stable = len(success_days) >= 3 and long_success
        reviews[q['id']] = {
            'stage': stage, 'interval': INTERVALS[stage], 'due_date': next_date.isoformat(),
            'last_attempt_day':effective.isoformat(),'last_hinted':bool(a['hinted']),
            'last_review': last_review.isoformat(), 'last_grade': a['grade'], 'had_error': had_error,
            'success_days': success_days, 'long_success': long_success,
            'mistake_status': ('已稳定' if stable else '待订正' if a['grade']=='incorrect' else '待复习' if failure else '巩固中') if had_error else None,
            'attempt_count': (prev['attempt_count'] if prev else 0)+1,
        }
    for q in questions.values():
        k = knowledge[q['knowledge_id']]
        k['question_count'] += 1
        if q['id'] in reviews and reviews[q['id']]['due_date'] <= day.isoformat():
            k['due_count'] += 1
    for k in knowledge.values():
        k['mastery'] = round(k['alpha']/(k['alpha']+k['beta'])*100)
        k['evidence'] = round(k['evidence'], 2)
        k['status'] = '待评估' if k['evidence']==0 else '证据较少' if k['evidence']<3 else '需加强' if k['mastery']<50 else '巩固中' if k['mastery']<75 else '较熟练'
    return knowledge, questions, reviews, attempts


def candidates(db, day=None):
    day = day or today()
    knowledge, questions, reviews, _ = derive_state(db, day)
    result = []
    for q in questions.values():
        if not q['verified']:
            continue
        k = knowledge[q['knowledge_id']]
        review = reviews.get(q['id'])
        if review and review['last_attempt_day']==day.isoformat() and review['last_grade']=='correct' and not review['last_hinted']:
            continue
        reasons = []
        if review:
            due = date.fromisoformat(review['due_date'])
            overdue = (day-due).days
            if overdue >= 0:
                d = min(1, 0.7+0.3*overdue/max(1,review['interval']))
                reasons.append(f'已逾期 {overdue} 天' if overdue else '今天到复习日')
                category = 'review'
            else:
                d = max(0, min(.5, .5*(day-date.fromisoformat(review['last_review'])).days/review['interval']))
                category = 'weak' if review['had_error'] and review['mistake_status'] != '已稳定' else 'future'
            e = {'待订正':1,'待复习':.8,'巩固中':.4}.get(review['mistake_status'],0)
            if e:
                reasons.append('曾经做错，需要独立检索')
        else:
            d, e, overdue = 0, 0, 0
            category = 'new'
            reasons.append('尚未独立练习，补充评估证据')
        if category == 'future':
            continue
        w = 1-k['mastery']/100 if k['evidence']>=3 else .5
        if k['evidence']>=3 and k['mastery']<60:
            reasons.append(f"知识点表现偏弱，指标 {k['mastery']}%")
        if review:
            waiting = max(0,(day-date.fromisoformat(review['due_date'])).days)
        else:
            waiting = max(0,(day-local_day(q['created_at'])).days)
        score = round(100*(.35*d+.25*w+.20*e+.10*.5+.10*min(1,waiting/7)),1)
        result.append({
            'id': q['id'], 'question_id': q['id'], 'title': q['title'], 'knowledge_id': k['id'],
            'knowledge': k['name'], 'subject': k['subject'], 'type': q['type'],
            'minutes': q['minutes'], 'category': category, 'priority': score,
            'reasons': reasons, 'due_date': review['due_date'] if review else None,
            'factors': {'复习紧迫度':round(d,2),'薄弱程度':round(w,2),'错题需要':e,'目标相关性':.5,'等待补偿':round(min(1,waiting/7),2)},
            'status': 'todo',
            'revision':q.get('revision',1),
        })
    return sorted(result,key=lambda c:(-c['priority'],c['due_date'] or '9999',c['id']))


def make_plan(db, budget, day=None, exclude=None):
    day = day or today()
    all_candidates = [c for c in candidates(db,day) if c['question_id'] not in (exclude or set())]
    with_break = budget >= 50
    buffer = max(1, round(budget*.1))
    rest = 5 if with_break else 0
    usable = max(0,budget-buffer-rest)
    chosen = []
    counts = defaultdict(int)
    remaining = usable
    # Soft category budgets, followed by a fill pass. Never exceed total budget.
    for category, ratio in [('review',.5),('weak',.3),('new',.2)]:
        allowance = usable*ratio
        for c in all_candidates:
            if c['category'] != category or c['minutes']>remaining or c['minutes']>allowance:
                continue
            if counts[c['knowledge_id']]>=2:
                continue
            chosen.append(c)
            counts[c['knowledge_id']]+=1
            remaining -= c['minutes']
            allowance -= c['minutes']
    for c in all_candidates:
        if any(t['id']==c['id'] for t in chosen) or c['minutes']>remaining or counts[c['knowledge_id']]>=2:
            continue
        chosen.append(c)
        counts[c['knowledge_id']]+=1
        remaining -= c['minutes']
    chosen.sort(key=lambda c:(-c['priority'],c['id']))
    if not chosen:
        rest, buffer = 0, 0
    return {
        'tasks':chosen,'budget':budget,'study_minutes':sum(t['minutes'] for t in chosen),
        'buffer_minutes':buffer,'break_minutes':rest,
        'total_minutes':sum(t['minutes'] for t in chosen)+buffer+rest,
        'backlog':sum(c['category']=='review' for c in all_candidates)-sum(c['category']=='review' for c in chosen),
        'rule_version':'baseline-0.1',
    }
