"""Where each file of a set sits against its accompaniment track.

    python3 -m mixset.lags ACCOMP.mp3 OTHER.mp3 ...

Prints each file's lag in samples and seconds, measured at the start and near the end: the same
number twice means one clock. In the first set measured this way every Predominant and Muted
mix ran 1.000 s (44101-44103 samples) behind the Balanced and Accompaniment files, start to end.
"""
import argparse, os
from .audio import SR, decode, lag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('accomp'); ap.add_argument('files', nargs='+')
    a = ap.parse_args()
    A = decode(a.accomp)
    end = len(A) / SR
    for f in a.files:
        x = decode(f)
        l0, l1 = lag(x, A, 20, 50), lag(x, A, end - 60, end - 30)
        print(f'{l0:7d} {l1:7d}  {l0 / SR:8.4f} s  {"" if abs(l0 - l1) <= 2 else "DRIFTS  "}{os.path.basename(f)}')


if __name__ == '__main__':
    main()
