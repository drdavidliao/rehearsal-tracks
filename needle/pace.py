"""Finish times for a batch of jobs from the pace of the ones already finished, for the needle's estimate and band.

    from pace import finish_times
    jobs = [dict(name='a', size=10, start=t0, end=t1), dict(name='b', size=14, start=t2), dict(name='c', size=6)]
    est = finish_times(jobs, slots=2, lag=120)
    # {'a': None, 'b': (lo, mid, hi), 'c': (lo, mid, hi), 'all': (lo, mid, hi), 'basis': 'from 1 finished job'}

size is whatever the work scales with (pages, bars, minutes of audio); start and end are epoch seconds. Each finished
job gives a rate (seconds per unit of size); lo, mid and hi use the fastest, median and slowest rate, so the band is
the spread actually measured and narrows or widens as jobs finish. A running job finishes at start + rate * size (not
before now); a job not started takes the next slot to free, lag seconds after. Before any job finishes there is no
pace to go on, and the result is None: give a hand estimate instead and say so in the basis.
"""
import statistics, time


def finish_times(jobs, slots=1, lag=0.0, now=None):
    now = time.time() if now is None else now
    rates = [(j['end'] - j['start']) / j['size'] for j in jobs if j.get('end') and j.get('start') and j['size']]
    if not rates: return None
    r = (min(rates), statistics.median(rates), max(rates))
    est = {j['name']: None for j in jobs if j.get('end')}
    running = [j for j in jobs if j.get('start') and not j.get('end')]
    waiting = [j for j in jobs if not j.get('start') and not j.get('end')]
    for j in running:
        est[j['name']] = tuple(max(now, j['start'] + k * j['size']) for k in r)
    cases = []
    for i in range(3):
        free = sorted([est[j['name']][i] for j in running] + [now] * max(0, slots - len(running)))
        for j in waiting:
            t0 = free.pop(0) + lag; f = t0 + r[i] * j['size']
            est.setdefault(j['name'], [0.0, 0.0, 0.0]); est[j['name']] = tuple(f if k == i else v for k, v in enumerate(est[j['name']]))
            free.append(f); free.sort()
    left = [v for v in est.values() if v]
    est['all'] = tuple(max(v[i] for v in left) for i in range(3)) if left else None
    n = len(rates)
    est['basis'] = f'fastest to slowest pace so far, from {n} finished job{"s" if n != 1 else ""}'
    return est


def hm(t):
    """epoch seconds as the needle's HH:MM"""
    return time.strftime('%H:%M', time.localtime(t))
