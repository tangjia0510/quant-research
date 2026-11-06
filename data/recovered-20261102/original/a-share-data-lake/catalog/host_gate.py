"""Shared cross-process host concurrency and minimum request start interval.
Each request must hold the returned context through receipt of the response body.
Files contain no credentials. Locks are released automatically on process exit.
"""
from contextlib import contextmanager
from pathlib import Path
import fcntl,time,os
LOGS=Path(__file__).resolve().parents[1]/'logs'
@contextmanager
def host_gate(host='eastmoney', max_inflight=2, interval=1.1):
    if not host.replace('-','').isalnum(): raise ValueError('invalid host key')
    LOGS.mkdir(exist_ok=True)
    acquired=None
    while acquired is None:
        mode=LOGS/(host+'-backpressure-until.txt')
        try: limited=float(mode.read_text())>time.time()
        except (ValueError,OSError): limited=False
        for slot in range(1 if limited else max_inflight):
            f=open(LOGS/(host+f'-slot-{slot}.lock'),'a+')
            try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: f.close();continue
            acquired=f;break
        if acquired is None:time.sleep(.1)
    try:
        with open(LOGS/(host+'-rate.lock'),'a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX);p=LOGS/(host+'-last-request.txt')
            try:last=float(p.read_text())
            except (ValueError,OSError):last=0
            time.sleep(max(0,interval-(time.time()-last)));p.write_text(str(time.time()))
        yield
    finally:
        fcntl.flock(acquired,fcntl.LOCK_UN);acquired.close()
def signal_backpressure(host='eastmoney',seconds=300):
    (LOGS/(host+'-backpressure-until.txt')).write_text(str(time.time()+seconds))
