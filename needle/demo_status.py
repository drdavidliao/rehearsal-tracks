#!/usr/bin/env python3
"""A made-up batch, for trying the page: server.py --cmd "python3 demo_status.py".
Five transcriptions (two at a time, sized in pages) and a separation queue; the times run from when this was first run."""
import json, os, time
from pace import finish_times, hm

STAMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.demo_start')
if not os.path.exists(STAMP): open(STAMP, 'w').write(str(time.time()))
T0 = float(open(STAMP).read()) - 50 * 60          # the batch "began" 50 minutes before the first run
now = time.time()
m = lambda minutes: T0 + minutes * 60

jobs = [dict(name='Song A', size=6, start=m(0), end=m(33)), dict(name='Song B', size=9, start=m(0), end=m(41)),
        dict(name='Song C', size=11, start=m(35)), dict(name='Song D', size=14, start=m(43)), dict(name='Song E', size=10)]
jobs = [dict(j, end=j['end'] if j.get('end', now + 1) <= now else None) for j in jobs]
est = finish_times(jobs, slots=2, lag=120, now=now)

def row(j):
    if j.get('end'): return dict(name=j['name'], done=True, time=hm(j['end']))
    return dict(name=j['name'], state='typing' if j.get('start') else 'waiting', time=hm(est[j['name']][1]))

sep = [dict(name=f'Part {k}', size=1, start=m(5 * k), end=m(5 * k + 5)) for k in range(4)] + \
      [dict(name='Part 4', size=1, start=m(20)), dict(name='Part 5', size=1)]
sep = [dict(j, end=j['end'] if j.get('end', now + 1) <= now else None) for j in sep]
se = finish_times(sep, slots=1, now=now)

print(json.dumps(dict(
    title='Demo batch', refresh=20, note='a made-up batch',
    needles=[dict(label='all five done', estimate=hm(est['all'][1]), band=[hm(est['all'][0]), hm(est['all'][2])],
                  basis=est['basis'], items=[row(j) for j in jobs]),
             dict(title='Separation', label='separation done', estimate=hm(se['all'][1]) if se['all'] else None,
                  band=[hm(se['all'][0]), hm(se['all'][2])] if se['all'] else None, basis=se['basis'],
                  items=[dict(name=j['name'], done=True, time=hm(j['end'])) if j.get('end') else
                         dict(name=j['name'], state='running' if j.get('start') else 'waiting', time=hm(se[j['name']][1]))
                         for j in sep])])))
